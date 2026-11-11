"""
auth/securite.py
================
Briques de sécurité de l'authentification :
  - vérifier un mot de passe contre son hash
  - hacher un nouveau mot de passe (pour /register)
  - récupérer l'utilisateur actuellement connecté depuis la session
  - utilisateur_requis : LA dépendance FastAPI de toutes les routes privées

On réutilise le PasswordHelper de fastapi-users (déjà utilisé à la migration),
donc les hashs créés hier restent valides.
"""

import hashlib
import hmac

from fastapi import Request
from fastapi_users.password import PasswordHelper

from database.connexion import SessionLocal
from database.models import User
from shared.config import secret_key

_pwd = PasswordHelper()

# Pour les nouveaux comptes seulement : les hashs existants restent valides
LONGUEUR_MIN_MOT_DE_PASSE = 10


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


def verifier_nouveau_mot_de_passe(mot_de_passe: str) -> str | None:
    """Règles d'un nouveau mot de passe (inscription, changement) : message
    d'erreur, ou None s'il est accepté."""
    if len(mot_de_passe or "") < LONGUEUR_MIN_MOT_DE_PASSE:
        return f"Mot de passe trop court ({LONGUEUR_MIN_MOT_DE_PASSE} caractères minimum)."
    return None


def empreinte_session(hash_mot_de_passe: str) -> str:
    """Empreinte du mot de passe gardée dans le cookie de session (D122) :
    HMAC du hash par SECRET_KEY, jamais le hash lui-même (le cookie est signé,
    pas chiffré). Un changement de mot de passe change l'empreinte : toutes
    les sessions ouvertes avant deviennent invalides."""
    return hmac.new(secret_key().encode(), (hash_mot_de_passe or "").encode(), hashlib.sha256).hexdigest()[:32]


def ouvrir_session(request: Request, user: User):
    """Connecte user dans ce navigateur : son id et l'empreinte de son mot de passe."""
    request.session["user_id"] = user.id
    request.session["empreinte"] = empreinte_session(user.mot_de_passe_hash)


def utilisateur_courant(request: Request):
    """
    Récupère l'utilisateur connecté à partir de la session.
    Retourne l'objet User, ou None si personne n'est connecté.
    À utiliser dans les routes pour savoir qui fait la requête.
    Une session dont l'empreinte ne correspond plus au mot de passe (changé
    depuis, ou session ouverte avant D122) est fermée.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id).first()
    finally:
        db.close()
    empreinte = request.session.get("empreinte") or ""
    if not user or not hmac.compare_digest(empreinte, empreinte_session(user.mot_de_passe_hash)):
        request.session.clear()
        return None
    return user


class NonConnecte(Exception):
    """Levée par utilisateur_requis ; main.py la traduit en 401 JSON (/api)
    ou en redirection vers /login (pages)."""


def utilisateur_requis(request: Request) -> User:
    """
    Dépendance FastAPI unique pour les routes privées : renvoie l'utilisateur
    connecté, ou lève NonConnecte. FastAPI la met en cache le temps d'une
    requête, donc la base n'est lue qu'une fois même si elle est déclarée
    à la fois sur le routeur et dans la signature de la route.
    """
    user = utilisateur_courant(request)
    if not user:
        raise NonConnecte()
    return user

