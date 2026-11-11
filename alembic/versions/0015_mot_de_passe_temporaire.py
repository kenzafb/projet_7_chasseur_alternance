"""Mot de passe temporaire (phase 10, D123) : users.mot_de_passe_temporaire,
faux pour les comptes existants. Vrai après
scripts/reinitialiser_mot_de_passe.py, jusqu'au changement de mot de passe.

Retour arrière : la colonne disparaît (un mot de passe temporaire en cours
devient un mot de passe ordinaire).

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Pas de batch_alter_table ici : sur SQLite, il recrée la table users, et
# la suppression de l'ancienne efface en cascade (ON DELETE CASCADE, clés
# étrangères actives) profils, candidatures, entreprises... de chaque compte.
# ADD COLUMN et DROP COLUMN (SQLite 3.35 et plus) modifient la table en place.


def upgrade() -> None:
    """Ajoute l'indicateur, faux pour tous les comptes existants."""
    op.add_column('users', sa.Column('mot_de_passe_temporaire', sa.Boolean(), server_default=sa.false(),
                                     nullable=False))


def downgrade() -> None:
    """Retire l'indicateur."""
    op.drop_column('users', 'mot_de_passe_temporaire')
