"""
auth/securite.py
================
Briques de sécurité de l'authentification :
  - vérifier un mot de passe contre son hash
  - hacher un nouveau mot de passe (pour /register)
  - récupérer l'utilisateur actuellement connecté depuis la session

On réutilise le PasswordHelper de fastapi-users (déjà utilisé à la migration),
donc les hashs créés hier restent valides.
"""

from fastapi import Request
from fastapi_users.password import PasswordHelper

from database.connexion import SessionLocal
from database.models import User

_pwd = PasswordHelper()


def verifier_mot_de_passe(mot_de_passe: str, hash_stocke: str) -> bool:
    """True si le mot de passe correspond au hash en base."""
    valide, _ = _pwd.verify_and_update(mot_de_passe, hash_stocke)
    return valide


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    """Hache un mot de passe pour le stocker (inscription)."""
    return _pwd.hash(mot_de_passe)


def authentifier(email: str, mot_de_passe: str):
    """
    Vérifie email + mot de passe.
    Retourne l'objet User si OK, None sinon.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email.lower().strip()).first()
        if user and verifier_mot_de_passe(mot_de_passe, user.mot_de_passe_hash):
            return user
        return None
    finally:
        db.close()


def utilisateur_courant(request: Request):
    """
    Récupère l'utilisateur connecté à partir de la session.
    Retourne l'objet User, ou None si personne n'est connecté.
    À utiliser dans les routes pour savoir qui fait la requête.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter_by(id=user_id).first()
    finally:
        db.close()


def mode_courant(request) -> str:
    """Mode de chasse actuel ('alternance' ou 'job'), lu depuis la session.
    Défaut : 'alternance' (rétrocompat — comportement historique)."""
    from shared.modes import MODES, MODE_DEFAUT
    m = request.session.get("mode", MODE_DEFAUT)
    return m if m in MODES else MODE_DEFAUT
