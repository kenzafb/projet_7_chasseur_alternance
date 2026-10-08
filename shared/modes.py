"""
shared/modes.py
===============
Définit les "modes" de chasse : alternance ou job (mission courte).
Chaque mode décrit ce qui change dans la recherche, l'analyse et l'interface.

Le mode par défaut est "alternance" → comportement historique inchangé.
"""

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
}

MODE_DEFAUT = "alternance"


def get_mode(cle):
    """Retourne la config d'un mode, ou le mode par défaut si inconnu."""
    return MODES.get(cle or MODE_DEFAUT, MODES[MODE_DEFAUT])


def labels_modes():
    """Liste {cle, label, couleur} pour l'interface de choix."""
    return [{"cle": k, "label": v["label"], "couleur": v["couleur"]} for k, v in MODES.items()]
