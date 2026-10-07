"""
database/dates.py
=================
Dates de l'application : stockées en UTC, affichées en heure de Paris.

Règles :
  - en base, toute date est un INSTANT en UTC (colonnes DateTime). Même
    une date « seule » (offre trouvée, candidature envoyée) est l'instant
    où l'événement a eu lieu, jamais un minuit local ;
  - la conversion vers l'heure affichée (FUSEAU_AFFICHAGE, Europe/Paris par
    défaut) se fait uniquement à la sortie de la couche d'accès (en_texte)
    ou à l'affichage (maintenant_affichage) ;
  - le fuseau du serveur (variable TZ, réglage du système) n'intervient
    nulle part : le résultat est le même sur n'importe quelle machine.
"""

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from shared import config

JOUR = "%Y-%m-%d"
JOUR_HEURE = "%Y-%m-%d %H:%M"

_DATE_SEULE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fuseau_affichage() -> ZoneInfo:
    """Fuseau dans lequel les dates sont montrées (Europe/Paris par défaut)."""
    return ZoneInfo(config.FUSEAU_AFFICHAGE)


def maintenant_utc() -> datetime:
    return datetime.now(timezone.utc)


def maintenant_affichage() -> datetime:
    """Maintenant, en heure d'affichage (date d'une lettre, heure d'un log)."""
    return datetime.now(fuseau_affichage())


def vers_utc(valeur) -> datetime | None:
    """Valeur à stocker → datetime UTC, ou None si vide.

    Accepte un datetime ou une chaîne ISO avec heure. Avec fuseau (« Z »,
    « +02:00 »), l'instant est pris tel quel ; sans fuseau, l'heure est lue
    dans le fuseau d'affichage (une chaîne « AAAA-MM-JJ HH:MM » relue par
    en_texte revient donc au même instant). Une date seule est refusée :
    elle ne désigne pas un instant."""
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, str):
        texte = valeur.strip()
        if _DATE_SEULE.match(texte):
            raise ValueError(f"date seule refusée ({texte}) : il faut un instant (date et heure)")
        valeur = datetime.fromisoformat(texte)
    if not isinstance(valeur, datetime):
        raise TypeError(f"date et heure attendues, reçu {type(valeur).__name__}")
    if valeur.tzinfo is None:
        valeur = valeur.replace(tzinfo=fuseau_affichage())
    return valeur.astimezone(timezone.utc)


def instant_depuis_api(texte) -> datetime:
    """Horodatage reçu d'une API (France Travail, La Bonne Alternance) → UTC.
    Sans fuseau, il est en UTC (format de ces API). Une date seule devient
    midi heure d'affichage ce jour-là (la date affichée reste la bonne). Vide
    ou illisible : maintenant."""
    texte = (texte or "").strip()
    try:
        if _DATE_SEULE.match(texte):
            jour = datetime.fromisoformat(texte)
            return jour.replace(hour=12, tzinfo=fuseau_affichage()).astimezone(timezone.utc)
        dt = datetime.fromisoformat(texte)
    except ValueError:
        return maintenant_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def depuis_base(valeur: datetime | None) -> datetime | None:
    """Date relue en base → datetime UTC conscient du fuseau (SQLite relit
    des dates naïves : elles sont en UTC)."""
    if valeur is None:
        return None
    if valeur.tzinfo is None:
        return valeur.replace(tzinfo=timezone.utc)
    return valeur.astimezone(timezone.utc)


def en_texte(valeur: datetime | None, fmt: str) -> str:
    """Date relue en base → chaîne en heure d'affichage ("" si absente)."""
    dt = depuis_base(valeur)
    return dt.astimezone(fuseau_affichage()).strftime(fmt) if dt else ""
