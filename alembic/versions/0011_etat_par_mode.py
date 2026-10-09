"""État d'envoi par entreprise et par mode (phase 6a, remplace D2).

Une entreprise reste unique par utilisateur ; ses données publiques (site,
emails, contacts) sont communes à tous les modes. La sélection pour un
mode, l'envoi, sa date, les destinataires et le statut de suivi passent
dans la table entreprises_modes, une ligne par entreprise et par mode.

Données existantes : chaque entreprise reçoit une ligne en mode
alternance avec son état d'envoi ; mail_destinataires et mail_note quittent
extra pour leurs colonnes. Les colonnes mode, mail_envoye, mail_envoye_le
et statut_suivi d'entreprises disparaissent.

Retour arrière : l'état du mode alternance revient dans entreprises (à
défaut, celui d'un autre mode) ; les lignes des autres modes sont perdues.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-09 22:00:00.000000

"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODE_DES_EXISTANTES = "alternance"

entreprises = sa.table("entreprises", sa.column("id", sa.Integer), sa.column("user_id", sa.Integer),
                       sa.column("mode", sa.String), sa.column("mail_envoye", sa.Boolean),
                       sa.column("mail_envoye_le", sa.DateTime(timezone=True)),
                       sa.column("statut_suivi", sa.String), sa.column("extra", sa.JSON))
modes = sa.table("entreprises_modes", sa.column("entreprise_id", sa.Integer), sa.column("user_id", sa.Integer),
                 sa.column("mode", sa.String), sa.column("selectionnee_le", sa.DateTime(timezone=True)),
                 sa.column("mail_envoye", sa.Boolean), sa.column("mail_envoye_le", sa.DateTime(timezone=True)),
                 sa.column("statut_suivi", sa.String), sa.column("mail_destinataires", sa.JSON),
                 sa.column("mail_note", sa.String), sa.column("historique", sa.Boolean))

CHAMPS_EXTRA = ("mail_destinataires", "mail_note")


def _creer_table() -> None:
    op.create_table('entreprises_modes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entreprise_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('selectionnee_le', sa.DateTime(timezone=True), nullable=True),
        sa.Column('mail_envoye', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('mail_envoye_le', sa.DateTime(timezone=True), nullable=True),
        sa.Column('statut_suivi', sa.String(length=30), nullable=True),
        sa.Column('mail_destinataires', sa.JSON(), nullable=True),
        sa.Column('mail_note', sa.String(length=200), nullable=True),
        sa.Column('historique', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(['entreprise_id'], ['entreprises.id'],
                                name=op.f('fk_entreprises_modes_entreprise_id_entreprises'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                name=op.f('fk_entreprises_modes_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_entreprises_modes')),
        sa.UniqueConstraint('entreprise_id', 'mode', name=op.f('uq_entreprises_modes_entreprise_id_mode')),
    )
    op.create_index('ix_entreprises_modes_user_id_mode', 'entreprises_modes', ['user_id', 'mode'], unique=False)


# Ordre imposé par SQLite : le mode batch d'Alembic recopie la table
# entreprises puis supprime l'ancienne, ce qui, clés étrangères actives,
# viderait entreprises_modes (ON DELETE CASCADE). La table entreprises est
# donc modifiée quand entreprises_modes n'existe pas : après sa lecture au
# retour arrière, avant sa création à la montée.
def upgrade() -> None:
    cx = op.get_bind()
    maintenant = datetime.now(timezone.utc)
    lignes = cx.execute(sa.select(entreprises.c.id, entreprises.c.user_id, entreprises.c.mail_envoye,
                                  entreprises.c.mail_envoye_le, entreprises.c.statut_suivi,
                                  entreprises.c.extra)).all()
    etats = []
    for id_, user_id, envoye, envoye_le, statut, extra in lignes:
        extra = dict(extra or {})
        etats.append(dict(
            entreprise_id=id_, user_id=user_id, mode=MODE_DES_EXISTANTES, selectionnee_le=maintenant,
            mail_envoye=bool(envoye), mail_envoye_le=envoye_le, statut_suivi=statut or "envoye",
            mail_destinataires=list(extra.get("mail_destinataires") or []),
            mail_note=str(extra.get("mail_note") or "")[:200], historique=False))
        if any(c in extra for c in CHAMPS_EXTRA):
            for c in CHAMPS_EXTRA:
                extra.pop(c, None)
            cx.execute(entreprises.update().where(entreprises.c.id == id_).values(extra=extra))

    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.drop_column('mode')
        batch_op.drop_column('mail_envoye')
        batch_op.drop_column('mail_envoye_le')
        batch_op.drop_column('statut_suivi')

    _creer_table()
    for etat in etats:
        cx.execute(modes.insert().values(**etat))


def downgrade() -> None:
    cx = op.get_bind()
    etats = {}
    for ligne in cx.execute(sa.select(modes)).mappings().all():
        # L'état du mode alternance l'emporte, à défaut celui d'un autre mode
        if ligne["entreprise_id"] not in etats or ligne["mode"] == MODE_DES_EXISTANTES:
            etats[ligne["entreprise_id"]] = dict(ligne)
    op.drop_index('ix_entreprises_modes_user_id_mode', table_name='entreprises_modes')
    op.drop_table('entreprises_modes')

    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mode', sa.String(length=20), server_default='alternance', nullable=False))
        batch_op.add_column(sa.Column('mail_envoye', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('mail_envoye_le', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('statut_suivi', sa.String(length=30), nullable=True))

    for id_, extra in cx.execute(sa.select(entreprises.c.id, entreprises.c.extra)).all():
        etat = etats.get(id_)
        if etat is None:
            continue
        extra = dict(extra or {})
        if etat["mail_destinataires"]:
            extra["mail_destinataires"] = list(etat["mail_destinataires"])
        if etat["mail_note"]:
            extra["mail_note"] = etat["mail_note"]
        cx.execute(entreprises.update().where(entreprises.c.id == id_).values(
            mode=etat["mode"], mail_envoye=bool(etat["mail_envoye"]), mail_envoye_le=etat["mail_envoye_le"],
            statut_suivi=etat["statut_suivi"] or "envoye", extra=extra))
