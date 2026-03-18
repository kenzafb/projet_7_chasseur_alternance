import anthropic
import json
import re
import os
from dotenv import load_dotenv
from profil import PROFIL

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODELE = "claude-sonnet-4-20250514"


def construire_contexte_profil():
    competences = ", ".join(PROFIL["competences"])
    noms_projets = ", ".join([p["nom"] for p in PROFIL["projets"]])
    return (
        "Candidate : Kenza Filali-Bouami, Paris 9e (Gare du Nord) + pied-a-terre Issy-les-Moulineaux\n"
        "Niveau : Bac+1 DSP DevOps CNAM. Integre DEUST IOSI Bac+2 en alternance septembre 2026.\n"
        "Programme DEUST IOSI couvre : programmation OO, algo avancee, BDD, dev web full-stack, "
        "administration systeme et reseau, securite, gestion de projet, API.\n"
        f"Competences actuelles : {competences}\n"
        f"Projets realises : {noms_projets}\n"
        "Langues : Francais natif, Anglais B2, Espagnol A2\n"
        "Disponibilite : alternance 2 semaines ecole / 2 semaines entreprise, septembre 2026, 1 ou 2 ans IDF"
    )


def analyser_offre(offre):
    contexte = construire_contexte_profil()

    # Extraction du departement pour estimer la distance
    lieu = offre.get("lieu", "")
    dept = ""
    if "75" in lieu:
        dept = "Paris intramuros"
    elif any(x in lieu for x in ["92", "93", "94"]):
        dept = "petite couronne"
    elif any(x in lieu for x in ["77", "78", "91", "95"]):
        dept = "grande couronne"

    json_exemple = '{"score":7,"verdict":"bon","niveau_requis":"Bac+2","eligible":true,"points_forts":["ex"],"points_faibles":["ex"],"diplome_equivalent":false,"resume":"explication concise"}'

    prompt = (
        "Tu es un recruteur expert en informatique. Analyse cette offre pour la candidate et reponds UNIQUEMENT avec le JSON, sans backticks ni texte autour.\n\n"
        f"PROFIL :\n{contexte}\n\n"
        f"OFFRE :\n"
        f"Titre : {offre['titre']}\n"
        f"Entreprise : {offre['entreprise']}\n"
        f"Lieu : {lieu}" + (f" ({dept})" if dept else "") + "\n"
        f"Description : {offre['description']}\n\n"

        "CRITERES ELIMINATOIRES (eligible:false, score max 2) :\n"
        "- Titre ou description contient : ingenieur, engineer, Bac+4, Bac+5, master, senior, 3+ ans experience\n"
        "- Poste sans rapport avec informatique, dev, systemes, reseaux, data ou IA\n"
        "- Formation requise completement differente (BTS comptabilite, licence RH...)\n\n"

        "SCORING - utilise toute l'echelle avec ces references :\n"
	"10 : offre DevOps/dev junior Bac+2 explicite Paris, toutes competences matchent, missions = tes projets\n"
	"8-9 : bon match technique, niveau ok, 1-2 lacunes mineures rattrapables\n"
	"6-7 : match partiel OU localisation > 45min OU competences importantes manquantes\n"
	"4-5 : peu de correspondance technique OU poste eloigne de DevOps/dev\n"
	"1-3 : ineligible\n"
	"IMPORTANT : les scores doivent etre differencies, evite de tout mettre a 8.\n\n"

        "IMPORTANT :\n"
        "- Ne pas penaliser pour Windows Server, Active Directory, cloud basique : rattrapables facilement\n"
        "- Ne pas penaliser pour Kubernetes junior, CI/CD basique : au programme ou tres proche\n"
        "- Le score DOIT varier entre offres : evite de tout mettre a 7 ou 8\n"
        "- Resume : 1-2 phrases max, concis, pas de mention inutile du Bac+1\n\n"

        "JSON attendu (champs EXACTEMENT ces noms) :\n"
        + json_exemple
    )

    try:
        message = client.messages.create(
            model=MODELE,
            max_tokens=600,
            system="Tu es un recruteur informatique strict et precis. Tu analyses des offres d'alternance et attribues des scores differencies sur 10. Tu suis les regles de scoring a la lettre. Tu reponds UNIQUEMENT en JSON valide sans backticks.",
            messages=[{"role": "user", "content": prompt}]
        )
        texte = message.content[0].text
        texte_propre = re.sub(r'```json\s*', '', texte)
        texte_propre = re.sub(r'```\s*', '', texte_propre)
        match = re.search(r'\{.*\}', texte_propre, re.DOTALL)
        if match:
            result = json.loads(match.group())
            # Securite cote Python : si ineligible, score max 2
            if not result.get("eligible", True):
                result["score"] = min(result.get("score", 2), 2)
                result["verdict"] = "faible"
            # Clamp entre 1 et 10
            result["score"] = max(1, min(10, int(result.get("score", 5))))
            return result
    except Exception as e:
        print(f"  Erreur analyse : {e}")

    return {
        "score": 5,
        "verdict": "moyen",
        "niveau_requis": "non precis",
        "eligible": True,
        "points_forts": [],
        "points_faibles": ["Analyse impossible"],
        "diplome_equivalent": False,
        "resume": "Analyse echouee"
    }


def analyser_offres(offres, callback=None):
    print(f"Analyse de {len(offres)} offres avec Claude...\n")
    offres_analysees = []

    for i, offre in enumerate(offres, 1):
        print(f"  [{i}/{len(offres)}] {offre['titre'][:50]}...")
        analyse = analyser_offre(offre)
        offre.update({
            "score": analyse.get("score", 5),
            "verdict": analyse.get("verdict", "moyen"),
            "niveau_requis": analyse.get("niveau_requis", "non precis"),
            "eligible": analyse.get("eligible", True),
            "points_forts": analyse.get("points_forts", []),
            "points_faibles": analyse.get("points_faibles", []),
            "diplome_equivalent": analyse.get("diplome_equivalent", False),
            "resume_analyse": analyse.get("resume", "")
        })
        offres_analysees.append(offre)
        if callback:
            callback(i, len(offres), offre)
        eligible_str = "eligible" if offre["eligible"] else "INELIGIBLE"
        print(f"     Score : {offre['score']}/10 - {offre['verdict']} - {eligible_str}")

    offres_analysees.sort(key=lambda x: x["score"], reverse=True)
    print(f"\nTermine ! Top : {offres_analysees[0]['titre'][:50]} ({offres_analysees[0]['score']}/10)")
    return offres_analysees
