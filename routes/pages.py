"""
routes/pages.py
===============
Pages HTML : choix du mode (/) et page de chaque mode (/alternance, /job,
/stage), toutes privées.
"""


from fastapi import Depends, Request
from fastapi.responses import RedirectResponse

from auth.securite import LONGUEUR_MIN_MOT_DE_PASSE, utilisateur_requis
from database.models import User
from database.profil_db import lire_profil
from lettres.redaction import (lettre_par_defaut)
from routes.commun import routeur_prive, templates
from shared import config
from shared.reglages import reglages_complets
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
    return templates.TemplateResponse(request, "choix_mode.html", {
        "modes": modes_accueil(), "ancien_mode": ancien if ancien in MODES else MODE_DEFAUT})


def initiales(profil: dict, email: str) -> str:
    """Initiales du rond « Mon compte » : prénom et nom du profil du mode,
    sinon la première lettre de l'email."""
    lettres = "".join((profil.get(champ) or "").strip()[:1] for champ in ("prenom", "nom"))
    return (lettres or (email or "?")[:1]).upper()


def _page_du_mode(request: Request, mode: str, user: User):
    profil = lire_profil(user.id, mode=mode)
    return templates.TemplateResponse(request, "base.html", {"mode": mode, "label_mode": get_mode(mode)["label"],
                                                             "initiales": initiales(profil, user.email),
                                                             "email_utilisateur": user.email,
                                                             "sources": get_mode(mode)["sources"],
                                                             "limites": config.LIMITES_LANCEMENT,
                                                             "reglages": reglages_complets(profil.get("reglages")),
                                                             "analyse_auto": bool(profil.get("analyse_auto")),
                                                             "analyse_ia": config.analyse_ia_active(),
                                                             "modele_analyse": config.modele_ia("analyse"),
                                                             "exemple_lettre": lettre_par_defaut(mode),
                                                             "longueur_min_mot_de_passe": LONGUEUR_MIN_MOT_DE_PASSE})

@router.get("/alternance")
def page_alternance(request: Request, user: User = Depends(utilisateur_requis)):
    return _page_du_mode(request, "alternance", user)

@router.get("/job")
def page_job(request: Request, user: User = Depends(utilisateur_requis)):
    return _page_du_mode(request, "job", user)

@router.get("/stage")
def page_stage(request: Request, user: User = Depends(utilisateur_requis)):
    return _page_du_mode(request, "stage", user)
