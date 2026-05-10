import json
import os
import time
import random
import re
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────

FICHIER_JSON    = "data/entreprises_enrichies.json"
PROJET_GCP      = os.getenv("GOOGLE_CLOUD_PROJECT", "")
MODELE_GEMINI   = "gemini-2.5-flash"
PAUSE_GEMINI    = (4, 8)      # secondes entre chaque appel (rate limit)
SAUVEGARDE_TOUS = 20

# ─── Initialisation Gemini ────────────────────────────────────────────────────

gemini_client = genai.Client(
    vertexai=True,
    project=PROJET_GCP,
    location="us-central1"
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def charger_json():
    with open(FICHIER_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def sauvegarder_json(data):
    with open(FICHIER_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def nettoyer_json_gemini(texte):
    texte = re.sub(r'```json\s*', '', texte)
    texte = re.sub(r'```\s*', '', texte)
    return texte.strip()


# ─── Appel Gemini ─────────────────────────────────────────────────────────────

def generer_phrases_mail(entreprise):
    """
    Génère 1-2 phrases de personnalisation à insérer dans le mail fixe.
    Ces phrases montrent que la candidate connaît l'entreprise et expliquent
    pourquoi elle la contacte spécifiquement.

    Retourne un dict {"phrases_ia": "..."} ou None si erreur.
    """
    nom   = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    ville = entreprise.get("ville") or ""
    cp    = entreprise.get("code_postal") or ""
    site  = entreprise.get("site_web") or entreprise.get("url_scrapee") or ""

    prompt = f"""
Tu aides une candidate (Kenza Filali-Bouami) à personnaliser un mail de candidature spontanée.

CONTEXTE :
Le mail est déjà rédigé et ne sera PAS modifié. Tu dois uniquement générer
1 à 2 phrases à insérer dans le mail pour montrer un intérêt spécifique pour cette entreprise.

ENTREPRISE CIBLE :
- Nom : {nom}
- Ville : {ville} ({cp})
- Site web : {site if site else "inconnu"}

CONTRAINTES STRICTES :
- 1 à 2 phrases maximum — pas plus.
- 200 caractères maximum au total.
- Ne commence PAS par "Je" — commence par le nom de l'entreprise, "Votre", "C'est", etc.
- Ton naturel et direct, pas de superlatifs, pas d'expressions génériques type "dynamique" ou "innovant".
- Pas de formulation IA évidente.
- Ne répète pas les compétences (déjà mentionnées dans le reste du mail).
- Le style doit rester cohérent avec un mail professionnel simple.
- Déduis le secteur d'activité depuis le nom/site de l'entreprise si possible.

Réponds UNIQUEMENT en JSON valide sans backticks :
{{"phrases_ia": "..."}}
"""

    try:
        response = gemini_client.models.generate_content(
            model=MODELE_GEMINI,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,
            )
        )
        texte = nettoyer_json_gemini(response.text)
        result = json.loads(texte)

        if "phrases_ia" not in result or not result["phrases_ia"].strip():
            print(f"    [⚠️] Gemini — réponse vide ou incomplète")
            return None

        return result

    except Exception as e:
        print(f"    [❌] Gemini erreur : {e}")
        return None


# ─── Pipeline principal ────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Générateur mail — Chasseur d'Alternance")
    print(f"  Modèle : {MODELE_GEMINI}  |  Projet : {PROJET_GCP}")
    print("=" * 60)

    entreprises = charger_json()

    # Uniquement celles avec email ET pas encore de mail généré
    a_traiter = [
        e for e in entreprises
        if e.get("emails_trouves") and not e.get("mail_generee")
    ]
    deja_faites = sum(1 for e in entreprises if e.get("mail_generee"))

    print(f"[Queue] {len(a_traiter)} à traiter | {deja_faites} déjà générées\n")

    if not a_traiter:
        print("✅ Tous les mails sont générés ! Lance : python -m spontanees.envoyeur")
        return

    traites_ce_run = 0
    succes = 0
    erreurs = 0

    for e in entreprises:
        if not e.get("emails_trouves") or e.get("mail_generee"):
            continue

        nom = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
        idx = deja_faites + traites_ce_run + 1
        total_avec_email = deja_faites + len(a_traiter)

        print(f"[{idx}/{total_avec_email}] {nom}")

        result = generer_phrases_mail(e)

        if result:
            e["mail_zones"] = {
                "nom_entreprise": e.get("nom_commercial") or e.get("nom", ""),
                "phrases_ia":     result["phrases_ia"],
            }
            e["mail_generee"] = True
            print(f"  ✅ Phrases : {result['phrases_ia'][:80]}...")
            succes += 1
        else:
            e["mail_generee"] = False
            print(f"  ❌ Échec génération")
            erreurs += 1

        traites_ce_run += 1

        if traites_ce_run % SAUVEGARDE_TOUS == 0:
            sauvegarder_json(entreprises)
            print(f"\n  [💾 Sauvegarde — {idx}/{total_avec_email} | {succes} générés]\n")

        time.sleep(random.uniform(*PAUSE_GEMINI))

    sauvegarder_json(entreprises)

    print("\n" + "=" * 60)
    print(f"  Mails générés : {succes}")
    print(f"  Échecs        : {erreurs}")
    print(f"  Fichier       : {FICHIER_JSON}")
    print("=" * 60)
    print("\n→ Lance : python -m spontanees.envoyeur")


if __name__ == "__main__":
    main()
