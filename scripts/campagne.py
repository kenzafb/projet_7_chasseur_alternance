"""
scripts/campagne.py
===================
Campagne automatique d'entreprises à contacter (D213, docs/CAMPAGNE.md) :
recherche d'emails, liste à valider sur Telegram, envoi, mode par mode.
Peut tourner pendant que l'application est ouverte.

    venv/bin/python scripts/campagne.py --utilisateur 1 --modes stage,job --cible 30

Réglages : CAMPAGNE_* et TELEGRAM_* du .env. Ctrl+C ou SIGTERM : arrêt
propre, ce qui est fait est déjà en base.

Codes de sortie : 0 fait, 1 refus (réglage, utilisateur), 3 une campagne
tourne déjà.
"""

import argparse
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connexion import SessionLocal
from database.models import User
from shared.erreurs import ErreurUtilisateur
from shared.modes import verifier_mode
from shared.telegram import ErreurTelegram, depuis_env
from spontanees.campagne import Campagne, CampagneEnCours, reglages_env


def preparer(args) -> Campagne:
    """Campagne prête à lancer ; ErreurUtilisateur ou ErreurTelegram sinon."""
    modes = list(dict.fromkeys(m.strip() for m in args.modes.split(",") if m.strip()))
    if not modes:
        raise ErreurUtilisateur("Aucun mode : --modes stage,job")
    for mode in modes:
        verifier_mode(mode)
    reglages = reglages_env(args.cible)
    db = SessionLocal()
    try:
        if db.get(User, args.utilisateur) is None:
            raise ErreurUtilisateur(f"Utilisateur {args.utilisateur} inconnu.")
    finally:
        db.close()
    telegram = depuis_env()
    if telegram is None and reglages.validation == "telegram":
        raise ErreurUtilisateur("CAMPAGNE_VALIDATION=telegram demande TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID "
                                "(docs/CAMPAGNE.md).")
    if telegram is None and reglages.fin in ("eteindre", "veille"):
        raise ErreurUtilisateur(f"CAMPAGNE_FIN={reglages.fin} demande Telegram : sans lui, impossible d'annuler.")
    return Campagne(args.utilisateur, modes, reglages, telegram)


def main(argv=None) -> int:
    analyse = argparse.ArgumentParser(description="Campagne automatique d'entreprises à contacter")
    analyse.add_argument("--utilisateur", type=int, required=True)
    analyse.add_argument("--modes", default="stage,job", help="dans l'ordre, séparés par des virgules")
    analyse.add_argument("--cible", type=int, default=30, help="entreprises prêtes par mode")
    args = analyse.parse_args(argv)
    try:
        campagne = preparer(args)
    except (ErreurUtilisateur, ErreurTelegram) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    def arreter(*_):
        campagne.arret = True
    signal.signal(signal.SIGTERM, arreter)
    signal.signal(signal.SIGINT, arreter)
    try:
        campagne.executer()
    except CampagneEnCours as e:
        print(f"❌ {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
