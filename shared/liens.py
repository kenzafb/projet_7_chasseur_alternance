"""
shared/liens.py
===============
Liens venus de l'extérieur (API France Travail et LBA, sites scrapés) :
seuls les liens http(s) sont gardés (D132). Un lien « javascript: »,
« data: » ou sans schéma reçu d'une API n'arrive jamais dans la page.
"""

import re

_HTTP = re.compile(r"^https?://[^\s<>\"'`\x00-\x1f]+$", re.IGNORECASE)


def lien_http(url) -> str:
    """url si c'est un lien http(s) sans caractère d'échappement, sinon ""."""
    url = str(url or "").strip()
    return url if _HTTP.match(url) else ""
