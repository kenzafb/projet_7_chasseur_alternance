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
import math
import threading
import time

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


_hash_factice = None


def _hash_pour_email_inconnu() -> str:
    """Hash vérifié quand l'email n'existe pas : même durée de réponse qu'un
    mauvais mot de passe, rien ne dit si le compte existe (D134)."""
    global _hash_factice
    if _hash_factice is None:
        _hash_factice = hacher_mot_de_passe("email-inconnu-" + "x" * 20)
    return _hash_factice


def authentifier(email: str, mot_de_passe: str):
    """
    Vérifie email + mot de passe.
    Retourne l'objet User si OK, None sinon.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email.lower().strip()).first()
        if user is None:
            verifier_mot_de_passe(mot_de_passe, _hash_pour_email_inconnu())
            return None
        return user if verifier_mot_de_passe(mot_de_passe, user.mot_de_passe_hash) else None
    finally:
        db.close()


# ─── Échecs de connexion (D134) ───────────────────────────────────────────────
# Au plus ESSAIS_MAX échecs par email et adresse IP sur FENETRE_S secondes ;
# au-delà, la connexion est refusée jusqu'à ce que le plus ancien échec sorte
# de la fenêtre. En mémoire : un redémarrage remet les compteurs à zéro.
ESSAIS_MAX = 5
FENETRE_S = 15 * 60
_echecs: dict[str, list[float]] = {}
_verrou_echecs = threading.Lock()


def _recents(cle: str, maintenant: float) -> list[float]:
    return [t for t in _echecs.get(cle, []) if maintenant - t < FENETRE_S]


def attente_connexion(cle: str, maintenant: float | None = None) -> int:
    """Secondes à attendre avant un nouvel essai (0 : essai permis)."""
    maintenant = time.monotonic() if maintenant is None else maintenant
    with _verrou_echecs:
        recents = _recents(cle, maintenant)
        _echecs[cle] = recents
        if len(recents) < ESSAIS_MAX:
            return 0
        return math.ceil(FENETRE_S - (maintenant - recents[0]))


def noter_echec(cle: str, maintenant: float | None = None):
    maintenant = time.monotonic() if maintenant is None else maintenant
    with _verrou_echecs:
        _echecs[cle] = _recents(cle, maintenant) + [maintenant]


def effacer_echecs(cle: str):
    with _verrou_echecs:
        _echecs.pop(cle, None)


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


class MotDePasseTemporaire(Exception):
    """Levée par utilisateur_requis tant que le mot de passe temporaire
    (D123) n'est pas changé ; main.py la traduit en 403 JSON (/api) ou en
    redirection vers /mot-de-passe-temporaire (pages)."""


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
    if user.mot_de_passe_temporaire:
        raise MotDePasseTemporaire()
    return user

