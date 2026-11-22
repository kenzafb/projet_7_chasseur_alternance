"""Marques des offres (phase 15, D154) : candidatures.marques, liste JSON de
clés (shared.marques : niveau_different, organisme_formation), vide par
défaut ; les lignes existantes ne sont pas touchées.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-22 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0017'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute marques (vide)."""
    with op.batch_alter_table('candidatures', schema=None) as batch_op:
        batch_op.add_column(sa.Column('marques', sa.JSON(), server_default=sa.text("'[]'"), nullable=False))


def downgrade() -> None:
    """Retire marques."""
    with op.batch_alter_table('candidatures', schema=None) as batch_op:
        batch_op.drop_column('marques')
