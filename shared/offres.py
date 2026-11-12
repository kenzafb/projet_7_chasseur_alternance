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


# ─── Entreprise inconnue (D138) ───────────────────────────────────────────────
# Nom masqué par France Travail (environ une offre sur deux) ou absent
NOMS_VIDES = {"", "inconnue", "inconnu", "non précisé", "non precise", "non renseigné", "non renseigne", "n/a", "na",
              "none"}
# Ce que la lettre et son PDF écrivent à la place, et ce que la page en dit :
# des formulations neutres, jamais une balise « à compléter »
DESTINATAIRE_INCONNU = "À l'attention du service recrutement"
ENTREPRISE_INCONNUE = "votre entreprise"
INFO_DESTINATAIRE_INCONNU = ("Contact de l'entreprise inconnu : la lettre est adressée au service recrutement. "
                             "Tu peux modifier cette ligne.")
INFO_ENTREPRISE_INCONNUE = ("Nom de l'entreprise inconnu : la lettre parle de « votre entreprise ». "
                            "Tu peux modifier ce passage.")


def entreprise_connue(offre: dict) -> bool:
    return (offre.get("entreprise") or "").strip().lower() not in NOMS_VIDES

