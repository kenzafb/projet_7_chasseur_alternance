"""Garde-fou de la suite (phase 15) : empreinte de data/ comparée avant et après."""
import time

from tests.conftest import differences, dossiers_proteges, empreinte


def test_empreinte_voit_creation_modification_suppression(tmp_path):
    (tmp_path / "a.db").write_text("x")
    (tmp_path / "sous").mkdir()
    (tmp_path / "sous" / "b.json").write_text("{}")
    avant = empreinte(tmp_path)
    assert set(avant) == {"a.db", "sous/b.json"}
    time.sleep(0.01)
    (tmp_path / "a.db").write_text("xy")
    (tmp_path / "sous" / "b.json").unlink()
    (tmp_path / "c.gz").write_bytes(b"1")
    assert differences(avant, empreinte(tmp_path)) == ["créé : c.gz", "supprimé : sous/b.json", "modifié : a.db"]
    assert differences(avant, avant) == []


def test_le_vrai_data_est_surveille():
    from pathlib import Path
    assert (Path(__file__).resolve().parent.parent / "data").resolve() in dossiers_proteges()
