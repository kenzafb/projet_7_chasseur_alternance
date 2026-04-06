"""
generateur_lettres.py
=====================
Pour chaque entreprise avec un email dans entreprises_enrichies.json,
appelle Gemini (Vertex AI) pour générer les 4 zones personnalisées
de la lettre de motivation et sauvegarde le résultat dans le JSON.

Lancement : python generateur_lettres.py
"""


import json
import os
import time
import random
import re
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()


# ─── Config ───────────────────────────────────────────────────────────────────

FICHIER_JSON    = "data/entreprises_enrichies.json"
PROJET_GCP      = os.getenv("GOOGLE_CLOUD_PROJECT", "project-4fa72ea4-bd10-420c-988")
MODELE_GEMINI   = "gemini-2.5-flash"
PAUSE_GEMINI    = (4, 8)      # secondes entre chaque appel
SAUVEGARDE_TOUS = 20          # sauvegarde tous les N traitements

# ─── Profil Kenza (contexte fixe pour Gemini) ─────────────────────────────────

PROFIL_KENZA = """
Candidate : Kenza FILALI-BOUAMI
Formation : DSP DevOps (Bac+1) au CNAM Paris, actuellement en stage au Garage Numérique.
Prochaine formation : DEUST IOSI (Bac+2) au CNAM Paris, 2e année, démarrage septembre 2026 en alternance.
Disponibilité alternance : septembre 2026.
Compétences principales : Linux (Debian, Ubuntu, Arch), Docker/Docker-Compose, Bash scripting,
Python (FastAPI, API REST), Git/GitHub, CI/CD, administration système et réseau, sécurité informatique,
TCP/IP, DNS, DHCP, pare-feu, HTML/CSS/JavaScript, MySQL, WordPress.
Projets : Grabber (monitoring système FastAPI/Bash), outil CLI Docker-Compose (Node.js),
site Auburn & Cream (HTML/CSS pur, mobile-first).
Stage : Le Garage Numérique — maintenance matérielle/logicielle, configuration Linux,
développement web, support utilisateur.
Poste recherché : alternance DevOps / SysAdmin / Sécurité.
"""

# ─── Initialisation Gemini ────────────────────────────────────────────────────

