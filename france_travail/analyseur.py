import time
import json
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
MODELE = "gemini-2.5-flash"


def construire_contexte_profil():
    competences = ", ".join(PROFIL["competences"])
    projets = " | ".join([f"{p['nom']} : {p['description']}" for p in PROFIL["projets"]])
    return (
        "Candidate : Kenza Filali-Bouami, Paris 9e / Issy-les-Moulineaux, Navigo toutes zones IDF.\n"
        "\n"
        "NIVEAU : Bac+1 DSP DevOps CNAM (admin systemes, reseaux, scripting, dev web, algo, Java, BDD, Cloud, CMS).\n"
        "Integre DEUST IOSI Bac+2 en alternance septembre 2026.\n"
        "Programme DEUST : POO avancee, algo avancee, BDD relationnelles, dev web serveur, "
        "administration systeme/reseau, securite, gestion de projet, anglais professionnel.\n"
        "\n"
        f"COMPETENCES ACTUELLES : {competences}\n"
        "\n"
        f"PROJETS : {projets}\n"
        "\n"
        "EXPERIENCE : Stage technicienne au Garage Numerique (maintenance hardware/software, "
        "installation Linux Arch/Debian, support utilisateurs non-techniciens, dev web WordPress/HTML-CSS).\n"
        "\n"
        "DISPONIBILITE : alternance septembre 2026, IDF uniquement, 1 ou 2 ans."
    )


