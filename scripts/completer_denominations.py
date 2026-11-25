"""
scripts/completer_denominations.py
==================================
Phase 16 (D192) : dénomination de l'unité légale des entreprises déjà en
base qui n'en ont pas (venues de La Bonne Alternance seulement : son export
donne souvent l'enseigne ou le nom d'établissement, « PARIS HOTEL DE VILLE »
pour la BRED). Demandée à l'API publique Recherche d'entreprises (SIREN
seulement, sans clé), une requête par entreprise, une seconde entre deux.

Par défaut, lecture seule : la liste de ce qui serait écrit. --appliquer
écrit extra.denomination, en une seule transaction à la fin (un Ctrl+C
avant n'écrit rien).

    venv/bin/python scripts/completer_denominations.py
    venv/bin/python scripts/completer_denominations.py --appliquer
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_commun import session_lecture  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--appliquer", action="store_true")
    ap.add_argument("--base", help="URL SQLite (lecture seule ; défaut : DATABASE_URL)")
    ap.add_argument("--pause", type=float, default=1.0)
    args = ap.parse_args(argv)
    from database.models import Entreprise
    from spontanees.noms_entreprise import denomination_connue, fiche_annuaire
    trouvees = {}
    try:
        with session_lecture(args.base) as db:
            a_completer = [(e.id, e.siren, e.nom_commercial) for e in db.query(Entreprise).order_by(Entreprise.id)
                           if e.siren and not denomination_connue({"_extra": e.extra or {},
                                                                   "sources": list(e.sources or [])})]
        print(f"{len(a_completer)} entreprise(s) sans dénomination connue")
        for n, (ident, siren, nom) in enumerate(a_completer, 1):
            fiche = fiche_annuaire(siren)
            if fiche and fiche.get("denomination"):
                trouvees[ident] = fiche["denomination"]
                if fiche["denomination"].casefold() != (nom or "").casefold():
                    print(f"  {nom} -> {fiche['denomination']}")
            elif fiche is None:
                print(f"  {nom} : annuaire sans réponse")
            if n < len(a_completer):
                time.sleep(args.pause)
    except KeyboardInterrupt:
        print("\nInterrompu : rien n'a été écrit en base.")
        return 130
    print(f"{len(trouvees)} dénomination(s) trouvée(s)")
    if args.appliquer and trouvees:
        from database.connexion import SessionLocal
        with SessionLocal() as db:
            for ident, denomination in trouvees.items():
                e = db.get(Entreprise, ident)
                if e is not None:
                    e.extra = {**(e.extra or {}), "denomination": denomination}
            db.commit()
        print("Écrit en une transaction.")
    elif trouvees:
        print("Lecture seule : relance avec --appliquer pour les écrire.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
