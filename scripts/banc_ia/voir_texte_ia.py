"""
scripts/banc_ia/voir_texte_ia.py
================================
Phase 16 (point 5, D189) : ce que l'IA voit vraiment d'une offre avec le
prompt v2. Pour chaque offre : longueur de la description, texte exact
envoyé à chacun des deux appels (extraction, puis jugement avec le
profil), marque de coupure et texte perdu. Base ouverte en LECTURE SEULE ;
le .env n'est pas chargé (seules les variables IA_* sont lues, avec
--analyser).

    venv/bin/python scripts/banc_ia/voir_texte_ia.py --mode stage --offres 5
    venv/bin/python scripts/banc_ia/voir_texte_ia.py --mode job --id FT-123456 --max-jugement 4000
    venv/bin/python scripts/banc_ia/voir_texte_ia.py --mode stage --offres 5 --analyser --num-ctx 8192

--offres N : les N offres de description la plus longue du mode ;
--id : une offre (son identifiant, ref_offre) ; --user : l'utilisateur
(défaut : le premier qui a des offres dans le mode) ; --max-extraction,
--max-jugement : caractères de description lus par chaque appel (défaut :
le plafond de sécurité IA_LONGUEUR_DESCRIPTION, description entière, D193).
--analyser : lance les deux appels avec ces limites (Ollama démarré) et
affiche la catégorie, la note finale, prompt_eval_count et num_ctx de
chaque appel ; --num-ctx remplace IA_NUM_CTX pour l'essai. Rien n'est écrit
en base.
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("CHASSEUR_ENV_FILE", os.devnull)     # jamais le .env complet
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit_commun import session_lecture  # noqa: E402
from commun import activer_ia  # noqa: E402

TRAIT = "─" * 78


def lire_offres(base, mode, user, ident, nombre):
    """(offres, profil) en lecture seule : l'offre --id, ou les N plus longues."""
    from sqlalchemy import func

    from database.candidatures_db import candidature_vers_dict
    from database.models import Candidature, Profil
    from database.profil_db import _profil_vers_dict
    with session_lecture(base) as db:
        q = db.query(Candidature).filter(Candidature.mode == mode)
        if user:
            q = q.filter(Candidature.user_id == user)
        if ident:
            q = q.filter(Candidature.ref_offre == ident)
        lignes = q.order_by(func.length(Candidature.description).desc()).limit(1 if ident else nombre).all()
        if not lignes:
            raise SystemExit(f"Aucune offre en mode {mode}" + (f" avec l'identifiant {ident}" if ident else "") + ".")
        uid = user or lignes[0].user_id
        offres = [candidature_vers_dict(c) for c in lignes if c.user_id == uid]
        p = db.query(Profil).filter_by(user_id=uid, mode=mode).first()
        profil = _profil_vers_dict(p) if p else {}
    return offres, profil


def coupe(description: str, limite: int) -> tuple[str, str]:
    """(texte gardé, texte perdu), même coupe que offres.analyse._court."""
    from offres.analyse import _court
    complet = " ".join(str(description or "").split())
    garde = _court(complet, limite)
    if garde == complet:
        return garde, ""
    return garde, complet[len(garde.removesuffix("…")):].strip()


def afficher_messages(titre: str, messages: list[dict]):
    print(f"\n{TRAIT}\n{titre} : texte exact envoyé ({sum(len(m['content']) for m in messages)} caractères)\n{TRAIT}")
    for m in messages:
        print(f"[{m['role']}]\n{m['content']}\n")


def afficher_coupe(appel: str, description: str, limite: int):
    garde, perdu = coupe(description, limite)
    if not perdu:
        print(f"→ {appel} : description entière lue ({len(garde)} caractères, limite {limite}).")
        return
    print(f"→ {appel} : ✂ COUPÉE après {len(garde.removesuffix('…'))} caractères (limite {limite}), marque « … » ; "
          f"texte perdu ({len(perdu)} caractères) :\n«{perdu}»")


