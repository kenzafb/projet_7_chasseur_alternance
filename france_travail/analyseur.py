import time
import json
import re
from shared.ia import ErreurIABloquante, ErreurIAPassagere, appeler_mistral, reponse_json
from shared.erreurs import exiger_profil

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
    from shared.domaines import domaines_du_profil, libelles_domaines
    domaines_pref   = ", ".join(libelles_domaines(domaines_du_profil(profil)))

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
    if domaines_pref:  parties.append(f"DOMAINES PRÉFÉRÉS (optionnel) : {domaines_pref}")
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
        "Le critère N°1 est l'ADÉQUATION AUX PRÉFÉRENCES DU CANDIDAT telles qu'il les a écrites "
        "dans son profil : types de jobs qui lui conviennent, types de jobs à éviter, disponibilité "
        "horaire, mobilité, durée souhaitée, localisation et domaines préférés. Juge la nature réelle "
        "du poste (rythme, effort physique, contact client, horaires, tâches) depuis la description "
        "et compare-la à ces préférences. N'applique AUCUNE préférence que le profil n'exprime pas.\n\n"
        "Barème (sois DISCRIMINANT, écarte vraiment les notes) :\n"
        "9-10 : le poste correspond clairement à un type de job qui convient au candidat, rien ne "
        "contredit ses contraintes (horaires, durée, mobilité) ET il est proche de sa localisation "
        "préférée s'il en a une. Le top du candidat.\n"
        "7-8 : bon job accessible (débutant accepté, pas d'expérience exigée) et compatible avec ses "
        "préférences sans y correspondre exactement, OU dans un de ses domaines préférés. "
        "Job 'standard correct'.\n"
        "5-6 : accessible MAIS avec un vrai bémol : horaires peu compatibles avec sa disponibilité "
        "horaire, OU loin de sa localisation préférée, OU éloigné des types de jobs qui lui conviennent.\n"
        "3-4 : peu adapté : proche de ce que le candidat veut éviter, ou cumul de défauts "
        "(loin + horaires incompatibles + hors de ses types de jobs).\n"
        "1-2 : inéligible (voir section inéligibilité).\n\n"
        "Principes IMPORTANTS :\n"
        "- PRÉFÉRENCES = critère prioritaire. Deux postes également accessibles ne doivent PAS avoir "
        "la même note si l'un correspond mieux aux types de jobs souhaités ou s'éloigne moins de ce "
        "que le candidat veut éviter : départage-les nettement.\n"
        "- Si le profil ne précise ni types de jobs souhaités ni types à éviter, juge surtout "
        "l'accessibilité et la compatibilité pratique (horaires, durée, trajet).\n"
        "- DURÉE : si la durée MINIMALE du contrat dépasse nettement le maximum du candidat "
        "(ex. un CDD de plusieurs mois pour quelqu'un qui ne peut travailler que quelques semaines), "
        "ce n'est pas qu'un détail : BAISSE la note de plusieurs points (plafonne autour de 4-5 même "
        "si le job est sympa). Une durée plus courte ou flexible (intérim, saisonnier) est au "
        "contraire un BON point.\n"
        "- HORAIRES : compare les horaires de l'offre (nuit, week-end, coupures, temps partiel...) à "
        "la disponibilité horaire du candidat ; une incompatibilité nette coûte plusieurs points.\n"
        "- LOCALISATION : si une localisation préférée est indiquée, plus c'est proche, mieux c'est ; "
        "un poste juste à côté mérite un bonus, un poste loin perd des points (sans être éliminé). "
        "Sans localisation préférée, ne note pas la distance.\n"
        "- DOMAINE : un job dans un des domaines préférés du candidat, ou proche de son expérience, "
        "est un bon point.\n"
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

    # Appel Mistral avec retry sur les erreurs passagères (4 tentatives, pauses 15s, 30s, 45s).
    # ErreurIABloquante / ErreurIAPassagere remontent : jamais de note inventée.
    response = appeler_mistral(
        [
            {"role": "system", "content": (
                "Tu es un recruteur spécialisé dans les jobs courts et missions. "
                "Tu reponds UNIQUEMENT en JSON valide sans backticks. "
                "Tu ignores totalement la date de debut et la disponibilite dans ta notation."
            )},
            {"role": "user", "content": prompt},
        ],
        usage="analyse",
        response_format={"type": "json_object"},
    )
    return _valider_analyse(reponse_json(response))


