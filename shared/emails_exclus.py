"""
shared/emails_exclus.py
=======================
Adresses email techniques ou factices (suivi d'erreurs, gabarits de site,
exemples de formulaire), jamais enregistrées ni gardées par le scraper
(décision D47). Règles dans shared/referentiels/emails_exclus.txt, fichier
de données à compléter sans toucher au code :
  @domaine       domaine et ses sous-domaines
  local@         partie locale, sur tout domaine
  local@domaine  adresse exacte
"""

from functools import lru_cache
from pathlib import Path

FICHIER = Path(__file__).resolve().parent / "referentiels" / "emails_exclus.txt"


@lru_cache(maxsize=1)
def regles() -> tuple[frozenset, frozenset, frozenset]:
    """(domaines, parties locales, adresses exactes) du fichier."""
    domaines, locales, adresses = set(), set(), set()
    for ligne in FICHIER.read_text(encoding="utf-8").splitlines():
        regle = ligne.split("#", 1)[0].strip().lower()
        if not regle or "@" not in regle:
            continue
        local, _, domaine = regle.partition("@")
        if not local:
            domaines.add(domaine)
        elif not domaine:
            locales.add(local)
        else:
            adresses.add(regle)
    return frozenset(domaines), frozenset(locales), frozenset(adresses)


def email_exclu(email) -> bool:
    """Vrai si l'adresse est technique ou factice d'après le fichier de règles."""
    email = str(email or "").strip().lower()
    local, _, domaine = email.rpartition("@")
    if not local or not domaine:
        return False
    domaines, locales, adresses = regles()
    if email in adresses or local in locales:
        return True
    parties = domaine.split(".")
    return any(".".join(parties[i:]) in domaines for i in range(len(parties) - 1))


def filtrer(emails) -> list:
    """Emails gardés, dans l'ordre, sans les adresses exclues."""
    return [e for e in (emails or []) if not email_exclu(e)]
