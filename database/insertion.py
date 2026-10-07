"""
database/insertion.py
=====================
Insertion idempotente : une ligne qui violerait une contrainte d'unicité
est ignorée sans erreur (INSERT ... ON CONFLICT DO NOTHING), y compris
quand deux threads insèrent la même ligne au même moment.
"""

from sqlalchemy.dialects import postgresql, sqlite

TAILLE_PAQUET = 500


def insert_du_dialecte(db):
    """insert() de SQLite ou de PostgreSQL : celui qui connaît ON CONFLICT."""
    dialecte = db.get_bind().dialect.name
    if dialecte == "sqlite":
        return sqlite.insert
    if dialecte == "postgresql":
        return postgresql.insert
    raise NotImplementedError(f"insertion idempotente non prévue pour {dialecte}")


def inserer_ou_ignorer(db, modele, lignes: list[dict], cles: list[str]) -> int:
    """Insère `lignes` dans la table de `modele`, ignore celles dont les
    colonnes `cles` (une contrainte UNIQUE) existent déjà. Ne valide pas la
    transaction. Retourne le nombre de lignes réellement insérées."""
    if not lignes:
        return 0
    insert = insert_du_dialecte(db)
    inserees = 0
    # Par paquets : SQLite limite le nombre de paramètres d'une requête
    for debut in range(0, len(lignes), TAILLE_PAQUET):
        paquet = lignes[debut:debut + TAILLE_PAQUET]
        requete = insert(modele).values(paquet).on_conflict_do_nothing(index_elements=cles)
        inserees += db.execute(requete).rowcount or 0
    return inserees
