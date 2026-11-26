"""
shared/reseau.py
================
Accès à internet pour la campagne automatique (D218) : au démarrage, et
dès qu'une recherche ou un envoi échoue, la campagne vérifie que la
connexion est là ; sinon, pause, nouvel essai toutes les 30 s, 30 min au
plus. Une coupure ne compte ni comme une panne du moteur de recherche
(D187), ni comme une entreprise sans site, ni comme un serveur SMTP en
panne.

Connexion présente : api.telegram.org OU le site de référence répond,
quel que soit le statut HTTP (une page d'erreur prouve que le réseau
passe). Un seul des deux en panne n'est pas une coupure.
"""

import time
from datetime import datetime

import requests

CIBLES = ("https://api.telegram.org", "https://www.wikidata.org")
ESSAI_S = 30                 # entre deux essais
ATTENTE_MAX_S = 30 * 60      # au-delà : la campagne s'arrête
DELAI_S = 10                 # par essai et par cible


def _joindre(url: str) -> bool:
    """Seul accès réseau du module (remplacé dans les tests)."""
    try:
        requests.head(url, timeout=DELAI_S, allow_redirects=False)
        return True
    except requests.RequestException:
        return False


def en_ligne() -> bool:
    return any(_joindre(url) for url in CIBLES)


class Reseau:
    """Attente de la connexion, au rythme de l'horloge de la campagne.
    arret() : vrai si la campagne doit s'arrêter (Ctrl+C, SIGTERM)."""

    def __init__(self, horloge, log, arret=lambda: False, essai_s: float = ESSAI_S,
                 attente_max_s: float = ATTENTE_MAX_S):
        self.horloge, self.log, self.arret = horloge, log, arret
        self.essai_s, self.attente_max_s = essai_s, attente_max_s
        self.coupures = 0                   # coupures vues (revenues ou non)
        self.perdu_depuis: datetime | None = None   # abandon : début de la coupure

    def en_ligne(self) -> bool:
        return en_ligne()

    def attendre(self, ou: str) -> bool:
        """Vrai dès que la connexion est là (tout de suite si elle n'est pas
        coupée) ; faux après attente_max_s sans elle, ou sur arrêt demandé."""
        if self.en_ligne():
            return True
        if self.perdu_depuis is not None:      # déjà abandonné : la campagne s'arrête
            return False
        debut = self.horloge.maintenant()
        self.coupures += 1
        minutes = round(self.attente_max_s / 60)
        self.log(f"🌐 Pas d'accès internet ({ou}) : pause, nouvel essai toutes les {self.essai_s:g} s, "
                 f"{minutes} min au plus.")
        depart = time.monotonic()
        while not self.arret():
            ecoule = max((self.horloge.maintenant() - debut).total_seconds(), time.monotonic() - depart)
            if ecoule >= self.attente_max_s:
                self.perdu_depuis = debut
                self.log(f"🌐 Toujours pas d'accès internet après {minutes} min ({ou}).")
                return False
            self.horloge.dormir(min(self.essai_s, self.attente_max_s - ecoule))
            if self.en_ligne():
                duree = (self.horloge.maintenant() - debut).total_seconds()
                self.log(f"🌐 Connexion revenue après {_duree(duree)} : reprise ({ou}).")
                return True
        return False


def _duree(secondes: float) -> str:
    return f"{round(secondes / 60)} min" if secondes >= 90 else f"{round(secondes)} s"
