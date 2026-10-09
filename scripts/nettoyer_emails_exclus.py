"""
scripts/nettoyer_emails_exclus.py
=================================
Applique les règles de shared/referentiels/emails_exclus.txt (décision
D47) aux entreprises déjà en base, tous utilisateurs : les adresses
techniques ou factices sont retirées de emails_trouves (et de
extra.emails_lba), et notées dans extra.emails_exclus_retires. À lancer
par l'humain, sur la base de DATABASE_URL :

    venv/bin/python scripts/nettoyer_emails_exclus.py              # liste seulement
    venv/bin/python scripts/nettoyer_emails_exclus.py --appliquer  # écrit en base

Sans --appliquer, rien n'est écrit. Une entreprise dont toutes les
adresses sont retirées reste « traitée » (le scraper n'y retourne pas) ;
elle n'est plus proposée à l'envoi. Code de sortie 0.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connexion import SessionLocal  # noqa: E402
from database.models import Entreprise  # noqa: E402
from shared.emails_exclus import email_exclu  # noqa: E402


def nettoyer(appliquer: bool = False, afficher=print) -> list[dict]:
    """Entreprises concernées : [{id, user_id, nom, retirees, restantes, envoyee}]."""
    concernees = []
    db = SessionLocal()
    try:
        for e in db.query(Entreprise).order_by(Entreprise.id):
            extra = dict(e.extra or {})
            emails = list(e.emails_trouves or [])
            retirees = [a for a in emails + list(extra.get("emails_lba") or []) if email_exclu(a)]
            if not retirees:
                continue
            restantes = [a for a in emails if not email_exclu(a)]
            concernees.append({"id": e.id, "user_id": e.user_id, "nom": e.nom_commercial or extra.get("nom", "?"),
                               "retirees": sorted(set(retirees)), "restantes": restantes,
                               "envoyee": any(m.mail_envoye for m in e.modes)})
            if appliquer:
                e.emails_trouves = restantes
                if "emails_lba" in extra:
                    extra["emails_lba"] = [a for a in extra["emails_lba"] if not email_exclu(a)]
                extra["emails_exclus_retires"] = sorted(set(extra.get("emails_exclus_retires", [])) | set(retirees))
                e.extra = extra
        if appliquer:
            db.commit()
    finally:
        db.close()
    for c in concernees:
        afficher(f"  utilisateur {c['user_id']}, entreprise {c['id']} « {c['nom'][:40]} » : "
                 f"{', '.join(c['retirees'])} retirée(s)"
                 + (f" ; reste {', '.join(c['restantes'])}" if c["restantes"] else " ; plus aucune adresse")
                 + (" (mail déjà envoyé)" if c["envoyee"] else ""))
    afficher(f"{len(concernees)} entreprise(s) concernée(s) : "
             + ("adresses retirées en base." if appliquer else "rien écrit (ajouter --appliquer pour retirer)."))
    return concernees


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retire des entreprises en base les adresses techniques ou factices.")
    parser.add_argument("--appliquer", action="store_true", help="écrire en base (sinon : liste seulement)")
    nettoyer(parser.parse_args().appliquer)
