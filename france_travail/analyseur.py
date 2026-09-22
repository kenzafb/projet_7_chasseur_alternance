import time
import json
import re
import os
from mistralai.client import Mistral
from dotenv import load_dotenv

load_dotenv()

client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

MODELE = "mistral-large-latest"
PAUSE_MISTRAL = 10 # secondes entre chaque appel Mistral (rate limit)

def construire_contexte_profil(profil):
    """Construit le contexte candidat à partir du profil de l'utilisateur (depuis la base)."""
    nom_complet = f"{profil.get('prenom','')} {profil.get('nom','')}".strip() or "Le candidat"
    ville       = profil.get("ville", "")
    competences = ", ".join(profil.get("competences", []))
    projets     = " | ".join(
        f"{p.get('nom','')} : {p.get('description','')}"
        for p in profil.get("projets", [])
    )
    formation     = (profil.get("formation", "") or "").strip()
    experience    = (profil.get("experience", "") or "").strip()
    langues       = profil.get("langues", "")
    disponibilite = (profil.get("disponibilite", "") or "").strip()
    niveau_vise       = (profil.get("niveau_vise", "") or "").strip()
    formation_apporte = (profil.get("formation_apporte", "") or "").strip()
    criteres_eviter   = (profil.get("criteres_eviter", "") or "").strip()
    localisation = (profil.get("recherche", {}) or {}).get("localisation", "")

    parties = [f"Candidat : {nom_complet}" + (f", {ville}." if ville else ".")]
    if niveau_vise:       parties.append(f"NIVEAU D'ÉTUDES VISÉ (ce que le contrat prépare) :\n{niveau_vise}")
    if formation:         parties.append(f"FORMATION :\n{formation}")
    if formation_apporte: parties.append(f"COMPÉTENCES QUE LA FORMATION VA APPORTER (ne pas pénaliser si l'offre les demande) :\n{formation_apporte}")
    if competences:       parties.append(f"COMPÉTENCES DÉJÀ MAÎTRISÉES : {competences}")
    if projets:           parties.append(f"PROJETS : {projets}")
    if experience:        parties.append(f"EXPÉRIENCE :\n{experience}")
    if langues:           parties.append(f"LANGUES : {langues}")
    if localisation:      parties.append(f"LOCALISATION SOUHAITÉE : {localisation}")
    if disponibilite:     parties.append(f"DISPONIBILITÉ : {disponibilite}")
    if criteres_eviter:   parties.append(f"CE QUE LE CANDIDAT PRÉFÈRE ÉVITER :\n{criteres_eviter}")
    return "\n\n".join(parties)

def construire_contexte_profil_job(profil):
    """Contexte candidat pour le mode JOB (job court / mission)."""
    nom = f"{profil.get('prenom','')} {profil.get('nom','')}".strip() or "Le candidat"
    ville = profil.get("ville", "")
    niveau_etudes   = (profil.get("niveau_etudes", "") or "").strip()
    experience      = (profil.get("experience", "") or "").strip()
    competences     = ", ".join(profil.get("competences", [])) if profil.get("competences") else ""
    atouts          = (profil.get("langues", "") or "").strip()   # langues/permis/savoir-être
    duree           = (profil.get("duree_souhaitee", "") or "").strip()
    dispo_dates     = (profil.get("recherche", {}) or {}).get("disponibilite", "")
    dispo_horaires  = (profil.get("dispo_horaires", "") or "").strip()
    mobilite        = (profil.get("mobilite", "") or "").strip()
    jobs_ok         = (profil.get("types_jobs_ok", "") or "").strip()
    jobs_eviter     = (profil.get("types_jobs_eviter", "") or "").strip()
    loc_pref        = (profil.get("localisation_pref", "") or "").strip()

    parties = [f"Candidat : {nom}" + (f", {ville}." if ville else ".")]
    if niveau_etudes:  parties.append(f"NIVEAU D'ÉTUDES OBTENU : {niveau_etudes}")
    if experience:     parties.append(f"EXPÉRIENCE :\n{experience}")
    if competences:    parties.append(f"COMPÉTENCES : {competences}")
    if atouts:         parties.append(f"ATOUTS (langues, permis, savoir-être) : {atouts}")
    if duree:          parties.append(f"DURÉE DE CONTRAT SOUHAITÉE : {duree}")
    if dispo_dates:    parties.append(f"DISPONIBILITÉ (dates) : {dispo_dates}")
    if dispo_horaires: parties.append(f"DISPONIBILITÉ HORAIRE : {dispo_horaires}")
    if mobilite:       parties.append(f"MOBILITÉ : {mobilite}")
    if jobs_ok:        parties.append(f"TYPES DE JOBS QUI CONVIENNENT : {jobs_ok}")
    if jobs_eviter:    parties.append(f"TYPES DE JOBS À ÉVITER : {jobs_eviter}")
    if loc_pref:       parties.append(f"LOCALISATION PRÉFÉRÉE (optionnel) : {loc_pref}")
    return "\n\n".join(parties)


