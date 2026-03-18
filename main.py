import json
import os
from scraper import chercher_offres, sauvegarder_offres_vues
from analyseur import analyser_offres

FICHIER_CANDIDATURES = "candidatures.json"


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

    # Tri global par score décroissant
    candidatures.sort(key=lambda x: x.get("score", 0), reverse=True)
    sauvegarder_candidatures(candidatures)
    return ajoutees


def lancer_recherche(analyser=True, max_analyse=999):
    print("\n" + "=" * 55)
    print("   CHASSEUR D'ALTERNANCE — Recherche en cours")
    print("=" * 55 + "\n")

    nouvelles_offres, offres_vues = chercher_offres()

    if not nouvelles_offres:
        print("Aucune nouvelle offre trouvée.")
        return []

    if analyser:
        offres_analysees = analyser_offres(nouvelles_offres[:max_analyse])
        # Les éventuelles non analysées (si max_analyse < total)
        for o in nouvelles_offres[max_analyse:]:
            o.update({"score": 5, "verdict": "non analysé", "points_forts": [],
                      "points_faibles": [], "resume_analyse": "Non analysée — cliquer pour analyser"})
        toutes = offres_analysees + nouvelles_offres[max_analyse:]
    else:
        for o in nouvelles_offres:
            o.update({"score": 5, "verdict": "non analysé", "points_forts": [],
                      "points_faibles": [], "resume_analyse": "Non analysée"})
        toutes = nouvelles_offres

    nb = ajouter_candidatures(toutes)

    for offre in toutes:
        offres_vues.add(offre["id"])
    sauvegarder_offres_vues(offres_vues)

    print(f"\n{nb} nouvelles offres ajoutées au tableau de bord !")
    print("Ouvre http://localhost:5002 pour les voir.\n")
    return toutes
