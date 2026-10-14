"""
shared/ia.py
============
Client d'IA unique du projet. Deux API (IA_API) :
  - ollama (défaut) : API native d'Ollama, POST <IA_BASE_URL>/api/chat
    (http://localhost:11434), avec "think": false au premier niveau de la
    requête, le schéma JSON dans "format", et dans "options" num_ctx
    (IA_NUM_CTX) et temperature ; keep_alive (IA_KEEP_ALIVE) au premier
    niveau, où Ollama le lit ;
  - openai : format compatible OpenAI, POST <IA_BASE_URL>/chat/completions
    (llama.cpp, LM Studio, vLLM, un service en ligne avec IA_API_KEY),
    schéma dans response_format, reasoning_effort "none".
Jamais "tools" et un format de sortie dans la même requête.

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
  - ReponseInvalide (ErreurIAPassagere) : réponse qui ne respecte pas le
    schéma JSON attendu, une fois retentée (appeler_structure).

Réponses structurées : appeler_structure(messages, Modele) impose le
schéma JSON du modèle Pydantic au serveur ("format" de l'API native,
response_format en OpenAI), puis valide la réponse avec ce modèle. Le mode
de réflexion des modèles qui en ont un est coupé ("think": false,
reasoning_effort "none" en OpenAI), sauf IA_REFLEXION=true.

Jamais de mode dégradé : un serveur qui refuse le schéma ou la coupure de
la réflexion, ou qui renvoie un texte de réflexion malgré elle, donne une
erreur bloquante avec un message clair. Avant le premier appel structuré
d'un modèle (dans le processus), un test de démarrage (verifier_demarrage)
envoie une requête courte avec un petit schéma : la réponse doit être un
objet JSON valide, sans rien autour ni texte de réflexion. Échec : erreur
bloquante, rien n'est analysé.

ANALYSE_IA=false (shared.config.analyse_ia_active) : appeler_ia lève
IADesactivee sans rien appeler.
"""

import json
import re
import threading
import time

import httpx
from pydantic import BaseModel, ValidationError

from shared.config import (IA_DELAI_CONNEXION_S, MESSAGE_IA_DESACTIVEE, analyse_ia_active, ia_api, ia_api_key,
                           ia_base_url, ia_delai_s, ia_keep_alive, ia_num_ctx, ia_reflexion,
                           modele_ia)

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


class ReponseInvalide(ErreurIAPassagere):
    """Réponse hors du schéma JSON attendu, même après un second essai."""


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


def _contenu(reponse: httpx.Response) -> tuple[str, str]:
    """(texte de la réponse, texte de réflexion éventuel). API native :
    message.content et message.thinking ; OpenAI : choices[0].message.content
    et reasoning_content. Un bloc <think>...</think> du texte compte comme
    réflexion et en est retiré."""
    try:
        donnees = reponse.json()
        message = donnees["message"] if ia_api() == "ollama" else donnees["choices"][0]["message"]
        texte = str(message["content"] or "")
    except (ValueError, KeyError, IndexError, TypeError):
        raise ErreurIAPassagere("Réponse du serveur d'IA illisible (format de l'API "
                                f"{ia_api()} attendu)") from None
    reflexion = " ".join(str(message.get(cle) or "") for cle in ("thinking", "reasoning_content", "reasoning"))
    reflexion += " ".join(re.findall(r"<think>(.*?)</think>", texte, flags=re.DOTALL))
    return re.sub(r"<think>.*?</think>", "", texte, flags=re.DOTALL).strip(), reflexion.strip()


def _requete(modele: str, messages, schema_json: dict | None, options: dict) -> tuple[str, dict, dict]:
    """(url, corps, facultatifs) de la requête selon IA_API. options :
    temperature, max_tokens. Les facultatifs (coupure de la réflexion,
    format de sortie) sont ajoutés au corps par _envoyer."""
    options = dict(options)
    if "tools" in options and schema_json is not None:
        raise ValueError("« tools » et un format de sortie ne s'envoient jamais ensemble.")
    temperature, max_tokens = options.pop("temperature", None), options.pop("max_tokens", None)
    base = ia_base_url()
    if ia_api() == "ollama":
        reglages = {"num_ctx": ia_num_ctx()}
        if temperature is not None:
            reglages["temperature"] = temperature
        if max_tokens:
            reglages["num_predict"] = max_tokens
        corps = {"model": modele, "messages": messages, "stream": False, "options": reglages,
                 "keep_alive": ia_keep_alive(), **options}
        facultatifs = {} if ia_reflexion() else {"think": False}
        if schema_json is not None:
            facultatifs["format"] = schema_json
        return f"{base}/api/chat", corps, facultatifs
    corps = {"model": modele, "messages": messages, "stream": False, **options}
    if temperature is not None:
        corps["temperature"] = temperature
    if max_tokens:
        corps["max_tokens"] = max_tokens
    facultatifs = {} if ia_reflexion() else {"reasoning_effort": "none"}
    if schema_json is not None:
        facultatifs["response_format"] = {"type": "json_schema",
                                          "json_schema": {"name": "reponse", "schema": schema_json, "strict": True}}
    return f"{base}/chat/completions", corps, facultatifs


