import json
import re
from shared.ia import ErreurIABloquante, ErreurIAPassagere, appeler_structure
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
    '{"score": <entier de 1 à 10>, "eligible": <true ou false>, '
    '"points_forts": [<3 phrases courtes au plus>], "points_faibles": [<2 phrases courtes au plus>], '
    '"domaine": "<catégorie métier en 2 à 4 mots>", "resume": "<12 mots au plus>"}'
)

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


def contexte_alternance(profil) -> str:
    projets = " | ".join(_court(f"{p.get('nom', '')} : {p.get('description', '')}", 150)
                         for p in (profil.get("projets") or [])[:3])
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
    return _lignes([
        ("Formation", _court(profil.get("formation"), 200)),
        ("Établissement", _court(profil.get("etablissement"), 200)),
        ("Missions visées", _court(profil.get("missions"))),
        ("Période du stage", periode or "non précisée"),
        ("Domaines recherchés", _domaines(profil) or "ceux qui correspondent aux missions visées"),
    ])


REGLES = {
    "alternance": (
        "Tu évalues une offre d'alternance pour ce candidat.",
        contexte_alternance,
        "INÉLIGIBLE (eligible false, score 1 ou 2) si l'une de ces conditions est vraie :\n"
        "- le poste réel est hors des domaines recherchés ;\n"
        "- l'offre exige un niveau d'études nettement supérieur au niveau visé (ex. Bac+5 pour un Bac+2) ;\n"
        "- l'offre exige 3 ans d'expérience ou plus ;\n"
        "- le poste est senior (ingénieur confirmé, architecte, senior), sauf offre d'une école ou d'un CFA.\n\n"
        "NOTE de 1 à 10, d'après les missions réelles et non le seul titre :\n"
        "- 9-10 : domaine recherché, niveau cohérent avec le niveau visé, plusieurs compétences du candidat utiles ;\n"
        "- 7-8 : bon accord avec une ou deux réserves (niveau non précisé, compétences manquantes, lieu éloigné) ;\n"
        "- 5-6 : accord moyen (niveau un peu au-dessus, compétences importantes manquantes) ;\n"
        "- 3-4 : faible accord (domaine éloigné, prérequis incompatibles) ;\n"
        "- 1-2 : inéligible.\n"
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
        "INÉLIGIBLE (eligible false, score 1 ou 2) si l'une de ces conditions est vraie :\n"
        "- l'offre exige un diplôme que le candidat n'a pas ;\n"
        "- l'offre exige plus d'expérience que la sienne (« souhaitée » ou « appréciée » n'élimine pas) ;\n"
        "- la durée minimale du contrat dépasse ce que le candidat peut faire (plus court : c'est bien) ;\n"
        "- le poste correspond clairement aux types de jobs à éviter.\n\n"
        "NOTE de 1 à 10. Critère principal : l'accord avec les préférences écrites dans le profil (types de "
        "jobs, horaires, mobilité, durée, localisation, domaines). N'applique AUCUNE préférence que le profil "
        "n'exprime pas. Utilise toute l'échelle et départage nettement deux offres :\n"
        "- 9-10 : un type de job qui convient, rien ne contredit ses contraintes, proche de sa localisation préférée ;\n"
        "- 7-8 : accessible (débutant accepté) et compatible sans correspondre exactement, ou dans un domaine préféré ;\n"
        "- 5-6 : accessible avec un vrai bémol (horaires peu compatibles, loin, hors de ses types de jobs) ;\n"
        "- 3-4 : proche de ce qu'il veut éviter, ou plusieurs défauts ;\n"
        "- 1-2 : inéligible.\n"
        "Un job sans diplôme ni expérience exigés vaut environ 7 au départ. Une durée minimale nettement trop "
        "longue plafonne la note vers 4-5 ; des horaires incompatibles coûtent plusieurs points ; sans "
        "permis, préfère un lieu accessible en transports. Sans localisation préférée, la distance ne compte "
        "pas. La date de début ne compte pas.\n\n"
        "domaine : catégorie métier courte (ex. « Vente », « Restauration », « Manutention »).",
    ),
    "stage": (
        "Tu évalues une offre de stage pour cet étudiant.",
        contexte_stage,
        "INÉLIGIBLE (eligible false, score 1 ou 2) si l'une de ces conditions est vraie :\n"
        "- ce n'est pas un stage pour un étudiant (emploi salarié, alternance, formation payante) ;\n"
        "- le poste réel est hors des domaines recherchés ;\n"
        "- l'offre exige un niveau d'études nettement supérieur à la formation de l'étudiant ;\n"
        "- les dates sont incompatibles : durée minimale exigée nettement plus longue que sa période, ou "
        "début après la fin de sa période.\n\n"
        "NOTE de 1 à 10, d'après les missions réelles et non le seul titre :\n"
        "- 9-10 : missions proches des missions visées, domaine recherché, niveau et dates compatibles ;\n"
        "- 7-8 : bon accord avec une ou deux réserves (missions un peu différentes, dates non précisées) ;\n"
        "- 5-6 : accord moyen (missions assez éloignées, niveau un peu au-dessus) ;\n"
        "- 3-4 : faible accord ;\n"
        "- 1-2 : inéligible.\n"
        "Des dates absentes de l'offre ne sont pas une pénalité.\n\n"
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
        f"CANDIDAT\n{contexte(profil)}\n\n"
        "OFFRE\n"
        f"Titre : {offre.get('titre', '')}\n"
        f"Entreprise : {offre.get('entreprise', '') or 'non précisée'}\n"
        f"Lieu : {offre.get('lieu', '') or 'non précisé'}\n"
        f"Description : {description}\n\n"
        f"{regles}\n\n"
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
                                usage="analyse", modele=modele, essais=essais, temperature=0.2)
    result = _valider_analyse(analyse)
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


def _valider_analyse(analyse: AnalyseOffre) -> dict:
    """Analyse validée par son schéma (score entier de 1 à 10, tous les champs
    présents), mise au format de l'application : verdict déduit du score,
    score ramené à 2 pour une offre inéligible, listes raccourcies. Rien
    n'est complété par défaut, sauf un domaine vide (« Non classé »)."""
    result = analyse.model_dump()
    if not result["eligible"]:
        result["score"] = min(result["score"], 2)
    result["verdict"] = score_to_verdict(result["score"])
    result["points_forts"] = result["points_forts"][:3]
    result["points_faibles"] = result["points_faibles"][:2]
    result["domaine"] = result["domaine"] or "Non classé"
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
            continue
        appliquer_analyse(offre, analyse, mode=mode)
        eligible_str = "eligible" if offre["eligible"] else "INELIGIBLE"
        print(f"     Score : {offre['score']}/10 — {offre['verdict']} — {eligible_str}")
        offres_analysees.append(offre)
        if callback:
            callback(i, len(offres), offre)
    offres_analysees.sort(key=lambda x: x["score"], reverse=True)
    return offres_analysees
