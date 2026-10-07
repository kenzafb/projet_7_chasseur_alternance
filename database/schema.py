"""
database/schema.py
==================
Création et mise à jour du schéma par Alembic, depuis Python.
Équivaut à `alembic upgrade head` lancé à la racine du projet.
"""

from alembic import command
from alembic.config import Config

from shared.config import BASE_DIR


def config_alembic(database_url: str | None = None) -> Config:
    """Config Alembic du projet. database_url : base visée (défaut : DATABASE_URL)."""
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.attributes["configurer_logs"] = False
    if database_url:
        cfg.attributes["database_url"] = database_url
    return cfg


def migrer(database_url: str | None = None):
    """alembic upgrade head sur la base visée."""
    command.upgrade(config_alembic(database_url), "head")
