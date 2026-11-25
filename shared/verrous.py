"""
shared/verrous.py
=================
Verrous entre processus (application, campagne automatique), par flock sur
des fichiers de config.VERROUS_DIR (D213). Un verrou tombe tout seul si son
processus s'arrête : jamais de verrou fantôme. Le contenu des fichiers ne
compte pas, ils ne sont jamais supprimés.
"""

import fcntl
import time

from shared import config

CAMPAGNE = "campagne"


def nom_pipeline(type_: str, user_id: int) -> str:
    """Verrou d'un traitement (recherche, analyse, spontanees) d'un utilisateur."""
    return f"{type_}_{user_id}"


class Verrou:
    def __init__(self, nom: str):
        self.nom = nom
        self._fichier = None

    def prendre(self, essais: int = 3) -> bool:
        """Vrai si le verrou est pris. Quelques essais rapprochés : occupes()
        tient un verrou libre le temps de le regarder."""
        config.VERROUS_DIR.mkdir(parents=True, exist_ok=True)
        fichier = open(config.VERROUS_DIR / f"{self.nom}.lock", "a")   # noqa: SIM115 (gardé ouvert)
        for i in range(essais):
            try:
                fcntl.flock(fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fichier = fichier
                return True
            except BlockingIOError:
                if i + 1 < essais:
                    time.sleep(0.02)
        fichier.close()
        return False

    def liberer(self):
        if self._fichier is not None:
            self._fichier.close()      # ferme le descripteur : flock rendu
            self._fichier = None


def occupes(sauf=()) -> list[str]:
    """Noms des verrous tenus en ce moment, par n'importe quel processus."""
    noms = []
    for chemin in sorted(config.VERROUS_DIR.glob("*.lock")):
        if chemin.stem in sauf:
            continue
        with open(chemin, "a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                noms.append(chemin.stem)
    return noms
