"""
scripts/audit_commun.py
=======================
Outils communs aux scripts d'audit de la phase 15 (scripts/audit_*.py et
scripts/banc_ia/). Aucun ne modifie l'application ni la base :

  - la base est ouverte en LECTURE SEULE (SQLite, mode=ro) ; --base pour
    une autre base que DATABASE_URL ;
  - les résultats sont écrits dans audit_exports/ (ignoré par git), un
    fichier JSON par mesure, horodaté, sans clé ni jeton.

Pour lancer un script sans charger le .env (base seulement, aucune API) :

    CHASSEUR_ENV_FILE=/dev/null venv/bin/python scripts/<script>.py --base sqlite:///data/chasseur_v2.db
"""

import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

SORTIE = RACINE / "audit_exports"
# Références annotées sans donnée personnelle, versionnées (ménage, D196)
REFERENCES = RACINE / "scripts" / "references"


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def url_lecture_seule(url: str) -> str:
    """sqlite:///chemin/base.db -> URL SQLite ouverte en lecture seule."""
    if not url.startswith("sqlite:///"):
        raise ValueError("Seule une base SQLite (sqlite:///...) est prise en charge en lecture seule.")
    chemin = url.removeprefix("sqlite:///")
    return f"sqlite:///file:{chemin}?mode=ro&uri=true"


def url_base(base: str | None) -> str:
    if base:
        return base
    from shared.config import DATABASE_URL
    return DATABASE_URL


@contextmanager
def session_lecture(base: str | None = None):
    """Session SQLAlchemy sur la base ouverte en lecture seule : toute
    écriture échoue (« attempt to write a readonly database »)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    moteur = create_engine(url_lecture_seule(url_base(base)))
    try:
        with Session(moteur) as db:
            yield db
            db.rollback()
    finally:
        moteur.dispose()


def ecrire_json(nom: str, donnees, sortie: Path | str | None = None) -> Path:
    """audit_exports/<nom>.json (dossier créé au besoin)."""
    dossier = Path(sortie) if sortie else SORTIE
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{nom}.json"
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return chemin


def lire_json(chemin) -> object:
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


class Chrono:
    def __init__(self):
        self.debut = time.monotonic()

    @property
    def s(self) -> float:
        return round(time.monotonic() - self.debut, 2)


def pourcentage(n: int, total: int) -> str:
    return f"{n}/{total} ({100 * n / total:.1f} %)" if total else f"{n}/0"


# Liste d'avant D156 (offres.analyse.ECOLES_MOTS_CLES), sous-chaînes : pour
# mesurer avant et après
ANCIENS_MOTS_ECOLE = [
    "iscod", "scholia", "imc alternance", "mydigitalschool", "simplon",
    "afpa", "cfa", "epitech", "openclassrooms", "studi", "ikigai",
    "la plateforme", "digital campus", "m2i", "doranco", "efficom",
    "ecole", "organisme de formation", "centre de formation",
    "hitema", "h3", "igs", "isefac", "sup de vinci",
    "aureis", "nexa", "Groupe IGF",
]


def _champs(offre: dict) -> dict:
    return {"titre": offre.get("titre"), "entreprise": offre.get("entreprise"),
            "description": offre.get("description")}


def mots_ecole_trouves(offre: dict) -> list[str]:
    """Mots de l'ancienne liste qui archivaient l'offre avant D156, avec le
    champ : « cfa@description »."""
    return [f"{m}@{c}" for m in ANCIENS_MOTS_ECOLE for c, t in _champs(offre).items() if m in (t or "").lower()]


def organismes_trouves(offre: dict) -> list[str]:
    """Organismes vérifiés (D156) qui archivent l'offre aujourd'hui, avec le champ."""
    from shared.marques import liste, simplifier
    return [f"{nom}@{c}" for nom, motif in liste()[0] for c, t in _champs(offre).items()
            if motif.search(simplifier(t))]
