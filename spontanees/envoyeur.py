"""
envoyeur.py
===========
Pour chaque entreprise avec mail_generee=true et mail_envoye=false,
envoie le mail de motivation avec CV et plaquette DEUST en pièces jointes.

Lancement CLI :
  python -m spontanees.envoyeur
  python -m spontanees.envoyeur --limite 10
  python -m spontanees.envoyeur --test

Depuis Flask :
  from spontanees.envoyeur import main as env_main
  env_main(limite=10, test=True)
"""

import json
import os
import time
import random
import smtplib
import argparse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────

FICHIER_JSON      = "data/entreprises_enrichies.json"
CV_PATH           = "assets/CV_Kenza_Filali-Bouami.pdf"
PLAQUETTE_PATH    = "assets/Programme_DEUST_IOSI.pdf"

GMAIL_SENDER      = os.getenv("GMAIL_SENDER", "")
GMAIL_PASSWORD    = os.getenv("GMAIL_APP_PASSWORD", "")

SUJET_FIXE        = "Alternance DevOps / SysAdmin — septembre 2026"
LIMITE_PAR_RUN    = 50
PAUSE_ENTRE_MAILS = (30, 90)   # secondes (anti-spam)
SAUVEGARDE_TOUS   = 10

# ─── Mail de motivation fixe ──────────────────────────────────────────────────
# {phrases_ia} est le seul endroit généré par Gemini (1-2 phrases, 200 car. max).
# Tout le reste est rédigé par Kenza et ne change jamais.

MAIL_TEMPLATE = """\
Bonjour,

Je me permets de vous contacter pour une candidature spontanée en alternance à partir de septembre 2026, au rythme d'une semaine en entreprise et une semaine en formation.

Je termine actuellement un Diplôme de Spécialisation DevOps au CNAM de Paris et j'intègre en septembre la deuxième année du DEUST Informatique, toujours au CNAM, en alternance. Mon quotidien tourne autour de Linux, Python, Docker, Bash et des réseaux — des compétences que j'ai eu l'occasion de mettre en pratique lors d'un stage de deux mois et à travers plusieurs projets personnels disponibles sur mon GitHub.

Je cherche une entreprise où je peux continuer à apprendre sur le terrain, contribuer concrètement, et m'investir sur la durée. {phrases_ia}

Vous trouverez en pièce jointe mon CV ainsi que la plaquette de la formation. Je suis disponible pour un échange si vous souhaitez en savoir plus.

Cordialement,

Kenza Filali-Bouami
kenzafilbou@gmail.com | 07 50 87 21 76
linkedin.com/in/kenza-filali-bouami | github.com/kenzafb\
"""

# ─── Helpers JSON ─────────────────────────────────────────────────────────────

