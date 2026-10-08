"""
shared/naf.py
=============
Codes NAF cherchés sur Sirene pour un profil (SPEC_SOURCES section 4.1).

- Domaines avec une correspondance (shared/referentiels/correspondance_naf.json,
  fichier de données versionné) : secteurs cœurs, toutes tailles, et
  secteurs transverses, seulement pour les unités légales de 250 salariés
  et plus.
- Profil « indifférent », ou domaine sans correspondance : secteurs choisis
  directement dans le profil (divisions NAF à deux chiffres, les mêmes que
  le filtre « secteur de l'employeur » de France Travail), toutes leurs
  sous-classes, mêmes tailles que les cœurs.
- Exclusions systématiques (supports juridiques 68.32B, 41.10D, 66.19A,
  sans salarié), quelle que soit l'origine du code.

Chaque code existe en NAF rév. 2 et en NAF 2025 (table officielle de
l'INSEE, docs/referentiels/insee/correspondance_naf_rev2_naf2025.csv) ; la
nomenclature employée suit shared.config.nomenclature_naf.
"""

import csv
import json
from functools import lru_cache
from pathlib import Path

from shared import referentiels
from shared.config import BASE_DIR, nomenclature_naf
from shared.domaines import domaines_du_grand_domaine, est_grand_domaine, normaliser_domaines

FICHIER = Path(__file__).resolve().parent / "referentiels" / "correspondance_naf.json"
TABLE_INSEE = BASE_DIR / "docs" / "referentiels" / "insee" / "correspondance_naf_rev2_naf2025.csv"


@lru_cache(maxsize=1)
def correspondance() -> dict:
    return json.loads(FICHIER.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def table_insee() -> dict[str, tuple[str, ...]]:
    """Code NAF rév. 2 -> codes NAF 2025 de la table officielle (toutes cibles)."""
    table = {}
    with open(TABLE_INSEE, encoding="utf-8") as f:
        for ligne in csv.DictReader(f):
            table.setdefault(ligne["naf_rev2"], [])
            if ligne["naf_2025"] not in table[ligne["naf_rev2"]]:
                table[ligne["naf_rev2"]].append(ligne["naf_2025"])
    return {k: tuple(v) for k, v in table.items()}


def _codes(entree: dict, nomenclature: str) -> list[str]:
    return [entree["naf_rev2"]] if nomenclature == "NAFRev2" else list(entree["retenus_2025"])


def exclusions(nomenclature: str) -> set[str]:
    return {c for e in correspondance()["exclusions"] for c in _codes(e, nomenclature)}


def codes_division(division: str, nomenclature: str) -> list[str]:
    """Sous-classes d'une division NAF rév. 2 (« 62 »), dans la nomenclature
    demandée ; en NAF 2025, toutes les cibles officielles de ces
    sous-classes (une division a pu être répartie entre plusieurs)."""
    rev2 = [c for c in table_insee() if c.startswith(f"{division}.")]
    if nomenclature == "NAFRev2":
        return rev2
    return list(dict.fromkeys(c for code in rev2 for c in table_insee()[code]))


def domaines_couverts() -> set[str]:
    return set(correspondance()["domaines"])


def _domaines_cherches(code: str) -> list[str]:
    """Domaines d'un code du profil qui ont une correspondance."""
    if est_grand_domaine(code):
        return [d for d in domaines_du_grand_domaine(code) if d in domaines_couverts()]
    return [code] if code in domaines_couverts() else []


def domaines_sans_correspondance(codes) -> list[str]:
    """Codes du profil pas entièrement couverts par la correspondance : un
    domaine sans entrée, un grand domaine dont un domaine au moins n'en a pas."""
    manquants = []
    for c in normaliser_domaines(codes):
        sous = domaines_du_grand_domaine(c) if est_grand_domaine(c) else [c]
        if any(d not in domaines_couverts() for d in sous):
            manquants.append(c)
    return manquants


def _uniques(codes) -> list[str]:
    return list(dict.fromkeys(codes))


def secteurs_sirene(domaines, secteurs=(), nomenclature: str | None = None) -> dict:
    """Codes à chercher : {nomenclature, coeurs, transverses, secteurs,
    sans_correspondance, secteurs_requis}. secteurs (divisions) ne servent
    que pour un profil indifférent ou un domaine sans correspondance."""
    nomenclature = nomenclature or nomenclature_naf()
    exclus = exclusions(nomenclature)
    domaines = normaliser_domaines(domaines)
    table = correspondance()["domaines"]
    coeurs, transverses = [], []
    for code in domaines:
        for d in _domaines_cherches(code):
            coeurs += [c for e in table[d]["coeurs"] for c in _codes(e, nomenclature)]
            transverses += [c for e in table[d]["transverses"] for c in _codes(e, nomenclature)]
    manquants = domaines_sans_correspondance(domaines)
    requis = not domaines or bool(manquants)
    divisions = [d for d in (secteurs or []) if requis]
    par_secteurs = [c for d in divisions for c in codes_division(d, nomenclature)]
    coeurs = [c for c in _uniques(coeurs) if c not in exclus]
    par_secteurs = [c for c in _uniques(par_secteurs) if c not in exclus and c not in coeurs]
    # Un code déjà cherché toutes tailles n'a pas à l'être pour les grandes seulement
    transverses = [c for c in _uniques(transverses) if c not in exclus and c not in coeurs + par_secteurs]
    return {"nomenclature": nomenclature, "coeurs": coeurs, "transverses": transverses,
            "secteurs": par_secteurs, "divisions": divisions, "sans_correspondance": manquants,
            "secteurs_requis": requis}


def _libelle(code: str) -> str:
    libelles = {g["code"]: g["libelle"] for g in referentiels.local("grands_domaines")}
    libelles.update({d["code"]: d["libelle"] for d in referentiels.france_travail("domaines")})
    return f"{libelles.get(code, code)} ({code})"


def avertissement_sirene(domaines, secteurs=()) -> str:
    """Message pour l'interface au lancement de « Récupérer », vide si rien à dire."""
    domaines = normaliser_domaines(domaines)
    manquants = domaines_sans_correspondance(domaines)
    if not domaines and not secteurs:
        return ("Aucun domaine ni secteur choisi : Sirene n'est pas interrogé. Choisis des domaines, "
                "ou des secteurs d'entreprise, dans le profil.")
    if manquants and not secteurs:
        return (f"Domaines sans correspondance NAF pour Sirene : {', '.join(map(_libelle, manquants))} ; "
                "choisis des secteurs d'entreprise dans le profil pour les y chercher.")
    if manquants:
        return (f"Domaines sans correspondance NAF pour Sirene : {', '.join(map(_libelle, manquants))} ; "
                "cherchés par les secteurs d'entreprise choisis.")
    return ""
