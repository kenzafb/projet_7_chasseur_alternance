import re
from shared.ia import appeler_structure
from shared.schemas_ia import AnalyseOffre
from shared.config import ia_longueur_description
from shared.erreurs import exiger_profil


# ─── Prompts d'analyse, un par mode ──────────────────────────────────────────
# Écrits pour un petit modèle local : courts, en français, seulement les
# champs du profil qui servent à noter, description tronquée
# (IA_LONGUEUR_DESCRIPTION), schéma JSON écrit en toutes lettres en plus du
# format imposé au serveur (shared.schemas_ia.AnalyseOffre).

LONGUEUR_CHAMP = 400   # caractères gardés d'un champ libre du profil

FORMAT_REPONSE = (
    "Réponds uniquement avec cet objet JSON :\n"
    '{"score": <entier de 0 à 10>, '
    '"points_forts": [<3 phrases courtes au plus>], "points_faibles": [<2 phrases courtes au plus>], '
    '"domaine": "<catégorie métier en 2 à 4 mots>", "resume": "<12 mots au plus>", '
    '"niveau_requis": "<bac, bac+2, bac+3, bac+4, bac+5 ou non_precise>", '
    '"duree_mois": <nombre ou null>, "date_debut_offre": "<texte ou null>", '
    '"alternance_seulement": <true ou false>, "niveau_exigence": "<exige, souhaite ou non_precise>"}'
)

# Ce que le modèle recopie de l'offre, sans juger : l'éligibilité qui en
# dépend (niveau, durée, dates, alternance) est décidée en Python (D94)
EXTRACTION = (
    "CHAMPS À RECOPIER DU TEXTE DE L'OFFRE, et de lui seul : jamais du profil du candidat. "
    "null (ou non_precise) si l'offre ne le dit pas.\n"
    "- niveau_requis : niveau d'études demandé au candidat dans le texte de l'offre (« école d'ingénieurs », "
    "« Master 2 » ou « Bac+5 » = bac+5 ; « licence » = bac+3 ; « BTS », « DUT » = bac+2). L'intitulé du poste "
    "(« Ingénieur système ») n'est pas un niveau d'études ;\n"
    "- niveau_exigence : exige si ce niveau est obligatoire ; souhaite s'il est écrit « ou équivalent », "
    "« idéalement », « de préférence » ou « souhaité » ; non_precise si l'offre ne demande aucun niveau ;\n"
    "- duree_mois : durée du stage ou du contrat écrite dans l'offre, en mois (6 mois = 6, 10 semaines = 2.5) ; "
    "ce n'est jamais la période du candidat ;\n"
    "- date_debut_offre : date ou mois de début écrit dans l'offre, avec l'année, null sinon ;\n"
    "- alternance_seulement : true si l'offre n'est proposée qu'en alternance ou apprentissage.\n\n"
    "Le niveau, la durée et les dates sont vérifiés à part : ne les compte pas dans la note."
)

ETALEMENT = ("Étale les notes : réserve 8 à 10 aux offres qui correspondent vraiment au profil et aux missions "
             "visées ; une offre correcte sans plus vaut 5 à 7 ; une offre éloignée, 3 à 4.")

SYSTEME = ("Tu es un recruteur qui évalue des offres pour un candidat. Tu réponds uniquement par un "
           "objet JSON valide, en français, sans texte autour.")


def _court(texte, longueur=LONGUEUR_CHAMP) -> str:
    texte = " ".join(str(texte or "").split())
    return texte if len(texte) <= longueur else texte[:longueur].rsplit(" ", 1)[0] + "…"


def _lignes(champs) -> str:
    """« - Libellé : valeur » pour chaque valeur non vide."""
    return "\n".join(f"- {libelle} : {valeur}" for libelle, valeur in champs if valeur)


def _domaines(profil) -> str:
    from shared.domaines import domaines_du_profil, libelles_domaines
    return ", ".join(libelles_domaines(domaines_du_profil(profil)))


def _projets(profil) -> str:
    return " | ".join(_court(f"{p.get('nom', '')} : {p.get('description', '')}", 150)
                      for p in (profil.get("projets") or [])[:3] if p.get("nom") or p.get("description"))


def contexte_alternance(profil) -> str:
    projets = _projets(profil)
    return _lignes([
        ("Niveau visé (diplôme préparé par le contrat)", _court(profil.get("niveau_vise"))),
        ("Formation", _court(profil.get("formation"))),
        ("Ce que la formation va lui apporter", _court(profil.get("formation_apporte"))),
        ("Compétences", _court(", ".join(profil.get("competences") or []))),
        ("Expérience", _court(profil.get("experience"))),
        ("Projets", projets),
        ("Langues", _court(profil.get("langues"), 150)),
        ("Préfère éviter", _court(profil.get("criteres_eviter"))),
        ("Domaines recherchés", _domaines(profil) or "ceux qui correspondent au profil"),
    ])


