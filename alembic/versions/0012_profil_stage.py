"""Profil du mode stage (phase 6b) : dates de début et de fin du stage,
établissement, missions visées, lien vers un portfolio. La formation
utilise la colonne commune profils.formation. Colonnes vides (NULL) pour
les profils existants, lues comme vides.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-09 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute les champs du profil de stage."""
    with op.batch_alter_table('profils', schema=None) as batch_op:
        batch_op.add_column(sa.Column('date_debut', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('date_fin', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('etablissement', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('missions', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('portfolio', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Retire les champs du profil de stage."""
    with op.batch_alter_table('profils', schema=None) as batch_op:
        batch_op.drop_column('portfolio')
        batch_op.drop_column('missions')
        batch_op.drop_column('etablissement')
        batch_op.drop_column('date_fin')
        batch_op.drop_column('date_debut')
