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

def _chemin_sous(racine: Path, relatif: str) -> Path | None:
    """racine / relatif, ou None si relatif est vide ou sort de racine."""
    if not relatif:
        return None
    racine = racine.resolve()
    chemin = (racine / relatif).resolve()
    if not chemin.is_relative_to(racine):
        return None
    return chemin

def chemin_piece_jointe(relatif: str) -> Path | None:
    """Chemin absolu d'une pièce jointe stockée en base (relatif à UPLOADS_DIR).
    None si le chemin est vide ou sort du dossier des pièces jointes."""
    return _chemin_sous(UPLOADS_DIR, relatif)

def chemin_lettre_pdf(relatif: str) -> Path | None:
    """Chemin absolu d'une lettre PDF stockée en base (relatif à LETTRES_PDF_DIR).
    None si le chemin est vide ou sort du dossier des lettres."""
    return _chemin_sous(LETTRES_PDF_DIR, relatif)

# Base de données : DATABASE_URL du .env si présente, sinon SQLite local
# (une ligne "DATABASE_URL=" vide dans le .env vaut absence)
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'chasseur.db'}"

# Fuseau dans lequel les dates sont AFFICHÉES (elles sont stockées en UTC).
# Le fuseau du serveur n'intervient jamais.
FUSEAU_AFFICHAGE = os.getenv("FUSEAU_AFFICHAGE") or "Europe/Paris"

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

# ─── Pipelines ────────────────────────────────────────────────────────────────
# Lignes de log gardées en mémoire par utilisateur (les plus anciennes sont jetées)
LOGS_MAX_PAR_UTILISATEUR = 200

# ─── Envoi de mails ───────────────────────────────────────────────────────────
# Plafond de mails envoyés par utilisateur et par jour (jour calendaire dans
# FUSEAU_AFFICHAGE), tous lancements et mails de test confondus, en plus de
# la limite par lancement. Surchargeable dans le .env.
PLAFOND_ENVOIS_JOUR = int(os.getenv("PLAFOND_ENVOIS_JOUR") or 50)
# Plafond par lancement du pipeline d'envoi (valeur maximale acceptée par la route)
LIMITE_ENVOIS_PAR_LANCEMENT = 50

# ─── Limites par lancement ────────────────────────────────────────────────────
# Choisies dans l'interface au moment de lancer. Valeur absente : défaut ;
# inférieure à 1 : 1 ; au-delà du plafond : ramenée au plafond (côté serveur).
LIMITES_LANCEMENT = {
    "analyses":    {"defaut": 30,  "max": 200},    # offres analysées par Mistral (France Travail + LBA)
    "sans_ia":     {"defaut": 100, "max": 500},    # offres ajoutées sans analyse, ANALYSE_IA=false (D20)
    "entreprises": {"defaut": 200, "max": 5000},   # nouvelles entreprises récupérées (Sirene)
    "scrapees":    {"defaut": 20,  "max": 200},    # entreprises dont on cherche le site et les emails
    "revalidations": {"defaut": 20, "max": 200},   # entreprises aux emails non validés repassées à l'IA
    "mails":       {"defaut": 10,  "max": LIMITE_ENVOIS_PAR_LANCEMENT},   # mails envoyés
}

def limite_lancement(cle: str, demandee) -> int:
    """Limite effective d'un lancement : défaut si absente, bornée à [1, plafond]."""
    regle = LIMITES_LANCEMENT[cle]
    if demandee is None:
        return regle["defaut"]
    return max(1, min(int(demandee), regle["max"]))

# ─── IA ───────────────────────────────────────────────────────────────────────
def analyse_ia_active() -> bool:
    """Interrupteur ANALYSE_IA du .env (vrai par défaut). Faux : aucun appel
    à Mistral nulle part ; offres insérées « non analysées », scraper en
    lecture directe seulement. Relu à chaque appel."""
    valeur = os.getenv("ANALYSE_IA", "").strip().lower()
    return valeur not in ("0", "false", "non", "no", "off")

