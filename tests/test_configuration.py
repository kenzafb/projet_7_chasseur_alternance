"""Configuration des dossiers et de la base (audit phase 12, lot 7, D139) :
lue au démarrage, dans un processus neuf, sans le vrai .env."""

import json
import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _config(**env):
    """Valeurs de shared.config dans un processus neuf, avec env seulement."""
    base = {k: v for k, v in os.environ.items()
            if k not in ("DATABASE_URL", "DATA_DIR", "UPLOADS_DIR", "LETTRES_PDF_DIR")}
    base.update(CHASSEUR_ENV_FILE=str(RACINE / "absent.env"), PYTHONDONTWRITEBYTECODE="1", **env)
    code = ("import json; from shared import config; print(json.dumps({'data': str(config.DATA_DIR), "
            "'uploads': str(config.UPLOADS_DIR), 'pdf': str(config.LETTRES_PDF_DIR), 'db': config.DATABASE_URL}))")
    r = subprocess.run([sys.executable, "-c", code], cwd=RACINE, env=base, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_defauts():
    c = _config()
    assert c == {"data": str(RACINE / "data"), "uploads": str(RACINE / "data" / "uploads"),
                 "pdf": str(RACINE / "lettres_pdf"), "db": f"sqlite:///{RACINE / 'data' / 'chasseur_v2.db'}"}
    assert "chasseur.db" not in c["db"].replace("chasseur_v2.db", "")   # jamais l'ancienne base


def test_dossiers_reglables(tmp_path):
    c = _config(DATA_DIR=str(tmp_path / "donnees"), LETTRES_PDF_DIR="pdf_local")
    assert c["data"] == str(tmp_path / "donnees")
    assert c["uploads"] == str(tmp_path / "donnees" / "uploads")          # suit DATA_DIR
    assert c["pdf"] == str(RACINE / "pdf_local")                          # relatif : depuis le projet
    assert c["db"] == f"sqlite:///{tmp_path / 'donnees' / 'chasseur_v2.db'}"
    c = _config(DATA_DIR=str(tmp_path), UPLOADS_DIR=str(tmp_path / "pj"), DATABASE_URL="sqlite:////ailleurs/b.db")
    assert c["uploads"] == str(tmp_path / "pj") and c["db"] == "sqlite:////ailleurs/b.db"
    assert _config(DATA_DIR="  ")["data"] == str(RACINE / "data")       # vide : défaut


def test_variables_documentees():
    texte = (RACINE / ".env.example").read_text(encoding="utf-8")
    for variable in ("DATA_DIR", "UPLOADS_DIR", "LETTRES_PDF_DIR", "DATABASE_URL"):
        assert f"\n{variable}=" in texte