def analyser_offre(offre, profil, mode="alternance"):
    # Profil obligatoire (plus de repli sur un utilisateur par défaut)
    exiger_profil(profil)

    # ─── Mode JOB : prompt dédié (job court accessible) ───
    if mode == "job":
        return _analyser_offre_job(offre, profil)

    contexte = construire_contexte_profil(profil)
    # Domaines recherchés par le candidat (libellés lisibles)
    from shared.domaines import domaines_du_profil, libelles_domaines
    _labels = libelles_domaines(domaines_du_profil(profil))
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

    est_ecole = est_ecole_cfa(offre)

    # Appel Mistral avec retry sur les erreurs passagères (4 tentatives, pauses 15s, 30s, 45s).
    # ErreurIABloquante / ErreurIAPassagere remontent : jamais de note inventée.
    response = appeler_mistral(
        [
            {"role": "system", "content": (
                "Tu es un recruteur spécialisé en alternance. Tu reponds UNIQUEMENT en JSON valide sans backticks. "
                "Tu ignores totalement la date de debut et la disponibilite dans ta notation."
            )},
            {"role": "user", "content": prompt},
        ],
        usage="analyse",
        response_format={"type": "json_object"},
        on_attente=lambda t, n, s: print(
            f"     Mistral indisponible - pause {s}s puis nouvelle tentative ({t}/{n - 1})"),
    )
    result = _valider_analyse(reponse_json(response))
    if est_ecole:
        result["statut_auto"] = "archive"
        print(f"     → Archivée automatiquement (école/CFA détectée)")
    return result

# Détection écoles/CFA (mots-clés) → archivage automatique
ECOLES_MOTS_CLES = [
    "iscod", "scholia", "imc alternance", "mydigitalschool", "simplon",
    "afpa", "cfa", "epitech", "openclassrooms", "studi", "ikigai",
    "la plateforme", "digital campus", "m2i", "doranco", "efficom",
    "ecole", "organisme de formation", "centre de formation",
    "hitema", "h3", "igs", "isefac", "sup de vinci",
    "aureis","nexa","Groupe IGF",
]


def est_ecole_cfa(offre) -> bool:
    """Vrai si l'offre semble publiée par une école ou un CFA (mots-clés
    dans la description, l'entreprise ou le titre ; pas d'IA)."""
    description_lower = (offre.get("description") or "").lower()
    entreprise_lower = (offre.get("entreprise") or "").lower()
    titre_lower = (offre.get("titre") or "").lower()
    return any(
        mot in description_lower or mot in entreprise_lower or mot in titre_lower
        for mot in ECOLES_MOTS_CLES
    )


def _valider_analyse(result: dict) -> dict:
    """Analyse renvoyée par Mistral, contrôlée : un score entier de 1 à 10 est
    exigé (sinon ErreurIAPassagere, l'offre sera reprise), le reste est
    normalisé. Aucune valeur de repli pour le score ou l'éligibilité."""
    try:
        score = int(result["score"])
    except (KeyError, TypeError, ValueError):
        raise ErreurIAPassagere("Réponse de Mistral sans score exploitable") from None
    result["score"] = max(1, min(10, score))
    result["eligible"] = bool(result.get("eligible", True))
    if not result["eligible"]:
        result["score"] = min(result["score"], 2)
    result["verdict"] = score_to_verdict(result["score"])
    for cle in ("points_forts", "points_faibles"):
        if not isinstance(result.get(cle), list):
            result[cle] = []
    # Domaine : on garde la catégorie libre donnée par l'IA (ou "Non classé" si vide)
    if not result.get("domaine"):
        result["domaine"] = "Non classé"
    result["resume"] = str(result.get("resume") or "")
    return result


def score_to_verdict(score):
    if score >= 9: return "excellent"
    if score >= 7: return "bon"
    if score >= 5: return "moyen"
    if score >= 3: return "faible"
    return "ineligible"

