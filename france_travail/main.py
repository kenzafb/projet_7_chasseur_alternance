"""
france_travail/main.py
======================
Pipeline "offres" : recherche France Travail, analyse IA, puis écriture
de chaque offre via le callback on_offre (l'appelant écrit en base).
Les offres déjà vues sont suivies en base par utilisateur et par mode
(database/dedup_db.py).
"""

from france_travail.scraper import chercher_offres
from france_travail.analyseur import analyser_offres


def lancer_recherche(user_id, profil, analyser=True, max_analyse=999, on_offre=None, mode="alternance"):
    """Recherche France Travail puis analyse d'au plus max_analyse offres.
    Seules les offres retenues sont marquées vues : celles au-delà de la
    limite seront proposées au lancement suivant. Retourne les offres retenues."""
    print("\nRecherche des offres...")
    from shared.modes import get_mode
    cfg = get_mode(mode)
    ft_params = cfg["ft_params"]
    filtrer_domaines = cfg["utilise_domaines"]
    # Domaines choisis par l'utilisateur (seulement si le mode filtre par domaine)
    from shared.domaines import ft_grands_domaines
    cles_domaines = profil.get("recherche", {}).get("domaines", [])
    grands_domaines = ft_grands_domaines(cles_domaines) if filtrer_domaines else None
    lot = min(cfg.get("limite_lot") or max_analyse, max_analyse)
    nouvelles_offres = chercher_offres(
        user_id, grands_domaines, ft_params=ft_params, filtrer_domaines=filtrer_domaines,
        mode=mode, limite_lot=lot)

    if not nouvelles_offres:
        print("Aucune nouvelle offre.")
        return []

    if analyser:
        # Callback : sauvegarde chaque offre dès qu'elle est analysée
        def sauvegarder_au_fur(index, total, offre_analysee):
            on_offre(offre_analysee)

        analyser_offres(nouvelles_offres, profil=profil, callback=sauvegarder_au_fur, mode=mode)
    else:
        for offre in nouvelles_offres:
            on_offre(offre)

    return nouvelles_offres
