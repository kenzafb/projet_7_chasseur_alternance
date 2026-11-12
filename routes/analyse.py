"""
routes/analyse.py
=================
Analyse des offres en attente par l'IA, en différé (D21) : lancement dans
un thread, arrêt, état ; analyse automatique après une recherche.
"""

import threading

from fastapi import Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from auth.securite import utilisateur_requis
from database.candidatures_db import (compter_en_attente)
from database.models import User
from database.profil_db import (lire_profil)
from france_travail.analyse_differee import analyser_en_attente, duree_lisible, estimation_file
from routes import commun
from routes.commun import limite_appliquee, mode_requis, routeur_prive
from shared import config
from shared.erreurs import ErreurUtilisateur, exiger_profil
from shared.ia import ErreurIABloquante
from shared.pipelines import ANALYSE

router = routeur_prive()


class Analyse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_analyses: int | None = None
    toute_la_file: bool = False   # lancement de nuit : toutes les offres en attente, sans plafond


# ─── Analyse des offres en attente (D21) ──────────────────────────────────────
def _lancer_analyse(user_id: int, mode: str, maximum: int, note: str = "") -> bool:
    """Lance l'analyse des offres en attente dans un thread. False si une
    analyse de l'utilisateur tourne déjà (tous modes confondus)."""
    profil = lire_profil(user_id, mode=mode)
    if not commun.pipelines.demarrer(ANALYSE, user_id, message="Analyse des offres en attente...", mode=mode):
        return False
    arret = commun.pipelines.evenement_arret(user_id, ANALYSE)

    def log(msg):
        commun.pipelines.log(user_id, msg)

    def progression(faites, total, restant_s):
        reste = duree_lisible(restant_s) if faites < total else ""
        commun.pipelines.maj(ANALYSE, user_id, faites=faites, total=total, restant_s=restant_s,
                      pourcentage=round(faites / total * 100) if total else 100,
                      message=f"Analyse {faites}/{total}" + (f", {reste} restantes" if reste else ""))

    def lancer():
        log(f"🧠 Analyse des offres en attente démarrée (au plus {maximum}){note}, "
            f"modèle {config.modele_ia('analyse')}")
        try:
            bilan = analyser_en_attente(user_id, mode, profil, maximum, stop_event=arret, log=log,
                                        on_progress=progression)
            fin = (f"{bilan['analysees']} offres analysées, {bilan['archivees']} archivées, "
                   f"{bilan['sautees']} sautées")
            if bilan["mots_cles"]:
                fin += f", {bilan['mots_cles']} archivées par mots-clés sans IA"
            commun.pipelines.maj(ANALYSE, user_id, message=("Arrêtée : " if bilan["arret"] else "Terminée : ") + fin)
            log(f"✅ Analyse terminée : {fin}")
        except ErreurIABloquante as e:
            # IA injoignable, modèle absent... : arrêt immédiat, rien d'inventé
            commun.pipelines.maj(ANALYSE, user_id, message=f"Erreur : {e}")
            log(f"❌ Analyse arrêtée : {e}")
        except Exception as e:
            commun.pipelines.maj(ANALYSE, user_id, message=f"Erreur : {e}")
            log(f"❌ Erreur analyse : {e}")
        finally:
            commun.pipelines.terminer(ANALYSE, user_id)

    threading.Thread(target=lancer, daemon=True).start()
    return True


def analyse_automatique(user_id: int, mode: str):
    """Après une recherche, si l'option du profil est cochée : analyse des
    offres en attente avec la limite par défaut. Rien sans IA ni offre."""
    if not config.analyse_ia_active():
        commun.pipelines.log(user_id, f"ℹ️  Analyse automatique non lancée : {config.MESSAGE_IA_DESACTIVEE}")
        return
    if not compter_en_attente(user_id, mode):
        return
    maximum = config.limite_lancement("analyses", None)
    if not _lancer_analyse(user_id, mode, maximum, note=" (automatique après la recherche)"):
        commun.pipelines.log(user_id, "ℹ️  Analyse automatique non lancée : une analyse tourne déjà.")


@router.post("/api/analyse")
def api_analyse(body: Analyse | None = None, user: User = Depends(utilisateur_requis),
                mode: str = Depends(mode_requis)):
    """Analyse les offres « non analysées » du mode, les plus récentes d'abord."""
    if not config.analyse_ia_active():
        raise ErreurUtilisateur("Analyse indisponible : l'IA est désactivée (ANALYSE_IA=false).")
    exiger_profil(lire_profil(user.id, mode=mode))
    disponibles = compter_en_attente(user.id, mode)
    if not disponibles:
        raise ErreurUtilisateur("Aucune offre en attente d'analyse dans ce mode.")
    if body and body.toute_la_file:
        maximum = disponibles
        note = f" (toute la file : {disponibles} offres, {estimation_file(disponibles)['texte']})"
    else:
        maximum, note = limite_appliquee("analyses", body.max_analyses if body else None, disponibles)
    if not _lancer_analyse(user.id, mode, maximum, note):
        en_cours = commun.pipelines.etat(ANALYSE, user.id).get("mode")
        return JSONResponse({"erreur": f"Analyse déjà en cours (mode {en_cours})"}, status_code=400)
    return {"status": "démarré", "max_analyses": maximum, "en_attente": disponibles,
            "estimation": estimation_file(maximum)}

@router.post("/api/analyse/stop")
def api_analyse_stop(user: User = Depends(utilisateur_requis)):
    """Arrête l'analyse en cours de l'utilisateur, après l'offre en cours."""
    en_cours = commun.pipelines.demander_arret(user.id, ANALYSE)
    if en_cours:
        commun.pipelines.log(user.id, "⏹️  Arrêt de l'analyse demandé (après l'offre en cours)")
    return {"ok": True, "en_cours": en_cours}

@router.get("/api/analyse/statut")
def api_analyse_statut(user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    en_attente = compter_en_attente(user.id, mode)
    return {**commun.pipelines.etat(ANALYSE, user.id), "en_attente": en_attente, "estimation": estimation_file(en_attente)}
