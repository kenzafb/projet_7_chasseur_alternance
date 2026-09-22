"""
fetch_envoyes_gmail.py
======================
Script one-shot : récupère tous les To: / Cc: de la boîte Envoyés Gmail
et les sauvegarde dans data/emails_deja_envoyes.json

Usage :
  python fetch_envoyes_gmail.py

À lancer une seule fois pour initialiser le fichier de déduplication,
avant de relancer envoyeur.py sur la nouvelle base.
"""

import imaplib
import email
from email.header import decode_header
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()

GMAIL_SENDER   = os.getenv("GMAIL_SENDER", "")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
FICHIER_SORTIE = "/home/kenza/Bureau/chasseur_alternance/data/emails_deja_envoyes.json"

# Noms possibles du dossier Envoyés selon la langue du compte Gmail
DOSSIERS_ENVOYES = [
    '"[Gmail]/Sent Mail"',
    '"[Gmail]/Messages envoy&AOk-s"',
    "[Gmail]/Sent Mail",
    "Sent",
    "Sent Items",
]


def decode_str(s):
    if not s:
        return ""
    try:
        decoded = decode_header(s)
        result = ""
        for part, charset in decoded:
            if isinstance(part, bytes):
                result += part.decode(charset or "utf-8", errors="replace")
            else:
                result += str(part)
        return result
    except Exception:
        return str(s)


def extraire_emails_header(header_value):
    if not header_value:
        return []
    emails = re.findall(
        r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
        header_value
    )
    return [e.lower().strip() for e in emails]


def charger_existants():
    if os.path.exists(FICHIER_SORTIE):
        with open(FICHIER_SORTIE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def sauvegarder(emails_set):
    os.makedirs(os.path.dirname(FICHIER_SORTIE), exist_ok=True)
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(sorted(emails_set), f, ensure_ascii=False, indent=2)
    print(f"  💾 Sauvegardé → {FICHIER_SORTIE}")


def main():
    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        print("❌ GMAIL_SENDER ou GMAIL_APP_PASSWORD manquant dans .env")
        return

    print(f"Connexion IMAP Gmail ({GMAIL_SENDER})...")

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(GMAIL_SENDER, GMAIL_PASSWORD)
        print("  ✅ Connecté")
    except Exception as e:
        print(f"❌ Erreur connexion : {e}")
        return

    # ── Sélection du dossier Envoyés ─────────────────────────────────────────
    dossier_ok = None
    for dossier in DOSSIERS_ENVOYES:
        status, _ = mail.select(dossier)
        if status == "OK":
            dossier_ok = dossier
            print(f"  📁 Dossier sélectionné : {dossier}")
            break

    if not dossier_ok:
        print("❌ Impossible de trouver le dossier Envoyés. Dossiers disponibles :")
        _, folders = mail.list()
        for f in folders:
            print("  ", f.decode(errors="replace"))
        mail.logout()
        return

    # ── Récupération des IDs ──────────────────────────────────────────────────
    _, data = mail.search(None, "ALL")
    ids = data[0].split()
    total = len(ids)
    print(f"  📬 {total} mails dans la boîte Envoyés")

    if total == 0:
        print("  Aucun mail trouvé.")
        mail.logout()
        return

    emails_existants = charger_existants()
    emails_trouves   = set(emails_existants)
    nouveaux         = 0

    print("  Lecture des headers...")

    for i, num in enumerate(ids, 1):
        if i % 200 == 0 or i == total:
            print(f"  {i}/{total} — {nouveaux} nouveaux emails trouvés")

        try:
            _, msg_data = mail.fetch(num, "(BODY[HEADER.FIELDS (TO CC)])")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if not raw:
                continue
            msg = email.message_from_bytes(raw)

            for header in ["To", "Cc"]:
                val = decode_str(msg.get(header, ""))
                for addr in extraire_emails_header(val):
                    # Ignorer son propre email
                    if addr == GMAIL_SENDER.lower():
                        continue
                    if addr not in emails_trouves:
                        emails_trouves.add(addr)
                        nouveaux += 1

        except Exception:
            continue

    mail.logout()
    sauvegarder(emails_trouves)

    print(f"\n✅ Terminé !")
    print(f"  Déjà connus au départ : {len(emails_existants)}")
    print(f"  Nouveaux ce run       : {nouveaux}")
    print(f"  Total dans le fichier : {len(emails_trouves)}")
    print(f"\n→ Tu peux maintenant lancer envoyeur.py en sécurité.")


if __name__ == "__main__":
    main()
