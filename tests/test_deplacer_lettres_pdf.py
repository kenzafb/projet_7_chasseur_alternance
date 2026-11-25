"""scripts/deplacer_lettres_pdf.py (D197) : lecture seule par défaut,
jamais d'écrasement, sous-dossiers gardés."""

from scripts.deplacer_lettres_pdf import main


def test_lecture_seule_puis_appliquer(tmp_path, capsys):
    ancien, nouveau = tmp_path / "lettres_pdf", tmp_path / "data" / "lettres_pdf"
    (ancien / "user_1").mkdir(parents=True)
    (ancien / "user_1" / "a.pdf").write_bytes(b"A")
    (ancien / "user_1" / "b.pdf").write_bytes(b"B")
    (nouveau / "user_1").mkdir(parents=True)
    (nouveau / "user_1" / "b.pdf").write_bytes(b"deja")
    args = ["--source", str(ancien), "--cible", str(nouveau)]
    assert main(args) == 0
    assert (ancien / "user_1" / "a.pdf").exists() and not (nouveau / "user_1" / "a.pdf").exists()
    assert "1 fichier(s) à déplacer, 1 déjà présent(s)" in capsys.readouterr().out
    assert main(args + ["--appliquer"]) == 0
    assert (nouveau / "user_1" / "a.pdf").read_bytes() == b"A"
    assert (nouveau / "user_1" / "b.pdf").read_bytes() == b"deja"        # jamais écrasé
    assert (ancien / "user_1" / "b.pdf").exists()                         # laissé à l'ancien endroit
