"""
database/connexion.py
=====================
Moteur de base de données + session.

Aujourd'hui : SQLite (fichier local data/chasseur.db).
Le schéma est créé et mis à jour par Alembic (alembic upgrade head),
jamais par ce module.
Le jour du déploiement : il suffira de changer DATABASE_URL
(ex. PostgreSQL sur Railway) — tout le reste du code ne bouge pas.
C'est tout l'intérêt de SQLAlchemy.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
# shared.config charge le .env : DATABASE_URL y est surchargeable
# (ce qui permettra de basculer sur PostgreSQL sans toucher au code).
from shared.config import DATABASE_URL

def creer_moteur(url: str):
    """Moteur SQLAlchemy pour `url`. Sert à l'app, à Alembic et au script d'import."""
    if not url.startswith("sqlite"):
        return create_engine(url)
    # check_same_thread=False : nécessaire car FastAPI peut accéder à la base
    # depuis plusieurs threads (les pipelines tournent en threads).
    moteur = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(moteur, "connect")
    def _activer_cles_etrangeres(connexion_dbapi, _):
        """SQLite n'applique les clés étrangères (et ON DELETE CASCADE)
        que si on le lui demande, à chaque connexion."""
        connexion_dbapi.execute("PRAGMA foreign_keys=ON")

    return moteur


engine = creer_moteur(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session():
    """
    Fournit une session de base de données, à utiliser puis fermer.
    Dans FastAPI on s'en servira via Depends ; en script direct, en context manager.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
