"""
Environnement Alembic du projet.

URL de la base : DATABASE_URL lue par shared/config.py (donc le .env).
Un appel programmatique peut viser une autre base en posant
config.attributes["database_url"] (script d'import, tests).

Schéma cible : database/models.py (Base.metadata), seule source de vérité.
render_as_batch=True : SQLite ne sait pas modifier une colonne ou une
contrainte en place ; Alembic recrée alors la table (mode batch).
"""

from logging.config import fileConfig

from alembic import context

from database.connexion import creer_moteur
from database.models import Base
from shared.config import DATABASE_URL

config = context.config

# Pas de reconfiguration des logs quand Alembic est appelé depuis Python
# (tests, script d'import) : on ne touche qu'aux logs de la ligne de commande.
if config.config_file_name is not None and config.attributes.get("configurer_logs", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
url = config.attributes.get("database_url") or DATABASE_URL


def run_migrations_offline() -> None:
    """Génère le SQL sans se connecter (alembic upgrade head --sql)."""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    moteur = creer_moteur(url)
    with moteur.connect() as connexion:
        context.configure(
            connection=connexion,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    moteur.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
