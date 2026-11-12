"""
routes/profil.py
================
Profil du mode : lecture et enregistrement, référentiels proposés dans la
page (domaines, secteurs, tailles), pièces jointes, copie de sections depuis
un autre mode (D117).
"""

import os
import re
import secrets
import unicodedata

from fastapi import Body, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from auth.securite import utilisateur_requis
from database.models import User
from database.profil_db import (ajouter_piece_jointe, fichiers_references, lire_profil, sauvegarder_profil,
                                supprimer_piece_jointe)
from routes.commun import mode_requis, routeur_prive
from shared.config import chemin_piece_jointe
from shared.modes import get_mode

router = routeur_prive()


# ─── Profil utilisateur ───────────────────────────────────────────────────────
@router.get("/api/mode")
def api_get_mode(mode: str = Depends(mode_requis)):
    """Label et couleur du mode demandé (alternance, job, stage)."""
    m = get_mode(mode)
    return {"mode": mode, "label": m["label"], "couleur": m["couleur"]}


@router.get("/api/domaines")
def api_domaines():
    """Grands domaines et leurs domaines, pour le choix dans le profil."""
    from shared.domaines import grands_domaines
    return grands_domaines()


@router.get("/api/criteres_options")
def api_criteres_options():
    """Secteurs employeur, tailles d'entreprise et thèmes proposés dans le profil."""
    from shared.criteres import options_du_profil
    return options_du_profil()


