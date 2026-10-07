"""Colonne candidatures.lettre_pdf : chemin de la dernière lettre PDF générée
(relatif à LETTRES_PDF_DIR), servie par une route qui vérifie le propriétaire
(phase 2b).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08 00:56:11.994387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute candidatures.lettre_pdf (NULL pour les lignes existantes, lu comme vide)."""
    with op.batch_alter_table('candidatures', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lettre_pdf', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Retire candidatures.lettre_pdf (les fichiers restent sur le disque)."""
    with op.batch_alter_table('candidatures', schema=None) as batch_op:
        batch_op.drop_column('lettre_pdf')