def contexte_job(profil) -> str:
    return _lignes([
        ("Niveau d'études obtenu", _court(profil.get("niveau_etudes"), 150)),
        ("Expérience", _court(profil.get("experience"))),
        ("Compétences", _court(", ".join(profil.get("competences") or []))),
        ("Projets", _projets(profil)),
        ("Atouts (langues, permis, savoir-être)", _court(profil.get("langues"), 200)),
        ("Durée de contrat souhaitée", _court(profil.get("duree_souhaitee"), 150)),
        ("Disponibilité (dates)", _court((profil.get("recherche") or {}).get("disponibilite"), 150)),
        ("Disponibilité horaire", _court(profil.get("dispo_horaires"), 150)),
        ("Mobilité", _court(profil.get("mobilite"), 150)),
        ("Types de jobs qui conviennent", _court(profil.get("types_jobs_ok"))),
        ("Types de jobs à éviter", _court(profil.get("types_jobs_eviter"))),
        ("Localisation préférée", _court(profil.get("localisation_pref"), 150)),
        ("Domaines préférés", _domaines(profil)),
    ])


def contexte_stage(profil) -> str:
    from shared.stage import date_en_lettres, lire_date
    debut, fin = lire_date(profil.get("date_debut") or None), lire_date(profil.get("date_fin") or None)
    periode = ""
    if debut and fin:
        periode = f"du {date_en_lettres(debut)} au {date_en_lettres(fin)}"
        if profil.get("duree_semaines"):
            periode += f" ({profil['duree_semaines']} semaines)"
    from shared.eligibilite import niveau_du_profil
    niveau = niveau_du_profil(profil)
    return _lignes([
        ("Niveau d'études", _court(profil.get("niveau_etudes"), 150) or niveau["libelle"]),
        ("Formation", _court(profil.get("formation"), 200)),
        ("Établissement", _court(profil.get("etablissement"), 200)),
        ("Missions visées", _court(profil.get("missions"))),
        ("Compétences", _court(", ".join(profil.get("competences") or []))),
        ("Expérience", _court(profil.get("experience"))),
        ("Projets", _projets(profil)),
        ("Période du stage", periode or "non précisée"),
        ("Domaines recherchés", _domaines(profil) or "ceux qui correspondent aux missions visées"),
    ])


