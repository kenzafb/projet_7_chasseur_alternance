"""
scripts/mesurer_wikidata.py
===========================
Phase 16 (point 4 d, D188) : combien d'entreprises de
audit_exports/scraper_reference.json ont un site officiel dans Wikidata
(SIREN P1616 -> site P856), et combien sont justes face à la référence
(même domaine principal). Une requête par lot de 100 SIREN, rien en base.

    venv/bin/python scripts/mesurer_wikidata.py

Sortie : audit_exports/mesure_wikidata.json
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_commun import SORTIE, ecrire_json, lire_json, maintenant  # noqa: E402
from audit_scraper import _parent  # noqa: E402


def verdict(sites: list[str], ref: dict) -> str:
    from spontanees.lecture_site import domaine
    if not sites:
        return "absent de Wikidata"
    o = ref.get("site_officiel")
    officiels = {_parent(x) for x in (o if isinstance(o, list) else [o]) if x}
    if ref.get("confiance") not in ("haute", "moyenne"):
        return "non tranché"
    if not officiels:
        return "faux"                               # la référence dit : pas de site
    return "juste" if any(_parent(domaine(s)) in officiels for s in sites) else "faux"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--reference", default=str(SORTIE / "scraper_reference.json"))
    args = ap.parse_args(argv)
    from spontanees import wikidata
    refs = lire_json(args.reference)["entreprises"]
    trouves = wikidata.precharger([r.get("siren") for r in refs])
    lignes = []
    for r in refs:
        sites = wikidata.sites_wikidata({"siren": r.get("siren")})
        lignes.append({"id": r["id"], "nom": r["nom"], "siren": r.get("siren"), "wikidata": sites,
                       "officiel": r.get("site_officiel"), "confiance": r.get("confiance"),
                       "verdict": verdict(sites, r)})
    bilan = {"entreprises": len(refs), "avec_siren": sum(1 for r in refs if r.get("siren")),
             "site_dans_wikidata": trouves, "verdicts": dict(Counter(x["verdict"] for x in lignes))}
    print(bilan)
    for x in lignes:
        if x["wikidata"]:
            print(f"  {x['verdict']} : {x['nom']} -> {', '.join(x['wikidata'])} (référence {x['officiel']})")
    print("->", ecrire_json("mesure_wikidata", {"le": maintenant(), "bilan": bilan, "lignes": lignes}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