def _analyser_offre_job(offre, profil):
    """Analyse d'une offre en mode JOB (job court / mission accessible)."""
    contexte = construire_contexte_profil_job(profil)
    prompt = (
        "Tu es un recruteur. Un candidat cherche un JOB COURT (mission, CDD, intérim, saisonnier) "
        "pour une période limitée. Analyse si cette offre lui est ACCESSIBLE et adaptée.\n"
        "Réponds UNIQUEMENT en JSON valide, sans backticks ni texte autour.\n\n"

        "=== PROFIL DU CANDIDAT ===\n"
        f"{contexte}\n\n"

        "=== OFFRE ===\n"
        f"Titre : {offre.get('titre', '')}\n"
        f"Entreprise : {offre.get('entreprise', '')}\n"
        f"Lieu : {offre.get('lieu', '')}\n"
        f"Description : {offre.get('description', '')[:1000]}\n\n"

        "=== INÉLIGIBILITÉ (score max 2, eligible: false) ===\n"
        "Marque INÉLIGIBLE si l'une de ces conditions est vraie :\n"
        "- L'offre EXIGE un diplôme/une formation que le candidat n'a PAS "
        "(se baser sur son niveau d'études obtenu).\n"
        "- L'offre EXIGE plus d'expérience que celle du candidat "
        "(une expérience 'souhaitée' ou 'appréciée' n'est PAS éliminatoire).\n"
        "- La durée MINIMALE du contrat dépasse la durée maximale que le candidat peut faire "
        "(voir sa durée souhaitée / ses dates de disponibilité). Une durée plus COURTE est OK.\n"
        "- Le poste correspond clairement à ce que le candidat veut ÉVITER.\n\n"

        "=== SCORING (1-10) — UTILISE TOUTE L'ÉCHELLE, NE METS PAS TOUT À 7 ===\n"
        "Le critère N°1 est la PÉNIBILITÉ du poste (juge-la depuis la description). "
        "Le candidat préfère AVANT TOUT les jobs CALMES, peu physiques, avec peu de tâches "
        "(surveillance, gardiennage, accueil, billetterie, loge, saisie...). "
        "Plus un poste est tranquille et peu fatigant, plus la note est haute. "
        "Plus il est physique/pénible/répétitif, plus elle baisse.\n\n"
        "Barème (sois DISCRIMINANT, écarte vraiment les notes) :\n"
        "9-10 : job CALME et peu fatigant (surveillance, gardiennage, agent d'accueil/sécurité, "
        "loge, billetterie, hôte(sse), poste où l'on 'veille' surtout) ET proche de la localisation "
        "préférée. Le top du candidat.\n"
        "7-8 : bon job accessible — débutant accepté, pas d'expérience exigée, OU dans son domaine "
        "(relation client / téléconseil / saisie). Peut demander du travail et de la polyvalence "
        "(ex. employé polyvalent restauration rapide, vente, libre-service). Job 'standard correct'.\n"
        "5-6 : accessible MAIS avec un vrai bémol : assez physique/fatigant, OU loin de la "
        "localisation préférée, OU éloigné des types de jobs souhaités.\n"
        "3-4 : peu adapté : poste physique/pénible marqué, proche de ce que le candidat veut éviter, "
        "ou cumul de défauts (loin + fatigant).\n"
        "1-2 : inéligible (voir section inéligibilité).\n\n"
        "Principes IMPORTANTS :\n"
        "- PÉNIBILITÉ = critère prioritaire. Un poste calme passe DEVANT un poste physique, "
        "même si les deux sont accessibles. Ne mets pas la même note à un agent de surveillance "
        "et à un préparateur de commandes : le premier est plus haut.\n"
        "- DURÉE : si la durée MINIMALE du contrat dépasse nettement le maximum du candidat "
        "(ex. CDD 6 mois alors qu'il veut 2,5 mois max), ce n'est pas qu'un détail : BAISSE la note "
        "de plusieurs points (plafonne autour de 4-5 même si le job est sympa). Une durée plus "
        "courte ou flexible (intérim, saisonnier) est au contraire un BON point.\n"
        "- LOCALISATION : plus c'est proche de la localisation préférée, mieux c'est. Un job dans "
        "l'arrondissement préféré ou juste à côté mérite un bonus ; un job en grande couronne loin "
        "perd des points (sans être éliminé).\n"
        "- DOMAINE : un job dans le domaine du candidat (relation client, téléconseil, accueil, "
        "informatique légère) est un bon point.\n"
        "- Un job qui ne demande NI diplôme NI expérience est ACCESSIBLE : bon point de base (~7).\n"
        "- Ne JAMAIS pénaliser pour la date de début ou la disponibilité.\n"
        "- Tenir compte de la mobilité (pas de permis → privilégier accessible en transports).\n\n"

        "=== CLASSIFICATION ===\n"
        "Renseigne 'domaine' avec une courte catégorie métier du job (2-4 mots, "
        "ex. 'Vente', 'Restauration', 'Manutention', 'Accueil', 'Saisie de données'...).\n\n"

        "=== FORMAT RÉPONSE ===\n"
        '{"score": 7, "verdict": "bon", "eligible": true, '
        '"points_forts": ["max 3 points concrets : accessibilité, type de job, localisation"], '
        '"points_faibles": ["max 2 points : ce qui pourrait gêner le candidat"], '
        '"domaine": "courte catégorie métier", '
        '"resume": "max 12 mots factuels"}'
    )

    try:
        response = None
        for tentative in range(1, 5):
            try:
                response = client.chat.complete(
                    model=MODELE,
                    messages=[
                        {"role": "system", "content": (
                            "Tu es un recruteur spécialisé dans les jobs courts et missions. "
                            "Tu reponds UNIQUEMENT en JSON valide sans backticks. "
                            "Tu ignores totalement la date de debut et la disponibilite dans ta notation."
                        )},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                break
            except Exception as err_api:
                msg = str(err_api).lower()
                if ("429" in msg or "rate" in msg) and tentative < 4:
                    time.sleep(15 * tentative)
                else:
                    raise
        texte = response.choices[0].message.content
        texte = re.sub(r'```json\s*', '', texte)
        texte = re.sub(r'```\s*', '', texte)
        result = json.loads(texte)
        if "score" in result:
            result["score"] = max(1, min(10, int(result["score"])))
        if not result.get("eligible", True):
            result["score"] = min(result["score"], 2)
            result["verdict"] = "faible"
        if not result.get("domaine"):
            result["domaine"] = "Non classé"
        return result
    except Exception as e:
        print(f"  Erreur analyse job : {e}")
        return {
            "score": 5, "verdict": "erreur", "eligible": True,
            "points_forts": [], "points_faibles": [], "domaine": "Non classé", "resume": "Erreur analyse"
        }


def analyser_offre(offre, profil=None, mode="alternance"):
    if profil is None:
        from database.profil_db import lire_profil
        profil = lire_profil(1, mode=mode)

    # ─── Mode JOB : prompt dédié (job court accessible) ───
    if mode == "job":
        return _analyser_offre_job(offre, profil)

    contexte = construire_contexte_profil(profil)
    # Domaines recherchés par le candidat (libellés lisibles)
    from shared.domaines import DOMAINES
    _cles = (profil.get("recherche", {}) or {}).get("domaines", []) or []
    _labels = [DOMAINES[c]["label"] for c in _cles if c in DOMAINES]
    domaines_txt = ", ".join(_labels) if _labels else "le domaine correspondant au profil ci-dessus"

    prompt = (
        "Tu es un recruteur spécialisé en alternance. Analyse cette offre pour le candidat ci-dessous.\n"
        "Réponds UNIQUEMENT en JSON valide, sans backticks ni texte autour.\n\n"

        "=== PROFIL DU CANDIDAT ===\n"
        f"{contexte}\n\n"

        f"=== DOMAINE(S) RECHERCHÉ(S) ===\n{domaines_txt}\n\n"

        "=== OFFRE ===\n"
        f"Titre : {offre.get('titre', '')}\n"
        f"Entreprise : {offre.get('entreprise', '')}\n"
        f"Lieu : {offre.get('lieu', '')}\n"
        f"Description : {offre.get('description', '')[:1000]}\n\n"

        "=== INÉLIGIBILITÉ (score max 2, eligible: false) ===\n"
        "Marque INÉLIGIBLE si l'une de ces conditions est vraie :\n"
        "- Le poste réel est clairement hors du/des domaine(s) recherché(s) par le candidat.\n"
        "- L'offre exige un niveau d'études NETTEMENT supérieur au niveau visé par le candidat "
        "(ex. Master/Bac+5 exigé alors que le candidat vise un Bac+2).\n"
        "- L'offre exige une expérience professionnelle importante (ex. 3 ans ou plus).\n"
        "- Le poste correspond à un niveau de séniorité incompatible avec une alternance "
        "(ex. 'Ingénieur', 'Architecte', 'Senior' exigé), sauf si l'offre vient d'une école/CFA.\n\n"

        "=== SCORING (1-10) ===\n"
        "Juge la correspondance ENTRE CE CANDIDAT (son niveau visé, ses compétences, ce que sa "
        "formation va lui apporter, sa localisation) ET cette offre.\n"
        "9-10 : excellent match — domaine recherché, niveau cohérent avec le niveau visé, "
        "plusieurs compétences du candidat correspondent, localisation compatible.\n"
        "7-8 : bon match avec 1-2 réserves (niveau non précisé, quelques compétences manquantes, "
        "ou localisation un peu éloignée).\n"
        "5-6 : correspondance moyenne (niveau demandé un peu supérieur au niveau visé, "
        "compétences importantes manquantes).\n"
        "3-4 : faible correspondance (domaine éloigné, prérequis incompatibles).\n"
        "1-2 : inéligible.\n\n"
        "Principes IMPORTANTS :\n"
        "- Ne JAMAIS pénaliser pour la date de début ou la disponibilité.\n"
        "- Une compétence demandée par l'offre que le candidat NE maîtrise pas encore MAIS que sa "
        "formation va lui apporter = point faible MINEUR (il va l'acquérir), pas rédhibitoire.\n"
        "- Une compétence demandée hors de ce que le candidat a ET hors de ce que la formation "
        "apporte = point faible IMPORTANT.\n"
        "- Si l'offre correspond à ce que le candidat préfère ÉVITER, baisse le score en conséquence.\n"
        "- Juge sur les MISSIONS réelles décrites, pas sur le titre seul.\n\n"

        "=== CLASSIFICATION ===\n"
        "Renseigne le champ 'domaine' avec une courte catégorie métier de l'offre (2-4 mots, "
        "ex. selon le secteur : 'Administration systèmes', 'Développement web', 'Gestion locative', "
        "'Transaction immobilière'...).\n"
        "Si le poste réel est HORS du/des domaine(s) recherché(s) par le candidat, mets "
        "EXACTEMENT 'Hors domaine' comme valeur de 'domaine'.\n\n"

        "=== FORMAT RÉPONSE ===\n"
        '{"score": 7, "verdict": "bon", "eligible": true, '
        '"points_forts": ["max 3 points concrets liés à l\'offre"], '
        '"points_faibles": ["max 2 points, préciser si la formation couvre la lacune ou non"], '
        '"domaine": "courte catégorie métier, ou Hors domaine", '
        '"resume": "max 12 mots factuels"}'
    )

    # Détection écoles/CFA → archivage automatique
    ECOLES_MOTS_CLES = [
        "iscod", "scholia", "imc alternance", "mydigitalschool", "simplon",
        "afpa", "cfa", "epitech", "openclassrooms", "studi", "ikigai",
        "la plateforme", "digital campus", "m2i", "doranco", "efficom",
        "ecole", "organisme de formation", "centre de formation",
        "hitema", "h3", "igs", "isefac", "sup de vinci",
        "aureis","nexa","Groupe IGF",
    ]
    description_lower = offre.get("description", "").lower()
    entreprise_lower = offre.get("entreprise", "").lower()
    titre_lower = offre.get("titre", "").lower()
    est_ecole = any(
        mot in description_lower or mot in entreprise_lower or mot in titre_lower
        for mot in ECOLES_MOTS_CLES
    )

    try:
        # Appel Mistral avec retry sur rate limit (429)
        response = None
        for tentative in range(1, 5):   # 4 tentatives max
            try:
                response = client.chat.complete(
                    model=MODELE,
                    messages=[
                        {"role": "system", "content": (
                            "Tu es un recruteur spécialisé en alternance. Tu reponds UNIQUEMENT en JSON valide sans backticks. "
                            "Tu ignores totalement la date de debut et la disponibilite dans ta notation."
                        )},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                break  # succes -> on sort de la boucle de retry
            except Exception as err_api:
                msg = str(err_api).lower()
                est_rate_limit = "429" in msg or "rate" in msg
                if est_rate_limit and tentative < 4:
                    attente = 15 * tentative   # 15s, 30s, 45s
                    print(f"     Rate limit - pause {attente}s puis nouvelle tentative ({tentative}/3)")
                    time.sleep(attente)
                else:
                    raise  # autre erreur, ou derniere tentative -> on abandonne
        texte = response.choices[0].message.content
        texte = re.sub(r'```json\s*', '', texte)
        texte = re.sub(r'```\s*', '', texte)
        result = json.loads(texte)
        if "score" in result:
            result["score"] = max(1, min(10, int(result["score"])))
        if not result.get("eligible", True):
            result["score"] = min(result["score"], 2)
            result["verdict"] = "faible"
        # Domaine : on garde la catégorie libre donnée par l'IA (ou "Non classé" si vide)
        if not result.get("domaine"):
            result["domaine"] = "Non classé"
        if est_ecole:
            result["statut_auto"] = "archive"
            print(f"     → Archivée automatiquement (école/CFA détectée)")
        return result
    except Exception as e:
        print(f"  Erreur analyse : {e}")
        return {
            "score": 5, "verdict": "erreur", "eligible": True,
            "points_forts": [], "points_faibles": [], "domaine": "Non classé", "resume": "Erreur analyse"
        }

def score_to_verdict(score):
    if score >= 9: return "excellent"
    if score >= 7: return "bon"
    if score >= 5: return "moyen"
    if score >= 3: return "faible"
    return "ineligible"

def analyser_offres(offres, profil=None, callback=None, mode="alternance"):
    offres_analysees = []
    for i, offre in enumerate(offres, 1):
        print(f"  [{i}/{len(offres)}] {offre['titre'][:50]}...")
        analyse = analyser_offre(offre, profil, mode=mode)
        offre.update({
            "score": analyse.get("score", 5),
            "verdict": analyse.get("verdict", "moyen"),
            "eligible": analyse.get("eligible", True),
            "points_forts": analyse.get("points_forts", []),
            "points_faibles": analyse.get("points_faibles", []),
            "domaine": analyse.get("domaine", "Non classé"),
            "resume_analyse": analyse.get("resume", "")
        })
        offre["verdict"] = score_to_verdict(offre["score"])

        titre_lower = offre.get("titre", "").lower()
        desc_lower  = offre.get("description", "").lower()

        # Archivage auto avec raison — dépend du mode
        offre["raison_archivage"] = ""
        if mode == "job":
            # Mode job : on archive seulement les inéligibles (niveau/exp/durée non compatibles)
            if not offre.get("eligible", True) and offre.get("score", 10) <= 2:
                offre["statut"] = "archive"
                offre["raison_archivage"] = "note_basse"
                print(f"     -> Archivée automatiquement (inéligible score {offre['score']})")
        else:
            # Mode alternance : règles complètes
            if "boeth" in desc_lower or "maazi" in desc_lower or "situation de handicap" in desc_lower:
                offre["statut"] = "archive"
                offre["raison_archivage"] = "public_specifique"
                print(f"     -> Archivée automatiquement (réservé public spécifique / BOETH)")
            elif analyse.get("statut_auto") == "archive":
                offre["statut"] = "archive"
                offre["raison_archivage"] = "ecole_cfa"
            elif offre.get("domaine") == "Hors domaine":
                offre["statut"] = "archive"
                offre["raison_archivage"] = "hors_it"
                print(f"     -> Archivée automatiquement (hors domaine recherché)")
            elif "stage" in titre_lower:
                offre["statut"] = "archive"
                offre["raison_archivage"] = "stage"
                print(f"     -> Archivée automatiquement (stage détecté)")
            elif not offre.get("eligible", True) and offre.get("score", 10) <= 2:
                offre["statut"] = "archive"
                offre["raison_archivage"] = "note_basse"
                print(f"     -> Archivée automatiquement (inéligible score {offre['score']})")
        eligible_str = "eligible" if offre["eligible"] else "INELIGIBLE"
        print(f"     Score : {offre['score']}/10 — {offre['verdict']} — {eligible_str}")
        offres_analysees.append(offre)
        if callback:
            callback(i, len(offres), offre)
        time.sleep(PAUSE_MISTRAL)
    offres_analysees.sort(key=lambda x: x["score"], reverse=True)
    return offres_analysees
