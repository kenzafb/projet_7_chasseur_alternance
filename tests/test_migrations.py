"""Chaque migration, montée puis descendue sur une base remplie (une ligne
par table) : aucune ligne perdue (audit phase 12, D132). Garde-fou contre
batch_alter_table sur une table parente, qui recrée la table et efface en
cascade ses tables enfants sous SQLite."""

import sqlite3

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from database.schema import config_alembic

REVISIONS = [r.revision for r in reversed(list(ScriptDirectory.from_config(config_alembic("sqlite://")).walk_revisions()))]


def _tables(cx):
    return [r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                                     "AND name != 'alembic_version' AND name NOT LIKE '_alembic%'")]


def _remplir(cx):
    """Une ligne par table, users d'abord ; valeurs neutres pour les colonnes
    obligatoires sans défaut."""
    tables = _tables(cx)
    for t in ["users"] + [t for t in tables if t != "users"]:
        valeurs = {}
        for _, nom, type_, notnull, defaut, pk in cx.execute(f"PRAGMA table_info({t})"):
            if pk:
                continue
            if nom in ("user_id", "entreprise_id"):
                valeurs[nom] = 1
            elif nom == "mode":
                valeurs[nom] = "alternance"
            elif notnull and defaut is None:
                type_ = (type_ or "").upper()
                valeurs[nom] = 0 if ("INT" in type_ or "BOOL" in type_) else ("{}" if "JSON" in type_ else f"{t}-{nom}")
        if t == "users":
            valeurs.update(email="a@test.fr", mot_de_passe_hash="x")
        cx.execute(f"INSERT INTO {t} ({','.join(valeurs)}) VALUES ({','.join('?' * len(valeurs))})", list(valeurs.values()))
    cx.commit()


def _compter(chemin) -> dict:
    cx = sqlite3.connect(chemin)
    try:
        return {t: cx.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in _tables(cx)}
    finally:
        cx.close()


@pytest.mark.parametrize("precedente,revision", list(zip(REVISIONS, REVISIONS[1:], strict=False)))
def test_montee_et_descente_sans_perte(tmp_path, precedente, revision):
    chemin = tmp_path / "t.db"
    cfg = config_alembic(f"sqlite:///{chemin}")
    command.upgrade(cfg, precedente)
    cx = sqlite3.connect(chemin)
    _remplir(cx)
    cx.close()
    avant = _compter(chemin)
    assert all(avant.values()), avant
    command.upgrade(cfg, revision)
    apres = _compter(chemin)
    command.downgrade(cfg, precedente)
    retour = _compter(chemin)
    for table, n in avant.items():
        assert apres.get(table, n) >= n, f"{revision} : lignes perdues dans {table} à la montée"
        assert retour.get(table, n) >= n, f"{revision} : lignes perdues dans {table} à la descente"
