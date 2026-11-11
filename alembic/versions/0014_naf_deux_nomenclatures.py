"""Code NAF des entreprises dans les deux nomenclatures (phase 8, D112) :
entreprises.naf_rev2 et entreprises.naf_2025.

Entreprises existantes : naf_rev2 vient du code déjà enregistré (secteur,
ou extra.code_naf ; « 6201Z » de La Bonne Alternance devient « 62.01Z »),
naf_2025 de la table de correspondance de l'INSEE quand elle ne donne
qu'une cible. Correspondance multiple : naf_2025 reste vide, complété
quand Sirene retrouve l'entreprise. Un code déjà en NAF 2025 remplit
naf_2025 (et naf_rev2 si l'INSEE ne lui donne qu'une origine).

La table est lue dans docs/referentiels/insee/correspondance_naf_rev2_naf2025.csv,
sans passer par shared.naf : la migration ne dépend pas du code de l'application.

Retour arrière : les deux colonnes disparaissent (secteur et extra.code_naf
ne sont pas touchés).

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-12 10:00:00.000000

"""
import csv
import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_INSEE = (Path(__file__).resolve().parents[2] / "docs" / "referentiels" / "insee"
               / "correspondance_naf_rev2_naf2025.csv")

entreprises = sa.table("entreprises", sa.column("id", sa.Integer), sa.column("secteur", sa.String),
                       sa.column("extra", sa.JSON), sa.column("naf_rev2", sa.String),
                       sa.column("naf_2025", sa.String))


def _tables():
    vers_2025, vers_rev2 = {}, {}
    with open(TABLE_INSEE, encoding="utf-8") as f:
        for ligne in csv.DictReader(f):
            vers_2025.setdefault(ligne["naf_rev2"], set()).add(ligne["naf_2025"])
            vers_rev2.setdefault(ligne["naf_2025"], set()).add(ligne["naf_rev2"])
    return vers_2025, vers_rev2


def _normaliser(code) -> str:
    code = str(code or "").strip().upper().replace(" ", "")
    return f"{code[:2]}.{code[2:]}" if len(code) == 5 and "." not in code else code


def _deux_codes(codes, vers_2025, vers_rev2):
    rev2 = naf2025 = ""
    for code in map(_normaliser, codes):
        if code in vers_2025 and not rev2:
            rev2 = code
        elif code in vers_rev2 and not naf2025:
            naf2025 = code
    if rev2 and not naf2025 and len(vers_2025[rev2]) == 1:
        naf2025 = next(iter(vers_2025[rev2]))
    if naf2025 and not rev2 and len(vers_rev2[naf2025]) == 1:
        rev2 = next(iter(vers_rev2[naf2025]))
    return rev2, naf2025


def upgrade() -> None:
    """Ajoute les deux colonnes et les remplit d'après le code connu."""
    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('naf_rev2', sa.String(length=10), server_default='', nullable=False))
        batch_op.add_column(sa.Column('naf_2025', sa.String(length=10), server_default='', nullable=False))
    cx = op.get_bind()
    vers_2025, vers_rev2 = _tables()
    for id_, secteur, extra in cx.execute(sa.select(entreprises.c.id, entreprises.c.secteur, entreprises.c.extra)):
        if isinstance(extra, str):
            extra = json.loads(extra or "{}")
        rev2, naf2025 = _deux_codes([secteur, (extra or {}).get("code_naf")], vers_2025, vers_rev2)
        if rev2 or naf2025:
            cx.execute(entreprises.update().where(entreprises.c.id == id_)
                       .values(naf_rev2=rev2, naf_2025=naf2025))


def downgrade() -> None:
    """Retire les deux colonnes."""
    with op.batch_alter_table('entreprises', schema=None) as batch_op:
        batch_op.drop_column('naf_2025')
        batch_op.drop_column('naf_rev2')
