"""
database/connexion.py
=====================
Moteur de base de données + session.

Aujourd'hui : SQLite (fichier local data/chasseur.db).
Le jour du déploiement : il suffira de changer DATABASE_URL
(ex. PostgreSQL sur Railway) — tout le reste du code ne bouge pas.
C'est tout l'intérêt de SQLAlchemy.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base
# shared.config charge le .env : DATABASE_URL y est surchargeable
# (ce qui permettra de basculer sur PostgreSQL sans toucher au code).
from shared.config import DATABASE_URL

# check_same_thread=False : nécessaire car FastAPI peut accéder à la base
# depuis plusieurs threads (tes pipelines tournent en threads).
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def creer_tables():
    """Crée toutes les tables définies dans models.py si elles n'existent pas."""
    Base.metadata.create_all(bind=engine)


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
