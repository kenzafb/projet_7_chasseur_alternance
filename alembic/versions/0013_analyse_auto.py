"""Option du profil « analyser automatiquement après chaque recherche »
(phase 7) : profils.analyse_auto, faux pour les profils existants.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute l'option d'analyse automatique, coupée."""
    with op.batch_alter_table('profils', schema=None) as batch_op:
        batch_op.add_column(sa.Column('analyse_auto', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Retire l'option d'analyse automatique."""
    with op.batch_alter_table('profils', schema=None) as batch_op:
        batch_op.drop_column('analyse_auto')
