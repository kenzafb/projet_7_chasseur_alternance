import base64
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from connexion import connecter_gmail
from pdf_generator import generer_pdf_lettre
from profil import PROFIL

CV_PATH = "CV_Kenza_Filali-Bouami.pdf"


def envoyer_candidature(offre, lettre, email_texte, destinataire, objet=""):
    service = connecter_gmail()
    p = PROFIL

    if not objet:
        objet = f"Candidature alternance — {p['prenom']} {p['nom']}"

    # Le corps c'est tout le texte de l'email (sans la ligne objet si elle y est)
    lignes = email_texte.strip().split("\n")
    corps_lignes = []
    i = 0
    for idx, ligne in enumerate(lignes):
        if ligne.lower().startswith("objet :") or ligne.lower().startswith("objet:"):
            i = idx + 1
            break
    while i < len(lignes) and lignes[i].strip() == "":
        i += 1
    corps_lignes = lignes[i:]
    corps = "\n".join(corps_lignes).strip()
    if not corps:
        corps = email_texte.strip()

    # Génération PDF lettre
    chemin_pdf = generer_pdf_lettre(offre, lettre)

    # Construction MIME
    message = MIMEMultipart()
    message["to"] = destinataire
    message["from"] = p["email"]
    message["subject"] = objet
    message.attach(MIMEText(corps, "plain", "utf-8"))

    # PJ 1 : lettre PDF
    nom_lettre = f"Lettre_motivation_{p['prenom']}_{p['nom']}.pdf"
    with open(chemin_pdf, "rb") as f:
        pdf_lettre = MIMEApplication(f.read(), _subtype="pdf")
        pdf_lettre.add_header("Content-Disposition", "attachment", filename=nom_lettre)
        message.attach(pdf_lettre)

    # PJ 2 : CV PDF
    if os.path.exists(CV_PATH):
        with open(CV_PATH, "rb") as f:
            pdf_cv = MIMEApplication(f.read(), _subtype="pdf")
            pdf_cv.add_header("Content-Disposition", "attachment", filename=f"CV_{p['prenom']}_{p['nom']}.pdf")
            message.attach(pdf_cv)
    else:
        print(f"  CV introuvable : {CV_PATH}")

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    try:
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"  Candidature envoyee a : {destinataire}")
        return True
    except Exception as e:
        print(f"  Erreur envoi : {e}")
        return False
