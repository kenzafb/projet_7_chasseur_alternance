import re
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from shared.profil import PROFIL

load_dotenv()

client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location="us-central1"
)
MODELE_LETTRE = "gemini-2.5-pro"
MODELE_EMAIL  = "gemini-2.5-flash"


def generer_lettre(offre):
    p = PROFIL
    projets = "\n".join([f"- {proj['nom']} ({proj['url']}) : {proj['description']}" for proj in p["projets"]])
    prompt = (
        "Redige une lettre de motivation professionnelle en francais pour ce poste.\n\n"
        f"CANDIDATE : {p['prenom']} {p['nom']} — {p['ville']} — {p['email']} — {p['github']}\n"
        f"Formation : Bac+1 DSP DevOps CNAM, integre DEUST IOSI Bac+2 en alternance septembre 2026\n"
        f"Competences : {', '.join(p['competences'])}\n"
        f"Experience : {p['experience'].strip()}\n"
        f"Projets :\n{projets}\n"
        f"Paragraphe personnel : {p['paragraphe_perso'].strip()}\n\n"
        f"OFFRE : {offre.get('titre', '')} — {offre.get('entreprise', '')} — {offre.get('lieu', '')}\n"
        f"Description : {offre.get('description', '')}\n\n"
        "Structure (2800 caracteres max, tenir sur une page A4) :\n"
        "1. 'Madame, Monsieur,' + accroche liee au poste ET a l entreprise\n"
        "2. Competences techniques en lien DIRECT avec l offre\n"
        "3. 1-2 projets GitHub les plus pertinents pour CE poste\n"
        "4. Motivation personnelle\n"
        "5. Disponibilite septembre 2026 + invitation entretien\n"
        f"6. '{p['prenom']} {p['nom']}'\n\n"
        "Contraintes : francais sans fautes, feminin, sans markdown, sans en-tete, sans 'Je me permets de'."
    )
    try:
        response = client.models.generate_content(
            model=MODELE_LETTRE,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=8000)
        )
        lettre = response.text.strip()
        return re.sub(r'\*\*(.*?)\*\*', r'\1', re.sub(r'#{1,6}\s', '', lettre))
    except Exception as e:
        print(f"  Erreur lettre : {e}")
        return "Erreur lors de la generation."


def generer_email(offre):
    p = PROFIL
    prompt = (
        f"Genere un email de candidature court en francais (4-5 lignes).\n\n"
        f"Candidature de : {p['prenom']} {p['nom']} (feminin)\n"
        f"Poste : {offre.get('titre', '')} chez {offre.get('entreprise', '')}\n"
        f"Contacts : {p['email']} | {p['telephone']} | {p['linkedin']}\n\n"
        "Format :\n"
        "Objet : [accrocheur]\n"
        "[ligne vide]\n"
        "[corps 4-5 lignes : mentionner lettre jointe, donner envie de lire]\n"
        "[coordonnees]\n\n"
        "Sans markdown, sans 'Je me permets de'."
    )
    try:
        response = client.models.generate_content(
            model=MODELE_EMAIL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=500)
        )
        email = response.text.strip()
        return re.sub(r'\*\*(.*?)\*\*', r'\1', email)
    except Exception as e:
        print(f"  Erreur email : {e}")
        return "Erreur lors de la generation."
