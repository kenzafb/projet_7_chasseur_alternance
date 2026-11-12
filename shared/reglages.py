"""
shared/reglages.py
==================
Réglages avancés d'un mode (profils.reglages, D145), modifiables dans
Paramètres : plafonds de chaque lancement et « toute la file » pour la
notation de nuit. Enregistrés côté serveur : ils suivent la personne d'un
appareil à l'autre. Une valeur absente prend le défaut de
config.LIMITES_LANCEMENT ; toute valeur est bornée à [1, plafond].
"""

from shared import config

CASES = ("analyse_toute_file",)   # réglages oui / non


def normaliser_reglages(reglages) -> dict:
    """Copie propre : plafonds entiers bornés, cases booléennes, le reste retiré."""
    if not isinstance(reglages, dict):
        return {}
    out = {}
    for cle, valeur in reglages.items():
        if cle in config.LIMITES_LANCEMENT:
            try:
                out[cle] = config.limite_lancement(cle, int(valeur))
            except (TypeError, ValueError):
                continue
        elif cle in CASES:
            out[cle] = valeur is True
    return out


def reglages_complets(reglages) -> dict:
    """Chaque réglage avec sa valeur : celle de la personne, sinon le défaut."""
    propres = normaliser_reglages(reglages)
    complets = {cle: propres.get(cle, regle["defaut"]) for cle, regle in config.LIMITES_LANCEMENT.items()}
    complets.update({cle: propres.get(cle, False) for cle in CASES})
    return complets
