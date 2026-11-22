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


def mots_ecole_trouves(offre: dict) -> list[str]:
    """Mots-clés d'école ou de CFA (offres.analyse.ECOLES_MOTS_CLES) que
    est_ecole_cfa trouve dans l'offre, avec le champ : « cfa@description »."""
    from offres.analyse import ECOLES_MOTS_CLES
    champs = {"titre": offre.get("titre"), "entreprise": offre.get("entreprise"),
              "description": offre.get("description")}
    return [f"{m}@{c}" for m in ECOLES_MOTS_CLES for c, t in champs.items() if m in (t or "").lower()]
