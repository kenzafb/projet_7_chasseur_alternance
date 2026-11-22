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


# ─── Sous-domaines de préproduction ou de test (D165) ─────────────────────────
# Une étiquette de sous-domaine (jamais le domaine lui-même) qui vaut l'un de
# ces mots, suivi ou non d'un chiffre ou d'un tiret : « prepod.fun.x.fr »,
# « staging2.acme.fr », « recette-v2.acme.fr ». Constat : le site vérifié de
# France Université Numérique était prepod.fun.luniversitenumerique.fr.
MOTS_PREPRODUCTION = ("preprod", "pre-prod", "prepod", "staging", "dev", "test", "tests", "recette", "qa", "demo")
_PREPROD = re.compile(r"^(?:" + "|".join(re.escape(m) for m in MOTS_PREPRODUCTION) + r")(?:\d+|-[a-z0-9-]*)?$")


def est_preproduction(hote: str) -> bool:
    """Vrai si un sous-domaine de hote est de préproduction ou de test."""
    etiquettes = (hote or "").lower().strip(".").split(".")
    return any(_PREPROD.match(e) for e in etiquettes[:-2])


def sans_preproduction(url: str) -> str:
    """Même adresse sur le domaine principal : étiquettes jusqu'à la dernière
    de préproduction retirées (« https://prepod.fun.x.fr/a » ->
    « https://fun.x.fr/a ») ; url telle quelle sinon."""
    from urllib.parse import urlsplit, urlunsplit
    p = urlsplit(url if "://" in url else "https://" + url)
    etiquettes = p.netloc.lower().split(".")
    rangs = [i for i, e in enumerate(etiquettes[:-2]) if _PREPROD.match(e)]
    if not rangs:
        return url
    hote = ".".join(etiquettes[rangs[-1] + 1:])
    return urlunsplit((p.scheme, hote, p.path, p.query, p.fragment))