def charger_json():
    with open(FICHIER_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def sauvegarder_json(data):
    with open(FICHIER_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Construction du corps du mail ────────────────────────────────────────────

def construire_corps(zones):
    phrases_ia = zones.get("phrases_ia", "").strip()
    return MAIL_TEMPLATE.format(phrases_ia=phrases_ia)


# ─── Envoi du mail ────────────────────────────────────────────────────────────

def envoyer_mail(destinataire, corps):
    """
    Envoie le mail avec CV et plaquette DEUST en pièces jointes.
    Retourne True si succès, False sinon.
    """
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = destinataire
    msg["Subject"] = SUJET_FIXE

    msg.attach(MIMEText(corps, "plain", "utf-8"))

    # Pièce jointe 1 : CV PDF
    try:
        with open(CV_PATH, "rb") as f:
            part_cv = MIMEBase("application", "pdf")
            part_cv.set_payload(f.read())
        encoders.encode_base64(part_cv)
        part_cv.add_header("Content-Disposition", "attachment",
                           filename="CV_Kenza_Filali-Bouami.pdf")
        msg.attach(part_cv)
    except FileNotFoundError:
        print(f"    [❌] CV introuvable : {CV_PATH}")
        return False

    # Pièce jointe 2 : Plaquette DEUST IOSI PDF
    try:
        with open(PLAQUETTE_PATH, "rb") as f:
            part_plaquette = MIMEBase("application", "pdf")
            part_plaquette.set_payload(f.read())
        encoders.encode_base64(part_plaquette)
        part_plaquette.add_header("Content-Disposition", "attachment",
                                  filename="Programme_DEUST_IOSI_CNAM.pdf")
        msg.attach(part_plaquette)
    except FileNotFoundError:
        print(f"    [⚠️] Plaquette introuvable : {PLAQUETTE_PATH} — envoi sans plaquette")

    # Envoi SMTP Gmail
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, destinataire, msg.as_string())
        return True
    except Exception as e:
        print(f"    [❌] Erreur SMTP : {e}")
        return False


# ─── Pipeline principal ────────────────────────────────────────────────────────

def main(limite=LIMITE_PAR_RUN, test=False):
    """
    Paramètres :
      limite (int) : nombre max de mails à envoyer ce run
      test   (bool): si True, envoie tout à GMAIL_SENDER sans marquer mail_envoye
    """
    print("=" * 60)
    print("  Envoyeur — Chasseur d'Alternance")
    if test:
        print(f"  ⚠️  MODE TEST — tous les mails vont à {GMAIL_SENDER}")
    print("=" * 60)

    if not GMAIL_PASSWORD:
        print("❌ GMAIL_APP_PASSWORD manquant dans .env")
        return
    if not GMAIL_SENDER:
        print("❌ GMAIL_SENDER manquant dans .env")
        return

    entreprises = charger_json()

    a_envoyer = [
        e for e in entreprises
        if e.get("mail_generee") and
           e.get("emails_trouves") and
           not e.get("mail_envoye")
    ]

    deja_envoyes = sum(1 for e in entreprises if e.get("mail_envoye"))
    print(f"[Queue] {len(a_envoyer)} à envoyer | {deja_envoyes} déjà envoyés")
    print(f"[Limite] {limite} mails ce run")
    print(f"[Sujet] {SUJET_FIXE}\n")

    if not a_envoyer:
        print("✅ Rien à envoyer.")
        return

    envoyes = 0
    echecs  = 0
    traites = 0

    for e in entreprises:
        if envoyes >= limite:
            print(f"\n⏹️  Limite de {limite} mails atteinte pour ce run.")
            break

        if not e.get("mail_generee") or not e.get("emails_trouves") or e.get("mail_envoye"):
            continue

        nom          = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
        zones        = e.get("mail_zones", {})
        destinataire = GMAIL_SENDER if test else e["emails_trouves"][0]

        idx   = deja_envoyes + traites + 1
        total = deja_envoyes + len(a_envoyer)
        print(f"[{idx}/{total}] {nom}")
        print(f"  → {destinataire}")

        corps = construire_corps(zones)
        ok    = envoyer_mail(destinataire, corps)

        if ok:
            print(f"  ✅ Envoyé")
            if not test:
                e["mail_envoye"]       = True
                e["mail_envoye_le"]    = datetime.today().strftime("%Y-%m-%d %H:%M")
                e["mail_destinataire"] = destinataire
            envoyes += 1
        else:
            print(f"  ❌ Échec envoi")
            echecs += 1

        traites += 1

        if traites % SAUVEGARDE_TOUS == 0:
            sauvegarder_json(entreprises)
            print(f"\n  [💾 Sauvegarde — {envoyes} envoyés, {echecs} échecs]\n")

        if envoyes < limite and traites < len(a_envoyer):
            pause = random.uniform(*PAUSE_ENTRE_MAILS)
            print(f"  ⏸️  Pause {pause:.0f}s...")
            time.sleep(pause)

    sauvegarder_json(entreprises)

    print("\n" + "=" * 60)
    print(f"  Envoyés  : {envoyes}")
    print(f"  Échecs   : {echecs}")
    print("=" * 60)
    if not test and envoyes > 0:
        print("\n→ Relance demain pour continuer le batch.")


# ─── Entrée CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limite", type=int, default=LIMITE_PAR_RUN)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    main(limite=args.limite, test=args.test)