MESSAGE_IA_DESACTIVEE = "IA désactivée (ANALYSE_IA=false dans le .env) : aucun appel à Mistral."

# Modèle par usage : MODELE_MISTRAL_<USAGE> du .env, sinon MODELE_MISTRAL, sinon
# le défaut de l'usage. scripts/verifier_mistral.py teste ceux de la clé.
USAGES_MISTRAL = {
    "analyse":    "mistral-medium-latest",   # notation des offres
    "lettre":     "mistral-medium-latest",   # paragraphe des lettres de motivation
    "extraction": "mistral-small-latest",    # emails et contacts des pages d'entreprise
}

def modele_mistral(usage: str) -> str:
    """Modèle Mistral d'un usage, relu dans l'environnement à chaque appel."""
    return (os.getenv(f"MODELE_MISTRAL_{usage.upper()}", "").strip()
            or os.getenv("MODELE_MISTRAL", "").strip()
            or USAGES_MISTRAL[usage])
# Intervalle minimum entre deux appels Mistral, commun à tout le processus
# (tous utilisateurs et pipelines confondus). Surchargeable dans le .env.
MISTRAL_INTERVALLE_MIN_S = float(os.getenv("MISTRAL_INTERVALLE_MIN_S") or 2.0)

# ─── Géographie (Île-de-France) ───────────────────────────────────────────────
# France Travail : code région INSEE de l'Île-de-France
FT_REGION = "11"

# Départements IDF (filtre des offres FT et LBA, calcul de la zone)
DEPTS_IDF             = {"75", "77", "78", "91", "92", "93", "94", "95"}
DEPTS_PETITE_COURONNE = {"92", "93", "94"}

# La Bonne Alternance : plusieurs centres à rayon réduit plutôt qu'un cercle
# de 60 km autour de Paris (qui débordait sur l'Oise et manquait l'est de la
# Seine-et-Marne). Rayon court là où les offres sont denses (plafond de 150
# résultats par source et par requête), plus large en grande couronne.
# Les cercles se chevauchent : résultats dédoublonnés. Rayons ramenés à
# parametres_lba.RAYON_MAX_KM. (nom, latitude, longitude, rayon en km)
LBA_CENTRES = [
    ("Paris",                 48.8566, 2.3522,  8),
    ("Nanterre",              48.8924, 2.2069, 10),
    ("Clamart",               48.8000, 2.2667, 10),
    ("Bobigny",               48.9077, 2.4397, 10),
    ("Créteil",               48.7904, 2.4556, 10),
    ("Versailles",            48.8049, 2.1204, 18),
    ("Cergy",                 49.0364, 2.0761, 20),
    ("Roissy",                49.0097, 2.5479, 20),
    ("Marne-la-Vallée",       48.8486, 2.6347, 18),
    ("Évry",                  48.6296, 2.4410, 20),
    ("Melun",                 48.5421, 2.6554, 20),
    ("Meaux",                 48.9601, 2.8788, 20),
    ("Coulommiers",           48.8130, 3.0840, 20),
    ("Provins",               48.5600, 3.2990, 25),
    ("Fontainebleau",         48.4047, 2.7016, 22),
    ("Nemours",               48.2667, 2.6970, 20),
    ("Étampes",               48.4346, 2.1615, 22),
    ("Rambouillet",           48.6440, 1.8300, 25),
    ("Mantes-la-Jolie",       48.9906, 1.7171, 25),
]

# Redécoupage d'un cercle au plafond (150 résultats) : sept cercles de rayon
# moitié, pas en dessous de ce rayon (km) ; au-delà, le cercle est signalé
LBA_RAYON_MIN_KM = 1
# Requêtes LBA au plus par recherche (redécoupages compris), environ 3 min
LBA_REQUETES_MAX = 300

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
