"""
france_travail/main.py
======================
Pipeline "offres" : recherche France Travail, puis écriture de chaque
offre « non analysée » via le callback on_offre (l'appelant écrit en base).
L'analyse par l'IA vient après, en différé (france_travail/analyse_differee.py) :
la recherche n'attend jamais l'IA. Les offres déjà vues sont suivies en
base par utilisateur et par mode (database/dedup_db.py).
"""

from france_travail.scraper import chercher_offres
from france_travail.analyseur import marquer_non_analysee
from database.dedup_db import marquer_offres_vues


def lancer_recherche(user_id, profil, max_offres=999, on_offre=None, mode="alternance", log_fn=None):
    """Recherche France Travail, au plus max_offres nouvelles offres. Chaque
    offre est écrite « non analysée » (archivage par mots-clés seulement)
    puis marquée vue ; celles au-delà de la limite reviendront au lancement
    suivant. Retourne les offres écrites."""
    print("\nRecherche des offres...")
    from shared.criteres import criteres_france_travail
    from shared.modes import get_mode
    cfg = get_mode(mode)
    lot = min(cfg.get("limite_lot") or max_offres, max_offres)
    nouvelles_offres = chercher_offres(
        user_id, criteres_france_travail(profil, mode), mode=mode, limite_lot=lot, marquer=False,
        log=log_fn or print)

    if not nouvelles_offres:
        print("Aucune nouvelle offre.")
        return []

    for offre in nouvelles_offres:
        marquer_non_analysee(offre, mode=mode)
        on_offre(offre)
        marquer_offres_vues(user_id, mode, {offre["id"]})
    return nouvelles_offres
