"""
scripts/banc_ia/banc_lettre.py
==============================
B4 (phase 15), lettre : rédige le paragraphe personnalisé (D106, D109) avec
un modèle et un prompt donnés, plusieurs fois, sur les offres du jeu de
référence, et mesure automatiquement ce qui peut l'être. Rien n'est écrit
en base.

    venv/bin/python scripts/banc_ia/banc_lettre.py audit_exports/banc_reference.json --max 10
    venv/bin/python scripts/banc_ia/banc_lettre.py ref.json --modele ministral-3:8b --temperatures 0,0.6 --essais 3
    venv/bin/python scripts/banc_ia/banc_lettre.py ref.json --prompt mes_prompts/lettre_v2.py

--prompt : fichier Python définissant construire_messages_paragraphe(offre,
profil, mode, lettre_type) ; sans lui, celui de lettres/redaction.py. La
lettre type est celle du profil, sinon l'exemple du mode (D109).
Température de l'application : 0.6.

Mesures par paragraphe (puis moyennes par température) :
  - longueur en mots, au-delà de MOTS_MAX (80), consigne de 60 ;
  - première personne : part des phrases avec je, j', me, m', mon, ma, mes,
    moi ; tournures impersonnelles interdites par le prompt ; « tu » ou
    « vous » adressé à la personne candidate (inversion des rôles, D101) ;
  - faits inventés (indice, à relire) : termes techniques, noms propres,
    sigles et nombres du paragraphe absents du profil, de l'offre et de la
    lettre type ;
  - reprises de la lettre type : suites de 5 mots communes ;
  - forme : markdown, tiret cadratin, esperluette, « expertise ».
Les paragraphes sont tous écrits dans la sortie, pour une lecture humaine.
"""

import argparse
import re
import time

from commun import activer_ia, charger_prompt, charger_reference, moyenne, ngrammes, profil_de  # noqa: E402

from audit_commun import ecrire_json, maintenant  # noqa: E402

PREMIERE_PERSONNE = re.compile(r"\b(je|j'|j’|me|m'|m’|mon|ma|mes|moi)\b", re.I)
IMPERSONNEL = re.compile(r"correspondent à|renforcent|permettent|\bil est\b|\bcela\b|ce poste offre|"
                         r"les intérêts portés vers", re.I)
INVERSION = re.compile(r"\b(tu|ton|ta|tes|votre profil|vos compétences|vous êtes|vous avez)\b", re.I)
FORME = {"markdown": re.compile(r"\*\*|__|^#|^\s*[-*] ", re.M), "tiret_cadratin": re.compile(r"[—–]"),
         "esperluette": re.compile(r"&"), "expertise": re.compile(r"\bexpertise\b", re.I)}
TERME = re.compile(r"\b(?:[A-Z][\wÀ-ÿ+#.-]{1,}|[\w+#.-]*\d[\w+#.-]*|[a-z]+[A-Z][\w]*)\b")


def phrases(texte: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.!?])\s+", (texte or "").strip()) if p]


def termes_non_sources(paragraphe: str, sources: str) -> list[str]:
    """Termes du paragraphe (majuscule hors début de phrase, chiffres,
    casse mixte) absents des sources : indice de fait inventé."""
    bas = sources.lower()
    debuts = {p.split()[0] for p in phrases(paragraphe) if p.split()}
    return sorted({t for t in TERME.findall(paragraphe) if t not in debuts and t.lower().strip(".") not in bas})


