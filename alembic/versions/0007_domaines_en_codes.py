"""Domaines du profil en codes France Travail (phase 5b) : dans
profils.recherche.domaines, « informatique » devient M18 et « immobilier »
devient C15. Pas de changement de schéma, seulement des données.

Retour arrière : M18 et C15 reprennent leur ancienne clé ; les autres codes,
qui n'existaient pas avant, sont retirés.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Figé ici : la migration ne dépend pas du code de l'application
ANCIENNES_CLES = {"informatique": "M18", "immobilier": "C15"}

profils = sa.table("profils", sa.column("id", sa.Integer), sa.column("recherche", sa.JSON))


def _convertir(convertir) -> None:
    cx = op.get_bind()
    for id_, recherche in cx.execute(sa.select(profils.c.id, profils.c.recherche)).all():
        if not isinstance(recherche, dict) or not isinstance(recherche.get("domaines"), list):
            continue
        domaines = []
        for d in recherche["domaines"]:
            d = convertir(d)
            if d is not None and d not in domaines:
                domaines.append(d)
        if domaines != recherche["domaines"]:
            cx.execute(profils.update().where(profils.c.id == id_)
                       .values(recherche={**recherche, "domaines": domaines}))


def upgrade() -> None:
    _convertir(lambda d: ANCIENNES_CLES.get(d, d))


def downgrade() -> None:
    inverse = {v: k for k, v in ANCIENNES_CLES.items()}
    _convertir(lambda d: inverse.get(d))
