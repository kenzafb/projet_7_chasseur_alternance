"""
shared/metiers_informatique.py
==============================
Mode stage : offre hors informatique d'après son code métier ROME (D203),
fourni par France Travail pour chaque offre (champ romeCode), sans IA.

Gardée si son code est de la famille M18 (systèmes d'information et
télécommunications), sauf cartographie et météo (HORS_INFORMATIQUE), ou si
son intitulé contient un mot informatique. Code inconnu : gardée, jamais
d'archivage par défaut d'information.

Plusieurs utilisateurs : un profil de stage qui a choisi des domaines sans
M18 n'est pas concerné ; avec M18 et d'autres domaines, ceux-ci sont
gardés aussi.
"""

import re

from shared.domaines import domaines_du_profil
from shared.marques import simplifier

FAMILLE = "M18"
# Cartographe, météorologue, modélisation climatique, station, prévisionniste, technicien de la météorologie
HORS_INFORMATIQUE = frozenset({"M1808", "M1809", "M1888", "M1890", "M1891", "M1893"})
# « Développement RH », « développement commercial »... : pas de l'informatique (D207)
_SAUF = (r"(?!\s+(?:rh|des\s+ressources\s+humaines|commercia(?:l|le|ux|les)|business|durables?|personnels?"
         r"|des\s+competences)(?![a-z0-9]))")
_MOTS = re.compile(
    r"(?<![a-z0-9])(?:informatiques?|developpeu(?:r|rs|se|ses)|developpements?" + _SAUF + r"|logiciels?|reseaux?|systemes?"
    r"|bases? de donnees|web|cyber[\s-]?securite|devops|cloud|ia|data)(?![a-z0-9])")


def titre_informatique(titre: str) -> bool:
    """Un mot informatique entier dans l'intitulé (accents et casse ignorés)."""
    return bool(_MOTS.search(simplifier(titre)))


def hors_informatique(offre: dict, profil: dict | None = None) -> bool:
    """L'offre de stage est hors informatique d'après son code métier."""
    code = (offre.get("code_rome") or "").strip().upper()
    if not re.fullmatch(r"[A-Z]\d{4}", code):
        return False
    domaines = domaines_du_profil(profil or {})
    if domaines and FAMILLE not in domaines and FAMILLE[0] not in domaines:
        return False
    if any(code.startswith(d) for d in domaines if d != FAMILLE):
        return False
    if code.startswith(FAMILLE) and code not in HORS_INFORMATIQUE:
        return False
    return not titre_informatique(offre.get("titre") or "")
