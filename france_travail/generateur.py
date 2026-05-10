import re
import os
import json
from datetime import datetime
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

# ─── Lettre de motivation fixe ────────────────────────────────────────────────
# Seuls {contact_entreprise} et {paragraphe_entreprise} sont générés par l'IA.
# Tout le reste est rédigé par Kenza et ne change jamais.

LETTRE_TEMPLATE = """\
{contact_entreprise}

Paris, le {date}

Objet : Candidature alternance DevOps / SysAdmin / Sécurité — septembre 2026

Madame, Monsieur,

Actuellement en fin de Diplôme de Spécialisation Professionnelle DevOps au Conservatoire National des Arts et Métiers de Paris, je prépare mon entrée en deuxième année de DEUST Informatique d'Organisation et Systèmes d'Information en septembre 2026, en alternance au rythme d'une semaine sur deux. C'est dans ce cadre que je vous adresse ma candidature pour un poste de technicienne en administration système, réseaux ou DevOps.

Ma formation au CNAM m'a permis de construire des bases solides en administration Linux, en scripting Bash et Python, en réseaux TCP/IP et en sécurité. La deuxième année du DEUST que je rejoins approfondira ces compétences avec des modules en programmation orientée objet, administration système et réseau avancée, bases de données et sécurité applicative. Ce double cursus m'offre à la fois un ancrage technique progressif et une expérience professionnelle continue, deux dimensions que je cherche à mettre au service d'une équipe dès la rentrée.

Lors de mon stage de deux mois au Garage Numérique, association d'inclusion numérique du 20ème arrondissement de Paris, j'ai installé et configuré des systèmes Linux sur des machines destinées au public, rédigé de la documentation technique et contribué au développement de deux sites web intégrant des pipelines d'intelligence artificielle. J'y ai également conçu de façon entièrement autonome le Chasseur d'Alternance, un outil Python qui interroge l'API France Travail, analyse les offres avec un LLM via Google Cloud et génère des candidatures personnalisées. En dehors du stage, j'ai développé plusieurs projets personnels, dont un système de gestion de parc informatique avec collecte automatisée de données système, une stack conteneurisée sous Docker Compose avec reverse proxy et interface web, et un outil CLI de gestion de fichiers YAML avec validation des images via l'API Docker Hub. Ces projets, disponibles sur mon GitHub, témoignent d'une approche concrète et d'un goût réel pour l'automatisation.

{paragraphe_entreprise}

Disponible en alternance dès septembre 2026 au rythme d'une semaine en entreprise et une semaine en formation, je serais ravie de vous présenter mon parcours plus en détail lors d'un entretien.

Je vous adresse, Madame, Monsieur, mes sincères salutations.

Kenza Filali-Bouami
"""


def _date_du_jour():
    mois = ["janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    today = datetime.today()
    return f"{today.day} {mois[today.month - 1]} {today.year}"


def generer_lettre(offre):
    """
    Demande à Gemini uniquement :
    1. Le bloc contact de l'entreprise (coin haut droit de la lettre)
    2. Le paragraphe de personnalisation (~3 phrases max)

    Assemble ensuite la lettre complète avec le template fixe.
    """
    p = PROFIL
    nom_entreprise = offre.get("entreprise", "")
    titre_poste    = offre.get("titre", "")
    lieu           = offre.get("lieu", "")
    description    = (offre.get("description", "") or "")[:800]  # tronquer pour le prompt

    prompt = (
        "Tu aides une candidate à personnaliser sa lettre de motivation.\n\n"
        "MISSION : Génère UNIQUEMENT deux éléments en JSON, rien d'autre.\n\n"
        f"ENTREPRISE : {nom_entreprise} — {lieu}\n"
        f"POSTE : {titre_poste}\n"
        f"DESCRIPTION : {description}\n\n"

        "1. CONTACT_ENTREPRISE : le bloc destinataire à afficher en haut à droite de la lettre.\n"
        "   Format sur 2-3 lignes : nom de l'entreprise, puis ville et/ou adresse si connue.\n"
        "   Exemple : \"ACME Solutions\\n75010 Paris\"\n"
        "   Si l'adresse est inconnue, mets uniquement le nom et la ville déduite du lieu.\n\n"

        "2. PARAGRAPHE_ENTREPRISE : UN paragraphe de 2 à 3 phrases MAXIMUM.\n"
        "   Règles impératives :\n"
        "   - Ne commence PAS par 'Je' — commence par le nom de l'entreprise, 'Votre', 'C'est', etc.\n"
        "   - Montre un intérêt spécifique pour cette entreprise (secteur, missions, taille, réputation).\n"
        "   - Relie les compétences de la candidate (Linux, Docker, Python, sécurité) au contexte de l'offre.\n"
        "   - Ton naturel et direct, pas de superlatifs, pas de formulations IA génériques.\n"
        "   - 350 caractères maximum.\n"
        "   - Ne répète pas ce qui est déjà dans la lettre (formations, projets, disponibilité).\n"
        "   - Le style doit être cohérent avec une lettre formelle en français.\n\n"

        "Réponds UNIQUEMENT en JSON valide sans backticks :\n"
        "{\"contact_entreprise\": \"...\", \"paragraphe_entreprise\": \"...\"}"
    )

    try:
        response = client.models.generate_content(
            model=MODELE_LETTRE,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=1000,
                response_mime_type="application/json",
                temperature=0.6,
            )
        )
        texte = re.sub(r'```json\s*', '', response.text)
        texte = re.sub(r'```\s*', '', texte).strip()
        result = json_parse(texte)

        contact     = result.get("contact_entreprise", nom_entreprise)
        paragraphe  = result.get("paragraphe_entreprise", "")

    except Exception as e:
        print(f"  Erreur génération IA : {e}")
        contact    = nom_entreprise
        paragraphe = ""

    lettre = LETTRE_TEMPLATE.format(
        contact_entreprise=contact,
        date=_date_du_jour(),
        paragraphe_entreprise=paragraphe,
    )
    return lettre


def json_parse(texte):
    """Parse JSON avec fallback propre."""
    try:
        return json.loads(texte)
    except Exception:
        return {}