# Mots qui, dans un refus du serveur (400 ou 422), désignent un des paramètres
# de sortie : le refus devient une erreur bloquante explicite, jamais un
# retrait du paramètre.
MOTS_DES_FACULTATIFS = {
    "think": ("think", "reasoning"),
    "format": ("format", "schema"),
    "reasoning_effort": ("reasoning", "think"),
    "response_format": ("response_format", "json_schema", "schema", "format"),
}


def _facultatif_refuse(reponse: httpx.Response, envoyes) -> str | None:
    """Paramètre de sortie envoyé que ce refus (400 ou 422) désigne, sinon None."""
    if reponse.status_code not in (400, 422):
        return None
    detail = _detail(reponse).lower()
    for nom in envoyes:
        if any(mot in detail for mot in MOTS_DES_FACULTATIFS.get(nom, (nom,))):
            return nom
    return None


def message_refus(parametre: str, modele: str, detail: str) -> str:
    if parametre in ("think", "reasoning_effort"):
        return (f"Le serveur d'IA refuse de couper la réflexion ({parametre}) avec « {modele} » : {detail}. "
                "Mets à jour Ollama ou choisis un autre modèle (IA_MODELE_<USAGE>) ; rien n'est analysé "
                "sans cette coupure.")
    return (f"Le serveur d'IA refuse le schéma JSON imposé ({parametre}) avec « {modele} » : {detail}. "
            "Mets à jour Ollama ou choisis un autre modèle ; rien n'est analysé sans schéma.")


def schema_json(schema: type[BaseModel]) -> dict:
    """Schéma JSON envoyé au serveur : celui du modèle Pydantic, ou celui
    qu'il construit lui-même (schema_ia, énumérations construites à la volée)."""
    construire = getattr(schema, "schema_ia", None)
    return construire() if construire else schema.model_json_schema()


def _envoyer(url: str, modele: str, corps: dict, facultatifs: dict) -> httpx.Response:
    """Un essai, sous le verrou commun. Un paramètre de sortie refusé :
    ErreurIABloquante explicite (aucun retrait silencieux)."""
    with verrou:
        reponse = _poster(url, {**corps, **facultatifs}, _entetes(), ia_delai_s())
    refuse = _facultatif_refuse(reponse, facultatifs)
    if refuse:
        raise ErreurIABloquante(message_refus(refuse, modele, _detail(reponse)), reponse.status_code, modele)
    return reponse


def appeler_ia(messages, *, usage="analyse", modele=None, tentatives=2, attente=lambda n: 5 * n,
               on_attente=None, schema: type[BaseModel] | None = None, **options) -> str:
    """
    Envoie messages au modèle de l'usage (ou `modele`) et renvoie le texte de
    la réponse. Retente les erreurs passagères du serveur (429, 5xx, réseau).

    tentatives : nombre total d'essais (1 = pas de retry)
    attente    : fonction n° de tentative échouée -> secondes d'attente
    on_attente : callback (tentative, tentatives, secondes) avant chaque pause
    schema     : modèle Pydantic dont le schéma JSON est imposé à la sortie
    options    : temperature, max_tokens

    Lève ErreurIABloquante tout de suite (IAInjoignable si le serveur ne
    répond pas), ErreurIAPassagere une fois les tentatives épuisées.
    IADesactivee sans rien appeler si ANALYSE_IA=false.
    """
    if not analyse_ia_active():
        raise IADesactivee(MESSAGE_IA_DESACTIVEE)
    modele = modele or modele_ia(usage)
    url, corps, facultatifs = _requete(modele, messages, schema_json(schema) if schema else None, options)
    for tentative in range(1, tentatives + 1):
        try:
            reponse = _envoyer(url, modele, corps, facultatifs)
        except httpx.HTTPError as err:
            erreur, a_retenter = classer_exception(err, modele)
        else:
            if reponse.status_code < 400:
                texte, reflexion = _contenu(reponse)
                if reflexion and not ia_reflexion():
                    raise ErreurIABloquante(
                        f"La réflexion de « {modele} » n'est pas coupée malgré la demande (texte de réflexion "
                        "dans la réponse) : mets à jour Ollama ou choisis un autre modèle.", None, modele)
                return texte
            erreur, a_retenter = classer_statut(reponse, modele)
        if not a_retenter or tentative >= tentatives:
            raise erreur
        secondes = attente(tentative)
        if on_attente:
            on_attente(tentative, tentatives, secondes)
        time.sleep(secondes)


