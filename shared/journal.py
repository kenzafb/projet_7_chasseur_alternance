"""
shared/journal.py
=================
Journal du serveur et des commandes en ligne (hors scripts/, qui affichent
leurs résultats) : logger « chasseur », messages tels quels sur la sortie
d'erreur, niveau INFO. Remplace les print des modules (phase 13).

Les pipelines lancés depuis la page écrivent en plus dans leur propre
journal, affiché dans l'interface (shared.pipelines) ; journaliser en est
la valeur par défaut quand rien n'est fourni (ligne de commande, tests).
"""

import logging
import sys

journal = logging.getLogger("chasseur")


class _SortieErreur(logging.StreamHandler):
    """Écrit sur la sortie d'erreur du moment (et non celle de l'import :
    pytest la remplace pendant chaque test)."""

    def emit(self, record):
        self.stream = sys.stderr
        super().emit(record)


if not journal.handlers:
    _gestionnaire = _SortieErreur()
    _gestionnaire.setFormatter(logging.Formatter("%(message)s"))
    journal.addHandler(_gestionnaire)
    journal.setLevel(logging.INFO)


def journaliser(message="") -> None:
    """Une ligne dans le journal, sans interprétation des « % » du message."""
    journal.info("%s", message)
