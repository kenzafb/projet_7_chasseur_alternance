"""
envoyeur.py
===========
Depuis Flask :
  from spontanees.envoyeur import main as env_main
  env_main(limite=10, test=True, stop_event=event, log_fn=log)

CLI :
  python -m spontanees.envoyeur --limite 10 --test

Système de déduplication :
  - Au démarrage : charge data/emails_deja_envoyes.json (généré par fetch_envoyes_gmail.py)
    + les emails déjà trackés dans entreprises_enrichies.json
  - À chaque envoi réussi : met à jour emails_deja_envoyes.json immédiatement
  - Si une entreprise a 2 emails et qu'un seul a déjà été contacté,
    le mail est envoyé uniquement à l'autre
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

FICHIER_JSON          = "/home/kenza/Bureau/chasseur_alternance/data/entreprises_enrichies.json"
FICHIER_EMAILS_ENVOYES = "/home/kenza/Bureau/chasseur_alternance/data/emails_deja_envoyes.json"
CV_PATH               = "/home/kenza/Bureau/chasseur_alternance/assets/CV_Kenza_Filali-Bouami.pdf"
PLAQUETTE_PATH        = "/home/kenza/Bureau/chasseur_alternance/assets/Programme_DEUST_IOSI.pdf"
RECO_PATH             = "/home/kenza/Bureau/chasseur_alternance/assets/Lettre_Recommandation_Kenza_Filali-Bouami.pdf"

GMAIL_SENDER      = os.getenv("GMAIL_SENDER", "")
GMAIL_PASSWORD    = os.getenv("GMAIL_APP_PASSWORD", "")

SUJET_FIXE        = "Candidature spontanée en alternance"
LIMITE_PAR_RUN    = 50
PAUSE_ENTRE_MAILS = (30, 90)
SAUVEGARDE_TOUS   = 10

MAIL_TEMPLATE = """\
Bonjour,

Je me permets de vous adresser une candidature spontanée en alternance à partir de la rentrée 2026.

Actuellement en formation, je recherche une entreprise où mettre en pratique mes compétences et m'investir sur la durée. Mon parcours et ma motivation m'amènent à vouloir contribuer concrètement au sein de votre équipe.

Vous trouverez mon CV en pièce jointe. Je reste à votre disposition pour tout échange.

Cordialement,
"""


# ─── Gestion du fichier emails_deja_envoyes.json ─────────────────────────────

def charger_emails_deja_envoyes():
    """
    Charge le fichier de déduplication Gmail (généré par fetch_envoyes_gmail.py).
    Retourne un set vide si le fichier n'existe pas encore.
    """
    if os.path.exists(FICHIER_EMAILS_ENVOYES):
        with open(FICHIER_EMAILS_ENVOYES, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(addr.lower().strip() for addr in data if addr)
    return set()


def ajouter_emails_envoyes(nouveaux_emails: list[str]):
    """
    Ajoute les nouveaux emails au fichier de déduplication.
    Appelé après chaque envoi réussi.
    """
    existants = charger_emails_deja_envoyes()
    existants.update(addr.lower().strip() for addr in nouveaux_emails if addr)
    os.makedirs(os.path.dirname(FICHIER_EMAILS_ENVOYES), exist_ok=True)
    with open(FICHIER_EMAILS_ENVOYES, "w", encoding="utf-8") as f:
        json.dump(sorted(existants), f, ensure_ascii=False, indent=2)


# ─── Chargement / sauvegarde JSON entreprises ────────────────────────────────

from database.entreprises_db import lire_entreprises, sauvegarder_entreprises

# Utilisateur pour lequel l'envoyeur travaille (défini au lancement).
# 1 = Kenza (la crontab). Surchargeable via --user en CLI.
def charger_json(user_id):
    """Lit les entreprises de l'utilisateur depuis la BASE."""
    return lire_entreprises(user_id)


def sauvegarder_json(user_id, data):
    """Réécrit les modifications (mail_envoye, etc.) en BASE pour l'utilisateur."""
    sauvegarder_entreprises(user_id, data)


# ─── Envoi mail ───────────────────────────────────────────────────────────────

def joindre_pdf(msg, path, filename):
    try:
        with open(path, "rb") as f:
            part = MIMEBase("application", "pdf")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)
        return True
    except FileNotFoundError:
        return False


