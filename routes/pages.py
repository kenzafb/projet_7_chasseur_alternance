"""
routes/pages.py
===============
Pages HTML : choix du mode (/) et page de chaque mode (/alternance, /job,
/stage), toutes privées.
"""


from fastapi import Request
from fastapi.responses import RedirectResponse

from auth.securite import LONGUEUR_MIN_MOT_DE_PASSE
from france_travail.generateur import (lettre_par_defaut)
from routes.commun import routeur_prive, templates
from shared import config
from shared.modes import MODE_DEFAUT, MODES, get_mode, modes_accueil

router = routeur_prive()


@router.get("/")
def accueil(request: Request, bienvenue: str | None = None):
    """Choix du mode. Ancienne URL d'après l'inscription (/?bienvenue=1) :
    redirigée vers le profil du mode alternance."""
    if bienvenue:
        return RedirectResponse(url=f"/{MODE_DEFAUT}?bienvenue=1", status_code=303)
    # Mode de l'ancienne session, pour les anciens liens « /#page »
    ancien = request.session.get("mode")
    return templates.TemplateResponse(request, "accueil.html", {
        "modes": modes_accueil(), "ancien_mode": ancien if ancien in MODES else MODE_DEFAUT})


def _page_du_mode(request: Request, mode: str):
    return templates.TemplateResponse(request, "base.html", {"mode": mode, "label_mode": get_mode(mode)["label"],
                                                             "sources": get_mode(mode)["sources"],
                                                             "limites": config.LIMITES_LANCEMENT,
                                                             "analyse_ia": config.analyse_ia_active(),
                                                             "modele_analyse": config.modele_ia("analyse"),
                                                             "exemple_lettre": lettre_par_defaut(mode),
                                                             "longueur_min_mot_de_passe": LONGUEUR_MIN_MOT_DE_PASSE})

@router.get("/alternance")
def page_alternance(request: Request):
    return _page_du_mode(request, "alternance")

@router.get("/job")
def page_job(request: Request):
    return _page_du_mode(request, "job")

@router.get("/stage")
def page_stage(request: Request):
    return _page_du_mode(request, "stage")
