"""
telegram_bot.py
===============
Bot Telegram pour contrôler le chasseur d'alternance depuis le téléphone.
Gemini comprend le langage naturel et appelle les routes Flask existantes.

Setup :
  1. pip install python-telegram-bot --break-system-packages
  2. Créer un bot via @BotFather sur Telegram → copier le token
  3. Récupérer ton Telegram user ID via @userinfobot
  4. Ajouter dans .env :
       TELEGRAM_BOT_TOKEN=xxxx:yyyy
       TELEGRAM_ALLOWED_ID=123456789   # ton ID numérique
  5. Lancer app.py Flask en premier, puis ce bot :
       python telegram_bot.py

Usage depuis Telegram (langage naturel) :
  "lance le scraper"
  "envoie 30 mails"
  "envoie 10 mails en mode test"
  "stats" / "où j'en suis" / "combien d'emails trouvés ?"
  "stop" / "arrête tout"
  "logs" / "qu'est-ce qui se passe"
  "c'est quoi le projet" / questions générales
"""

import os
import json
import logging
import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)

# ─── Config ───────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_ID = int(os.getenv("TELEGRAM_ALLOWED_ID", "0"))
FLASK_BASE          = os.getenv("FLASK_BASE_URL", "http://localhost:5002")

gemini_client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location="us-central1",
)

# ─── Prompt Gemini ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Tu es l'assistant personnel de Kenza qui contrôle son outil de recherche d'alternance depuis Telegram.

Contexte du projet :
- Kenza scrape des milliers d'entreprises IT en Île-de-France pour trouver leurs emails
- Elle envoie ensuite des candidatures spontanées (DevOps / Sysadmin, alternance septembre 2026)
- Le pipeline a 3 étapes : fetch (récupère les entreprises) → scraper (trouve les emails) → envoyeur (envoie les mails)
- Les données sont dans des fichiers JSON locaux

Tu reçois un message en langage naturel et retournes UNIQUEMENT un JSON avec l'action à effectuer.

Actions disponibles :
- "stats"            : statistiques globales (entreprises, emails trouvés, envoyés)
- "logs"             : derniers logs en temps réel
- "statut"           : état du pipeline en cours
- "start_fetch"      : lancer la récupération des entreprises
- "start_scraper"    : lancer le scraper d'emails
- "start_envoyeur"   : lancer l'envoi de mails. Params optionnels : limite (int, défaut 50), test (bool, défaut false)
- "stop"             : arrêter le processus en cours
- "chat"             : répondre à une question générale sur le projet

Format JSON attendu (exemples) :
{"action": "stats"}
{"action": "start_envoyeur", "limite": 30, "test": false}
{"action": "start_envoyeur", "limite": 10, "test": true}
{"action": "chat", "reponse": "Ta réponse ici"}

Mapping courant :
"lance le scraper" / "scraper" → start_scraper
"envoie X mails" → start_envoyeur avec limite=X
"envoie en test" / "mode test" → start_envoyeur test=true
"stats" / "où j'en suis" / "combien" → stats
"logs" / "qu'est-ce qui se passe" / "montre les logs" → logs
"stop" / "arrête" / "coupe" → stop
"statut" / "en cours ?" → statut
"fetch" / "récupère les entreprises" → start_fetch

