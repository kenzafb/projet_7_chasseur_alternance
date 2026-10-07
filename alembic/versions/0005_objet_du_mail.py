"""Colonne profils.email_objet : objet du mail de candidature spontanée, par
profil donc par mode (phase 3). Vide : objet par défaut du mode.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08 01:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute profils.email_objet (NULL pour les profils existants, lu comme vide)."""
    with op.batch_alter_table('profils', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_objet', sa.String(length=300), nullable=True))


def downgrade() -> None:
    """Retire profils.email_objet."""
    with op.batch_alter_table('profils', schema=None) as batch_op:
        batch_op.drop_column('email_objet')