# Ce que le code vérifie déjà n'est pas demandé au modèle : type ou nature
# de contrat (filtres France Travail du mode, alternance écartée en job et en
# stage, intitulés du stage), lieu (Île-de-France), niveau visé des offres
# LBA. Les dates des offres ne sont que du texte libre : le modèle les juge.
REGLES = {
    "alternance": (
        "Tu évalues une offre d'alternance pour ce candidat.",
        contexte_alternance,
        "NOTE BASSE (0 à 2) si l'une de ces conditions est vraie :\n"
        "- le poste réel est hors des domaines recherchés ;\n"
        "- l'offre exige 3 ans d'expérience ou plus ;\n"
        "- le poste est senior (ingénieur confirmé, architecte, senior), sauf offre d'une école ou d'un CFA.\n\n"
        "NOTE de 0 à 10, d'après les missions réelles et non le seul titre :\n"
        "- 9-10 : domaine recherché, niveau cohérent avec le niveau visé, plusieurs compétences du candidat utiles ;\n"
        "- 7-8 : bon accord avec une ou deux réserves (niveau non précisé, compétences manquantes, lieu éloigné) ;\n"
        "- 5-6 : accord moyen (niveau un peu au-dessus, compétences importantes manquantes) ;\n"
        "- 3-4 : faible accord (domaine éloigné, prérequis incompatibles) ;\n"
        "- 0-2 : conditions de note basse ci-dessus.\n"
        "Une compétence demandée que la formation va apporter n'est qu'un point faible mineur ; une compétence "
        "absente du profil et de la formation est un point faible important. Si le poste correspond à ce que "
        "le candidat préfère éviter, baisse la note. La date de début et la disponibilité ne comptent pas.\n\n"
        "domaine : catégorie métier courte (ex. « Développement web », « Gestion locative »), ou exactement "
        "« Hors domaine » si le poste réel est hors des domaines recherchés.",
    ),
    "job": (
        "Tu évalues une offre de job court (mission, CDD, intérim, saisonnier) pour ce candidat : "
        "est-elle accessible et adaptée ?",
        contexte_job,
        "NOTE BASSE (0 à 2) si l'une de ces conditions est vraie :\n"
        "- l'offre exige plus d'expérience que la sienne (« souhaitée » ou « appréciée » n'élimine pas) ;\n"
        "- la durée minimale du contrat dépasse ce que le candidat peut faire (plus court : c'est bien) ;\n"
        "- le poste correspond clairement aux types de jobs à éviter.\n\n"
        "NOTE de 0 à 10. Critère principal : l'accord avec les préférences écrites dans le profil (types de "
        "jobs, horaires, mobilité, durée, localisation, domaines). N'applique AUCUNE préférence que le profil "
        "n'exprime pas. Utilise toute l'échelle et départage nettement deux offres :\n"
        "- 9-10 : un type de job qui convient, rien ne contredit ses contraintes, proche de sa localisation préférée ;\n"
        "- 7-8 : accessible (débutant accepté) et compatible sans correspondre exactement, ou dans un domaine préféré ;\n"
        "- 5-6 : accessible avec un vrai bémol (horaires peu compatibles, loin, hors de ses types de jobs) ;\n"
        "- 3-4 : proche de ce qu'il veut éviter, ou plusieurs défauts ;\n"
        "- 0-2 : conditions de note basse ci-dessus.\n"
        "Un job sans diplôme ni expérience exigés vaut environ 7 au départ. Une durée minimale nettement trop "
        "longue plafonne la note vers 4-5 ; des horaires incompatibles coûtent plusieurs points ; sans "
        "permis, préfère un lieu accessible en transports. Sans localisation préférée, la distance ne compte "
        "pas. La date de début ne compte pas.\n\n"
        "domaine : catégorie métier courte (ex. « Vente », « Restauration », « Manutention »).",
    ),
    "stage": (
        "Tu évalues une offre de stage pour cet étudiant.",
        contexte_stage,
        "NOTE BASSE (0 à 2) si l'une de ces conditions est vraie :\n"
        "- ce n'est pas un stage pour un étudiant (emploi salarié, formation payante) ;\n"
        "- le poste réel est hors des domaines recherchés.\n\n"
        "NOTE de 0 à 10, d'après les missions réelles et non le seul titre :\n"
        "- 9-10 : missions proches des missions visées, domaine recherché ;\n"
        "- 7-8 : bon accord avec une ou deux réserves (missions un peu différentes) ;\n"
        "- 5-6 : accord moyen (missions assez éloignées) ;\n"
        "- 3-4 : faible accord ;\n"
        "- 0-2 : conditions de note basse ci-dessus.\n"

        "domaine : catégorie métier courte, ou exactement « Hors domaine » si le poste réel est hors des "
        "domaines recherchés.",
    ),
}


def construire_messages(offre, profil, mode="alternance") -> list[dict]:
    """Messages envoyés à l'IA pour analyser une offre dans un mode."""
    intro, contexte, regles = REGLES.get(mode, REGLES["alternance"])
    description = _court(offre.get("description"), ia_longueur_description())
    prompt = (
        f"{intro}\n\n"
        f"=== PROFIL DU CANDIDAT (sert seulement à la note) ===\n{contexte(profil)}\n\n"
        "=== TEXTE DE L'OFFRE (seule source des champs à recopier) ===\n"
        f"Titre : {offre.get('titre', '')}\n"
        f"Entreprise : {offre.get('entreprise', '') or 'non précisée'}\n"
        f"Lieu : {offre.get('lieu', '') or 'non précisé'}\n"
        f"Description : {description}\n"
        "=== FIN DU TEXTE DE L'OFFRE ===\n\n"
        f"{regles}\n{ETALEMENT}\n\n"
        f"{EXTRACTION}\n\n"
        f"{FORMAT_REPONSE}"
    )
    return [{"role": "system", "content": SYSTEME}, {"role": "user", "content": prompt}]


def analyser_offre(offre, profil, mode="alternance", modele=None, essais=2):
    """Analyse d'une offre par l'IA (modèle de l'usage « analyse », ou
    `modele`). ErreurIABloquante et ErreurIAPassagere (dont ReponseInvalide)
    remontent : jamais de note inventée. En alternance, une offre d'école ou
    de CFA est marquée à archiver (statut_auto)."""
    exiger_profil(profil)   # plus de repli sur un utilisateur par défaut
    analyse = appeler_structure(construire_messages(offre, profil, mode), AnalyseOffre,
                                usage="analyse", modele=modele, essais=essais, temperature=0.1)
    result = _valider_analyse(analyse)
    appliquer_eligibilite(result, offre, profil, mode)
    # Mode stage : une école peut accueillir un stagiaire (D74), rien à archiver
    if mode == "alternance" and est_ecole_cfa(offre):
        result["statut_auto"] = "archive"
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