@router.get("/api/profil")
def api_get_profil(request: Request, user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    return lire_profil(user.id, mode=mode)


@router.post("/api/profil")
def api_post_profil(request: Request, body: dict = Body(...), user: User = Depends(utilisateur_requis),
                    mode: str = Depends(mode_requis)):
    ok = sauvegarder_profil(user.id, body, mode=mode)
    return {"ok": ok}


# ─── Pièces jointes du profil ─────────────────────────────────────────────────
TAILLE_MAX_PJ = 5 * 1024 * 1024  # 5 Mo
LONGUEUR_MAX_NOM_PJ = 60          # caractères, hors suffixe unique et extension
LONGUEUR_MAX_NOM_AFFICHE_PJ = 100  # nom donné à la pièce dans le profil (D134)


def _base_nom_fichier(nom: str) -> str:
    """Nom d'origine -> base sûre : sans dossier ni extension, ASCII,
    [A-Za-z0-9_-] seulement, raccourcie (anti path-traversal)."""
    nom = nom.replace("\\", "/").split("/")[-1]
    base = re.sub(r"\.[^.]*$", "", nom)   # extension retirée (splitext garde "....pdf")
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_-")
    return base[:LONGUEUR_MAX_NOM_PJ].rstrip("_-") or "document"


def _ecrire_piece_jointe(user_id: int, nom_origine: str, contenu: bytes) -> str:
    """Écrit le fichier sous un nom unique (base_<hex>.pdf) dans le dossier de
    l'utilisateur, sans jamais écraser un fichier existant. Retourne le chemin
    relatif à UPLOADS_DIR stocké en base."""
    base = _base_nom_fichier(nom_origine)
    while True:
        relatif = f"user_{user_id}/{base}_{secrets.token_hex(4)}.pdf"
        chemin = chemin_piece_jointe(relatif)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(chemin, "xb") as out:   # "x" : échoue si le fichier existe
                out.write(contenu)
            return relatif
        except FileExistsError:
            continue


def _supprimer_si_orpheline(user_id: int, fichiers: list[str]):
    """Supprime du disque les fichiers qu'aucun profil de l'utilisateur
    (tous modes confondus) ne référence plus (bug 9)."""
    encore_utilises = fichiers_references(user_id)
    for relatif in fichiers:
        chemin = chemin_piece_jointe(relatif)
        if relatif in encore_utilises or not chemin:
            continue
        try:
            os.remove(chemin)
        except OSError:
            pass


@router.post("/api/profil/upload")
async def api_profil_upload(request: Request,
                            nom: str = Form(""),
                            fichier: UploadFile = File(...),
                            user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    # Validation type PDF
    if not (fichier.filename or "").lower().endswith(".pdf"):
        return JSONResponse({"erreur": "Seuls les fichiers PDF sont acceptés"}, status_code=400)
    # Si pas de nom fourni : utiliser le nom du fichier (sans extension)
    nom = (nom or "").strip()
    if not nom:   # tiré du nom du fichier, raccourci au besoin
        nom = os.path.splitext(fichier.filename or "Document")[0][:LONGUEUR_MAX_NOM_AFFICHE_PJ]
    if len(nom) > LONGUEUR_MAX_NOM_AFFICHE_PJ:
        return JSONResponse({"erreur": f"Nom trop long ({LONGUEUR_MAX_NOM_AFFICHE_PJ} caractères au plus)"},
                            status_code=400)
    # Lecture bornée : jamais plus que la limite + 1 octet en mémoire (D134)
    contenu = await fichier.read(TAILLE_MAX_PJ + 1)
    if len(contenu) > TAILLE_MAX_PJ:
        return JSONResponse({"erreur": "Fichier trop volumineux (max 5 Mo)"}, status_code=400)
    # Stockage dans le dossier de l'utilisateur ; en base, chemin relatif à UPLOADS_DIR
    relatif = _ecrire_piece_jointe(user.id, fichier.filename, contenu)
    remplacees = ajouter_piece_jointe(user.id, nom, relatif, mode=mode)
    _supprimer_si_orpheline(user.id, remplacees)
    return {"ok": True, "nom": nom, "fichier": relatif.split("/", 1)[1]}

@router.post("/api/profil/piece/supprimer")
def api_profil_piece_supprimer(request: Request, body: dict = Body(...),
                               user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    retirees = supprimer_piece_jointe(user.id, body.get("nom", ""), mode=mode)
    # Le fichier n'est effacé que si l'autre mode ne s'en sert plus
    _supprimer_si_orpheline(user.id, retirees)
    return {"ok": True}

@router.get("/api/profil/piece")
def api_profil_piece_get(request: Request, nom: str, user: User = Depends(utilisateur_requis),
                         mode: str = Depends(mode_requis)):
    prof = lire_profil(user.id, mode=mode)
    for pj in prof.get("pieces_jointes", []):
        chemin = chemin_piece_jointe(pj.get("fichier", ""))
        if pj.get("nom") == nom and chemin and chemin.is_file():
            return FileResponse(chemin, media_type="application/pdf")
    return JSONResponse({"erreur": "Pièce introuvable"}, status_code=404)


# ─── Copie de sections du profil depuis un autre mode (phase 9, D117) ─────────
# Le mode de la page (paramètre « mode ») est la cible ; la source est un
# autre mode du même utilisateur, jamais celui d'un autre (user.id de la session).
@router.get("/api/profil/copie/sections")
def api_profil_copie_sections(source: str, user: User = Depends(utilisateur_requis),
                              mode: str = Depends(mode_requis)):
    from shared.copie_profil import sections_copiables
    return {"sections": sections_copiables(source, mode),
            "source_existe": bool(lire_profil(user.id, mode=source))}


@router.post("/api/profil/copie/apercu")
def api_profil_copie_apercu(body: dict = Body(...), user: User = Depends(utilisateur_requis),
                            mode: str = Depends(mode_requis)):
    from shared.copie_profil import apercu
    source = str(body.get("source") or "")
    return {"sections": apercu(lire_profil(user.id, mode=source) if source != mode else {},
                               lire_profil(user.id, mode=mode), body.get("sections") or [], source, mode)}


@router.post("/api/profil/copie")
def api_profil_copie(body: dict = Body(...), user: User = Depends(utilisateur_requis),
                     mode: str = Depends(mode_requis)):
    from database.profil_db import copier_sections
    from shared.copie_profil import verifier_modes
    source = str(body.get("source") or "")
    verifier_modes(source, mode)
    res = copier_sections(user.id, source, mode, body.get("sections") or [], body.get("ecraser") or [])
    # Fichiers que le mode cible ne référence plus : effacés seulement si
    # aucun autre mode ne s'en sert (D118)
    _supprimer_si_orpheline(user.id, res["fichiers_retires"])
    return {"ok": True, "copiees": res["copiees"]}
