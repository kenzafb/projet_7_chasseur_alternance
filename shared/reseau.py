"""
shared/reseau.py
================
Accès à internet pour la campagne automatique (D218, D219) : au démarrage,
et dès qu'une recherche ou un envoi échoue, la campagne vérifie que la
connexion est là ; sinon, pause, nouvel essai toutes les 30 s, jusqu'à
l'heure butoir (CAMPAGNE_HEURE_BUTOIR, 13:00), et 30 min au moins pour une
coupure qui commence peu avant ou après elle. Une coupure ne compte ni
comme une panne du moteur de recherche (D187), ni comme une entreprise sans
site, ni comme un serveur SMTP en panne.

Connexion présente : api.telegram.org OU le site de référence répond,
quel que soit le statut HTTP (une page d'erreur prouve que le réseau
passe). Un seul des deux en panne n'est pas une coupure.
"""

import time
from datetime import datetime, timedelta

import requests

CIBLES = ("https://api.telegram.org", "https://www.wikidata.org")
ESSAI_S = 30                 # entre deux essais
HEURE_BUTOIR = "13:00"       # au-delà : la campagne s'arrête
ATTENTE_MIN_S = 30 * 60      # coupure commencée peu avant la butoir, ou après : attendue au moins ça
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


def _duree(secondes: float) -> str:
    if secondes < 90:
        return f"{round(secondes)} s"
    minutes = round(secondes / 60)
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60:02d}"


class Reseau:
    """Attente de la connexion, au rythme de l'horloge de la campagne.
    arret() : vrai si la campagne doit s'arrêter (Ctrl+C, SIGTERM).
    au_retour(debut, revenue, ou) : appelé quand la connexion revient avant
    la butoir. butoir : fixée par fixer_butoir (jour de la campagne), sinon
    le jour de la première coupure."""

    def __init__(self, horloge, log, arret=lambda: False, essai_s: float = ESSAI_S,
                 heure_butoir: str = HEURE_BUTOIR, au_retour=None):
        self.horloge, self.log, self.arret = horloge, log, arret
        self.essai_s, self.heure_butoir, self.au_retour = essai_s, heure_butoir, au_retour
        self.butoir: datetime | None = None
        self.coupures = 0                   # coupures vues (revenues ou non)
        self.perdu_depuis: datetime | None = None   # abandon : début de la coupure
        self.fin_attente: datetime | None = None    # abandon : fin de l'attente

    def fixer_butoir(self, jour: datetime):
        heures, minutes = map(int, self.heure_butoir.split(":"))
        self.butoir = jour.replace(hour=heures, minute=minutes, second=0, microsecond=0)

    def en_ligne(self) -> bool:
        return en_ligne()

    def attendre(self, ou: str) -> bool:
        """Vrai dès que la connexion est là (tout de suite si elle n'est pas
        coupée) ; faux à la butoir sans elle, ou sur arrêt demandé."""
        if self.en_ligne():
            return True
        if self.perdu_depuis is not None:      # déjà abandonné : la campagne s'arrête
            return False
        debut = self.horloge.maintenant()
        if self.butoir is None:
            self.fixer_butoir(debut)
        fin = max(self.butoir, debut + timedelta(seconds=ATTENTE_MIN_S))
        self.coupures += 1
        self.log(f"🌐 Pas d'accès internet ({ou}) : pause, nouvel essai toutes les {self.essai_s:g} s "
                 f"jusqu'à {fin:%H:%M}.")
        depart = time.monotonic()
        attente_max = (fin - debut).total_seconds()
        while not self.arret():
            # Horloge reculée (changement d'heure, NTP) : le temps écoulé réel compte aussi
            ecoule = max((self.horloge.maintenant() - debut).total_seconds(), time.monotonic() - depart)
            if ecoule >= attente_max:
                self.perdu_depuis, self.fin_attente = debut, self.horloge.maintenant()
                self.log(f"🌐 Toujours pas d'accès internet à {fin:%H:%M} ({ou}), coupure depuis {debut:%H:%M} : "
                         "arrêt.")
                return False
            self.horloge.dormir(min(self.essai_s, attente_max - ecoule))
            if self.en_ligne():
                revenue = self.horloge.maintenant()
                self.log(f"🌐 Connexion revenue à {revenue:%H:%M} après {_duree((revenue - debut).total_seconds())} : "
                         f"reprise ({ou}).")
                if self.au_retour:
                    self.au_retour(debut, revenue, ou)
                return True
        return False