gemini_client = genai.Client(
    vertexai=True,
    project=PROJET_GCP,
    location="us-central1"
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def date_du_jour():
    mois = ["janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    today = datetime.today()
    return f"{today.day} {mois[today.month - 1]} {today.year}"


def charger_json():
    with open(FICHIER_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def sauvegarder_json(data):
    with open(FICHIER_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def nettoyer_json_gemini(texte):
    """Nettoie les éventuels backticks markdown autour du JSON."""
    texte = re.sub(r'```json\s*', '', texte)
    texte = re.sub(r'```\s*', '', texte)
    return texte.strip()


# ─── Appel Gemini ─────────────────────────────────────────────────────────────

def generer_zones(entreprise):
    """
    Appelle Gemini pour générer les 4 zones personnalisées.
    Retourne un dict : {objet, adresse, paragraphe_personnalise} ou None si erreur.
    """
    nom         = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    ville       = entreprise.get("ville") or ""
    cp          = entreprise.get("code_postal") or ""
    site        = entreprise.get("site_web") or entreprise.get("url_scrapee") or ""
    emails      = entreprise.get("emails_trouves", [])
    telephone   = entreprise.get("telephone") or ""

    prompt = f"""
Tu aides une candidate (Kenza FILALI-BOUAMI) à personnaliser sa lettre de motivation
pour une candidature en alternance DevOps/SysAdmin/Sécurité.

PROFIL DE LA CANDIDATE :
{PROFIL_KENZA}

ENTREPRISE CIBLE :
- Nom : {nom}
- Ville : {ville} ({cp})
- Site web : {site if site else "inconnu"}

MISSION :
Génère exactement 3 éléments pour personnaliser la lettre :

1. OBJET : Une ligne d'objet percutante pour le mail/lettre (ex: "Candidature alternance DevOps – Septembre 2026")
   → Adapte-le au secteur/nom de l'entreprise si possible. Maximum 12 mots.

2. ADRESSE : L'adresse du destinataire à afficher sur la lettre.
   Format : "Nom de l'entreprise\\n{ville} ({cp})"
   → Si l'adresse exacte est inconnue, utilise juste le nom et la ville.

3. PARAGRAPHE_PERSONNALISE : UN seul paragraphe de 3 à 5 phrases maximum.
   → Montre que Kenza connaît ou s'intéresse à cette entreprise spécifiquement.
   → Explique pourquoi ses compétences (Linux, Docker, Python, sécurité) correspondent
     à ce que cette entreprise fait probablement (déduis-le du nom/secteur).
   → Ton professionnel, naturel, pas robotique. Pas de superlatifs excessifs.
   → Ne répète pas ce qui est déjà dans les autres paragraphes fixes de la lettre.
   → Ne mentionne PAS le CV (déjà dit dans la lettre).
   → Ne commence PAS par "Je" — commence par le nom de l'entreprise, "Votre", "C'est", etc.

IMPORTANT : Réponds UNIQUEMENT en JSON valide, sans backticks, sans texte autour :
{{"objet": "...", "adresse": "...", "paragraphe_personnalise": "..."}}
"""

    try:
        response = gemini_client.models.generate_content(
            model=MODELE_GEMINI,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Tu es un expert en rédaction de lettres de motivation professionnelles françaises. "
                    "Tu réponds UNIQUEMENT en JSON valide sans backticks ni texte autour."
                ),
                response_mime_type="application/json",
                temperature=0.7,
            )
        )
        texte = nettoyer_json_gemini(response.text)
        result = json.loads(texte)

        # Validation minimale
        if not all(k in result for k in ["objet", "adresse", "paragraphe_personnalise"]):
            print(f"    [⚠️] Gemini — réponse incomplète : {result}")
            return None

        return result

    except Exception as e:
        print(f"    [❌] Gemini erreur : {e}")
        return None


# ─── Pipeline principal ────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Générateur de lettres — Chasseur d'Alternance")
    print(f"  Modèle : {MODELE_GEMINI}  |  Projet : {PROJET_GCP}")
    print("=" * 60)

    entreprises = charger_json()

    # Filtrer : uniquement celles avec email ET pas encore de lettre générée
    a_traiter = [
        e for e in entreprises
        if e.get("emails_trouves") and not e.get("lettre_generee")
    ]
    deja_faites = sum(1 for e in entreprises if e.get("lettre_generee"))

    print(f"[Queue] {len(a_traiter)} à traiter | {deja_faites} déjà générées\n")

    if not a_traiter:
        print("✅ Toutes les lettres sont générées ! Lance : python envoyeur.py")
        return

    traites_ce_run = 0
    succes = 0
    erreurs = 0

    for e in entreprises:
        # Passer les entreprises sans email ou déjà traitées
        if not e.get("emails_trouves") or e.get("lettre_generee"):
            continue

        nom = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
        idx = deja_faites + traites_ce_run + 1
        total_avec_email = deja_faites + len(a_traiter)

        print(f"[{idx}/{total_avec_email}] {nom}")

        zones = generer_zones(e)

        if zones:
            e["lettre_zones"] = {
                "date"                  : date_du_jour(),
                "nom_entreprise"        : e.get("nom_commercial") or e.get("nom", ""),
                "adresse"               : zones["adresse"],
                "objet"                 : zones["objet"],
                "paragraphe_personnalise": zones["paragraphe_personnalise"],
            }
            e["lettre_generee"] = True
            print(f"  ✅ Objet : {zones['objet']}")
            succes += 1
        else:
            e["lettre_generee"] = False
            print(f"  ❌ Échec génération")
            erreurs += 1

        traites_ce_run += 1

        # Sauvegarde intermédiaire
        if traites_ce_run % SAUVEGARDE_TOUS == 0:
            sauvegarder_json(entreprises)
            print(f"\n  [💾 Sauvegarde — {idx}/{total_avec_email} | {succes} lettres générées]\n")

        # Pause anti-rate-limit
        time.sleep(random.uniform(*PAUSE_GEMINI))

    sauvegarder_json(entreprises)

    print("\n" + "=" * 60)
    print(f"  Lettres générées : {succes}")
    print(f"  Échecs           : {erreurs}")
    print(f"  Fichier          : {FICHIER_JSON}")
    print("=" * 60)
    print("\n→ Lance : python envoyeur.py")


if __name__ == "__main__":
    main()
