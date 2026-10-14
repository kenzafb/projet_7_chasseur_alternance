"""
shared/ia.py
============
Client d'IA unique du projet, au format compatible OpenAI
(POST <IA_BASE_URL>/chat/completions). Par défaut Ollama sur la machine
(http://localhost:11434/v1) ; tout serveur qui parle ce format convient
(llama.cpp, LM Studio, vLLM, un service en ligne avec IA_API_KEY).

Utilisé par l'analyseur d'offres, le générateur de lettres et la
validation des emails du scraper. Chaque appel déclare son usage
("analyse", "lettre", "extraction") : le modèle vient de
shared.config.modele_ia(usage).

Un seul appel à la fois dans tout le processus (tous utilisateurs, tous
pipelines) : sur processeur, deux générations simultanées iraient chacune
deux fois moins vite et pourraient forcer le chargement d'un second
modèle. Les autres appelants attendent leur tour.

Erreurs, jamais d'exception brute ni de résultat inventé :
  - IAInjoignable (ErreurIABloquante) : connexion impossible, Ollama ne
    tourne pas. Le pipeline s'arrête, message clair.
  - ErreurIABloquante : 400, 401, 403, 404, 422, mémoire insuffisante
    (modèle absent, clé refusée, requête refusée). Inutile d'insister.
  - ErreurIAPassagere : 429, 5xx (retentés), délai dépassé, réponse
    illisible. L'élément en cours est sauté, il reviendra.

ANALYSE_IA=false (shared.config.analyse_ia_active) : appeler_ia lève
IADesactivee sans rien appeler.
"""

import json
import re
import threading
import time

import httpx

from shared.config import (IA_DELAI_CONNEXION_S, MESSAGE_IA_DESACTIVEE, analyse_ia_active, ia_api_key,
                           ia_base_url, ia_delai_s, modele_ia)

CODES_BLOQUANTS = {400, 401, 403, 404, 422}


class ErreurIA(Exception):
    """Échec d'un appel à l'IA. Message lisible, sans clé ni contenu envoyé."""

    def __init__(self, message: str, statut: int | None = None, modele: str = ""):
        super().__init__(message)
        self.statut = statut
        self.modele = modele


class ErreurIABloquante(ErreurIA):
    """Rien ne passera tant que la configuration n'aura pas changé."""


class ErreurIAPassagere(ErreurIA):
    """Échec ponctuel (serveur occupé, délai dépassé, réponse illisible)."""


class IAInjoignable(ErreurIABloquante):
    """Serveur d'IA injoignable : Ollama ne tourne pas, ou IA_BASE_URL est faux."""


class IADesactivee(ErreurIABloquante):
    """ANALYSE_IA=false : l'appel n'est pas tenté. Les pipelines testent
    l'interrupteur avant ; ceci est le dernier rempart."""


# Un seul appel à la fois dans tout le processus
verrou = threading.Lock()


def _poster(url: str, corps: dict, entetes: dict, delai: float) -> httpx.Response:
    """Seule sortie réseau vers l'IA (remplacée par une fausse IA dans les tests)."""
    with httpx.Client(timeout=httpx.Timeout(delai, connect=IA_DELAI_CONNEXION_S)) as client:
        return client.post(url, json=corps, headers=entetes)


def _obtenir(url: str, entetes: dict, delai: float) -> httpx.Response:
    """GET vers le serveur d'IA (liste des modèles ; remplacée dans les tests)."""
    with httpx.Client(timeout=httpx.Timeout(delai, connect=IA_DELAI_CONNEXION_S)) as client:
        return client.get(url, headers=entetes)


def _entetes() -> dict:
    cle = ia_api_key()
    return {"Authorization": f"Bearer {cle}"} if cle else {}


def message_injoignable() -> str:
    return f"IA locale injoignable : vérifie qu'Ollama tourne (IA_BASE_URL = {ia_base_url()})."


def _detail(reponse: httpx.Response) -> str:
    """Message d'erreur du serveur (« model "x" not found... »), court.
    Ollama : {"error": {"message": ...}} ou {"error": "..."}."""
    texte = reponse.text or ""
    try:
        donnees = reponse.json()
        erreur = donnees.get("error") if isinstance(donnees, dict) else None
        if isinstance(erreur, dict):
            texte = erreur.get("message") or texte
        elif erreur:
            texte = str(erreur)
        elif isinstance(donnees, dict):
            texte = donnees.get("message") or donnees.get("detail") or texte
    except ValueError:
        pass
    return " ".join(str(texte).split())[:200]


def message_bloquant(statut: int, modele: str, detail: str) -> str:
    if statut in (401, 403):
        return f"Accès refusé par le serveur d'IA ({statut}) : vérifie IA_API_KEY dans le .env. {detail}".strip()
    if statut == 404:
        return (f"Modèle « {modele} » introuvable sur le serveur d'IA (404) : installe-le "
                f"(ollama pull {modele}) ou corrige IA_MODELE_<USAGE> dans le .env.")
    return f"Requête refusée par le serveur d'IA ({statut}) avec le modèle « {modele} » : {detail}"


