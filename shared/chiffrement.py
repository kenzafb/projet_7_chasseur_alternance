"""
shared/chiffrement.py
=====================
Chiffrement symétrique (Fernet) des secrets stockés en base : le mot de
passe SMTP des comptes d'envoi.

La clé vient de CLE_CHIFFREMENT (.env), relue à chaque appel. Absente ou
invalide : l'application démarre quand même, mais tout ce qui doit chiffrer
ou déchiffrer lève ChiffrementIndisponible, avec un message lisible.
"""

import os

from cryptography.fernet import Fernet, InvalidToken

from shared.erreurs import ErreurUtilisateur

COMMANDE_GENERATION = ('python -c "from cryptography.fernet import Fernet; '
                       'print(Fernet.generate_key().decode())"')


class ChiffrementIndisponible(Exception):
    """CLE_CHIFFREMENT absente ou invalide : configuration et envoi de mails
    désactivés. main.py la renvoie en 503 {"erreur": message}."""


class SecretIllisible(ErreurUtilisateur):
    """Le secret stocké ne se déchiffre pas avec la clé actuelle (clé changée)."""

    def __init__(self):
        super().__init__(
            "Le mot de passe du compte d'envoi ne peut plus être relu (la clé de "
            "chiffrement du serveur a changé) : saisis-le à nouveau dans Profil, "
            "section Compte d'envoi.")


def _fernet() -> Fernet:
    cle = os.getenv("CLE_CHIFFREMENT", "").strip()
    if not cle:
        raise ChiffrementIndisponible(
            "Envoi de mails désactivé : la clé de chiffrement CLE_CHIFFREMENT "
            "n'est pas configurée sur le serveur.")
    try:
        return Fernet(cle.encode())
    except (ValueError, TypeError):
        # Le message de cryptography ne contient pas la clé, mais on ne le relaie pas
        raise ChiffrementIndisponible(
            "Envoi de mails désactivé : la clé de chiffrement CLE_CHIFFREMENT "
            "du serveur est invalide.") from None


def raison_indisponible() -> str | None:
    """None si le chiffrement est utilisable, sinon le message à afficher."""
    try:
        _fernet()
        return None
    except ChiffrementIndisponible as e:
        return str(e)


def chiffrer(texte: str) -> str:
    return _fernet().encrypt(texte.encode("utf-8")).decode("ascii")


def dechiffrer(jeton: str) -> str:
    try:
        return _fernet().decrypt(jeton.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        raise SecretIllisible() from None
