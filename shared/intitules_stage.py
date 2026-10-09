"""
shared/intitules_stage.py
=========================
Mode stage, offres France Travail (décision D74) : l'intitulé doit montrer
que « stage » ou « stagiaire » désigne le poste. Règles dans
shared/referentiels/intitules_stage.txt, fichier de données à compléter :
une offre est gardée si une règle « + » la trouve et aucune règle « - ».
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

FICHIER = Path(__file__).resolve().parent / "referentiels" / "intitules_stage.txt"


@lru_cache(maxsize=1)
def regles() -> tuple[tuple[re.Pattern, ...], tuple[re.Pattern, ...]]:
    """(règles « + », règles « - ») du fichier, compilées."""
    garder, ecarter = [], []
    for ligne in FICHIER.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        signe, _, motif = ligne.partition(" ")
        if signe not in ("+", "-") or not motif.strip():
            raise ValueError(f"{FICHIER.name} : règle illisible « {ligne} »")
        (garder if signe == "+" else ecarter).append(re.compile(motif.strip()))
    return tuple(garder), tuple(ecarter)


def _simplifier(texte: str) -> str:
    """Minuscules, sans accents."""
    texte = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in texte if not unicodedata.combining(c)).lower()


def designe_un_stage(intitule: str) -> bool:
    """Vrai si l'intitulé désigne un poste de stage."""
    texte = _simplifier(intitule)
    garder, ecarter = regles()
    return any(r.search(texte) for r in garder) and not any(r.search(texte) for r in ecarter)
