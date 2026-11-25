"""
shared/telegram.py
==================
Messages et boutons de la campagne automatique par l'API Bot de Telegram
(D213) : sendMessage, getUpdates, answerCallbackQuery, editMessageReplyMarkup.
Aucun modèle d'IA, aucun serveur à ouvrir (interrogation longue).

Un clic n'est accepté que si son auteur ET la conversation sont
TELEGRAM_CHAT_ID (conversation privée) ; tout autre est ignoré. Le jeton du
bot est dans l'URL de l'API : aucune erreur de requests n'est relayée telle
quelle. Texte brut (pas de mise en forme) : un nom d'entreprise ne peut rien
y injecter.
"""

import os
from dataclasses import dataclass

import requests

from shared.journal import journaliser

LONGUEUR_MAX = 4000      # 4096 acceptés par Telegram
DELAI = 15               # secondes, en plus de l'attente de getUpdates


class ErreurTelegram(Exception):
    """Message sûr : ni jeton, ni URL."""


@dataclass
class Clic:
    id: str
    donnee: str
    message_id: int | None = None


def _poster(url: str, charge: dict, delai: float):
    """Seul accès réseau du module (remplacé dans les tests)."""
    return requests.post(url, json=charge, timeout=delai)


def decouper(texte: str) -> list[str]:
    """Texte en morceaux de LONGUEUR_MAX au plus, coupés entre deux lignes."""
    morceaux, actuel = [], ""
    for ligne in texte.split("\n"):
        ligne = ligne[:LONGUEUR_MAX]
        if actuel and len(actuel) + 1 + len(ligne) > LONGUEUR_MAX:
            morceaux.append(actuel)
            actuel = ligne
        else:
            actuel = f"{actuel}\n{ligne}" if actuel else ligne
    return [*morceaux, actuel]


class Telegram:
    def __init__(self, jeton: str, chat_id: str):
        self._jeton, self.chat_id = jeton, str(chat_id)
        self._suivant = None      # prochain update_id à lire

    def _appeler(self, methode: str, charge: dict, attente: float = 0):
        try:
            r = _poster(f"https://api.telegram.org/bot{self._jeton}/{methode}", charge, DELAI + attente)
            corps = r.json()
        except (requests.RequestException, ValueError) as e:
            raise ErreurTelegram(f"Telegram injoignable ({methode} : {type(e).__name__})") from None
        if not (isinstance(corps, dict) and corps.get("ok")):
            detail = str((corps or {}).get("description") if isinstance(corps, dict) else "")[:120]
            raise ErreurTelegram(f"Telegram refuse {methode} : {detail.replace(self._jeton, '***')}")
        return corps.get("result")

    def envoyer(self, texte: str, boutons=None) -> int:
        """Envoie le texte (en plusieurs messages s'il est long) ; boutons, une
        ligne de [(texte, donnée)], sous le dernier. Retourne son identifiant."""
        morceaux = decouper(texte)
        resultat = None
        for i, morceau in enumerate(morceaux):
            charge = {"chat_id": self.chat_id, "text": morceau, "disable_web_page_preview": True}
            if boutons and i == len(morceaux) - 1:
                charge["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in boutons]]}
            resultat = self._appeler("sendMessage", charge)
        return int((resultat or {}).get("message_id") or 0)

    def clics(self, attente: int = 0) -> list[Clic]:
        """Clics reçus depuis le dernier appel, de la bonne personne seulement.
        attente : secondes d'interrogation longue."""
        charge = {"timeout": attente, "allowed_updates": ["callback_query"]}
        if self._suivant is not None:
            charge["offset"] = self._suivant
        out = []
        for maj in self._appeler("getUpdates", charge, attente) or []:
            self._suivant = int(maj["update_id"]) + 1
            q = maj.get("callback_query")
            if not q:
                continue
            auteur = str((q.get("from") or {}).get("id") or "")
            chat = str(((q.get("message") or {}).get("chat") or {}).get("id") or "")
            if auteur != self.chat_id or chat != self.chat_id:
                journaliser("[Telegram] Clic ignoré : il ne vient pas de TELEGRAM_CHAT_ID.")
                continue
            out.append(Clic(str(q.get("id") or ""), str(q.get("data") or ""),
                            (q.get("message") or {}).get("message_id")))
        return out

    def confirmer_lecture(self):
        """Dit à Telegram que les clics lus le sont : ils ne reviendront pas au
        prochain lancement (avant une extinction)."""
        if self._suivant is not None:
            self._appeler("getUpdates", {"timeout": 0, "offset": self._suivant, "limit": 1,
                                         "allowed_updates": ["callback_query"]})

    def accuser(self, clic: Clic, texte: str = ""):
        self._appeler("answerCallbackQuery", {"callback_query_id": clic.id, "text": texte[:190]})

    def retirer_boutons(self, message_id: int):
        self._appeler("editMessageReplyMarkup", {"chat_id": self.chat_id, "message_id": message_id,
                                                 "reply_markup": {"inline_keyboard": []}})


def depuis_env() -> Telegram | None:
    """Client d'après TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID ; None si l'une
    manque. ErreurTelegram si l'identifiant n'est pas celui d'une personne."""
    jeton, chat = (os.getenv(v, "").strip() for v in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"))
    if not (jeton and chat):
        return None
    if not (chat.isascii() and chat.isdigit()):
        raise ErreurTelegram("TELEGRAM_CHAT_ID doit être ton identifiant personnel (un nombre positif), pas un groupe.")
    return Telegram(jeton, chat)
