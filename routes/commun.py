"""
routes/commun.py
================
Ce que partagent les routeurs : gabarits Jinja, états des pipelines par
utilisateur, mode de la requête, limites d'un lancement, routeur privé.
"""

from fastapi import APIRouter, Depends, Query
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from auth.securite import utilisateur_requis
from shared import config
from shared.config import TEMPLATES_DIR
from shared.modes import verifier_mode
from shared.pipelines import Pipelines
from shared.statique import importmap, url_statique

templates = Jinja2Templates(directory=TEMPLATES_DIR)
# URL des JS et CSS versionnées par leur contenu (cache navigateur)
templates.env.globals.update(statique=url_statique, importmap=importmap)

# ─── États, arrêts et logs des pipelines, par utilisateur ─────────────────────
# Lu par les routeurs sous la forme commun.pipelines (jamais importé par son
# nom) : les tests le remplacent par une instance neuve à chaque test.
pipelines = Pipelines()


def routeur_prive() -> APIRouter:
    """Routeur dont chaque route exige une session : utilisateur_requis
    s'applique à toutes, qu'elles se servent de l'utilisateur ou non."""
    return APIRouter(dependencies=[Depends(utilisateur_requis)])


# ─── Mode de chasse : dans l'URL des pages, explicite pour l'API ──────────────
def mode_requis(mode: str | None = Query(None, description="Mode de chasse : alternance, job ou stage (obligatoire)")
                ) -> str:
    """Mode d'une requête de l'API, donné par le paramètre « mode » (le front
    l'ajoute à chaque appel, d'après l'URL de la page). Absent, inconnu ou
    pas encore ouvert : 400. Jamais lu dans la session : deux onglets dans
    deux modes différents ne se gênent pas."""
    return verifier_mode(mode)


class OffreId(BaseModel):
    id: str


# Limites d'un lancement : absentes = défaut, bornées par config.limite_lancement
def reglage(user_id: int, mode: str, cle: str):
    """Réglage avancé du mode (D145) : celui de la personne, sinon le défaut."""
    from database.profil_db import lire_profil
    from shared.reglages import reglages_complets
    return reglages_complets(lire_profil(user_id, mode=mode).get("reglages"))[cle]


def limite_appliquee(cle: str, demandee, disponibles: int | None = None, *,
                     user_id: int | None = None, mode: str | None = None) -> tuple[int, str]:
    """Limite appliquée à un lancement, bornée par le plafond et, s'il est
    donné, par le nombre d'éléments disponibles ; et la précision à
    journaliser quand la valeur demandée a été ramenée (décision D6).
    Rien de demandé : le réglage avancé du mode (D145), s'il est connu."""
    if demandee is None and user_id is not None and mode:
        demandee = reglage(user_id, mode, cle)
    appliquee = config.limite_lancement(cle, demandee)
    if disponibles is not None:
        appliquee = min(appliquee, disponibles)
    if demandee is None or demandee == appliquee:
        return appliquee, ""
    return appliquee, f" (demandé : {demandee}, ramené à {appliquee})"