def analyser_offre(offre):
    contexte = construire_contexte_profil()

    prompt = (
        "Tu es un recruteur IT experimente. Evalue cette offre pour la candidate ci-dessous.\n"
        "Reponds UNIQUEMENT en JSON valide, sans backticks, sans texte autour.\n\n"
        f"=== PROFIL CANDIDATE ===\n{contexte}\n\n"
        f"=== OFFRE ===\n"
        f"Titre : {offre.get('titre', '')}\n"
        f"Entreprise : {offre.get('entreprise', '')}\n"
        f"Lieu : {offre.get('lieu', '')}\n"
        f"Description : {offre.get('description', '')}\n\n"
        "=== REGLES D'ELIGIBILITE ===\n"
        "INELIGIBLE (eligible:false, score max 2) si :\n"
        "- Le poste n'a aucun rapport avec l'informatique, le developpement, les systemes/reseaux, la data ou l'IA.\n"
        "- L'offre exige explicitement un niveau Master, Bac+4, Bac+5, ou mentionne 'cycle ingenieur' "
        "comme prerequis d'entree (pas comme diplome prepare).\n"
        "- L'offre exige 3+ ans d'experience professionnelle.
- Le poste n'a aucun rapport avec l'informatique technique : exclure les postes commerciaux, marketing, RH, finance, juridique, analyst metier non-technique, sales, business developer, meme si mentionne "IT" ou "data".\n"
        "\n"
        "REGLE STRICTE sur le mot 'Ingenieur' dans le titre ou la description :\n"
        "- Si 'Ingenieur' designe le POSTE OCCUPE (ex: 'Alternance Ingenieur DevOps', 'Ingenieur logiciel') "
        "et que l'offre n'est pas d'une ecole/CFA cherchant un etudiant → INELIGIBLE (score max 2).\n"
        "- Si l'offre est proposee par une ecole/CFA/organisme de formation (ISCOD, Scholia, IMC, "
        "MyDigitalSchool, Simplon, AFPA, etc.) pour PREPARER un diplome → ELIGIBLE, "
        "mais archiver automatiquement (statut: 'archive') car ces ecoles collectent les infos "
        "sans transmettre directement au recruteur.\n"
        "\n"
        "=== COMPETENCES A EVALUER ===\n"
        "Competences maitrisees maintenant : Linux, Bash, Python (Flask/FastAPI), Docker, Git, "
        "HTML/CSS/JS, TCP/IP/DNS/DHCP/SSH, Node.js, WordPress, C, virtualisation, IA/LLM, projets GitHub.\n"
        "Competences en cours (DSP) : algo, Java bases, HTML/CSS avance, BDD bases, scripting avance.\n"
        "Competences a venir (DEUST) : POO avancee, BDD relationnelles, dev serveur, securite reseau, "
        "admin systeme avancee, gestion projet.\n"
        "\n"
        "Pour les competences manquantes, distingue :\n"
        "- Competence absente mais dans le programme DEUST (Java, securite, BDD, POO) → point faible mineur, "
        "elle l'apprendra durant l'alternance.\n"
        "- Competence absente et hors programme (Azure, Kubernetes, .NET, COBOL, Mainframe) → point faible important.\n"
        "\n"
        "=== SCORING ===\n"
        "Ne jamais penaliser pour la date de debut ou disponibilite : ignorer ce critere.\n"
        "Localisation : toute l'IDF est acceptable. -1 point max pour grande couronne (77/78/91/95) "
        "si vraiment eloigne. Ne pas penaliser petite couronne (92/93/94).\n"
        "\n"
        "9-10 : alternance IT explicite Bac+2, competences principales matchent, Paris ou petite couronne.\n"
        "7-8  : bon match technique global, 1-2 lacunes dans des competences a venir au DEUST, "
        "ou grande couronne.\n"
        "5-6  : match partiel - competences importantes manquantes ET hors programme DEUST, "
        "ou techno tres specifique absente (.NET, Java avance).\n"
        "3-4  : peu de correspondance - poste trop specifique ou trop eloigne du profil.\n"
        "1-2  : ineligible (hors IT, niveau trop eleve, experience requise).\n"
        "\n"
        "PENALITE BAC+3 : si l'offre demande explicitement Bac+3/Licence ou superieur comme niveau "
        "MINIMUM d'entree, retire 4 points au score final (la candidate n'a pas encore Bac+2). "
        "Un score 9 avec penalite Bac+3 donne donc 5 maximum.\n"
        "\n"
        "Differencie bien les scores : ne mets pas tout a 8 ou 9.\n\n"
        "=== FORMAT DE REPONSE ===\n"
        '{"score": 7, "verdict": "bon", "eligible": true, '
        '"points_forts": ["max 3 points concrets lies a l\'offre"], '
        '"points_faibles": ["max 2 points, distinguer manquant-maintenant vs manquant-DEUST"], '
        '"resume": "max 12 mots factuels"}'
    )

    # Détection écoles/CFA → archivage automatique
    ECOLES_MOTS_CLES = [
        "iscod", "scholia", "imc alternance", "mydigitalschool", "simplon",
        "afpa", "cfa", "epitech", "openclassrooms", "studi", "ikigai",
        "la plateforme", "digital campus", "m2i", "doranco", "efficom",
        "ecole", "organisme de formation", "centre de formation"
    ]
    description_lower = offre.get("description", "").lower()
    entreprise_lower = offre.get("entreprise", "").lower()
    titre_lower = offre.get("titre", "").lower()
    est_ecole = any(
        mot in description_lower or mot in entreprise_lower or mot in titre_lower
        for mot in ECOLES_MOTS_CLES
    )

    try:
        response = client.models.generate_content(
            model=MODELE,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Tu es un recruteur IT. Tu reponds UNIQUEMENT en JSON valide sans backticks. "
                    "Tu ignores totalement la date de debut et la disponibilite dans ta notation."
                ),
                response_mime_type="application/json",
            )
        )
        texte = response.text
        texte = re.sub(r'```json\s*', '', texte)
        texte = re.sub(r'```\s*', '', texte)
        result = json.loads(texte)
        if "score" in result:
            result["score"] = max(1, min(10, int(result["score"])))
        if not result.get("eligible", True):
            result["score"] = min(result["score"], 2)
            result["verdict"] = "faible"
        if est_ecole:
            result["statut_auto"] = "archive"
            print(f"     → Archivée automatiquement (école/CFA détectée)")
        return result
    except Exception as e:
        print(f"  Erreur analyse : {e}")
        return {
            "score": 5, "verdict": "erreur", "eligible": True,
            "points_forts": [], "points_faibles": [], "resume": "Erreur analyse"
        }


def analyser_offres(offres, callback=None):
    offres_analysees = []
    for i, offre in enumerate(offres, 1):
        print(f"  [{i}/{len(offres)}] {offre['titre'][:50]}...")
        analyse = analyser_offre(offre)
        offre.update({
            "score": analyse.get("score", 5),
            "verdict": analyse.get("verdict", "moyen"),
            "eligible": analyse.get("eligible", True),
            "points_forts": analyse.get("points_forts", []),
            "points_faibles": analyse.get("points_faibles", []),
            "resume_analyse": analyse.get("resume", "")
        })
        if analyse.get("statut_auto") == "archive":
            offre["statut"] = "archive"
        eligible_str = "eligible" if offre["eligible"] else "INELIGIBLE"
        print(f"     Score : {offre['score']}/10 — {offre['verdict']} — {eligible_str}")
        offres_analysees.append(offre)
        if callback:
            callback(i, len(offres), offre)
        time.sleep(4)
    offres_analysees.sort(key=lambda x: x["score"], reverse=True)
    return offres_analysees
