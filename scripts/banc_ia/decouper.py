"""
scripts/banc_ia/decouper.py
===========================
Phase 15, étape 3 (D) : découpe le jeu de référence annoté en deux moitiés
fixes, « réglage » et « test », tirées au hasard avec une graine, réparties
par mode (la moitié des offres de chaque mode de chaque côté). Le prompt ne
s'ajuste que sur la moitié réglage ; la moitié test ne sert qu'à la mesure
finale.

    venv/bin/python scripts/banc_ia/decouper.py audit_exports/banc_reference.json

Sorties : audit_exports/banc_reglage.json et audit_exports/banc_test.json
(même format que la référence, profils compris).
"""

import argparse
import random
from collections import defaultdict

from commun import lire_json  # noqa: E402

from audit_commun import ecrire_json  # noqa: E402

GRAINE = 15


def decouper(reference: dict, graine: int = GRAINE) -> tuple[dict, dict]:
    par_mode = defaultdict(list)
    for o in sorted(reference["offres"], key=lambda o: o["ref"]):
        par_mode[o["mode"]].append(o)
    hasard = random.Random(graine)
    reglage, test = [], []
    for mode in sorted(par_mode):
        offres = par_mode[mode][:]
        hasard.shuffle(offres)
        moitie = (len(offres) + 1) // 2
        reglage += offres[:moitie]
        test += offres[moitie:]
    base = {k: v for k, v in reference.items() if k != "offres"}
    return ({**base, "moitie": "reglage", "graine": graine, "offres": reglage},
            {**base, "moitie": "test", "graine": graine, "offres": test})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("reference")
    ap.add_argument("--graine", type=int, default=GRAINE)
    args = ap.parse_args(argv)
    reglage, test = decouper(lire_json(args.reference), args.graine)
    for nom, moitie in (("banc_reglage", reglage), ("banc_test", test)):
        modes = {m: sum(1 for o in moitie["offres"] if o["mode"] == m) for m in ("alternance", "job", "stage")}
        print(nom, len(moitie["offres"]), modes, "->", ecrire_json(nom, moitie))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
