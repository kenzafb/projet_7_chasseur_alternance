"""
shared/offres.py
================
Utilitaires communs aux scrapers d'offres (France Travail, La Bonne Alternance).
"""

import hashlib

from shared.config import DEPTS_IDF, DEPTS_PETITE_COURONNE


def generer_id(texte: str) -> str:
    """Identifiant stable d'une offre : md5 de son identifiant source."""
    return hashlib.md5(texte.encode()).hexdigest()


def detecter_zone(lieu: str) -> str | None:
    """Zone IDF d'un libellé de lieu "75 - Paris 10e", ou None si hors IDF."""
    if not lieu:
        return None
    dept = lieu.split(" - ")[0].strip().lstrip("0")
    if dept not in DEPTS_IDF:
        return None
    if dept == "75" or "paris" in lieu.lower():
        return "Paris"
    if dept in DEPTS_PETITE_COURONNE:
        return "Petite couronne"
    return "Grande couronne"
