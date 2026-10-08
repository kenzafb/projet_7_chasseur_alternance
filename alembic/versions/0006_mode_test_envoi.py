"""Mode test du compte d'envoi : comptes_envoi.mode_test (phase 4). En mode
test, les candidatures spontanées partent vers l'adresse d'expédition de
l'utilisateur et rien n'est enregistré comme contacté. Les comptes
existants restent en envoi réel.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute comptes_envoi.mode_test, faux pour les comptes existants."""
    with op.batch_alter_table('comptes_envoi', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mode_test', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Retire comptes_envoi.mode_test."""
    with op.batch_alter_table('comptes_envoi', schema=None) as batch_op:
        batch_op.drop_column('mode_test')
