"""
shared/pipelines.py
===================
État en mémoire des pipelines longs (recherche d'offres, candidatures
spontanées), PAR UTILISATEUR : progression, événement d'arrêt et logs.

Chaque utilisateur ne voit que ses propres états et logs, et ne peut
arrêter que ses propres pipelines. Un seul pipeline de chaque type à la
fois par utilisateur ; deux utilisateurs différents travaillent en
parallèle. Toutes les lectures et écritures passent par un verrou : les
pipelines tournent dans des threads.

Limite connue : tout est en mémoire du processus. Un redémarrage (ou le
--reload d'uvicorn) tue les threads et efface états et logs.
"""

import collections
import threading

from database.dates import maintenant_affichage
from shared.config import LOGS_MAX_PAR_UTILISATEUR

RECHERCHE = "recherche"
SPONTANEES = "spontanees"

ETATS_INITIAUX = {
    RECHERCHE:  {"en_cours": False, "message": "Prêt", "pourcentage": 0},
    # mode_test : envoi en cours vers l'utilisateur lui-même (affiché par le front)
    SPONTANEES: {"en_cours": False, "etape": None, "message": "Prêt", "pourcentage": 0,
                 "mode_test": False},
}


class Pipelines:
    def __init__(self, logs_max: int = LOGS_MAX_PAR_UTILISATEUR):
        self._verrou = threading.Lock()
        self._logs_max = logs_max
        self._etats = {type_: {} for type_ in ETATS_INITIAUX}   # type -> user_id -> dict
        self._arrets = {}                                         # user_id -> Event (spontanées)
        self._logs = {}                                           # user_id -> deque bornée

    # ─── États ────────────────────────────────────────────────────────────────
    def etat(self, type_: str, user_id: int) -> dict:
        """Copie de l'état du pipeline `type_` de l'utilisateur."""
        with self._verrou:
            return dict(self._etats[type_].get(user_id) or ETATS_INITIAUX[type_])

    def demarrer(self, type_: str, user_id: int, **champs) -> bool:
        """Marque le pipeline en cours, sauf s'il l'est déjà pour cet
        utilisateur (vérification et marquage atomiques). Pour les
        spontanées, réarme l'événement d'arrêt de l'utilisateur."""
        with self._verrou:
            actuel = self._etats[type_].get(user_id)
            if actuel and actuel["en_cours"]:
                return False
            self._etats[type_][user_id] = {**ETATS_INITIAUX[type_], **champs, "en_cours": True}
            if type_ == SPONTANEES:
                self._arrets[user_id] = threading.Event()
            return True

    def maj(self, type_: str, user_id: int, **champs):
        with self._verrou:
            etat = self._etats[type_].setdefault(user_id, dict(ETATS_INITIAUX[type_]))
            etat.update(champs)

    def terminer(self, type_: str, user_id: int, **champs):
        self.maj(type_, user_id, **champs, en_cours=False)

    # ─── Arrêt (candidatures spontanées) ──────────────────────────────────────
    def evenement_arret(self, user_id: int) -> threading.Event:
        """Événement d'arrêt du pipeline spontané de l'utilisateur."""
        with self._verrou:
            return self._arrets.setdefault(user_id, threading.Event())

    def demander_arret(self, user_id: int) -> bool:
        """Arrête le pipeline spontané de CET utilisateur s'il tourne.
        Retourne True si un pipeline était en cours."""
        with self._verrou:
            etat = self._etats[SPONTANEES].get(user_id)
            if not (etat and etat["en_cours"]):
                return False
            self._arrets.setdefault(user_id, threading.Event()).set()
            etat["message"] = "Arrêt demandé — sauvegarde en cours..."
            return True

    # ─── Logs ─────────────────────────────────────────────────────────────────
    def log(self, user_id: int, msg: str):
        ligne = {"t": maintenant_affichage().strftime("%H:%M:%S"), "msg": msg}
        with self._verrou:
            journal = self._logs.setdefault(user_id, collections.deque(maxlen=self._logs_max))
            journal.append(ligne)
        print(f"[user {user_id}] {msg}")

    def logs(self, user_id: int) -> list[dict]:
        with self._verrou:
            return list(self._logs.get(user_id, ()))
