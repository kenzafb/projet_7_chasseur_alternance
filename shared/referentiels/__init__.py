"""
shared/referentiels
===================
Référentiels officiels versionnés dans le dépôt, lus à la demande.

- France Travail : fichiers téléchargés par scripts/explorer_france_travail.py
  dans docs/referentiels/france_travail/ (avec leur date de téléchargement).
  Seuls les éléments {code, libelle} sont lus ; les libellés sont nettoyés
  (restes de code du référentiel : apostrophe initiale, « '); » final).
- grands_domaines.json (ce dossier) : les 14 grands domaines (lettres A à N),
  que l'API ne publie pas en référentiel ; libellés de SPEC_SOURCES.md 1.1.

Les listes de codes viennent toujours de ces fichiers, jamais du code.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from shared.config import BASE_DIR

DOSSIER_FRANCE_TRAVAIL = BASE_DIR / "docs" / "referentiels" / "france_travail"
DOSSIER_LOCAL = Path(__file__).resolve().parent


def nettoyer_libelle(libelle) -> str:
    """Libellé affichable : restes de code retirés, espaces normalisés.

    « 'Fabrication industrielle de pain');  » -> « Fabrication industrielle de pain »
    « en liège,à l'exception » -> « en liège, à l'exception »
    """
    texte = " ".join(str(libelle or "").split())
    entre_apostrophes = texte.startswith("'")
    texte = texte.removeprefix("'")
    for reste in ("');", "')", ");"):
        if texte.endswith(reste):
            texte = texte[: -len(reste)]
            entre_apostrophes = True
            break
    if entre_apostrophes:
        texte = texte.removesuffix("'")
    texte = re.sub(r",(?=[^\s\d])", ", ", texte)   # virgule collée au mot suivant
    return texte.strip()


def _lire(chemin: Path) -> list[dict]:
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    if isinstance(donnees, dict):
        donnees = donnees.get("donnees") or []
    return [{"code": str(d["code"]), "libelle": nettoyer_libelle(d.get("libelle"))}
            for d in donnees if isinstance(d, dict) and d.get("code")]


@lru_cache(maxsize=None)
def france_travail(nom: str) -> tuple[dict, ...]:
    """Éléments {code, libelle} d'un référentiel France Travail téléchargé
    (domaines, metiers, secteurs_activites, themes, nafs...)."""
    return tuple(_lire(DOSSIER_FRANCE_TRAVAIL / f"{nom}.json"))


@lru_cache(maxsize=None)
def local(nom: str) -> tuple[dict, ...]:
    """Éléments {code, libelle} d'un référentiel de ce dossier."""
    return tuple(_lire(DOSSIER_LOCAL / f"{nom}.json"))


def libelles(elements) -> dict[str, str]:
    """Code -> libellé."""
    return {e["code"]: e["libelle"] for e in elements}
