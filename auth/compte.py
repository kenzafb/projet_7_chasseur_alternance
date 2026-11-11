"""
auth/compte.py
==============
Réglages du compte de connexion, communs aux trois modes (page Paramètres,
D122) : changer le mot de passe (ancien obligatoire), changer l'email de
connexion (mot de passe obligatoire). Les erreurs sont des
ErreurUtilisateur (400, message lisible). Rien n'est journalisé : ni
mot de passe, ni hash.
"""

import re

from auth.securite import hacher_mot_de_passe, verifier_mot_de_passe, verifier_nouveau_mot_de_passe
from database.connexion import SessionLocal
from database.models import User
from shared.erreurs import ErreurUtilisateur

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _utilisateur(db, user_id: int) -> User:
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise ErreurUtilisateur("Compte introuvable.")
    return user


def changer_mot_de_passe(user_id: int, ancien: str, nouveau: str, confirmation: str) -> User:
    """Nouveau hash enregistré ; retourne l'utilisateur à jour (pour rouvrir
    la session courante avec la nouvelle empreinte)."""
    db = SessionLocal()
    try:
        user = _utilisateur(db, user_id)
        if not verifier_mot_de_passe(ancien or "", user.mot_de_passe_hash):
            raise ErreurUtilisateur("Mot de passe actuel incorrect.")
        if erreur := verifier_nouveau_mot_de_passe(nouveau):
            raise ErreurUtilisateur(erreur)
        if nouveau != confirmation:
            raise ErreurUtilisateur("La confirmation ne correspond pas au nouveau mot de passe.")
        if nouveau == ancien:
            raise ErreurUtilisateur("Le nouveau mot de passe doit être différent de l'actuel.")
        user.mot_de_passe_hash = hacher_mot_de_passe(nouveau)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user
    finally:
        db.close()


def changer_email(user_id: int, nouvel_email: str, mot_de_passe: str) -> str:
    """Email de connexion changé (en minuscules) ; retourne le nouvel email.
    L'email de contact des profils et le compte d'envoi ne changent pas."""
    email = (nouvel_email or "").strip().lower()
    db = SessionLocal()
    try:
        user = _utilisateur(db, user_id)
        if not verifier_mot_de_passe(mot_de_passe or "", user.mot_de_passe_hash):
            raise ErreurUtilisateur("Mot de passe incorrect.")
        if not _EMAIL.match(email) or len(email) > 255:
            raise ErreurUtilisateur("Adresse email invalide.")
        if email == user.email:
            raise ErreurUtilisateur("C'est déjà ton email de connexion.")
        if db.query(User).filter(User.email == email, User.id != user_id).first():
            raise ErreurUtilisateur("Un compte existe déjà avec cet email.")
        user.email = email
        db.commit()
        return email
    finally:
        db.close()
