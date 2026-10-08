"""Sources des entreprises en liste : entreprises.sources remplace
entreprises.source (suite de la phase 5c, décision D44). Une entreprise
trouvée par Sirene et par La Bonne Alternance garde la trace des deux.
Les entreprises existantes reçoivent leur source d'avant ; une entreprise
passée de Sirene à « lba » (ancienne règle de priorité) ne garde que
« lba », sa première source n'ayant pas été notée.

Retour arrière : « lba » si la liste le contient, sinon « sirene ».

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

entreprises = sa.table("entreprises", sa.column("id", sa.Integer), sa.column("source", sa.String),
                       sa.column("sources", sa.JSON))


def upgrade() -> None:
    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sources', sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    cx = op.get_bind()
    for id_, source in cx.execute(sa.select(entreprises.c.id, entreprises.c.source)).all():
        cx.execute(entreprises.update().where(entreprises.c.id == id_).values(sources=[source or "sirene"]))
    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.drop_column('source')


def downgrade() -> None:
    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=20), server_default='sirene', nullable=False))
    cx = op.get_bind()
    for id_, sources in cx.execute(sa.select(entreprises.c.id, entreprises.c.sources)).all():
        cx.execute(entreprises.update().where(entreprises.c.id == id_)
                   .values(source="lba" if "lba" in (sources or []) else "sirene"))
    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.drop_column('sources')
