"""
envoyeur.py
===========
Pour chaque entreprise avec lettre_generee=true et mail_envoye=false,
génère le docx personnalisé, l'attache avec le CV et envoie le mail.

Lancement : python envoyeur.py
Lancement limité : python envoyeur.py --limite 10
"""

import json
import os
import io
import time
import random
import smtplib
import argparse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from dotenv import load_dotenv

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────

FICHIER_JSON  = "data/entreprises_enrichies.json"
CV_PATH       = "assets/CV_Kenza_Filali-Bouami.pdf"
TEMPLATE_PATH = "assets/lettre_template_KENZA.docx"

GMAIL_SENDER     = os.getenv("GMAIL_SENDER", "kenzafilbou@gmail.com")
GMAIL_PASSWORD   = os.getenv("GMAIL_APP_PASSWORD", "")

LIMITE_PAR_RUN   = 50          # max mails par lancement
PAUSE_ENTRE_MAILS = (30, 90)   # secondes (humain et anti-spam)
SAUVEGARDE_TOUS  = 10

# ─── Helpers JSON ─────────────────────────────────────────────────────────────

def charger_json():
    with open(FICHIER_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_json(data):
    with open(FICHIER_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Génération du DOCX personnalisé ─────────────────────────────────────────

def generer_docx(zones):
    """
    Charge le template, remplace les 4 balises {{...}} et retourne les bytes du docx.
    """
    doc = Document(TEMPLATE_PATH)

    remplacements = {
        "{{NOM_ENTREPRISE}}"        : zones.get("nom_entreprise", ""),
        "{{ADRESSE_ENTREPRISE}}"    : zones.get("adresse", ""),
        "{{DATE}}"                  : zones.get("date", ""),
        "{{OBJET_MAIL}}"            : zones.get("objet", ""),
        "{{PARAGRAPHE_PERSONNALISE}}": zones.get("paragraphe_personnalise", ""),
    }

    for para in doc.paragraphs:
        for balise, valeur in remplacements.items():
            if balise in para.text:
                # Remplacer en préservant le style du premier run
                for run in para.runs:
                    if balise in run.text:
                        run.text = run.text.replace(balise, valeur)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()

# ─── Construction du corps du mail ───────────────────────────────────────────

def corps_mail(zones):
    """Corps du mail court et professionnel."""
    nom_e = zones.get("nom_entreprise", "votre entreprise")
    return f"""\
Madame, Monsieur,

Je me permets de vous adresser ma candidature pour un contrat d'alternance \
en DevOps / SysAdmin / Sécurité à compter de septembre 2026, dans le cadre \
de ma 2ᵉ année de DEUST IOSI au CNAM Paris.

{zones.get("paragraphe_personnalise", "")}

Vous trouverez en pièce jointe mon curriculum vitae ainsi qu'une lettre de \
motivation détaillée.

Dans l'attente de votre retour, je reste disponible pour un entretien à votre \
convenance.

Cordialement,
Kenza FILALI-BOUAMI
07 50 87 21 76 | kenzafilbou@gmail.com | github.com/kenzafb
"""

# ─── Envoi du mail ────────────────────────────────────────────────────────────

def envoyer_mail(destinataire, sujet, corps, docx_bytes, nom_entreprise):
    """
    Envoie le mail avec le CV et la lettre en pièces jointes.
    Retourne True si succès, False sinon.
    """
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = destinataire
    msg["Subject"] = sujet

    # Corps texte
    msg.attach(MIMEText(corps, "plain", "utf-8"))

    # Pièce jointe 1 : CV PDF
    try:
        with open(CV_PATH, "rb") as f:
            cv_data = f.read()
        part_cv = MIMEBase("application", "pdf")
        part_cv.set_payload(cv_data)
        encoders.encode_base64(part_cv)
        part_cv.add_header(
            "Content-Disposition",
            "attachment",
            filename="CV_Kenza_Filali-Bouami.pdf"
        )
        msg.attach(part_cv)
    except FileNotFoundError:
        print(f"    [⚠️] CV introuvable : {CV_PATH}")
        return False

    # Pièce jointe 2 : Lettre DOCX
    nom_fichier = f"Lettre_Kenza_Filali-Bouami_{nom_entreprise[:30].replace(' ', '_')}.docx"
    part_lettre = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
    part_lettre.set_payload(docx_bytes)
    encoders.encode_base64(part_lettre)
    part_lettre.add_header(
        "Content-Disposition",
        "attachment",
        filename=nom_fichier
    )
    msg.attach(part_lettre)

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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limite", type=int, default=LIMITE_PAR_RUN,
                        help="Nombre maximum de mails à envoyer ce run")
    parser.add_argument("--test", action="store_true",
                        help="Mode test : envoie tout à kenzafilbou@gmail.com sans marquer mail_envoye")
    args = parser.parse_args()

    print("=" * 60)
    print("  Envoyeur — Chasseur d'Alternance")
    if args.test:
        print("  ⚠️  MODE TEST — tous les mails vont à", GMAIL_SENDER)
    print("=" * 60)

    if not GMAIL_PASSWORD:
        print("❌ GMAIL_APP_PASSWORD manquant dans .env")
        return

    entreprises = charger_json()

    a_envoyer = [
        e for e in entreprises
        if e.get("lettre_generee") and
           e.get("emails_trouves") and
           not e.get("mail_envoye")
    ]

    deja_envoyes = sum(1 for e in entreprises if e.get("mail_envoye"))
    print(f"[Queue] {len(a_envoyer)} à envoyer | {deja_envoyes} déjà envoyés")
    print(f"[Limite] {args.limite} mails ce run\n")

    if not a_envoyer:
        print("✅ Rien à envoyer.")
        return

    envoyes    = 0
    echecs     = 0
    traites    = 0

    for e in entreprises:
        if envoyes >= args.limite:
            print(f"\n⏹️  Limite de {args.limite} mails atteinte pour ce run.")
            break

        if not e.get("lettre_generee") or not e.get("emails_trouves") or e.get("mail_envoye"):
            continue

        nom       = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
        zones     = e.get("lettre_zones", {})
        emails    = e.get("emails_trouves", [])
        destinataire = GMAIL_SENDER if args.test else emails[0]

        idx = deja_envoyes + traites + 1
        total = deja_envoyes + len(a_envoyer)
        print(f"[{idx}/{total}] {nom}")
        print(f"  → {destinataire}")

        # Générer le docx
        try:
            docx_bytes = generer_docx(zones)
        except Exception as ex:
            print(f"  [❌] Erreur génération docx : {ex}")
            echecs += 1
            traites += 1
            continue

        # Corps et sujet du mail
        sujet = zones.get("objet", f"Candidature alternance DevOps – {nom}")
        corps = corps_mail(zones)

        # Envoi
        ok = envoyer_mail(destinataire, sujet, corps, docx_bytes, nom)

        if ok:
            print(f"  ✅ Envoyé")
            if not args.test:
                e["mail_envoye"]    = True
                e["mail_envoye_le"] = datetime.today().strftime("%Y-%m-%d %H:%M")
                e["mail_destinataire"] = destinataire
            envoyes += 1
        else:
            print(f"  ❌ Échec envoi")
            echecs += 1

        traites += 1

        # Sauvegarde intermédiaire
        if traites % SAUVEGARDE_TOUS == 0:
            sauvegarder_json(entreprises)
            print(f"\n  [💾 Sauvegarde — {envoyes} envoyés, {echecs} échecs]\n")

        # Pause anti-spam (sauf dernier)
        if envoyes < args.limite:
            pause = random.uniform(*PAUSE_ENTRE_MAILS)
            print(f"  ⏸️  Pause {pause:.0f}s...")
            time.sleep(pause)

    sauvegarder_json(entreprises)

    print("\n" + "=" * 60)
    print(f"  Envoyés  : {envoyes}")
    print(f"  Échecs   : {echecs}")
    print("=" * 60)
    if not args.test and envoyes > 0:
        print("\n→ Relance demain pour continuer le batch.")


if __name__ == "__main__":
    main()
