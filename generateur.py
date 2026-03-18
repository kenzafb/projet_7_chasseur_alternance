import anthropic
import re
import os
from dotenv import load_dotenv
from profil import PROFIL

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODELE_LETTRE = "claude-sonnet-4-20250514"
MODELE_EMAIL = "claude-haiku-4-5-20251001"


def generer_lettre(offre):
    p = PROFIL
    projets = "\n".join([f"- {proj['nom']} ({proj['url']}) : {proj['description']}" for proj in p["projets"]])
    equivalent = "Note : le DSP DevOps CNAM couvre les mêmes compétences qu'un BTS SIO SISR (60 ECTS)." if offre.get("diplome_equivalent") else ""

    prompt = f"""Génère une lettre de motivation professionnelle en français pour ce poste.

CANDIDATE : {p['prenom']} {p['nom']} — {p['ville']} — {p['email']} — {p['github']}
Formation : Bac+1 DSP DevOps CNAM, intègre DEUST IOSI Bac+2 en alternance septembre 2026
Compétences : {', '.join(p['competences'])}
Expérience : {p['experience'].strip()}
Projets : {projets}
{equivalent}

Paragraphe personnel : {p['paragraphe_perso'].strip()}

OFFRE : {offre['titre']} — {offre['entreprise']} — {offre['lieu']}
{offre['description']}

Structure (- 2800 caractères maximum (environ 350-380 mots) — LIMITE STRICTE pour tenir sur une page A4) :
1. "Madame, Monsieur," + accroche liée au poste
2. Compétences techniques en lien direct avec l'offre (cite les technos de l'annonce)
3. 1-2 projets GitHub pertinents pour ce poste
4. Motivation personnelle (intègre le paragraphe perso naturellement)
5. Disponibilité septembre 2026 + invitation entretien
6. "{p['prenom']} {p['nom']}"

Contraintes : français sans fautes, féminin, sans markdown, sans en-tête, sans "Je me permets de"."""

    try:
        message = client.messages.create(
            model=MODELE_LETTRE,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        lettre = message.content[0].text.strip()
        return re.sub(r'\*\*(.*?)\*\*', r'\1', re.sub(r'#{1,6}\s', '', lettre))
    except Exception as e:
        print(f"  Erreur lettre : {e}")
        return "Erreur lors de la génération."


def generer_email(offre):
    p = PROFIL
    prompt = f"""Génère un email de candidature court en français (4-5 lignes).

Candidature de : {p['prenom']} {p['nom']} (féminin)
Poste : {offre['titre']} chez {offre['entreprise']}
Contacts : {p['email']} | {p['telephone']} | {p['linkedin']}

Format :
Objet : [accrocheur]
[ligne vide]
[corps 4-5 lignes : mentionner lettre jointe, donner envie de lire]
[coordonnées]

Sans markdown, sans "Je me permets de"."""

    try:
        message = client.messages.create(
            model=MODELE_EMAIL,
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}]
        )
        email = message.content[0].text.strip()
        return re.sub(r'\*\*(.*?)\*\*', r'\1', email)
    except Exception as e:
        print(f"  Erreur email : {e}")
        return "Erreur lors de la génération."
