"""Source des entreprises des candidatures spontanées : entreprises.source
(phase 5c), « sirene » ou « lba » (entreprises à fort potentiel de La
Bonne Alternance, traitées et affichées en priorité). Les entreprises
existantes viennent toutes de Sirene.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute entreprises.source, « sirene » pour les entreprises existantes."""
    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=20), server_default='sirene', nullable=False))


def downgrade() -> None:
    """Retire entreprises.source (les entreprises LBA restent, sans leur source)."""
    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.drop_column('source')
