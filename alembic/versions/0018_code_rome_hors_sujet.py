"""Offres : code métier ROME donné par France Travail (candidatures.code_rome,
D203) et phrase du profil citée par l'IA pour un hors sujet
(candidatures.hors_sujet_car, D205) ; vides pour les lignes existantes.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-25 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0018'
down_revision: Union[str, Sequence[str], None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute code_rome et hors_sujet_car (vides)."""
    with op.batch_alter_table('candidatures', schema=None) as batch_op:
        batch_op.add_column(sa.Column('code_rome', sa.String(length=5), server_default='', nullable=False))
        batch_op.add_column(sa.Column('hors_sujet_car', sa.Text(), server_default='', nullable=False))


def downgrade() -> None:
    """Retire code_rome et hors_sujet_car."""
    with op.batch_alter_table('candidatures', schema=None) as batch_op:
        batch_op.drop_column('hors_sujet_car')
        batch_op.drop_column('code_rome')
