"""
scripts/banc_ia/tracer_niveau.py
================================
B5 (phase 15) : trace, pour des offres réelles, le chemin de la décision de
niveau, de la description à la note finale, sans rien écrire en base :

  1. profil : niveau retenu (shared.eligibilite.niveau_du_profil) ;
  2. ce que le modèle voit : la description tronquée à
     IA_LONGUEUR_DESCRIPTION caractères (indices de niveau au-delà : vus par
     Python seulement) ;
  3. indices de niveau lus par Python (INDICES_NIVEAU), avec la fenêtre de
     60 caractères avant et 120 après, les marqueurs d'exigence et de
     souhait trouvés dedans (D103) ;
  4. secours D100 (niveau_detecte) ;
  5. pour chaque niveau_requis que le modèle peut répondre : contrôle
     (controler_extraits), exigence, malus (penalite_souhait), raisons
     d'inéligibilité ; puis note finale pour une note du modèle de 6 à 10 ;
  6. --avec-ia : la vraie réponse du modèle (une fois, température de
     l'application) et le résultat final.

    CHASSEUR_ENV_FILE=/dev/null venv/bin/python scripts/banc_ia/tracer_niveau.py --base sqlite:///data/chasseur_v2.db --ids 13,119,12
    venv/bin/python scripts/banc_ia/tracer_niveau.py --auto 3 --avec-ia

--auto N : les N offres de stage éligibles les mieux notées dont la
description contient un indice Bac+4 ou plus. Sortie : texte à l'écran et
audit_exports/trace_niveau.json.
"""

import argparse
import copy

from commun import CHAMPS_IDENTITE, activer_ia  # noqa: E402

from audit_commun import ecrire_json, maintenant, session_lecture  # noqa: E402

NIVEAUX_MODELE = ["non_precise", "bac", "bac+2", "bac+3", "bac+4", "bac+5"]


def lire(base, ids, auto):
    from database.candidatures_db import candidature_vers_dict
    from database.models import Candidature, Profil
    from database.profil_db import profil_vers_dict
    from shared.eligibilite import CRANS, niveau_detecte
    out = []
    with session_lecture(base) as db:
        if ids:
            lignes = db.query(Candidature).filter(Candidature.id.in_(ids)).all()
            lignes.sort(key=lambda c: ids.index(c.id))
        else:
            lignes = [c for c in db.query(Candidature).filter_by(mode="stage", eligible=True)
                      .order_by(Candidature.score.desc()) if (d := niveau_detecte(c.description or ""))
                      and CRANS[d[0]] >= 4][:auto]
        for c in lignes:
            p = db.query(Profil).filter_by(user_id=c.user_id, mode=c.mode).first()
            profil = {k: v for k, v in profil_vers_dict(p).items() if k not in CHAMPS_IDENTITE} if p else {}
            out.append((c.id, candidature_vers_dict(c), profil, c.mode,
                        {"score": c.score, "verdict": c.verdict, "eligible": c.eligible, "statut": c.statut,
                         "points_faibles": c.points_faibles}))
    return out


def tracer(id_base, offre, profil, mode, stocke, avec_ia=False) -> dict:
    from offres.analyse import appliquer_eligibilite, score_to_verdict
    from shared import eligibilite as E
    from shared.config import ia_longueur_description
    texte = E._texte(offre)
    coupe = ia_longueur_description()
    t = {"id": id_base, "titre": offre["titre"], "mode": mode, "stocke": stocke,
         "profil": E.niveau_du_profil(profil), "longueur_description": len(texte),
         "vu_par_le_modele": f"{coupe} premiers caractères (IA_LONGUEUR_DESCRIPTION)", "indices": []}
    avant, apres = E.FENETRE_SOUHAIT
    for (a, b), permis in E._indices(texte):
        fen = texte[max(0, a - avant):b + apres]
        t["indices"].append({
            "texte": texte[a:b], "position": a, "vu_par_le_modele": a < coupe, "niveaux": sorted(permis),
            "marqueurs_exigence": [m.group(0) for m in E.MARQUEURS_EXIGENCE.finditer(fen.lower())],
            "marqueurs_souhait": [m.group(0) for m in E.MARQUEURS_SOUHAIT.finditer(fen.lower())],
            "fenetre": " ".join(fen.split())})
    t["secours_D100"] = E.niveau_detecte(texte)
    t["hypotheses"] = []
    for niveau in NIVEAUX_MODELE:
        for score in (6, 8, 10):
            res = {"score": score, "eligible": True, "verdict": score_to_verdict(score), "points_faibles": [],
                   "niveau_requis": niveau, "niveau_exigence": "non_precise", "duree_mois": None,
                   "date_debut_offre": None, "alternance_seulement": False}
            appliquer_eligibilite(res, copy.deepcopy(offre), profil, mode)
            t["hypotheses"].append({"modele_niveau": niveau, "modele_score": score,
                                    "niveau_final": res["niveau_requis"], "exigence": res["niveau_exigence"],
                                    "score_final": res["score"], "eligible": res["eligible"],
                                    "raison": res["raison_ineligibilite"], "ecartes": res["extraits_ecartes"]})
    if avec_ia:
        from offres.analyse import analyser_offre
        activer_ia()
        r = analyser_offre(copy.deepcopy(offre), profil, mode)
        t["ia"] = {k: r.get(k) for k in ("score", "verdict", "eligible", "niveau_requis", "niveau_exigence",
                                         "raison_ineligibilite", "extraits_ecartes", "points_faibles")}
    return t


def afficher(t: dict):
    print(f"\n=== #{t['id']} {t['titre']} ({t['mode']})")
    print(f"  en base : note {t['stocke']['score']}, {t['stocke']['verdict']}, éligible {t['stocke']['eligible']}")
    print(f"  profil : {t['profil']['libelle'] or 'inconnu'} (crans {t['profil']['crans']}, {t['profil']['source']})")
    print(f"  description : {t['longueur_description']} caractères, le modèle en voit {t['vu_par_le_modele']}")
    for i in t["indices"]:
        print(f"  indice « {i['texte']} » @{i['position']}{'' if i['vu_par_le_modele'] else ' (HORS de ce que voit le modèle)'}"
              f" -> {i['niveaux']} ; exigence {i['marqueurs_exigence']} ; souhait {i['marqueurs_souhait']}")
        print(f"      « {i['fenetre'][:180]} »")
    print(f"  secours D100 : {t['secours_D100']}")
    vus = set()
    for h in t["hypotheses"]:
        cle = (h["modele_niveau"], h["niveau_final"], h["exigence"], h["eligible"])
        if h["modele_score"] != 10 and cle in vus:
            continue
        vus.add(cle)
        if h["modele_score"] == 10 or h["modele_niveau"] == "non_precise":
            print(f"  modèle {h['modele_niveau']:>11}, note {h['modele_score']:>2} -> niveau {h['niveau_final']}, "
                  f"{h['exigence']}, note finale {h['score_final']}, éligible {h['eligible']}"
                  + (f" ({h['raison']})" if h["raison"] else ""))
    if "ia" in t:
        print(f"  IA réelle : {t['ia']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base")
    ap.add_argument("--ids", help="identifiants en base (colonne id), séparés par des virgules")
    ap.add_argument("--auto", type=int, default=3)
    ap.add_argument("--avec-ia", action="store_true")
    args = ap.parse_args(argv)
    ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    traces = [tracer(*x, avec_ia=args.avec_ia) for x in lire(args.base, ids, args.auto)]
    for t in traces:
        afficher(t)
    print("\n->", ecrire_json("trace_niveau", {"le": maintenant(), "traces": traces}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