def _objet_json(texte: str):
    """Objet JSON d'un texte : tel quel, sans blocs ```json, ou entre la
    première accolade ouvrante et la dernière fermante."""
    texte = re.sub(r"```(?:json)?\s*", "", texte or "").strip()
    try:
        return json.loads(texte)
    except ValueError:
        debut, fin = texte.find("{"), texte.rfind("}")
        if 0 <= debut < fin:
            try:
                return json.loads(texte[debut:fin + 1])
            except ValueError:
                pass
    return None


def lire_structure(texte: str, schema: type[BaseModel]) -> BaseModel:
    """Réponse validée par le modèle Pydantic ; ReponseInvalide sinon."""
    donnees = _objet_json(texte)
    if not isinstance(donnees, dict):
        raise ReponseInvalide(f"Réponse de l'IA illisible (objet JSON {schema.__name__} attendu)")
    try:
        return schema.model_validate(donnees)
    except ValidationError as err:
        champs = ", ".join(sorted({".".join(map(str, e["loc"])) or "?" for e in err.errors()}))
        raise ReponseInvalide(f"Réponse de l'IA hors du schéma {schema.__name__} (champs : {champs})") from None


class TestDemarrage(BaseModel):
    """Petit schéma du test de démarrage."""
    nombre: int
    mot: str


MESSAGES_DEMARRAGE = [
    {"role": "system", "content": "Tu réponds uniquement par un objet JSON valide, sans texte autour."},
    {"role": "user", "content": "TEST DE DÉMARRAGE. Réponds avec l'objet JSON où nombre vaut 7 et mot vaut \"ok\"."},
]

# Modèles qui ont passé le test de démarrage dans ce processus : (API, serveur, modèle)
_verifies: set[tuple[str, str, str]] = set()


def verifier_demarrage(modele: str | None = None, usage: str = "analyse") -> float:
    """Test de démarrage d'un modèle : requête courte avec un petit schéma,
    réponse qui doit être un objet JSON valide tel quel, sans texte autour
    ni réflexion. Retourne sa durée (secondes ; 0 s'il a déjà réussi dans ce
    processus). Échec : ErreurIABloquante avec la raison (IAInjoignable si
    le serveur ne répond pas)."""
    modele = modele or modele_ia(usage)
    cle = (ia_api(), ia_base_url(), modele)
    if cle in _verifies:
        return 0.0
    debut = time.monotonic()
    texte = appeler_ia(MESSAGES_DEMARRAGE, modele=modele, tentatives=1, schema=TestDemarrage, temperature=0,
                       max_tokens=50)
    try:
        TestDemarrage.model_validate(json.loads(texte))
    except (ValueError, ValidationError):
        raise ErreurIABloquante(
            f"Test de démarrage échoué avec « {modele} » : la réponse n'est pas l'objet JSON demandé "
            f"(« {texte[:80]} »). Le serveur n'applique pas le schéma : mets à jour Ollama ou choisis un "
            "autre modèle ; rien n'est analysé.", None, modele) from None
    _verifies.add(cle)
    return time.monotonic() - debut


def appeler_structure(messages, schema: type[BaseModel], *, usage="analyse", modele=None, essais=2,
                      **options) -> BaseModel:
    """appeler_ia avec le schéma JSON de `schema` imposé, réponse validée.
    Une réponse invalide est redemandée (essais au total, 2 par défaut),
    puis ReponseInvalide : l'élément est sauté, rien n'est inventé. Le test
    de démarrage du modèle passe avant son premier appel."""
    verifier_demarrage(modele, usage)
    for essai in range(1, essais + 1):
        texte = appeler_ia(messages, usage=usage, modele=modele, schema=schema, **options)
        try:
            return lire_structure(texte, schema)
        except ReponseInvalide as err:
            if essai >= essais:
                raise
            print(f"  ⚠️  {err} : nouvel essai.")


def lister_modeles() -> list[str]:
    """Identifiants des modèles du serveur (API native : GET /api/tags ;
    OpenAI : GET /models). IAInjoignable si le serveur ne répond pas."""
    native = ia_api() == "ollama"
    try:
        reponse = _obtenir(f"{ia_base_url()}/{'api/tags' if native else 'models'}", _entetes(), 30)
    except httpx.HTTPError as err:
        raise classer_exception(err, "(liste des modèles)")[0] from None
    if reponse.status_code >= 400:
        raise classer_statut(reponse, "(liste des modèles)")[0]
    try:
        donnees = reponse.json()
        if native:
            return sorted({m["name"] for m in donnees.get("models") or [] if m.get("name")})
        return sorted({m["id"] for m in donnees.get("data") or [] if m.get("id")})
    except (ValueError, AttributeError, TypeError, KeyError):
        raise ErreurIAPassagere("Liste des modèles illisible") from None
