"""
shared/ia.py
============
Client Mistral unique du projet et fonction d'appel avec retry.

Utilisé par l'analyseur d'offres, le générateur de lettres et le scraper
d'emails. Chaque appel déclare son usage ("analyse", "lettre",
"extraction") : le modèle vient de shared.config.modele_mistral(usage).

Erreurs (SDK mistralai 2.x : errors.MistralError porte status_code ;
httpx.RequestError pour le réseau), jamais d'exception brute ni de
résultat inventé :
  - ErreurIABloquante : 400, 401, 403, 404, 422 (clé invalide, modèle non
    autorisé ou inconnu, requête refusée). Inutile d'insister : le
    pipeline s'arrête, message clair.
  - ErreurIAPassagere : 429, 5xx, réseau (retentés jusqu'à épuisement),
    réponse illisible. L'élément en cours est sauté, il reviendra.

Tous les appels du processus (tous utilisateurs, tous pipelines, retries
compris) passent par un limiteur commun : au moins MISTRAL_INTERVALLE_MIN_S
secondes entre deux appels, pour que des pipelines simultanés ne se
prennent pas de 429.
"""

import json
import os
import threading
import time

import httpx
from mistralai.client import Mistral, errors

from shared.config import MISTRAL_INTERVALLE_MIN_S, modele_mistral

client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

CODES_BLOQUANTS = {400, 401, 403, 404, 422}


class ErreurIA(Exception):
    """Échec d'un appel Mistral. Message lisible, sans clé ni contenu envoyé."""

    def __init__(self, message: str, statut: int | None = None, modele: str = ""):
        super().__init__(message)
        self.statut = statut
        self.modele = modele


class ErreurIABloquante(ErreurIA):
    """Rien ne passera tant que la configuration n'aura pas changé."""


class ErreurIAPassagere(ErreurIA):
    """Échec ponctuel (quota, serveur, réseau, réponse illisible)."""


class Limiteur:
    """Espace les appels d'au moins `intervalle` secondes, tous threads
    confondus. Chaque appelant réserve le prochain créneau sous verrou, puis
    attend son tour hors du verrou : les créneaux sont servis dans l'ordre
    des réservations."""

    def __init__(self, intervalle: float):
        self.intervalle = intervalle
        self._verrou = threading.Lock()
        self._prochain = 0.0   # instant (time.monotonic) du prochain créneau libre

    def attendre(self):
        with self._verrou:
            maintenant = time.monotonic()
            creneau = max(maintenant, self._prochain)
            self._prochain = creneau + self.intervalle
        if creneau > maintenant:
            time.sleep(creneau - maintenant)


limiteur = Limiteur(MISTRAL_INTERVALLE_MIN_S)


def _detail(err) -> str:
    """Message de l'API (« This model is not available... »), court."""
    corps = getattr(err, "body", "") or ""
    try:
        donnees = json.loads(corps)
        texte = donnees.get("message") or donnees.get("detail") or corps
    except (ValueError, AttributeError):
        texte = corps or getattr(err, "message", "") or ""
    texte = " ".join(str(texte).split())
    return texte[:200]


def _statut(err) -> int | None:
    statut = getattr(err, "status_code", None)
    return statut if isinstance(statut, int) else None


def message_bloquant(statut: int, modele: str, detail: str) -> str:
    if statut == 401:
        return "Clé Mistral refusée (401) : vérifie MISTRAL_API_KEY dans le .env."
    if statut == 403:
        if "tier" in detail.lower() or "subscription" in detail.lower() or "1910" in detail:
            return (f"Modèle Mistral « {modele} » non autorisé pour l'abonnement de cette clé (403). "
                    "Choisis-en un autre dans le .env (MODELE_MISTRAL ou MODELE_MISTRAL_<USAGE>) ; "
                    "python scripts/verifier_mistral.py liste ceux qui répondent.")
        return f"Accès refusé par Mistral (403) pour le modèle « {modele} » : {detail}"
    if statut == 404:
        return (f"Modèle Mistral « {modele} » introuvable (404) : vérifie son nom dans le .env "
                "(python scripts/verifier_mistral.py).")
    return f"Requête refusée par Mistral ({statut}) avec le modèle « {modele} » : {detail}"


def classer(err, modele: str) -> tuple[ErreurIA, bool]:
    """(erreur du projet, faut-il retenter) pour une exception du SDK."""
    statut = _statut(err)
    if statut in CODES_BLOQUANTS:
        return ErreurIABloquante(message_bloquant(statut, modele, _detail(err)), statut, modele), False
    if statut == 429 or (statut is not None and statut >= 500):
        return ErreurIAPassagere(f"Mistral indisponible ({statut}) : {_detail(err)}", statut, modele), True
    if isinstance(err, (httpx.RequestError, errors.NoResponseError)):
        return ErreurIAPassagere(f"Mistral injoignable : {type(err).__name__}", None, modele), True
    if statut is None and "429" in str(err):
        return ErreurIAPassagere("Mistral : trop de requêtes (429)", 429, modele), True
    return ErreurIAPassagere(f"Échec de l'appel Mistral : {type(err).__name__}", statut, modele), False


def appeler_mistral(messages, *, usage="analyse", tentatives=4, attente=lambda n: 15 * n,
                    on_attente=None, **options):
    """
    Appelle client.chat.complete avec le modèle de l'usage et retente les
    erreurs passagères (429, 5xx, réseau).

    tentatives : nombre total d'essais (1 = pas de retry)
    attente    : fonction n° de tentative échouée -> secondes d'attente
    on_attente : callback (tentative, tentatives, secondes) avant chaque pause
    options    : passées telles quelles à chat.complete (response_format, temperature...)

    Lève ErreurIABloquante tout de suite, ErreurIAPassagere une fois les
    tentatives épuisées.
    """
    modele = modele_mistral(usage)
    for tentative in range(1, tentatives + 1):
        limiteur.attendre()
        try:
            return client.chat.complete(model=modele, messages=messages, **options)
        except Exception as err:
            erreur, a_retenter = classer(err, modele)
            if not a_retenter or tentative >= tentatives:
                raise erreur from None
            secondes = attente(tentative)
            if on_attente:
                on_attente(tentative, tentatives, secondes)
            time.sleep(secondes)


def reponse_json(response) -> dict:
    """Contenu JSON d'une réponse de chat ; ErreurIAPassagere s'il est illisible."""
    import re
    try:
        texte = response.choices[0].message.content or ""
        texte = re.sub(r"```(?:json)?\s*", "", texte).strip()
        donnees = json.loads(texte)
    except (ValueError, AttributeError, IndexError, TypeError):
        raise ErreurIAPassagere("Réponse de Mistral illisible (JSON attendu)") from None
    if not isinstance(donnees, dict):
        raise ErreurIAPassagere("Réponse de Mistral illisible (objet JSON attendu)")
    return donnees
