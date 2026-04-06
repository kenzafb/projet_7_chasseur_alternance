import json
import os

from france_travail.scraper import chercher_offres, sauvegarder_offres_vues
from france_travail.analyseur import analyser_offres

FICHIER_CANDIDATURES = "data/candidatures.json"

def charger_candidatures():
    if os.path.exists(FICHIER_CANDIDATURES):
        with open(FICHIER_CANDIDATURES, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def sauvegarder_candidatures(candidatures):
    with open(FICHIER_CANDIDATURES, "w", encoding="utf-8") as f:
        json.dump(candidatures, f, ensure_ascii=False, indent=2)


def ajouter_candidatures(nouvelles_offres):
    candidatures = charger_candidatures()
    ids_existants = {c["id"] for c in candidatures}
    ajoutees = 0
    for offre in nouvelles_offres:
        if offre["id"] not in ids_existants:
            offre.setdefault("statut", "nouveau")
            offre.setdefault("lettre", "")
            offre.setdefault("email_candidature", "")
            offre.setdefault("date_candidature", "")
            offre.setdefault("notes", "")
            candidatures.append(offre)
            ajoutees += 1
    candidatures.sort(key=lambda x: x.get("score", 0), reverse=True)
    sauvegarder_candidatures(candidatures)
    return ajoutees


def lancer_recherche(analyser=True, max_analyse=999):
    print("\nRecherche des offres...")
    nouvelles_offres, offres_vues = chercher_offres()

    if not nouvelles_offres:
        print("Aucune nouvelle offre.")
        return []

    if analyser:
        # Callback : sauvegarde chaque offre dès qu'elle est analysée
        def sauvegarder_au_fur(index, total, offre_analysee):
            ajouter_candidatures([offre_analysee])

        analyser_offres(nouvelles_offres[:max_analyse], callback=sauvegarder_au_fur)
    else:
        ajouter_candidatures(nouvelles_offres)

    for offre in nouvelles_offres:
        offres_vues.add(offre["id"])
    sauvegarder_offres_vues(offres_vues)

    return nouvelles_offres
