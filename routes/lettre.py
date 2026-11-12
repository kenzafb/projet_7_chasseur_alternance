"""
routes/lettre.py
================
Lettre de motivation (D106, D138) : paragraphe rédigé par l'IA, assemblage
avec la lettre type, PDF généré puis téléchargé.
"""

import os

from fastapi import Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from auth.securite import utilisateur_requis
from database.candidatures_db import (enregistrer_lettre_pdf,
                                     lire_candidature, lire_lettre_pdf, modifier_candidature)
from database.models import User
from database.profil_db import (lire_profil)
from france_travail.generateur import (A_COMPLETER, assembler_lettre, exiger_lettre_type, infos_lettre,
                                      marqueurs_a_completer, rediger_paragraphe_verifie)
from france_travail.pdf_generator import generer_pdf_lettre, nom_telechargement
from routes.commun import OffreId, mode_requis, routeur_prive
from shared import config
from shared.config import chemin_lettre_pdf
from shared.erreurs import CHAMPS_IDENTITE, exiger_profil

router = routeur_prive()


class Assembler(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    paragraphe: str = Field(max_length=3000)

class TelechargerPdf(BaseModel):
    id: str
    lettre: str | None = None


# ─── Lettre : lettre type du profil, paragraphe par l'IA (D106) ───────────────
@router.post("/api/lettre/paragraphe")
def api_lettre_paragraphe(body: OffreId, user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    """Paragraphe personnalisé rédigé par l'IA, rien n'est enregistré : il
    est affiché, modifiable, puis inséré par /api/lettre/assembler. Lettre
    type absente ou sans {paragraphe} : 400 qui renvoie au profil, avant
    tout appel à l'IA."""
    offre = lire_candidature(user.id, body.id, mode=mode)
    if not offre:
        return JSONResponse({"erreur": "Offre introuvable"}, status_code=404)
    profil = lire_profil(user.id, mode=mode)
    from france_travail.generateur import exiger_lettre_type
    exiger_profil(profil, CHAMPS_IDENTITE)
    exiger_lettre_type(profil)
    if not config.analyse_ia_active():
        return JSONResponse({"erreur": "Rédaction du paragraphe indisponible : l'IA est désactivée "
                                       "(ANALYSE_IA=false). Écris le paragraphe toi-même, puis insère-le."},
                            status_code=503)
    paragraphe, avertissement = rediger_paragraphe_verifie(offre, profil, mode=mode)
    return {"paragraphe": paragraphe, "avertissement": avertissement}

@router.post("/api/lettre/assembler")
def api_lettre_assembler(body: Assembler, user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    """Insère le paragraphe validé dans la lettre type (sans IA) et enregistre
    la lettre ; une offre « nouvelle » passe « en cours »."""
    offre = lire_candidature(user.id, body.id, mode=mode)
    if not offre:
        return JSONResponse({"erreur": "Offre introuvable"}, status_code=404)
    profil = lire_profil(user.id, mode=mode)
    lettre = assembler_lettre(offre, profil, body.paragraphe)
    modifs = {"lettre": lettre}
    if offre.get("statut") in (None, "", "nouveau"):
        modifs["statut"] = "en_cours"
    modifier_candidature(user.id, body.id, modifs, mode=mode)
    a_completer = marqueurs_a_completer(lettre)
    # Entreprise inconnue : informations neutres (D138) ; portfolio vide : à compléter (D125)
    return {"lettre": lettre, "a_completer": a_completer,
            "message": " ; ".join(dict.fromkeys(A_COMPLETER[b] for b in a_completer)),
            "infos": infos_lettre(offre, exiger_lettre_type(profil))}


@router.post("/api/telecharger_pdf")
def api_telecharger_pdf(body: TelechargerPdf, request: Request, user: User = Depends(utilisateur_requis),
                        mode: str = Depends(mode_requis)):
    """Génère le PDF de la lettre et renvoie l'URL de téléchargement."""
    offre = lire_candidature(user.id, body.id, mode=mode)
    if not offre:
        return JSONResponse({"erreur": "Non trouvé"}, status_code=404)
    lettre = body.lettre or offre.get("lettre")
    if not lettre:
        return JSONResponse({"erreur": "Vide"}, status_code=400)
    profil = lire_profil(user.id, mode=mode)
    fichier = generer_pdf_lettre(offre, lettre, profil, user.id)
    ancien = enregistrer_lettre_pdf(user.id, body.id, fichier, mode=mode)
    # Le PDF précédent de cette candidature est remplacé : on le supprime
    chemin_ancien = chemin_lettre_pdf(ancien or "")
    if chemin_ancien and ancien != fichier:
        try:
            os.remove(chemin_ancien)
        except OSError:
            pass
    return {"ok": True, "url": f"/api/lettre_pdf/{body.id}?mode={mode}", "nom": nom_telechargement(offre, profil)}

@router.get("/api/lettre_pdf/{ref_offre}")
def api_lettre_pdf(ref_offre: str, request: Request, user: User = Depends(utilisateur_requis),
                   mode: str = Depends(mode_requis)):
    """Renvoie le PDF d'une candidature de l'utilisateur connecté, en pièce
    jointe. Celui d'un autre utilisateur est introuvable (404)."""
    relatif = lire_lettre_pdf(user.id, ref_offre, mode=mode)
    chemin = chemin_lettre_pdf(relatif)
    # Défense en profondeur : le fichier doit être dans le dossier de l'utilisateur
    if not (chemin and relatif.startswith(f"user_{user.id}/") and chemin.is_file()):
        return JSONResponse({"erreur": "PDF introuvable"}, status_code=404)
    offre = lire_candidature(user.id, ref_offre, mode=mode) or {}
    nom = nom_telechargement(offre, lire_profil(user.id, mode=mode))
    return FileResponse(chemin, media_type="application/pdf", filename=nom)