def classer_statut(reponse: httpx.Response, modele: str) -> tuple[ErreurIA, bool]:
    """(erreur du projet, faut-il retenter) pour une réponse HTTP en erreur."""
    statut, detail = reponse.status_code, _detail(reponse)
    if statut in CODES_BLOQUANTS:
        return ErreurIABloquante(message_bloquant(statut, modele, detail), statut, modele), False
    if statut >= 500 and "memory" in detail.lower():
        # Ollama : « model requires more system memory (...) than is available »
        return ErreurIABloquante(
            f"Mémoire insuffisante pour charger « {modele} » : choisis un modèle plus petit ou "
            f"règle OLLAMA_MAX_LOADED_MODELS=1. {detail}", statut, modele), False
    return ErreurIAPassagere(f"Serveur d'IA indisponible ({statut}) : {detail}", statut, modele), True


def classer_exception(err: Exception, modele: str) -> tuple[ErreurIA, bool]:
    """(erreur du projet, faut-il retenter) pour une erreur réseau."""
    if isinstance(err, (httpx.ConnectError, httpx.ConnectTimeout)):
        return IAInjoignable(message_injoignable(), None, modele), False
    if isinstance(err, httpx.TimeoutException):
        # Retenter coûterait encore tout le délai : l'élément est sauté
        return ErreurIAPassagere(f"Pas de réponse de l'IA en {ia_delai_s():.0f} s (IA_DELAI_S) avec "
                                 f"« {modele} »", None, modele), False
    return ErreurIAPassagere(f"Échec de l'appel à l'IA : {type(err).__name__}", None, modele), True


def _contenu(reponse: httpx.Response) -> str:
    """Texte du premier choix, sans le raisonnement éventuel (<think>...</think>)."""
    try:
        texte = reponse.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError):
        raise ErreurIAPassagere("Réponse du serveur d'IA illisible (format chat/completions attendu)") from None
    return re.sub(r"<think>.*?</think>", "", str(texte), flags=re.DOTALL).strip()


def appeler_ia(messages, *, usage="analyse", modele=None, tentatives=2, attente=lambda n: 5 * n,
               on_attente=None, **options) -> str:
    """
    Envoie messages au modèle de l'usage (ou `modele`) et renvoie le texte de
    la réponse. Retente les erreurs passagères du serveur (429, 5xx, réseau).

    tentatives : nombre total d'essais (1 = pas de retry)
    attente    : fonction n° de tentative échouée -> secondes d'attente
    on_attente : callback (tentative, tentatives, secondes) avant chaque pause
    options    : ajoutées telles quelles au corps (temperature, max_tokens...)

    Lève ErreurIABloquante tout de suite (IAInjoignable si le serveur ne
    répond pas), ErreurIAPassagere une fois les tentatives épuisées.
    IADesactivee sans rien appeler si ANALYSE_IA=false.
    """
    if not analyse_ia_active():
        raise IADesactivee(MESSAGE_IA_DESACTIVEE)
    modele = modele or modele_ia(usage)
    corps = {"model": modele, "messages": messages, "stream": False, **options}
    url = f"{ia_base_url()}/chat/completions"
    for tentative in range(1, tentatives + 1):
        try:
            with verrou:
                reponse = _poster(url, corps, _entetes(), ia_delai_s())
        except httpx.HTTPError as err:
            erreur, a_retenter = classer_exception(err, modele)
        else:
            if reponse.status_code < 400:
                return _contenu(reponse)
            erreur, a_retenter = classer_statut(reponse, modele)
        if not a_retenter or tentative >= tentatives:
            raise erreur
        secondes = attente(tentative)
        if on_attente:
            on_attente(tentative, tentatives, secondes)
        time.sleep(secondes)


def lister_modeles() -> list[str]:
    """Identifiants des modèles du serveur (GET <IA_BASE_URL>/models).
    IAInjoignable si le serveur ne répond pas, ErreurIA sinon."""
    try:
        reponse = _obtenir(f"{ia_base_url()}/models", _entetes(), 30)
    except httpx.HTTPError as err:
        raise classer_exception(err, "(liste des modèles)")[0] from None
    if reponse.status_code >= 400:
        raise classer_statut(reponse, "(liste des modèles)")[0]
    try:
        return sorted({m["id"] for m in reponse.json().get("data") or [] if m.get("id")})
    except (ValueError, AttributeError, TypeError):
        raise ErreurIAPassagere("Liste des modèles illisible") from None


def reponse_json(texte: str) -> dict:
    """Objet JSON d'une réponse (blocs ```json tolérés) ; ErreurIAPassagere s'il est illisible."""
    try:
        donnees = json.loads(re.sub(r"```(?:json)?\s*", "", texte or "").strip())
    except ValueError:
        raise ErreurIAPassagere("Réponse de l'IA illisible (JSON attendu)") from None
    if not isinstance(donnees, dict):
        raise ErreurIAPassagere("Réponse de l'IA illisible (objet JSON attendu)")
    return donnees
