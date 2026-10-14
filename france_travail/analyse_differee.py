"""
france_travail/analyse_differee.py
==================================
Analyse en différé des offres « non analysées » (décision D21, phase 7).

La recherche insère toujours ses offres sans analyse : elle ne dépend pas
de l'IA et ne l'attend pas. Ce pipeline, lancé par l'utilisateur (ou
après chaque recherche si l'option du profil est cochée), reprend les
offres en attente d'un utilisateur dans un mode, des plus récentes aux plus
anciennes, au plus une limite par lancement, et enregistre chaque analyse
dès qu'elle est obtenue, avec l'archivage complet qui en dépend (note
basse, hors domaine, école ou CFA en alternance).

Jamais de résultat inventé : une offre dont l'analyse échoue (réponse
invalide, délai dépassé) reste « non analysée » et revient au lancement
suivant ; une erreur bloquante (IA injoignable, modèle absent) arrête le
lancement.
"""

import collections
import threading
import time

from database.candidatures_db import lire_candidature, lire_en_attente, modifier_candidature
from france_travail.analyseur import analyser_offre, appliquer_analyse, archivage_mots_cles
from shared.ia import ErreurIAPassagere, verifier_demarrage

# Champs de l'offre écrits après une analyse réussie
CHAMPS_ANALYSE = ("score", "verdict", "eligible", "points_forts", "points_faibles", "domaine",
                  "resume_analyse")


def enregistrer_analyse(user_id: int, mode: str, offre: dict, analyse: dict) -> dict:
    """Écrit une analyse réussie et l'archivage qui en découle. Une offre que
    l'utilisateur a déjà déplacée (statut autre que « nouveau ») garde son
    statut : l'archivage automatique ne touche qu'aux nouvelles. Retourne
    les modifications écrites."""
    copie = dict(offre)
    appliquer_analyse(copie, analyse, mode=mode, verbeux=False)
    modifs = {champ: copie[champ] for champ in CHAMPS_ANALYSE}
    actuelle = lire_candidature(user_id, offre["id"], mode=mode) or offre
    if copie.get("statut") == "archive" and actuelle.get("statut", "nouveau") == "nouveau":
        modifs["statut"] = "archive"
        modifs["raison_archivage"] = copie.get("raison_archivage") or ""
    modifier_candidature(user_id, offre["id"], modifs, mode=mode)
    return modifs


# Durée d'une analyse : moyenne des dernières mesurées dans ce processus,
# sinon une valeur prudente (ministral-3:8b sur processeur : une à deux minutes)
DUREE_ANALYSE_DEFAUT_S = 90
_durees = collections.deque(maxlen=50)
_verrou_durees = threading.Lock()


def noter_duree(secondes: float):
    with _verrou_durees:
        _durees.append(secondes)


def duree_moyenne_s() -> float:
    with _verrou_durees:
        return sum(_durees) / len(_durees) if _durees else DUREE_ANALYSE_DEFAUT_S


def estimation_file(en_attente: int) -> dict:
    """Temps estimé pour vider la file : {"secondes", "texte", "mesure"}
    (mesure : faux tant qu'aucune analyse n'a été chronométrée)."""
    secondes = en_attente * duree_moyenne_s()
    with _verrou_durees:
        mesure = bool(_durees)
    return {"secondes": secondes, "texte": duree_lisible(secondes) if en_attente else "", "mesure": mesure}


def duree_lisible(secondes: float | None) -> str:
    """« environ 12 min », « moins d'une minute » ; vide si inconnue."""
    if secondes is None:
        return ""
    minutes = round(secondes / 60)
    if minutes < 1:
        return "moins d'une minute"
    if minutes < 60:
        return f"environ {minutes} min"
    return f"environ {minutes // 60} h {minutes % 60:02d}"


def analyser_en_attente(user_id: int, mode: str, profil: dict, maximum: int, stop_event=None,
                        log=print, on_progress=None, horloge=time.monotonic) -> dict:
    """Analyse au plus `maximum` offres en attente, les plus récentes d'abord.
    on_progress(faites, total, restant_s) après chaque offre (restant_s :
    durée moyenne d'une offre traitée fois le nombre restant).
    Retourne {"analysees", "sautees", "archivees", "arret"}. Les erreurs
    bloquantes de l'IA remontent (le lancement s'arrête)."""
    # Test de démarrage du modèle avant tout : échec = arrêt, aucune analyse dégradée
    verifier_demarrage(usage="analyse")
    offres = lire_en_attente(user_id, mode, limite=maximum)
    total = len(offres)
    bilan = {"analysees": 0, "sautees": 0, "archivees": 0, "mots_cles": 0, "arret": False}
    debut = horloge()
    if on_progress:
        on_progress(0, total, None)
    for i, offre in enumerate(offres, 1):
        if stop_event and stop_event.is_set():
            bilan["arret"] = True
            log(f"⏹️  Analyse arrêtée : {i - 1}/{total} offres traitées, les autres restent en attente.")
            break
        titre = (offre.get("titre") or "?")[:60]
        # Mots-clés d'abord : une offre qui serait archivée de toute façon n'est pas analysée
        raison = archivage_mots_cles(offre, mode)
        if raison:
            if (lire_candidature(user_id, offre["id"], mode=mode) or offre).get("statut", "nouveau") == "nouveau":
                modifier_candidature(user_id, offre["id"], {"statut": "archive", "raison_archivage": raison}, mode=mode)
            bilan["mots_cles"] += 1
            log(f"  [{i}/{total}] « {titre} » archivée par mots-clés ({raison}), sans IA")
            if on_progress:
                on_progress(i, total, (horloge() - debut) / i * (total - i))
            continue
        debut_offre = horloge()
        try:
            analyse = analyser_offre(offre, profil, mode=mode)
        except ErreurIAPassagere as e:
            bilan["sautees"] += 1
            log(f"  ⚠️  [{i}/{total}] « {titre} » sautée : {e}. Elle reste à analyser.")
        else:
            noter_duree(horloge() - debut_offre)
            modifs = enregistrer_analyse(user_id, mode, offre, analyse)
            bilan["analysees"] += 1
            archive = ""
            if modifs.get("statut") == "archive":
                bilan["archivees"] += 1
                archive = f", archivée ({modifs['raison_archivage']})"
            log(f"  [{i}/{total}] « {titre} » : {modifs['score']}/10, {modifs['verdict']}{archive}")
        if on_progress:
            ecoule = horloge() - debut
            on_progress(i, total, ecoule / i * (total - i))
    return bilan
