"""
scripts/audit_champs_france_travail.py
======================================
Phase 15, étape 3 (B) : noms et valeurs réels des champs structurés des
offres France Travail qui peuvent décider de l'éligibilité : permis,
formations (niveau, exigence), site de l'entreprise
(entreprise.url, source du scraper), experienceExige et experienceLibelle,
competences (exigence), qualificationCode et qualificationLibelle,
qualitesProfessionnelles, langues. Lit au plus --max offres par mode avec
les critères de l'application (profil --user, base en lecture seule), sans
rien écrire en base. Réseau et identifiants France Travail (.env).

    venv/bin/python scripts/audit_champs_france_travail.py --user 1 --max 600

Sortie : audit_exports/audit_champs_france_travail.json (comptes par
valeur, exemples d'intitulés) ; à me transmettre.
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_commun import ecrire_json, maintenant  # noqa: E402
from audit_france_travail import criteres_du_mode  # noqa: E402

from offres import france_travail as ft  # noqa: E402

CERTIFS = re.compile(r"\b(caces|cases|ssiap|sst|habilitation|carte professionnelle|carte pro|bafa|haccp|fimo|fco|"
                     r"permis|diplôme d'état|diplome d'etat|\bde\b|cap|bep|bts|licence|master)\b", re.I)


def resume(offres: list[dict]) -> dict:
    c = {k: Counter() for k in ("cles", "permis", "permis_exigence", "experienceExige", "experienceLibelle",
                                "formations_niveau", "formations_exigence", "formations_domaine",
                                "competences_exigence", "competences_E_certifs", "qualificationCode",
                                "qualificationLibelle", "qualitesProfessionnelles", "langues_exigence",
                                "entreprise_url", "entreprise_cles")}
    exemples = []
    for o in offres:
        c["cles"].update(o.keys())
        c["entreprise_url"]["avec" if (o.get("entreprise") or {}).get("url") else "sans"] += 1
        c["entreprise_cles"].update((o.get("entreprise") or {}).keys())
        for p in o.get("permis") or []:
            c["permis"][p.get("libelle")] += 1
            c["permis_exigence"][p.get("exigence")] += 1
        c["experienceExige"][o.get("experienceExige")] += 1
        c["experienceLibelle"][re.sub(r"\d+", "N", o.get("experienceLibelle") or "")[:60]] += 1
        for f in o.get("formations") or []:
            c["formations_niveau"][f.get("niveauLibelle")] += 1
            c["formations_exigence"][f.get("exigence")] += 1
            c["formations_domaine"][f.get("domaineLibelle")] += 1
        for k in o.get("competences") or []:
            c["competences_exigence"][k.get("exigence")] += 1
            if k.get("exigence") == "E" and CERTIFS.search(k.get("libelle") or ""):
                c["competences_E_certifs"][k.get("libelle")] += 1
        c["qualificationCode"][o.get("qualificationCode")] += 1
        c["qualificationLibelle"][o.get("qualificationLibelle")] += 1
        for q in o.get("qualitesProfessionnelles") or []:
            c["qualitesProfessionnelles"][q.get("libelle")] += 1
        for la in o.get("langues") or []:
            c["langues_exigence"][la.get("exigence")] += 1
        if len(exemples) < 40 and (o.get("permis") or o.get("experienceExige") == "E"):
            exemples.append({k: o.get(k) for k in ("intitule", "permis", "experienceExige", "experienceLibelle",
                                                   "formations", "qualificationLibelle")})
    return {"offres": len(offres), **{k: v.most_common(60) for k, v in c.items()}, "exemples": exemples}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--user", type=int)
    ap.add_argument("--base")
    ap.add_argument("--max", type=int, default=600)
    args = ap.parse_args(argv)
    token = ft.get_token(print)
    if not token:
        raise SystemExit("Jeton France Travail refusé.")
    res = {"le": maintenant()}
    for mode in ("job", "alternance", "stage"):
        criteres = criteres_du_mode(mode, args.user, args.base)
        collecte = ft.Collecte(token, print, retenir=lambda o: True, objectif=args.max)
        for params in ft.requetes_initiales(criteres["filtres"], criteres["domaines"]):
            collecte.recuperer(params)
        res[mode] = resume(list(collecte.offres.values())[:args.max])
        print(mode, res[mode]["offres"], "offres ;", "experienceExige", res[mode]["experienceExige"][:4],
              "; permis", res[mode]["permis_exigence"][:3])
    print("->", ecrire_json("audit_champs_france_travail", res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
