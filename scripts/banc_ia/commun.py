"""
scripts/banc_ia/commun.py
=========================
Outils du banc d'essai de l'IA (phase 15) : format du jeu de référence,
catégories, lecture des profils, appel du modèle avec une température
donnée. Format décrit dans scripts/banc_ia/README.md.
"""

import importlib.util
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # scripts/ : audit_commun

from audit_commun import RACINE, SORTIE, lire_json  # noqa: E402,F401

# Catégories attendues (jeu de référence) et leur rang, de la meilleure à la pire
CATEGORIES = ["Très bien", "Bien", "Moyen", "Faible", "Hors sujet"]
RANG = {c: i for i, c in enumerate(CATEGORIES)}
NIVEAUX = ["bac", "bac+2", "bac+3", "bac+4", "bac+5", "non_precise"]

# Champs d'identité retirés des profils exportés (le banc n'en a pas besoin)
CHAMPS_IDENTITE = ("prenom", "nom", "email", "telephone", "linkedin", "github", "portfolio", "pieces_jointes",
                   "email_objet", "email_type")


def categorie_du_resultat(res: dict) -> str:
    """Catégorie de l'application pour une analyse finale (après les règles
    Python) : inéligible ou 0-2 : Hors sujet ; 3-4 Faible ; 5-6 Moyen ;
    7-8 Bien ; 9-10 Très bien. Même seuils que offres.analyse.score_to_verdict."""
    score = res.get("score")
    if score is None:
        return "?"
    if not res.get("eligible", True) or score <= 2:
        return "Hors sujet"
    if score >= 9:
        return "Très bien"
    if score >= 7:
        return "Bien"
    if score >= 5:
        return "Moyen"
    return "Faible"


def activer_ia():
    """ANALYSE_IA=false est ignoré pour le banc (rien n'est écrit en base)."""
    os.environ["ANALYSE_IA"] = "true"


def charger_prompt(chemin: str | None, fonction: str):
    """Fonction `fonction` d'un fichier Python donné (variante de prompt), ou
    None : celle de l'application."""
    if not chemin:
        return None
    spec = importlib.util.spec_from_file_location("prompt_variante", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, fonction)


def charger_reference(chemin) -> dict:
    ref = lire_json(chemin)
    if not isinstance(ref, dict) or "offres" not in ref:
        raise SystemExit(f"{chemin} : jeu de référence attendu ({{\"profils\": ..., \"offres\": [...]}})")
    return ref


def profil_de(ref: dict, offre: dict) -> dict:
    return ref["profils"].get(offre["profil"]) or {}


def mots(texte: str) -> list[str]:
    return re.findall(r"[\wÀ-ÿ'’+#.-]+", texte or "")


def ngrammes(texte: str, n: int = 5) -> set[tuple]:
    m = [x.lower().strip(".,;:!?") for x in mots(texte)]
    return {tuple(m[i:i + n]) for i in range(len(m) - n + 1)}


def moyenne(valeurs) -> float | None:
    valeurs = [v for v in valeurs if v is not None]
    return round(sum(valeurs) / len(valeurs), 2) if valeurs else None


def ecart_type(valeurs) -> float | None:
    valeurs = [v for v in valeurs if v is not None]
    if len(valeurs) < 2:
        return 0.0 if valeurs else None
    m = sum(valeurs) / len(valeurs)
    return round((sum((v - m) ** 2 for v in valeurs) / (len(valeurs) - 1)) ** 0.5, 2)
