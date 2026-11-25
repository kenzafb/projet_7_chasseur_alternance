"""
scripts/deplacer_lettres_pdf.py
===============================
Ménage (D197) : déplace les lettres PDF de l'ancien dossier lettres_pdf/
(racine du projet) vers LETTRES_PDF_DIR (défaut DATA_DIR/lettres_pdf).
Les chemins en base sont relatifs à ce dossier (lettre_pdf,
« user_<id>/<fichier>.pdf ») : la base ne change pas, seuls les fichiers
bougent, sous-dossiers compris.

Par défaut, lecture seule : la liste de ce qui serait déplacé, et les
fichiers déjà présents à l'arrivée (jamais écrasés). --appliquer déplace.
Application arrêtée.

    venv/bin/python scripts/deplacer_lettres_pdf.py
    venv/bin/python scripts/deplacer_lettres_pdf.py --appliquer
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def plan(source: Path, cible: Path) -> tuple[list[tuple[Path, Path]], list[Path]]:
    """([(fichier, destination)], [destinations déjà prises])."""
    if not source.is_dir() or source.resolve() == cible.resolve():
        return [], []
    a_deplacer, pris = [], []
    for f in sorted(p for p in source.rglob("*") if p.is_file()):
        dest = cible / f.relative_to(source)
        (pris if dest.exists() else a_deplacer).append(dest if dest.exists() else (f, dest))
    return a_deplacer, pris


def main(argv=None) -> int:
    from shared import config
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--appliquer", action="store_true")
    ap.add_argument("--source", default=str(config.LETTRES_PDF_ANCIEN))
    ap.add_argument("--cible", default=str(config.LETTRES_PDF_DIR))
    args = ap.parse_args(argv)
    source, cible = Path(args.source), Path(args.cible)
    a_deplacer, pris = plan(source, cible)
    print(f"{source} -> {cible} : {len(a_deplacer)} fichier(s) à déplacer, {len(pris)} déjà présent(s) à l'arrivée")
    for f, _ in a_deplacer:
        print(f"  {f.relative_to(source)}")
    for dest in pris:
        print(f"  déjà là, laissé tel quel : {dest.relative_to(cible)}")
    if not args.appliquer:
        if a_deplacer:
            print("Lecture seule : relance avec --appliquer pour les déplacer.")
        return 0
    for f, dest in a_deplacer:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(dest))
    print(f"{len(a_deplacer)} fichier(s) déplacé(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
