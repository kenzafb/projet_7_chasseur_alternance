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
load_dotenv(BASE_DIR / ".env")

# ─── Chemins ──────────────────────────────────────────────────────────────────
DATA_DIR        = BASE_DIR / "data"
UPLOADS_DIR     = DATA_DIR / "uploads"
LETTRES_PDF_DIR = BASE_DIR / "lettres_pdf"
TEMPLATES_DIR   = BASE_DIR / "templates"
STATIC_DIR      = BASE_DIR / "static"

# Base de données : DATABASE_URL du .env si présente, sinon SQLite local
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'chasseur.db'}")

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
