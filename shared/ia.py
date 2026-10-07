"""
shared/ia.py
============
Client Mistral unique du projet et fonction d'appel avec retry sur rate limit.

Utilisé par l'analyseur d'offres, le générateur de lettres et le scraper
d'emails. Chaque appelant garde sa propre politique de retry (nombre de
tentatives, délais, détection du rate limit) via les paramètres.
"""

import os
import time

from mistralai.client import Mistral

from shared.config import MODELE_MISTRAL

client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))


def est_rate_limit(erreur) -> bool:
    """Détection par défaut d'une erreur de rate limit (429)."""
    msg = str(erreur).lower()
    return "429" in msg or "rate" in msg


def appeler_mistral(messages, *, tentatives=4, attente=lambda n: 15 * n,
                    rate_limit=est_rate_limit, on_attente=None, **options):
    """
    Appelle client.chat.complete et retente tant que l'erreur est un rate limit.

    tentatives : nombre total d'essais (1 = pas de retry)
    attente    : fonction n° de tentative échouée -> secondes d'attente
    rate_limit : fonction erreur -> bool, True si on doit retenter
    on_attente : callback (tentative, tentatives, secondes) avant chaque pause
    options    : passées telles quelles à chat.complete (response_format, temperature...)

    Lève l'erreur si elle n'est pas un rate limit, ou si la dernière
    tentative échoue.
    """
    for tentative in range(1, tentatives + 1):
        try:
            return client.chat.complete(model=MODELE_MISTRAL, messages=messages, **options)
        except Exception as err:
            if not rate_limit(err) or tentative >= tentatives:
                raise
            secondes = attente(tentative)
            if on_attente:
                on_attente(tentative, tentatives, secondes)
            time.sleep(secondes)
