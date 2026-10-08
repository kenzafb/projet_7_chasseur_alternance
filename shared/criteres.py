"""
shared/criteres.py
==================
Critères de recherche du profil (profils.recherche, colonne JSON), remis
en forme à l'enregistrement : valeurs inconnues retirées, types fixés.
Les autres clés (disponibilité, champs en lecture seule) passent telles quelles.
"""

from shared.domaines import normaliser_domaines


def normaliser_recherche(recherche) -> dict:
    """Copie propre de recherche (dict vide si ce n'en est pas un)."""
    if not isinstance(recherche, dict):
        return {}
    out = dict(recherche)
    if "domaines" in out:
        out["domaines"] = normaliser_domaines(out["domaines"])
    return out