def analyser(offre, profil, mode, max_extraction, max_jugement, num_ctx=None) -> dict:
    """Les deux appels de la v2, avec les compteurs d'Ollama de chacun."""
    from offres import analyse_v2
    from shared import ia
    compteurs, vraie = [], analyse_v2.appeler_structure

    def espion(*a, **k):
        r = vraie(*a, **k)
        compteurs.append(ia.dernier_appel())
        return r
    analyse_v2.appeler_structure = espion
    try:
        res = analyse_v2.analyser_offre_v2(offre, profil, mode, essais=1, longueur_jugement=max_jugement,
                                           longueur_extraction=max_extraction, num_ctx=num_ctx)
    finally:
        analyse_v2.appeler_structure = vraie
    return {"resultat": res, "compteurs": compteurs}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mode", default="alternance", choices=["alternance", "job", "stage"])
    ap.add_argument("--offres", type=int, default=5, help="les N offres les plus longues du mode")
    ap.add_argument("--id", help="une offre précise (ref_offre)")
    ap.add_argument("--user", type=int)
    ap.add_argument("--base", help="URL SQLite (lecture seule ; défaut : la base de l'application)")
    ap.add_argument("--max-extraction", type=int)
    ap.add_argument("--max-jugement", type=int)
    ap.add_argument("--analyser", action="store_true", help="lancer les deux appels (Ollama)")
    ap.add_argument("--num-ctx", type=int, help="avec --analyser : remplace IA_NUM_CTX")
    ap.add_argument("--num-ctx-par-appel", action="store_true",
                    help="avec --analyser : un num_ctx par appel, comme avant D193 (comparaison)")
    args = ap.parse_args(argv)
    if args.analyser:
        activer_ia()                              # variables IA_* du .env seulement
        if args.num_ctx:
            os.environ["IA_NUM_CTX"] = str(args.num_ctx)
    from offres.analyse_v2 import messages_extraction, messages_jugement
    from shared.config import ia_longueur_description
    max_extraction = args.max_extraction or ia_longueur_description()
    max_jugement = args.max_jugement or ia_longueur_description()
    offres, profil = lire_offres(args.base, args.mode, args.user, args.id, args.offres)
    print(f"Mode {args.mode}, {len(offres)} offre(s) ; extraction : {max_extraction} caractères, "
          f"jugement : {max_jugement}")
    for n, offre in enumerate(offres, 1):
        description = offre.get("description") or ""
        print(f"\n{'═' * 78}\n{n}. {offre.get('titre')} — {offre.get('entreprise')} (id {offre['id']})\n"
              f"Description : {len(description)} caractères ({len(' '.join(description.split()))} espaces regroupés)")
        afficher_messages("Appel 1, extraction (sans le profil)", messages_extraction(offre, max_extraction))
        afficher_coupe("Extraction", description, max_extraction)
        afficher_messages("Appel 2, jugement (avec le profil)", messages_jugement(offre, profil, args.mode,
                                                                                    max_jugement))
        afficher_coupe("Jugement", description, max_jugement)
        if args.analyser:
            a = analyser(offre, profil, args.mode, max_extraction, max_jugement,
                         num_ctx=0 if args.num_ctx_par_appel else None)
            r = a["resultat"]
            print(f"\n→ Analyse : catégorie {r['categorie']}, note {r['score']}, "
                  f"{'éligible' if r['eligible'] else 'inéligible'} ({r['secondes']} s)")
            for appel, c in zip(("extraction", "jugement"), a["compteurs"], strict=False):
                print(f"   {appel} : prompt_eval_count {c.get('prompt_eval_count')}, eval_count {c.get('eval_count')}, "
                      f"num_ctx {c.get('num_ctx')}, chargement {c.get('load_duration_s')} s, "
                      f"total {c.get('total_duration_s')} s" + ("  ⚠️ FENÊTRE PLEINE" if c.get("fenetre_pleine") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
