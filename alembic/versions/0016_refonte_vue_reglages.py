"""Refonte de l'interface (phase 14, D145) : candidatures.vue (offre ouverte
au moins une fois, vrai pour les offres existantes) et profils.reglages
(réglages avancés du mode, vides : défauts de la configuration).

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute vue (offres existantes : déjà vues, sinon tout l'historique
    paraîtrait nouveau) et reglages (vides)."""
    with op.batch_alter_table('candidatures', schema=None) as batch_op:
        batch_op.add_column(sa.Column('vue', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute("UPDATE candidatures SET vue = 1")
    with op.batch_alter_table('profils', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reglages', sa.JSON(), server_default=sa.text("'{}'"), nullable=False))


def downgrade() -> None:
    """Retire reglages et vue."""
    with op.batch_alter_table('profils', schema=None) as batch_op:
        batch_op.drop_column('reglages')
    with op.batch_alter_table('candidatures', schema=None) as batch_op:
        batch_op.drop_column('vue')