Réponds UNIQUEMENT en JSON valide, sans backticks ni markdown.\
"""

# ─── Appels Flask ──────────────────────────────────────────────────────────────

def flask_get(path):
    try:
        r = requests.get(f"{FLASK_BASE}{path}", timeout=8)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, "❌ Flask non joignable — lance `python app.py` d'abord."
    except Exception as e:
        return None, f"❌ Erreur : {e}"


def flask_post(path, payload=None):
    try:
        r = requests.post(f"{FLASK_BASE}{path}", json=payload or {}, timeout=8)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, "❌ Flask non joignable — lance `python app.py` d'abord."
    except Exception as e:
        return None, f"❌ Erreur : {e}"


# ─── Formatage des réponses ────────────────────────────────────────────────────

def fmt_stats():
    data, err = flask_get("/api/spontanees/stats")
    if err:
        return err
    total      = data["raw"]
    avec       = data["avec_email"]
    envoyes    = data["mail_envoye"]
    en_cours   = data["en_cours"]
    pct_email  = round(avec / total * 100, 1) if total else 0
    pct_envoye = round(envoyes / avec * 100, 1) if avec else 0

    msg = (
        f"📊 *Statistiques chasseur*\n\n"
        f"🏢 Entreprises : `{total:,}`\n"
        f"📧 Avec email  : `{avec:,}` ({pct_email}%)\n"
        f"✉️  Envoyés     : `{envoyes:,}` ({pct_envoye}% des emails trouvés)\n"
        f"⚙️  Pipeline    : {'*En cours — ' + (data.get('etape') or '') + '*' if en_cours else 'Idle'}\n"
    )
    if en_cours and data.get("message"):
        msg += f"   ↳ _{data['message']}_\n"

    dernieres = data.get("dernieres", [])
    if dernieres:
        msg += "\n📨 *Derniers envois :*\n"
        for e in dernieres[-5:]:
            date = e["date"][:10] if e.get("date") else "?"
            msg += f"  • {e['nom']} — {date}\n"

    return msg


def fmt_logs():
    data, err = flask_get("/api/logs")
    if err:
        return err
    if not data:
        return "📋 Aucun log disponible."
    lignes = data[-20:]
    return "📋 *Derniers logs :*\n" + "\n".join(
        f"`{l['t']}` {l['msg']}" for l in lignes
    )


def fmt_statut():
    data, err = flask_get("/api/spontanees/statut")
    if err:
        return err
    if data.get("en_cours"):
        return (
            f"⚙️ *En cours : {data.get('etape', '?')}*\n"
            f"_{data.get('message', '')}_"
        )
    return f"✅ *Idle*\n_{data.get('message', 'Prêt')}_"


def fmt_start_scraper():
    data, err = flask_post("/api/spontanees/scraper")
    if err:
        return err
    if "erreur" in data:
        return f"⚠️ {data['erreur']}"
    return "▶️ *Scraper lancé !*\nRécupération des emails en cours…\nEnvoie `logs` pour suivre."


def fmt_start_fetch():
    data, err = flask_post("/api/spontanees/fetch")
    if err:
        return err
    if "erreur" in data:
        return f"⚠️ {data['erreur']}"
    return "▶️ *Fetch lancé !*\nRécupération des entreprises en cours…"


def fmt_start_envoyeur(limite=50, test=False):
    data, err = flask_post("/api/spontanees/envoyer", {"limite": limite, "test": test})
    if err:
        return err
    if "erreur" in data:
        return f"⚠️ {data['erreur']}"
    mode = " \\[MODE TEST — envoi à toi-même\\]" if test else ""
    return f"▶️ *Envoyeur lancé !*{mode}\nLimite : `{limite}` mails\nEnvoie `logs` pour suivre."


def fmt_stop():
    data, err = flask_post("/api/spontanees/stop")
    if err:
        return err
    return "⏹️ *Arrêt demandé*\nSauvegarde en cours…"


# ─── Appel Gemini ──────────────────────────────────────────────────────────────

def comprendre_intention(texte):
    """Envoie le message à Gemini et retourne le dict action."""
    response = gemini_client.models.generate_content(
        model="gemini-2.5-pro",
        contents=texte,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )
    raw = response.text.strip()
    return json.loads(raw)


# ─── Handler Telegram ─────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Sécurité : seul ton ID peut utiliser le bot
    if TELEGRAM_ALLOWED_ID and user_id != TELEGRAM_ALLOWED_ID:
        await update.message.reply_text("⛔ Accès non autorisé.")
        return

    texte = update.message.text.strip()
    await update.message.chat.send_action("typing")

    # Gemini comprend l'intention
    try:
        action_data = comprendre_intention(texte)
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur Gemini : {e}")
        return

    action = action_data.get("action", "chat")

    if action == "stats":
        reply = fmt_stats()
    elif action == "logs":
        reply = fmt_logs()
    elif action == "statut":
        reply = fmt_statut()
    elif action == "start_scraper":
        reply = fmt_start_scraper()
    elif action == "start_fetch":
        reply = fmt_start_fetch()
    elif action == "start_envoyeur":
        reply = fmt_start_envoyeur(
            limite=int(action_data.get("limite", 50)),
            test=bool(action_data.get("test", False)),
        )
    elif action == "stop":
        reply = fmt_stop()
    elif action == "chat":
        reply = action_data.get("reponse", "…")
    else:
        reply = f"❓ Action non reconnue : `{action}`"

    await update.message.reply_text(reply, parse_mode="Markdown")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Chasseur Alternance Bot*\n\n"
        "Parle-moi naturellement :\n"
        "• `stats` — voir les chiffres\n"
        "• `lance le scraper` — démarrer le scraping\n"
        "• `envoie 30 mails` — lancer l'envoyeur\n"
        "• `envoie 5 en mode test` — test sans vrai envoi\n"
        "• `stop` — arrêter ce qui tourne\n"
        "• `logs` — voir les logs en direct\n",
        parse_mode="Markdown",
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN manquant dans .env")
        return

    print(f"🤖 Bot Telegram démarré")
    print(f"   Flask attendu sur : {FLASK_BASE}")
    print(f"   ID autorisé       : {TELEGRAM_ALLOWED_ID or 'tous (dangereux !)'}")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