# ─── Offres réservées à un public spécifique (BOETH, RQTH) ────────────────────
# La mention d'égalité des chances (« ce poste est ouvert aux personnes en
# situation de handicap », « à compétences égales ») est présente sur une
# grande partie des offres : elle ne réserve rien. Seules des tournures de
# réservation ou d'exigence explicites archivent l'offre.
_PUBLIC = (r"(?:boeth|rqth|travailleurs? handicap[eé]s?|situation de handicap|obligation d'emploi"
           r"|reconnaissance de la qualit[eé] de travailleur handicap[eé])")
_RESERVATIONS = [re.compile(motif) for motif in (
    # « réservé(e)(s) / exclusivement / uniquement / seulement aux ... BOETH »
    rf"(?:r[eé]serv[eé]e?s?|exclusivement|uniquement|seulement)\s+(?:(?:ouverte?s?|accessibles?)\s+)?"
    rf"(?:aux?|à la|à des|à une|pour les?|pour des)\s+[^.;:!?\n]{{0,80}}?{_PUBLIC}",
    # « offre destinée aux travailleurs handicapés »
    rf"destin[eé]e?s?\s+(?:exclusivement\s+|uniquement\s+)?(?:aux?|à des)\s+[^.;:!?\n]{{0,40}}?{_PUBLIC}",
    # « offre / poste / recrutement BOETH » ou « offre réservée BOETH »
    rf"(?:offre|poste|recrutement|emploi)s?\s+(?:r[eé]serv[eé]e?s?\s+)?(?:aux?\s+)?(?:boeth|rqth)\b",
    # « RQTH obligatoire / exigée / requise / indispensable / impérative »
    rf"{_PUBLIC}[^.;:!?\n]{{0,40}}?\b(?:obligatoire|exig[eé]e?s?|requise?s?|indispensable|imp[eé]rati(?:f|ve|vement))",
    # « vous devez être bénéficiaire de l'obligation d'emploi / titulaire d'une RQTH »
    rf"(?:devez|doit|doivent|il faut|n[eé]cessaire d')\s*(?:être|etre|disposer d'une|avoir (?:une|la))\s+"
    rf"[^.;:!?\n]{{0,40}}?{_PUBLIC}",
)]


def reserve_public_specifique(texte: str) -> bool:
    """Vrai si l'offre est réservée aux bénéficiaires de l'obligation d'emploi
    (BOETH, RQTH...), et non simplement ouverte à tous."""
    t = (texte or "").lower().replace("’", "'")
    return any(motif.search(t) for motif in _RESERVATIONS)


def appliquer_archivage_auto(offre, analyse, mode="alternance", verbeux=True):
    """
    Règles d'archivage automatique d'une offre analysée, avec raison.
    Modifie offre en place (statut, raison_archivage).

    Un domaine "Hors domaine" (valeur imposée par le prompt) donne la raison
    "hors_domaine".
    verbeux : affiche la raison de l'archivage dans la console.
    """
    _log = print if verbeux else (lambda *a, **k: None)
    titre_lower = offre.get("titre", "").lower()
    desc_lower  = offre.get("description", "").lower()

    offre["raison_archivage"] = ""
    if mode == "job":
        # Mode job : on archive seulement les inéligibles (niveau/exp/durée non compatibles)
        if not offre.get("eligible", True) and offre.get("score", 10) <= 2:
            offre["statut"] = "archive"
            offre["raison_archivage"] = "note_basse"
            _log(f"     -> Archivée automatiquement (inéligible score {offre['score']})")
    else:
        # Mode alternance : règles complètes
        if reserve_public_specifique(desc_lower) or reserve_public_specifique(titre_lower):
            offre["statut"] = "archive"
            offre["raison_archivage"] = "public_specifique"
            _log(f"     -> Archivée automatiquement (réservé public spécifique / BOETH)")
        elif analyse.get("statut_auto") == "archive":
            offre["statut"] = "archive"
            offre["raison_archivage"] = "ecole_cfa"
        elif offre.get("domaine") == "Hors domaine":
            offre["statut"] = "archive"
            offre["raison_archivage"] = "hors_domaine"
            _log(f"     -> Archivée automatiquement (hors domaine recherché)")
        elif "stage" in titre_lower and mode != "stage":
            offre["statut"] = "archive"
            offre["raison_archivage"] = "stage"
            _log(f"     -> Archivée automatiquement (stage détecté)")
        elif not offre.get("eligible", True) and offre.get("score", 10) <= 2:
            offre["statut"] = "archive"
            offre["raison_archivage"] = "note_basse"
            _log(f"     -> Archivée automatiquement (inéligible score {offre['score']})")


