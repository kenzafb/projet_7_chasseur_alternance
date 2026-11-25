"""
scripts/renommer_pieces_jointes.py
==================================
Ménage (D198) : renomme les pièces jointes héritées de l'ancienne
application, dont le fichier porte un nom répété ou n'a pas d'extension
(« Programme_BTS_SIO_Programme_BTS_SIO.pdf » ->
« Programme_BTS_SIO.pdf »). Le nom reçu par les entreprises ne change
pas : c'est le nom affiché de la pièce (profil), déjà propre.

Un fichier partagé par plusieurs modes est renommé une fois, et toutes ses
références suivent. Jamais d'écrasement : si le nom propre est déjà pris,
le fichier garde le sien.

Par défaut, lecture seule. --appliquer renomme les fichiers puis écrit la
base en une seule transaction (fichiers remis en place si l'écriture
échoue). Application arrêtée.

    venv/bin/python scripts/renommer_pieces_jointes.py
    venv/bin/python scripts/renommer_pieces_jointes.py --appliquer
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def nom_propre(relatif: str) -> str:
    from routes.profil import nom_sans_repetition
    dossier, _, nom = relatif.rpartition("/")
    base = re.sub(r"\.pdf$", "", nom, flags=re.IGNORECASE)
    return f"{dossier}/{nom_sans_repetition(base)}.pdf" if dossier else f"{nom_sans_repetition(base)}.pdf"


def plan(pieces_par_profil: dict) -> tuple[dict[str, str], list[str]]:
    """({ancien relatif: nouveau}, [messages des fichiers laissés tels quels])."""
    from shared.config import chemin_piece_jointe
    renommages, laisses = {}, []
    fichiers = sorted({pj.get("fichier") for pieces in pieces_par_profil.values() for pj in pieces if pj.get("fichier")})
    for ancien in fichiers:
        nouveau = nom_propre(ancien)
        if nouveau == ancien:
            continue
        source, cible = chemin_piece_jointe(ancien), chemin_piece_jointe(nouveau)
        if not source or not source.is_file():
            laisses.append(f"{ancien} : fichier introuvable")
        elif cible is None or cible.exists() or nouveau in renommages.values() or nouveau in fichiers:
            laisses.append(f"{ancien} : {nouveau} déjà pris, nom gardé")
        else:
            renommages[ancien] = nouveau
    return renommages, laisses


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--appliquer", action="store_true")
    ap.add_argument("--base", help="URL SQLite (lecture seule ; défaut : DATABASE_URL)")
    args = ap.parse_args(argv)
    from audit_commun import session_lecture

    from database.models import Profil
    from shared.config import chemin_piece_jointe
    with session_lecture(args.base) as db:
        pieces = {p.id: list(p.pieces_jointes or []) for p in db.query(Profil)}
    renommages, laisses = plan(pieces)
    for a, n in renommages.items():
        print(f"  {a} -> {n}")
    for m in laisses:
        print(f"  laissé : {m}")
    print(f"{len(renommages)} fichier(s) à renommer")
    if not args.appliquer or not renommages:
        if renommages:
            print("Lecture seule : relance avec --appliquer pour les renommer.")
        return 0
    faits = []
    try:
        for a, n in renommages.items():
            os.rename(chemin_piece_jointe(a), chemin_piece_jointe(n))
            faits.append((a, n))
        from database.connexion import SessionLocal
        with SessionLocal() as db:
            for p in db.query(Profil):
                if any(pj.get("fichier") in renommages for pj in p.pieces_jointes or []):
                    p.pieces_jointes = [{**pj, "fichier": renommages.get(pj.get("fichier"), pj.get("fichier"))}
                                        for pj in p.pieces_jointes]
            db.commit()
    except BaseException:
        for a, n in reversed(faits):           # base non écrite : fichiers remis en place
            os.rename(chemin_piece_jointe(n), chemin_piece_jointe(a))
        print("Échec ou interruption : fichiers remis en place, base inchangée.")
        raise
    print(f"{len(faits)} fichier(s) renommé(s), base à jour en une transaction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
