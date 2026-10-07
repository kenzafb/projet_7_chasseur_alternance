"""
database/dates.py
=================
Conversion entre les colonnes DateTime de la base (UTC) et les chaînes que
le reste de l'app manipule depuis toujours ("AAAA-MM-JJ" pour les offres,
"AAAA-MM-JJ HH:MM" pour les envois spontanés), en heure locale du serveur.

Règles :
  - à l'écriture, une chaîne ou une date naïve est lue en heure locale,
    puis convertie en UTC ; chaîne vide ou None donne None ;
  - à la lecture, une date naïve (SQLite ne garde pas le fuseau) est en UTC.
"""

from datetime import datetime, timezone

JOUR = "%Y-%m-%d"
JOUR_HEURE = "%Y-%m-%d %H:%M"


def vers_utc(valeur) -> datetime | None:
    """Chaîne ISO ("AAAA-MM-JJ", "AAAA-MM-JJ HH:MM"...), datetime ou vide → datetime UTC ou None."""
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, str):
        valeur = datetime.fromisoformat(valeur.strip())
    if not isinstance(valeur, datetime):
        raise TypeError(f"date attendue, reçu {type(valeur).__name__}")
    if valeur.tzinfo is None:
        valeur = valeur.astimezone()   # naïve = heure locale
    return valeur.astimezone(timezone.utc)


def depuis_base(valeur: datetime | None) -> datetime | None:
    """Date relue en base → datetime UTC conscient du fuseau."""
    if valeur is None:
        return None
    if valeur.tzinfo is None:
        return valeur.replace(tzinfo=timezone.utc)
    return valeur.astimezone(timezone.utc)


def en_texte(valeur: datetime | None, fmt: str) -> str:
    """Date relue en base → chaîne en heure locale ("" si absente)."""
    dt = depuis_base(valeur)
    return dt.astimezone().strftime(fmt) if dt else ""
