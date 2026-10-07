"""
shared/config.py
================
Configuration centrale du projet.

Ce module charge le .env AVANT tout le reste : tout module qui lit une
variable d'environnement doit l'importer (directement ou via un autre
module du projet) pour que les valeurs du .env soient visibles.

Il expose aussi les chemins du projet (indépendants du dossier courant),
le modèle Mistral et la géographie de recherche (Île-de-France).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ─── Racine du projet + .env ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
# CHASSEUR_ENV_FILE permet aux tests de ne pas lire le vrai .env
load_dotenv(os.getenv("CHASSEUR_ENV_FILE", BASE_DIR / ".env"))

# ─── Chemins ──────────────────────────────────────────────────────────────────
DATA_DIR        = BASE_DIR / "data"
UPLOADS_DIR     = DATA_DIR / "uploads"
LETTRES_PDF_DIR = BASE_DIR / "lettres_pdf"
TEMPLATES_DIR   = BASE_DIR / "templates"
STATIC_DIR      = BASE_DIR / "static"

# Base de données : DATABASE_URL du .env si présente, sinon SQLite local
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'chasseur.db'}")

# ─── Sécurité ─────────────────────────────────────────────────────────────────
LONGUEUR_MIN_SECRET_KEY = 32

def secret_key() -> str:
    """Clé de signature des cookies de session. Pas de valeur de repli :
    absente ou trop courte, l'application refuse de démarrer."""
    cle = os.getenv("SECRET_KEY", "")
    if len(cle) < LONGUEUR_MIN_SECRET_KEY:
        raise RuntimeError(
            f"SECRET_KEY absente ou trop courte ({LONGUEUR_MIN_SECRET_KEY} caractères minimum). "
            "Génère-la avec : python -c \"import secrets; print(secrets.token_urlsafe(48))\" "
            "puis ajoute-la au .env.")
    return cle

def code_invitation() -> str:
    """Code exigé à l'inscription. Vide ou absent : inscriptions fermées.
    Relu à chaque appel, pour qu'un changement d'environnement suffise."""
    return os.getenv("CODE_INVITATION", "").strip()

# Cookie de session réservé à HTTPS : true en production, false en local (http)
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() in ("1", "true", "oui", "yes")

# ─── IA ───────────────────────────────────────────────────────────────────────
MODELE_MISTRAL = "mistral-large-latest"

# ─── Géographie (Île-de-France) ───────────────────────────────────────────────
# France Travail : code région INSEE de l'Île-de-France
FT_REGION = "11"

# Départements IDF (filtre des offres FT et LBA, calcul de la zone)
DEPTS_IDF             = {"75", "77", "78", "91", "92", "93", "94", "95"}
DEPTS_PETITE_COURONNE = {"92", "93", "94"}

# La Bonne Alternance : recherche par rayon autour de Paris
LBA_LATITUDE  = 48.8566
LBA_LONGITUDE = 2.3522
LBA_RAYON_KM  = 60

# INSEE Sirene : départements interrogés pour les candidatures spontanées
SIRENE_DEPARTEMENTS = [
    "75",   # Paris
#   "77",   # Seine-et-Marne
#   "78",   # Yvelines
#   "91",   # Essonne
    "92",   # Hauts-de-Seine
    "93",   # Seine-Saint-Denis
    "94",   # Val-de-Marne
#   "95",   # Val-d'Oise
]
