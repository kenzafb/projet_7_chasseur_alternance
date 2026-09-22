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
        # France Travail : filtre apprentissage
        "ft_params": {"natureContrat": "E2"},
        "utilise_domaines": True,         # filtre par grand domaine / ROME
    },
    "job": {
        "label": "Chasseur de Job",
        "mot_poste": "job",               # "offre de job", "mission"...
        "couleur": "orange",
        "sources": ["france_travail"],    # FT seulement (pas d'alternance → pas de LBA)
        # France Travail : CDD + intérim + saisonnier, non-cadre, tous domaines
        # Pas de filtre experience (trop d'offres sans mention) → Mistral juge le niveau
        "ft_params": {"typeContrat": "CDD,MIS,SAI", "qualification": "0"},
        "utilise_domaines": False,        # tous domaines, on ne filtre pas
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