def appliquer_analyse(offre, analyse, mode="alternance", verbeux=True):
    """Recopie dans l'offre une analyse réussie (validée par _valider_analyse)
    puis applique l'archivage automatique."""
    offre.update({
        "score":          analyse["score"],
        "verdict":        analyse["verdict"],
        "eligible":       analyse["eligible"],
        "points_forts":   analyse["points_forts"],
        "points_faibles": analyse["points_faibles"],
        "domaine":        analyse["domaine"],
        "resume_analyse": analyse["resume"],
    })
    appliquer_archivage_auto(offre, analyse, mode=mode, verbeux=verbeux)


# Offre insérée sans analyse (ANALYSE_IA=false) : verdict « non_analysee »,
# ni score ni points ; elle pourra être réanalysée quand l'IA reviendra.
VERDICT_NON_ANALYSEE = "non_analysee"


def marquer_non_analysee(offre, mode="alternance", verbeux=True):
    """Prépare une offre pour l'insertion sans IA et applique les seules
    règles d'archivage qui ne dépendent pas d'une analyse (mode alternance :
    réservée à un public spécifique, école ou CFA, stage ; mode stage :
    réservée à un public spécifique seulement, une école peut accueillir un
    stagiaire et le mot « stage » est attendu). Jamais d'archivage pour note
    basse ni hors domaine. Modifie offre en place."""
    _log = print if verbeux else (lambda *a, **k: None)
    offre.update({
        "score":          None,
        "verdict":        VERDICT_NON_ANALYSEE,
        "eligible":       True,
        "points_forts":   [],
        "points_faibles": [],
        "domaine":        "",
        "resume_analyse": "",
        "raison_archivage": "",
    })
    if mode == "job":
        return offre
    titre_lower = (offre.get("titre") or "").lower()
    desc_lower = (offre.get("description") or "").lower()
    if reserve_public_specifique(desc_lower) or reserve_public_specifique(titre_lower):
        offre["statut"], offre["raison_archivage"] = "archive", "public_specifique"
        _log("     -> Archivée automatiquement (réservé public spécifique / BOETH)")
    elif mode == "stage":
        pass
    elif est_ecole_cfa(offre):
        offre["statut"], offre["raison_archivage"] = "archive", "ecole_cfa"
        _log("     -> Archivée automatiquement (école/CFA détectée)")
    elif "stage" in titre_lower:
        offre["statut"], offre["raison_archivage"] = "archive", "stage"
        _log("     -> Archivée automatiquement (stage détecté)")
    return offre


def analyser_offres(offres, profil, callback=None, mode="alternance", log_fn=None):
    """Analyse les offres une à une ; callback(i, total, offre) pour chaque
    offre analysée. Erreur passagère (quota, serveur, réponse illisible) :
    l'offre est sautée, le callback n'est pas appelé (ni écrite ni marquée
    vue : elle reviendra). ErreurIABloquante : remonte, le pipeline s'arrête."""
    _log = log_fn or print
    offres_analysees = []
    for i, offre in enumerate(offres, 1):
        print(f"  [{i}/{len(offres)}] {offre['titre'][:50]}...")
        try:
            analyse = analyser_offre(offre, profil, mode=mode)
        except ErreurIAPassagere as e:
            _log(f"  ⚠️  Offre sautée, « {offre['titre'][:50]} » : {e}. Elle reviendra au prochain lancement.")
            time.sleep(PAUSE_MISTRAL)
            continue
        appliquer_analyse(offre, analyse, mode=mode)
        eligible_str = "eligible" if offre["eligible"] else "INELIGIBLE"
        print(f"     Score : {offre['score']}/10 — {offre['verdict']} — {eligible_str}")
        offres_analysees.append(offre)
        if callback:
            callback(i, len(offres), offre)
        time.sleep(PAUSE_MISTRAL)
    offres_analysees.sort(key=lambda x: x["score"], reverse=True)
    return offres_analysees
