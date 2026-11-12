"""
routes/candidatures.py
======================
Tableau Candidatures du mode (D107) : offres postulées et entreprises
contactées, statut de suivi.
"""

from typing import Literal

from fastapi import Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from auth.securite import utilisateur_requis
from database.models import User
from routes.commun import mode_requis, routeur_prive

router = routeur_prive()


# ─── Suivi unique des candidatures : offres postulées et spontanées (D107) ────
class StatutSuivi(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["offre", "spontanee"]
    id: str = Field(min_length=1, max_length=64)
    statut: str = Field(min_length=1, max_length=30)


@router.get("/api/suivi")
def api_suivi(user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    """Toutes les candidatures du mode, les plus récentes d'abord."""
    from database.suivi_db import lire_suivi
    return lire_suivi(user.id, mode)


@router.post("/api/suivi/statut")
def api_suivi_statut(body: StatutSuivi, user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    from database.suivi_db import modifier_statut
    if not modifier_statut(user.id, mode, body.type, body.id, body.statut):
        return JSONResponse({"erreur": "Candidature introuvable, ou statut impossible pour ce type"}, status_code=404)
    return {"ok": True}
