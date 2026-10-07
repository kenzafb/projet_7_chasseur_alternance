"""Compte d'envoi par utilisateur (SMTP, mot de passe chiffré) et compteur
de mails envoyés par utilisateur et par jour (phase 3).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08 01:20:20.937003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crée comptes_envoi et compteurs_envoi (vides : chacun configure son compte)."""
    op.create_table('comptes_envoi',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('adresse', sa.String(length=255), nullable=False),
    sa.Column('nom_affiche', sa.String(length=150), nullable=True),
    sa.Column('preset', sa.String(length=20), nullable=False),
    sa.Column('serveur', sa.String(length=255), nullable=False),
    sa.Column('port', sa.Integer(), nullable=False),
    sa.Column('chiffrement', sa.String(length=10), nullable=False),
    sa.Column('identifiant', sa.String(length=255), nullable=False),
    sa.Column('mot_de_passe_chiffre', sa.Text(), nullable=False),
    sa.Column('verifie_le', sa.DateTime(timezone=True), nullable=True),
    sa.Column('modifie_le', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_comptes_envoi_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_comptes_envoi')),
    sa.UniqueConstraint('user_id', name=op.f('uq_comptes_envoi_user_id'))
    )
    op.create_table('compteurs_envoi',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('jour', sa.Date(), nullable=False),
    sa.Column('nombre', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_compteurs_envoi_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_compteurs_envoi')),
    sa.UniqueConstraint('user_id', 'jour', name=op.f('uq_compteurs_envoi_user_id_jour'))
    )


def downgrade() -> None:
    """Supprime les deux tables (les comptes configurés sont perdus)."""
    op.drop_table('compteurs_envoi')
    op.drop_table('comptes_envoi')
