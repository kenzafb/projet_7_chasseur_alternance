"""Campagnes automatiques d'entreprises à contacter (D213) : état, bilan et
journal de chaque lancement.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-25 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0019'
down_revision: Union[str, Sequence[str], None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crée la table campagnes (vide)."""
    op.create_table(
        'campagnes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('debut', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fin', sa.DateTime(timezone=True), nullable=True),
        sa.Column('etat', sa.String(length=20), server_default='en_cours', nullable=False),
        sa.Column('bilan', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column('journal', sa.Text(), server_default='', nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('campagnes', schema=None) as batch_op:
        batch_op.create_index('ix_campagnes_user_id', ['user_id'], unique=False)


def downgrade() -> None:
    """Retire la table campagnes."""
    op.drop_table('campagnes')
