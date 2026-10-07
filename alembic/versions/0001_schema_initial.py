"""Schéma initial : users, profils, candidatures, entreprises, offres_vues,
emails_contactes, tel que décrit par database/models.py (phase 2a).

Revision ID: 0001
Revises: 
Create Date: 2026-10-08 00:34:09.527234

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crée tout le schéma."""
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('mot_de_passe_hash', sa.String(length=255), nullable=False),
    sa.Column('cree_le', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    op.create_table('candidatures',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.String(length=20), server_default='alternance', nullable=False),
    sa.Column('ref_offre', sa.String(length=64), nullable=False),
    sa.Column('titre', sa.String(length=300), nullable=True),
    sa.Column('entreprise', sa.String(length=300), nullable=True),
    sa.Column('lieu', sa.String(length=200), nullable=True),
    sa.Column('zone', sa.String(length=100), nullable=True),
    sa.Column('domaine', sa.String(length=100), nullable=True),
    sa.Column('lien', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=100), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('score', sa.Integer(), nullable=True),
    sa.Column('verdict', sa.String(length=50), nullable=True),
    sa.Column('eligible', sa.Boolean(), nullable=True),
    sa.Column('points_forts', sa.JSON(), nullable=True),
    sa.Column('points_faibles', sa.JSON(), nullable=True),
    sa.Column('resume_analyse', sa.Text(), nullable=True),
    sa.Column('lettre', sa.Text(), nullable=True),
    sa.Column('email_candidature', sa.String(length=255), nullable=True),
    sa.Column('objet_email', sa.String(length=300), nullable=True),
    sa.Column('statut', sa.String(length=50), nullable=True),
    sa.Column('raison_archivage', sa.String(length=40), nullable=True),
    sa.Column('date_trouvee', sa.DateTime(timezone=True), nullable=True),
    sa.Column('date_candidature', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_candidatures_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_candidatures')),
    sa.UniqueConstraint('user_id', 'mode', 'ref_offre', name=op.f('uq_candidatures_user_id_mode_ref_offre'))
    )
    with op.batch_alter_table('candidatures', schema=None) as batch_op:
        batch_op.create_index('ix_candidatures_user_id_mode', ['user_id', 'mode'], unique=False)

    op.create_table('emails_contactes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('contacte_le', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_emails_contactes_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_emails_contactes')),
    sa.UniqueConstraint('user_id', 'email', name=op.f('uq_emails_contactes_user_id_email'))
    )
    op.create_table('entreprises',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.String(length=20), server_default='alternance', nullable=False),
    sa.Column('nom_commercial', sa.String(length=300), nullable=True),
    sa.Column('ville', sa.String(length=150), nullable=True),
    sa.Column('code_postal', sa.String(length=10), nullable=True),
    sa.Column('siren', sa.String(length=20), nullable=True),
    sa.Column('site_web', sa.Text(), nullable=True),
    sa.Column('secteur', sa.String(length=200), nullable=True),
    sa.Column('emails_trouves', sa.JSON(), nullable=True),
    sa.Column('telephones', sa.JSON(), nullable=True),
    sa.Column('contact_rh', sa.String(length=200), nullable=True),
    sa.Column('traite', sa.Boolean(), nullable=True),
    sa.Column('mail_envoye', sa.Boolean(), nullable=True),
    sa.Column('mail_envoye_le', sa.DateTime(timezone=True), nullable=True),
    sa.Column('statut_suivi', sa.String(length=30), nullable=True),
    sa.Column('extra', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_entreprises_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_entreprises'))
    )
    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_entreprises_siren'), ['siren'], unique=False)
        batch_op.create_index(batch_op.f('ix_entreprises_user_id'), ['user_id'], unique=False)

    op.create_table('offres_vues',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.String(length=20), server_default='alternance', nullable=False),
    sa.Column('ref_offre', sa.String(length=64), nullable=False),
    sa.Column('vue_le', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_offres_vues_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_offres_vues')),
    sa.UniqueConstraint('user_id', 'mode', 'ref_offre', name=op.f('uq_offres_vues_user_id_mode_ref_offre'))
    )
    op.create_table('profils',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.String(length=20), server_default='alternance', nullable=False),
    sa.Column('prenom', sa.String(length=100), nullable=True),
    sa.Column('nom', sa.String(length=100), nullable=True),
    sa.Column('email_contact', sa.String(length=255), nullable=True),
    sa.Column('telephone', sa.String(length=50), nullable=True),
    sa.Column('ville', sa.String(length=150), nullable=True),
    sa.Column('linkedin', sa.String(length=255), nullable=True),
    sa.Column('github', sa.String(length=255), nullable=True),
    sa.Column('formation', sa.Text(), nullable=True),
    sa.Column('experience', sa.Text(), nullable=True),
    sa.Column('langues', sa.Text(), nullable=True),
    sa.Column('disponibilite', sa.Text(), nullable=True),
    sa.Column('paragraphe_perso', sa.Text(), nullable=True),
    sa.Column('niveau_vise', sa.Text(), nullable=True),
    sa.Column('formation_apporte', sa.Text(), nullable=True),
    sa.Column('criteres_eviter', sa.Text(), nullable=True),
    sa.Column('niveau_etudes', sa.Text(), nullable=True),
    sa.Column('duree_souhaitee', sa.Text(), nullable=True),
    sa.Column('dispo_horaires', sa.Text(), nullable=True),
    sa.Column('mobilite', sa.Text(), nullable=True),
    sa.Column('types_jobs_ok', sa.Text(), nullable=True),
    sa.Column('types_jobs_eviter', sa.Text(), nullable=True),
    sa.Column('localisation_pref', sa.Text(), nullable=True),
    sa.Column('lettre_type', sa.Text(), nullable=True),
    sa.Column('email_type', sa.Text(), nullable=True),
    sa.Column('pieces_jointes', sa.JSON(), nullable=True),
    sa.Column('competences', sa.JSON(), nullable=True),
    sa.Column('projets', sa.JSON(), nullable=True),
    sa.Column('recherche', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_profils_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profils')),
    sa.UniqueConstraint('user_id', 'mode', name=op.f('uq_profils_user_id_mode'))
    )


def downgrade() -> None:
    """Supprime tout le schéma."""
    op.drop_table('profils')
    op.drop_table('offres_vues')
    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_entreprises_user_id'))
        batch_op.drop_index(batch_op.f('ix_entreprises_siren'))

    op.drop_table('entreprises')
    op.drop_table('emails_contactes')
    with op.batch_alter_table('candidatures', schema=None) as batch_op:
        batch_op.drop_index('ix_candidatures_user_id_mode')

    op.drop_table('candidatures')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
