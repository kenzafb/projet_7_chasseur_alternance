"""
shared/modes.py
===============
Définit les "modes" de chasse : alternance, job (mission courte) et stage
(stage conventionné, phase 6b). Chaque mode décrit ce qui change dans la
recherche, l'analyse et l'interface.

Le mode vient de l'URL (/alternance, /job, /stage) et l'API le reçoit
explicitement à chaque requête (paramètre « mode ») : deux onglets dans
deux modes différents ne se gênent pas. Plus de mode en session.
"""

from shared.erreurs import ErreurUtilisateur

MODES = {
    "alternance": {
        "label": "Chasseur d'Alternance",
        "mot_poste": "alternance",        # pour les textes ("offre d'alternance"...)
        "couleur": "bleu",
        "sources": ["france_travail", "lba"],   # les deux sources
        # France Travail (SPEC_SOURCES 2.1) : apprentissage et professionnalisation,
        # aucun filtre de qualification ; domaines du profil (indifférent : aucun)
        "ft_filtres": {"natureContrat": ["E2", "FS"]},
        "ft_options": ["secteurs"],       # options du profil appliquées à la recherche
    },
    "job": {
        "label": "Chasseur de Job",
        "mot_poste": "job",               # "offre de job", "mission"...
        "couleur": "orange",
        "sources": ["france_travail"],    # FT seulement (pas d'alternance → pas de LBA)
        # France Travail : CDD, intérim, saisonnier ; aucun filtre de qualification
        # (qualification=0 écartait les offres « X », 61 % du total en IDF) ni
        # d'expérience ; domaines du profil, indifférent par défaut
        "ft_filtres": {"typeContrat": ["CDD", "MIS", "SAI"]},
        "ft_options": ["secteurs", "themes"],
        "ft_exclure_alternance": True,    # les contrats d'alternance en CDD sont écartés
        "limite_lot": 100,                # analyse 100 offres par run (le reste aux runs suivants)
    },
    "stage": {
        "label": "Chasseur de Stage",
        "mot_poste": "stage",
        "couleur": "vert",
        # Pas de LBA (alternance uniquement). France Travail n'a ni type ni
        # nature de contrat « stage » : mot-clé « stage » (essai du 9 octobre
        # 2026 : 73 offres en IDF, 55 E1, 12 E2, 6 FS), alternance (E2, FS)
        # écartée, intitulés filtrés par shared/referentiels/intitules_stage.txt
        "sources": ["france_travail"],
        "ft_filtres": {"motsCles": ["stage"]},
        "ft_options": ["secteurs"],
        "ft_exclure_alternance": True,    # natures E2 et FS : champ « alternance » de l'offre
        "ft_intitules_stage": True,       # « stage » doit désigner le poste
    },
}

MODE_DEFAUT = "alternance"

# Modes annoncés, pas encore ouverts : signalés « bientôt disponible » sur la
# page d'accueil, refusés par l'API (aucun depuis l'ouverture du stage)
MODES_A_VENIR: dict[str, dict] = {}

# Page d'accueil : choix du mode
TEXTES_ACCUEIL = {
    "alternance": ("Alternance", "Apprentissage ou professionnalisation : offres et candidatures spontanées."),
    "job":        ("Job", "CDD, intérim, saisonnier : missions courtes."),
    "stage":      ("Stage", "Stage conventionné : offres et candidatures spontanées."),
}


def get_mode(cle):
    """Retourne la config d'un mode, ou le mode par défaut si inconnu."""
    return MODES.get(cle or MODE_DEFAUT, MODES[MODE_DEFAUT])


def labels_modes():
    """Liste {cle, label, couleur} pour l'interface de choix."""
    return [{"cle": k, "label": v["label"], "couleur": v["couleur"]} for k, v in MODES.items()]


def verifier_mode(cle) -> str:
    """Mode reçu par l'API : un mode ouvert, sinon ErreurUtilisateur (400).
    Aucun défaut : le mode est toujours donné explicitement."""
    if not cle:
        raise ErreurUtilisateur("Mode manquant : chaque requête indique son mode (paramètre mode=alternance, job ou stage).")
    if cle in MODES_A_VENIR:
        raise ErreurUtilisateur(f"Le mode {cle} n'est pas encore disponible.")
    if cle not in MODES:
        raise ErreurUtilisateur(f"Mode inconnu : {cle}.")
    return cle


def modes_accueil() -> list[dict]:
    """Modes proposés sur la page d'accueil, ouverts puis à venir."""
    return [{"cle": cle, "nom": nom, "texte": texte, "bientot": cle in MODES_A_VENIR}
            for cle, (nom, texte) in TEXTES_ACCUEIL.items()]
