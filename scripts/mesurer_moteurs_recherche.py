"""
scripts/mesurer_moteurs_recherche.py
====================================
Phase 16 (point 4 b, D187) : quel moteur de ddgs, et dans quel ordre de
repli, pour la recherche web du site officiel. Pour chaque entreprise de
audit_exports/scraper_reference.json qui a un site officiel, la première
requête que construit le scraper part vers chaque moteur, à tour de rôle
(un moteur n'est sollicité qu'une fois toutes les len(moteurs) requêtes).
Mesuré par moteur : réponses, refus ou erreurs, site officiel parmi les
10 résultats (et son rang), temps. Les ordres de repli sont ensuite
simulés sur ces réponses. Réseau seulement, rien en base.

    venv/bin/python scripts/mesurer_moteurs_recherche.py
    venv/bin/python scripts/mesurer_moteurs_recherche.py --moteurs brave,mojeek,duckduckgo --max 10

Sortie : audit_exports/mesure_moteurs_recherche.json
"""

import argparse
import itertools
import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_commun import SORTIE, ecrire_json, lire_json, maintenant  # noqa: E402
from audit_scraper import _parent  # noqa: E402

MOTEURS = "brave,mojeek,duckduckgo,google,yahoo,yandex"


def officiels(ref) -> set[str]:
    o = ref.get("site_officiel")
    return {_parent(x) for x in (o if isinstance(o, list) else [o]) if x}


def interroger(moteur: str, requete: str) -> dict:
    from ddgs import DDGS
    from spontanees.recherche_emails import REGION_RECHERCHE, TIMEOUT_MOTEUR, extraire_domaine
    debut = time.monotonic()
    try:
        with DDGS(timeout=TIMEOUT_MOTEUR) as ddg:
            res = [r["href"] for r in ddg.text(requete, region=REGION_RECHERCHE, backend=moteur, max_results=10)
                   if r.get("href")]
        return {"domaines": [extraire_domaine(u) for u in res], "erreur": None,
                "secondes": round(time.monotonic() - debut, 1)}
    except Exception as e:   # refus, délai dépassé, aucun résultat
        return {"domaines": [], "erreur": f"{type(e).__name__}: {str(e)[:80]}",
                "secondes": round(time.monotonic() - debut, 1)}


def rang(domaines, attendus) -> int | None:
    return next((i + 1 for i, d in enumerate(domaines) if _parent(d) in attendus), None)


def simuler(lignes, ordre) -> dict:
    """Repli : le premier moteur de l'ordre qui répond donne les résultats."""
    trouves = sans_reponse = 0
    for ligne in lignes:
        rep = next((ligne["moteurs"][m] for m in ordre if ligne["moteurs"][m]["domaines"]), None)
        if rep is None:
            sans_reponse += 1
        elif rang(rep["domaines"], set(ligne["officiels"])):
            trouves += 1
    return {"ordre": ", ".join(ordre), "officiel_trouve": trouves, "sans_reponse": sans_reponse}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--moteurs", default=MOTEURS)
    ap.add_argument("--max", type=int)
    ap.add_argument("--reference", default=str(SORTIE / "scraper_reference.json"))
    ap.add_argument("--echantillon", default=str(SORTIE / "scraper_echantillon.json"))
    args = ap.parse_args(argv)
    from spontanees.recherche_emails import analyser_nom, construire_requetes
    moteurs = [m.strip() for m in args.moteurs.split(",") if m.strip()]
    fiches = {x["id"]: x for x in lire_json(args.echantillon)["entreprises"]}
    refs = [r for r in lire_json(args.reference)["entreprises"] if officiels(r) and r["id"] in fiches][:args.max]
    lignes = []
    for n, ref in enumerate(refs, 1):
        e = fiches[ref["id"]]
        requete = construire_requetes(e, analyser_nom(e.get("nom") or ""))[0]
        ligne = {"id": ref["id"], "nom": e.get("nom"), "requete": requete, "officiels": sorted(officiels(ref)),
                 "moteurs": {}}
        for m in moteurs:
            time.sleep(random.uniform(3, 6))
            ligne["moteurs"][m] = r = interroger(m, requete)
            r["rang_officiel"] = rang(r["domaines"], officiels(ref))
        lignes.append(ligne)
        print(f"{n}/{len(refs)} {e.get('nom')} : " + " ; ".join(
            f"{m} {'erreur' if r['erreur'] else (r['rang_officiel'] or '-')}" for m, r in ligne["moteurs"].items()),
            flush=True)
    par_moteur = {}
    for m in moteurs:
        reps = [x["moteurs"][m] for x in lignes]
        rangs = [r["rang_officiel"] for r in reps if r["rang_officiel"]]
        par_moteur[m] = {"requetes": len(reps), "reponses": sum(1 for r in reps if r["domaines"]),
                         "erreurs": dict(Counter(r["erreur"].split(":")[0] for r in reps if r["erreur"])),
                         "officiel_dans_les_10": len(rangs),
                         "rang_moyen": round(sum(rangs) / len(rangs), 1) if rangs else None,
                         "secondes_moyennes": round(sum(r["secondes"] for r in reps) / max(1, len(reps)), 1)}
    ordres = [simuler(lignes, list(o)) for k in (1, 2, 3) for o in itertools.permutations(moteurs, k)]
    ordres.sort(key=lambda x: (-x["officiel_trouve"], x["sans_reponse"], len(x["ordre"])))
    res = {"le": maintenant(), "entreprises": len(lignes), "par_moteur": par_moteur, "meilleurs_ordres": ordres[:15],
           "lignes": lignes}
    for m, v in par_moteur.items():
        print(m, v)
    for o in ordres[:8]:
        print(o)
    print("->", ecrire_json("mesure_moteurs_recherche", res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