def mesurer(paragraphe: str, profil: dict, offre: dict, lettre_type: str) -> dict:
    from lettres.redaction import MOTS_MAX, nombre_de_mots
    ph = phrases(paragraphe)
    sources = " ".join([str(v) for v in profil.values() if isinstance(v, (str, list))] + [
        offre.get("titre") or "", offre.get("entreprise") or "", offre.get("lieu") or "",
        offre.get("description") or "", lettre_type])
    communs = ngrammes(paragraphe) & ngrammes(lettre_type)
    return {"mots": nombre_de_mots(paragraphe), "trop_long": nombre_de_mots(paragraphe) > MOTS_MAX,
            "phrases": len(ph),
            "premiere_personne": round(sum(1 for p in ph if PREMIERE_PERSONNE.search(p)) / len(ph), 2) if ph else 0,
            "impersonnel": IMPERSONNEL.findall(paragraphe), "inversion_des_roles": INVERSION.findall(paragraphe),
            "termes_non_sources": termes_non_sources(paragraphe, sources),
            "reprises_lettre_type": [" ".join(n) for n in sorted(communs)][:10],
            "forme": {k: bool(r.search(paragraphe)) for k, r in FORME.items()}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("reference")
    ap.add_argument("--modele", help="modèle (défaut : IA_MODELE_LETTRE)")
    ap.add_argument("--prompt", help="fichier définissant construire_messages_paragraphe(offre, profil, mode, lettre_type)")
    ap.add_argument("--temperatures", default="0,0.6")
    ap.add_argument("--essais", type=int, default=3)
    ap.add_argument("--mode")
    ap.add_argument("--max", type=int, default=10, help="offres au plus (défaut 10)")
    args = ap.parse_args(argv)

    activer_ia()
    from lettres.redaction import construire_messages_paragraphe, lettre_par_defaut, nettoyer_paragraphe
    from shared.config import modele_ia
    from shared.ia import ErreurIAPassagere, appeler_structure, verifier_demarrage
    from shared.schemas_ia import ParagrapheIA
    modele = args.modele or modele_ia("lettre")
    construire = charger_prompt(args.prompt, "construire_messages_paragraphe") or construire_messages_paragraphe
    ref = charger_reference(args.reference)
    offres = [o for o in ref["offres"] if not args.mode or o["mode"] == args.mode][:args.max]
    print(f"Modèle {modele}, {len(offres)} offres ; test de démarrage {verifier_demarrage(modele, 'lettre'):.1f} s")
    sortie = {"le": maintenant(), "modele": modele, "prompt": args.prompt or "lettres.redaction", "par_temperature": {}}
    for t in [float(x) for x in args.temperatures.split(",")]:
        lignes = []
        for o in offres:
            profil = profil_de(ref, o)
            lettre_type = profil.get("lettre_type") or lettre_par_defaut(o["mode"])
            for essai in range(1, args.essais + 1):
                debut = time.monotonic()
                try:
                    r = appeler_structure(construire(o, profil, o["mode"], lettre_type), ParagrapheIA, usage="lettre",
                                          modele=modele, essais=1, temperature=t)
                except ErreurIAPassagere as e:
                    lignes.append({"ref": o["ref"], "essai": essai, "erreur": str(e)})
                    continue
                texte = nettoyer_paragraphe(r.paragraphe) or r.paragraphe
                m = mesurer(texte, profil, o, lettre_type)
                lignes.append({"ref": o["ref"], "titre": o["titre"], "essai": essai, "secondes": round(time.monotonic() - debut, 1),
                               "brut": r.paragraphe, "paragraphe": texte, "mesures": m})
                print(f"  T={t} {o['titre'][:40]} #{essai} : {m['mots']} mots, 1re pers. {m['premiere_personne']}, "
                      f"non sourcés {m['termes_non_sources'][:5]}, reprises {len(m['reprises_lettre_type'])}")
        ok = [x for x in lignes if "mesures" in x]
        sortie["par_temperature"][str(t)] = {
            "synthese": {"paragraphes": len(ok), "erreurs": len(lignes) - len(ok),
                         "mots_moyen": moyenne([x["mesures"]["mots"] for x in ok]),
                         "trop_longs": sum(1 for x in ok if x["mesures"]["trop_long"]),
                         "premiere_personne_moyenne": moyenne([x["mesures"]["premiere_personne"] for x in ok]),
                         "avec_tournure_impersonnelle": sum(1 for x in ok if x["mesures"]["impersonnel"]),
                         "avec_inversion_des_roles": sum(1 for x in ok if x["mesures"]["inversion_des_roles"]),
                         "avec_termes_non_sources": sum(1 for x in ok if x["mesures"]["termes_non_sources"]),
                         "avec_reprise_lettre_type": sum(1 for x in ok if x["mesures"]["reprises_lettre_type"]),
                         "secondes_moyen": moyenne([x["secondes"] for x in ok])},
            "lignes": lignes}
        print(f"T={t} :", sortie["par_temperature"][str(t)]["synthese"])
    print("->", ecrire_json(f"banc_lettre_{modele.replace(':', '_')}_{time.strftime('%Y%m%d_%H%M%S')}", sortie))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
