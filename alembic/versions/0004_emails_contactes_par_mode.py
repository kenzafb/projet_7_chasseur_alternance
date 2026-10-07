"""Adresses contactées par mode : emails_contactes reçoit une colonne mode et
l'unicité passe de (user_id, email) à (user_id, mode, email) (phase 3).
Les lignes existantes, toutes issues du pipeline d'alternance, prennent le
mode « alternance ».

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08 01:29:45.930784

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute mode (défaut alternance) et change la contrainte d'unicité."""
    with op.batch_alter_table('emails_contactes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mode', sa.String(length=20), server_default='alternance', nullable=False))
        batch_op.drop_constraint(batch_op.f('uq_emails_contactes_user_id_email'), type_='unique')
        batch_op.create_unique_constraint(batch_op.f('uq_emails_contactes_user_id_mode_email'), ['user_id', 'mode', 'email'])


def downgrade() -> None:
    """Revient à une adresse par utilisateur, tous modes confondus : seule la
    plus ancienne ligne de chaque (user_id, email) est gardée."""
    op.execute(
        "DELETE FROM emails_contactes WHERE id NOT IN "
        "(SELECT MIN(id) FROM emails_contactes GROUP BY user_id, email)")
    with op.batch_alter_table('emails_contactes', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_emails_contactes_user_id_mode_email'), type_='unique')
        batch_op.create_unique_constraint(batch_op.f('uq_emails_contactes_user_id_email'), ['user_id', 'email'])
        batch_op.drop_column('mode')
