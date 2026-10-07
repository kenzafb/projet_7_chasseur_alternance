"""
france_travail/main.py
======================
Pipeline "offres" : recherche France Travail, analyse IA, puis écriture
de chaque offre via le callback on_offre (l'appelant écrit en base).
"""

from france_travail.scraper import chercher_offres, sauvegarder_offres_vues
from france_travail.analyseur import analyser_offres


def lancer_recherche(analyser=True, max_analyse=999, on_offre=None, profil=None, mode="alternance"):
    print("\nRecherche des offres...")
    from shared.modes import get_mode
    cfg = get_mode(mode)
    ft_params = cfg["ft_params"]
    filtrer_domaines = cfg["utilise_domaines"]
    # Domaines choisis par l'utilisateur (seulement si le mode filtre par domaine)
    from shared.domaines import ft_grands_domaines
    cles_domaines = (profil or {}).get("recherche", {}).get("domaines", [])
    grands_domaines = ft_grands_domaines(cles_domaines) if filtrer_domaines else None
    nouvelles_offres, offres_vues = chercher_offres(
        grands_domaines, ft_params=ft_params, filtrer_domaines=filtrer_domaines,
        mode=mode, limite_lot=cfg.get("limite_lot"))

    if not nouvelles_offres:
        print("Aucune nouvelle offre.")
        return []

    if analyser:
        # Callback : sauvegarde chaque offre dès qu'elle est analysée
        def sauvegarder_au_fur(index, total, offre_analysee):
            on_offre(offre_analysee)

        analyser_offres(nouvelles_offres[:max_analyse], profil=profil, callback=sauvegarder_au_fur, mode=mode)
    else:
        for offre in nouvelles_offres:
            on_offre(offre)

    for offre in nouvelles_offres:
        offres_vues.add(offre["id"])
    sauvegarder_offres_vues(offres_vues)

    return nouvelles_offres