def appliquer_eligibilite(result: dict, offre: dict, profil: dict, mode: str) -> dict:
    """Critères bloquants décidés en Python (shared/eligibilite.py) à partir
    des champs extraits de l'offre, d'abord contrôlés contre son texte
    (une valeur absente du texte devient non précisée, extraits_ecartes) :
    inéligible, score plafonné à 3, verdict « ineligible », raison en tête
    des points faibles et dans raison_ineligibilite. Niveau seulement
    souhaité : score baissé de 1 à 2 points, raison dans les points faibles.
    Une information non précisée ne bloque jamais."""
    from shared.eligibilite import (PLAFOND_SCORE_INELIGIBLE, controler_extraits, penalite_souhait,
                                    raisons_ineligibilite)
    result["extraits_ecartes"] = controler_extraits(result, offre)
    points, souhait = penalite_souhait(result, profil)
    if points:
        result["score"] = max(0, result["score"] - points)
        if result["eligible"]:
            result["verdict"] = score_to_verdict(result["score"])
        result["points_faibles"] = [souhait] + result["points_faibles"][:2]
    raisons = raisons_ineligibilite(result, profil, mode)
    result["raison_ineligibilite"] = " ; ".join(raisons)
    if raisons:
        result["eligible"] = False
        result["score"] = min(result["score"], PLAFOND_SCORE_INELIGIBLE)
        result["verdict"] = "ineligible"
        result["points_faibles"] = [f"Inéligible : {r}" for r in raisons] + result["points_faibles"][:2]
    return result


def _valider_analyse(analyse: AnalyseOffre) -> dict:
    """Analyse validée par son schéma (score entier ramené à 0..10 en Python,
    tous les champs présents), mise au format de l'application : verdict déduit du score
    (excellent, bon, moyen, faible), listes raccourcies. Le modèle ne décide
    jamais de l'éligibilité (D99) : éligible jusqu'à ce que les règles
    Python (appliquer_eligibilite) en décident autrement. Rien n'est
    complété par défaut, sauf un domaine vide (« Non classé »)."""
    result = analyse.model_dump()
    result["eligible"] = True
    result["verdict"] = score_to_verdict(result["score"])
    result["points_forts"] = result["points_forts"][:3]
    result["points_faibles"] = result["points_faibles"][:2]
    result["domaine"] = result["domaine"] or "Non classé"
    return result


def score_to_verdict(score):
    """Verdict d'un score : « ineligible » n'en sort jamais, il ne vient que
    des règles Python (shared/eligibilite.py, D99)."""
    if score >= 9: return "excellent"
    if score >= 7: return "bon"
    if score >= 5: return "moyen"
    return "faible"

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
        # Mode job : on archive seulement les inéligibles, établis en Python (D95, D99)
        if not offre.get("eligible", True):
            offre["statut"] = "archive"
            offre["raison_archivage"] = "ineligible"
            _log(f"     -> Archivée automatiquement (inéligible, score {offre['score']})")
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
        elif not offre.get("eligible", True):
            offre["statut"] = "archive"
            offre["raison_archivage"] = "ineligible"
            _log(f"     -> Archivée automatiquement (inéligible, score {offre['score']})")


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


# Offre insérée sans analyse (toute offre trouvée par la recherche) : verdict
# « non_analysee », ni score ni points ; analysée ensuite en différé
# (france_travail/analyse_differee.py) ou une à une par le bouton « Analyser ».
VERDICT_NON_ANALYSEE = "non_analysee"


def archivage_mots_cles(offre, mode="alternance") -> str | None:
    """Raison d'archivage établie sans IA, ou None. Mode alternance :
    réservée à un public spécifique, école ou CFA, stage ; mode stage :
    réservée seulement (une école peut accueillir un stagiaire, le mot
    « stage » est attendu) ; mode job : aucune."""
    if mode == "job":
        return None
    titre_lower = (offre.get("titre") or "").lower()
    desc_lower = (offre.get("description") or "").lower()
    if reserve_public_specifique(desc_lower) or reserve_public_specifique(titre_lower):
        return "public_specifique"
    if mode == "stage":
        return None
    if est_ecole_cfa(offre):
        return "ecole_cfa"
    if "stage" in titre_lower:
        return "stage"
    return None


MESSAGES_ARCHIVAGE = {"public_specifique": "réservé public spécifique / BOETH", "ecole_cfa": "école/CFA détectée",
                      "stage": "stage détecté"}


def marquer_non_analysee(offre, mode="alternance", verbeux=True):
    """Prépare une offre pour l'insertion sans analyse et applique les seules
    règles d'archivage qui ne dépendent pas d'une analyse
    (archivage_mots_cles). Jamais d'archivage pour note basse ni hors
    domaine. Modifie offre en place."""
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
    raison = archivage_mots_cles(offre, mode)
    if raison:
        offre["statut"], offre["raison_archivage"] = "archive", raison
        if verbeux:
            print(f"     -> Archivée automatiquement ({MESSAGES_ARCHIVAGE[raison]})")
    return offre
