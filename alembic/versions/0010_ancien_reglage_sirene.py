"""Profils d'alternance existants : ancien réglage de Sirene pré-coché
(phase 5d, décision D60). Avant la phase, Sirene ne cherchait que les
entreprises de 10 salariés et plus, dans 4 départements (75, 92, 93, 94).
Désormais rien de coché veut dire toutes les tailles (sauf « sans
salarié ») et toute l'Île-de-France ; les profils existants sans choix
reçoivent donc l'ancien réglage pour ne pas changer de comportement.
Pas de changement de schéma, seulement des données.

Seules les tailles des candidatures spontanées (tailles_spontanees) sont
pré-cochées ; celles des offres (tailles) restent à toutes (D63).

Retour arrière : les listes égales à l'ancien réglage sont vidées.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Figé ici : la migration ne dépend pas du code de l'application
ANCIEN_REGLAGE = {
    "tailles_spontanees": ["10_49", "50_249", "250_4999", "5000_plus"],
    "departements": ["75", "92", "93", "94"],
}

profils = sa.table("profils", sa.column("id", sa.Integer), sa.column("mode", sa.String),
                   sa.column("recherche", sa.JSON))


def _profils_alternance(cx):
    return cx.execute(sa.select(profils.c.id, profils.c.recherche).where(profils.c.mode == "alternance")).all()


def upgrade() -> None:
    cx = op.get_bind()
    for id_, recherche in _profils_alternance(cx):
        recherche = dict(recherche) if isinstance(recherche, dict) else {}
        nouvelle = {**recherche, **{cle: list(valeur) for cle, valeur in ANCIEN_REGLAGE.items()
                                    if not recherche.get(cle)}}
        if nouvelle != recherche:
            cx.execute(profils.update().where(profils.c.id == id_).values(recherche=nouvelle))


def downgrade() -> None:
    cx = op.get_bind()
    for id_, recherche in _profils_alternance(cx):
        if not isinstance(recherche, dict):
            continue
        nouvelle = {cle: ([] if ANCIEN_REGLAGE.get(cle) == valeur else valeur) for cle, valeur in recherche.items()}
        if nouvelle != recherche:
            cx.execute(profils.update().where(profils.c.id == id_).values(recherche=nouvelle))
