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

Ma formation au CNAM m'a permis de construire des bases solides en administration Linux, en scripting Bash et Python, en réseaux TCP/IP et en sécurité. La deuxième année du DEUST approfondira ces compétences avec des modules en programmation orientée objet, administration système et réseau avancée, bases de données et sécurité applicative.

Lors de mon stage au Garage Numérique, j'ai configuré des systèmes Linux, rédigé de la documentation technique et développé de façon autonome le Chasseur d'Alternance, un outil Python couplant l'API France Travail et un LLM via Google Cloud. Parmi mes projets personnels : une stack Docker Compose avec reverse proxy, un système de gestion de parc avec collecte automatisée, et un outil CLI de validation d'images via l'API Docker Hub. Ces projets sont disponibles sur mon GitHub.

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


def _nettoyer_contact(contact):
    """
    Supprime les lignes parasites qu'un LLM peut glisser dans le bloc contact :
    dates, lignes "Objet :", formules de politesse, etc.
    Ne garde que les 3 premières lignes utiles au maximum.
    """
    PARASITES = re.compile(
        r'(?i)^(paris\s*,?\s*le|objet\s*:|madame|monsieur|le\s+\d|'
        r'candidature|cordialement|sincères|bonjour|\d{1,2}\s+\w+\s+20\d{2})',
    )
    lignes = [l.strip() for l in contact.splitlines() if l.strip()]
    lignes_propres = [l for l in lignes if not PARASITES.match(l)]
    return "\n".join(lignes_propres[:3]).strip()


def generer_lettre(offre):
    """
    Demande à Gemini uniquement :
    1. Le bloc contact de l'entreprise (coin haut gauche de la lettre)
    2. Le paragraphe de personnalisation (~3 phrases max)

    Assemble ensuite la lettre complète avec le template fixe.
    """
    nom_entreprise = offre.get("entreprise", "")
    titre_poste    = offre.get("titre", "")
    lieu           = offre.get("lieu", "")
    description    = (offre.get("description", "") or "")[:800]

    prompt = (
        "Tu aides une candidate à personnaliser sa lettre de motivation.\n\n"
        "MISSION : Génère UNIQUEMENT deux éléments en JSON, rien d'autre.\n\n"
        f"ENTREPRISE : {nom_entreprise} — {lieu}\n"
        f"POSTE : {titre_poste}\n"
        f"DESCRIPTION : {description}\n\n"

        "1. CONTACT_ENTREPRISE : le bloc destinataire, 2-3 lignes maximum.\n"
        "   Format : nom de l'entreprise sur la première ligne, puis ville ou adresse.\n"
        "   Exemple : \"ACME Solutions\\n75010 Paris\"\n"
        "   ⚠️ INTERDIT : ne mets JAMAIS de date, de ligne 'Objet :', de formule\n"
        "   de politesse, de 'Paris, le', ni aucun autre élément de la lettre.\n"
        "   UNIQUEMENT le nom et la ville, rien d'autre.\n\n"

        "2. PARAGRAPHE_ENTREPRISE : UN paragraphe de 2 à 3 phrases MAXIMUM.\n"
        "   Règles impératives :\n"
        "   - Ne commence PAS par 'Je' — commence par le nom de l'entreprise, 'Votre', 'C'est', etc.\n"
        "   - Montre un intérêt spécifique pour cette entreprise (secteur, missions, taille, réputation).\n"
        "   - Relie les compétences de la candidate (Linux, Docker, Python, sécurité) au contexte de l'offre.\n"
        "   - Ton naturel et direct, pas de superlatifs, pas de formulations IA génériques.\n"
        "   - 350 caractères maximum.\n"
        "   - Ne répète pas ce qui est déjà dans la lettre (formations, projets, disponibilité).\n"
        "   - Style cohérent avec une lettre formelle en français.\n\n"

        "Réponds UNIQUEMENT en JSON valide sans backticks :\n"
        "{\"contact_entreprise\": \"...\", \"paragraphe_entreprise\": \"...\"}"
    )

    try:
        response = client.models.generate_content(
            model=MODELE_LETTRE,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.6,
            )
        )
        # Log finish_reason pour détecter les coupures
        finish = getattr(response.candidates[0], "finish_reason", "?") if response.candidates else "?"
        texte = re.sub(r'```json\s*', '', response.text or "")
        texte = re.sub(r'```\s*', '', texte).strip()
        if str(finish) not in ("FinishReason.STOP", "STOP", "1"):
            print(f"  ⚠️  Gemini finish_reason={finish} — réponse potentiellement tronquée")
        result = json_parse(texte)

        contact    = result.get("contact_entreprise", nom_entreprise)
        paragraphe = result.get("paragraphe_entreprise", "")

        # ── Nettoyage défensif du bloc contact ────────────────────────────────
        contact = _nettoyer_contact(contact)
        if not contact:
            contact = nom_entreprise

        # ── Alerte si paragraphe manquant ─────────────────────────────────────
        if not paragraphe:
            print(f"  ⚠️  paragraphe_entreprise vide pour '{nom_entreprise}' — JSON reçu : {result}")

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
    """
    Parse JSON avec double fallback :
    1. json.loads direct
    2. Extraction regex si le JSON est tronqué (ex: string non fermée)
    """
    try:
        return json.loads(texte)
    except Exception:
        pass

    # Fallback : extraction champ par champ avec regex
    result = {}
    for champ in ("contact_entreprise", "paragraphe_entreprise"):
        m = re.search(rf'"{champ}"\s*:\s*"((?:[^"\\]|\\.)*)"', texte)
        if m:
            result[champ] = m.group(1).replace("\\n", "\n")

    if result:
        print(f"  [json_parse] récupération partielle via regex : {list(result.keys())}")
        return result

    print(f"  ⚠️  json_parse échec total — texte reçu : {texte[:300]!r}")
    return {}