def envoyer_mail(destinataires: list[str], corps: str, pieces_jointes=None, log_fn=print) -> bool:
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = ", ".join(destinataires)
    msg["Subject"] = SUJET_FIXE
    msg.attach(MIMEText(corps, "plain", "utf-8"))

    # Joindre les pièces jointes du profil de l'utilisateur
    import os as _os
    for pj in (pieces_jointes or []):
        chemin = pj.get("fichier", "")
        if not chemin or not _os.path.exists(chemin):
            log_fn(f"    [!] Pièce '{pj.get('nom','?')}' introuvable — ignorée")
            continue
        base = (pj.get("nom", "document") or "document").strip().replace(" ", "_")
        nom_affiche = base if base.lower().endswith(".pdf") else base + ".pdf"
        joindre_pdf(msg, chemin, nom_affiche)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, destinataires, msg.as_string())
        return True
    except Exception as e:
        log_fn(f"    [❌] Erreur SMTP : {e}")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(limite=LIMITE_PAR_RUN, test=False, stop_event=None, log_fn=None, user_id=1, on_progress=None, mode="alternance"):
    _log = log_fn or print

    _log(f"Envoyeur | limite={limite} | test={test}")

    # Profil de l'utilisateur : son mail type (fallback sur MAIL_TEMPLATE)
    from database.profil_db import lire_profil
    _profil = lire_profil(user_id, mode=mode)
    corps_mail = (_profil.get("email_type") or "").strip() or MAIL_TEMPLATE
    pieces_profil = _profil.get("pieces_jointes", [])

    if not GMAIL_PASSWORD:
        _log("❌ GMAIL_APP_PASSWORD manquant dans .env")
        return
    if not GMAIL_SENDER:
        _log("❌ GMAIL_SENDER manquant dans .env")
        return

    entreprises = charger_json(user_id)

    # ── Déduplication : fusion fichier Gmail + champ mail_destinataires ───────
    emails_deja_envoyes = charger_emails_deja_envoyes()
    nb_gmail = len(emails_deja_envoyes)

    # Ajoute aussi ce qui est tracké dans le JSON (au cas où)
    for e in entreprises:
        if e.get("mail_envoye") and e.get("mail_destinataires"):
            for addr in e["mail_destinataires"]:
                emails_deja_envoyes.add(addr.lower().strip())

    _log(f"Déduplication : {nb_gmail} emails depuis Gmail + "
         f"{len(emails_deja_envoyes) - nb_gmail} depuis le JSON "
         f"= {len(emails_deja_envoyes)} total")

    if not os.path.exists(FICHIER_EMAILS_ENVOYES):
        _log(f"  ⚠️  {FICHIER_EMAILS_ENVOYES} introuvable — "
             f"lance fetch_envoyes_gmail.py pour initialiser la déduplication Gmail")

    # ── Queue ─────────────────────────────────────────────────────────────────
    a_envoyer = [
        e for e in entreprises
        if e.get("emails_trouves") and not e.get("mail_envoye")
    ]

    deja_envoyes = sum(1 for e in entreprises if e.get("mail_envoye"))
    _log(f"Queue : {len(a_envoyer)} à envoyer | {deja_envoyes} déjà envoyés")

    if not a_envoyer:
        _log("✅ Rien à envoyer.")
        return

    envoyes = 0
    echecs  = 0
    traites = 0

    for e in entreprises:
        if stop_event and stop_event.is_set():
            _log("⏹️  Arrêt — sauvegarde en cours...")
            sauvegarder_json(user_id, entreprises)
            return

        if envoyes >= limite:
            _log(f"⏹️  Limite de {limite} mails atteinte.")
            break

        if not e.get("emails_trouves") or e.get("mail_envoye"):
            continue

        nom = (e.get("nom_commercial") or e.get("nom", "?"))[:50]

        # ── Déduplication : ne garder que les emails pas encore contactés ─────
        emails_bruts = e.get("emails_trouves", [])
        emails_uniques = list(dict.fromkeys(
            addr.lower().strip() for addr in emails_bruts
            if addr and addr.strip()
        ))
        emails_nouveaux = [
            addr for addr in emails_uniques
            if addr not in emails_deja_envoyes
        ]

        if not emails_nouveaux:
            _log(f"  ⏭️  {nom} — tous les emails déjà contactés, skip")
            # Marquer quand même comme traité pour ne plus y revenir
            e["mail_envoye"]        = True
            e["mail_envoye_le"]     = datetime.today().strftime("%Y-%m-%d %H:%M")
            e["mail_destinataires"] = []
            e["mail_note"]          = "skip — tous emails déjà contactés"
            continue

        nb_ignores = len(emails_uniques) - len(emails_nouveaux)
        if nb_ignores > 0:
            _log(f"  ℹ️  {nb_ignores} email(s) ignoré(s) (déjà contactés)")

        destinataires = [GMAIL_SENDER] if test else emails_nouveaux

        idx   = deja_envoyes + traites + 1
        total = deja_envoyes + len(a_envoyer)
        _log(f"[{idx}/{total}] {nom} → {', '.join(destinataires)}")

        ok = envoyer_mail(destinataires, corps_mail, pieces_jointes=pieces_profil, log_fn=_log)

        if ok:
            _log(f"  ✅ Envoyé à {len(destinataires)} adresse(s)")
            if not test:
                e["mail_envoye"]        = True
                e["mail_envoye_le"]     = datetime.today().strftime("%Y-%m-%d %H:%M")
                e["mail_destinataires"] = destinataires

                # Mise à jour immédiate du fichier de déduplication
                ajouter_emails_envoyes(destinataires)
                for addr in destinataires:
                    emails_deja_envoyes.add(addr)

            envoyes += 1
            _total_envoi = min(len(a_envoyer), limite)
            if on_progress and _total_envoi:
                _pct = round(envoyes / _total_envoi * 100)
                on_progress(min(_pct, 100), f"{envoyes}/{_total_envoi} mails envoyés")
        else:
            _log(f"  ❌ Échec envoi")
            echecs += 1

        traites += 1

        if traites % SAUVEGARDE_TOUS == 0:
            sauvegarder_json(user_id, entreprises)
            avec = sum(1 for x in entreprises if x.get("emails_trouves"))
            _log(f"  💾 Sauvegarde — {envoyes} envoyés, {echecs} échecs")

        if envoyes < limite and traites < len(a_envoyer):
            if not (stop_event and stop_event.is_set()):
                pause = random.uniform(*PAUSE_ENTRE_MAILS)
                _log(f"  ⏸️  Pause {pause:.0f}s...")
                time.sleep(pause)

    sauvegarder_json(user_id, entreprises)
    _log(f"✅ Envoi terminé — {envoyes} envoyés, {echecs} échecs")
    _log(f"   Emails dans la base de dédup : {len(emails_deja_envoyes)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limite", type=int, default=LIMITE_PAR_RUN)
    parser.add_argument("--test",   action="store_true")
    parser.add_argument("--user",   type=int, default=1,
                        help="ID de l'utilisateur pour lequel envoyer (défaut: 1)")
    args = parser.parse_args()
    main(limite=args.limite, test=args.test, user_id=args.user)
