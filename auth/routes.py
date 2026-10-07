"""
auth/routes.py
=============
Routes d'authentification : affichage des pages + traitement des formulaires.
  GET  /login     → page de connexion
  POST /login     → vérifie, ouvre la session, redirige vers l'accueil
  GET  /logout    → ferme la session
  GET  /register  → page d'inscription
  POST /register  → crée le compte + son profil vide, connecte, redirige

Inscription sur invitation : le formulaire exige un code égal à la variable
CODE_INVITATION. Si elle est absente ou vide, l'inscription est fermée.
"""

import hmac

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from shared.config import TEMPLATES_DIR, code_invitation
from database.connexion import SessionLocal
from database.models import User, Profil
from auth.securite import authentifier, hacher_mot_de_passe, LONGUEUR_MIN_MOT_DE_PASSE

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ─── Connexion ────────────────────────────────────────────────────────────────
@router.get("/login")
def page_login(request: Request):
    return templates.TemplateResponse(request, "login.html", {"erreur": None})


@router.post("/login")
def traiter_login(request: Request, email: str = Form(...), mot_de_passe: str = Form(...)):
    user = authentifier(email, mot_de_passe)
    if not user:
        return templates.TemplateResponse(
            request, "login.html",
            {"erreur": "Email ou mot de passe incorrect."},
        )
    # Ouvre la session : on ne stocke que l'id, jamais le mot de passe
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


# ─── Déconnexion ───────────────────────────────────────────────────────────────
@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ─── Inscription ───────────────────────────────────────────────────────────────
def _page_register(request, erreur=None, status_code=200):
    return templates.TemplateResponse(
        request, "register.html",
        {"erreur": erreur, "ouverte": bool(code_invitation()),
         "longueur_min": LONGUEUR_MIN_MOT_DE_PASSE},
        status_code=status_code,
    )


@router.get("/register")
def page_register(request: Request):
    return _page_register(request)


@router.post("/register")
def traiter_register(request: Request,
                     email: str = Form(...),
                     mot_de_passe: str = Form(...),
                     code_invitation_saisi: str = Form("", alias="code_invitation"),
                     prenom: str = Form(""),
                     nom: str = Form("")):
    code_attendu = code_invitation()
    if not code_attendu:
        return _page_register(request, status_code=403)
    # Comparaison à temps constant (pas d'indice sur le code par le chronométrage)
    if not hmac.compare_digest(code_invitation_saisi.strip().encode(), code_attendu.encode()):
        return _page_register(request, "Code d'invitation invalide.", status_code=403)
    if len(mot_de_passe) < LONGUEUR_MIN_MOT_DE_PASSE:
        return _page_register(
            request, f"Mot de passe trop court ({LONGUEUR_MIN_MOT_DE_PASSE} caractères minimum).",
            status_code=400)
    email = email.lower().strip()
    db = SessionLocal()
    try:
        if db.query(User).filter_by(email=email).first():
            return _page_register(request, "Un compte existe déjà avec cet email.", status_code=400)
        # Crée l'utilisateur
        user = User(email=email, mot_de_passe_hash=hacher_mot_de_passe(mot_de_passe))
        db.add(user)
        db.commit()
        db.refresh(user)
        # Crée un profil vide rattaché (il sera rempli via l'onboarding plus tard)
        db.add(Profil(user_id=user.id, prenom=prenom, nom=nom, email_contact=email))
        db.commit()
        # Connecte directement
        request.session["user_id"] = user.id
        return RedirectResponse(url="/?bienvenue=1", status_code=303)
    finally:
        db.close()
