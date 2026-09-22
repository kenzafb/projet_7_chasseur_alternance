"""
auth/routes.py
=============
Routes d'authentification : affichage des pages + traitement des formulaires.
  GET  /login     → page de connexion
  POST /login     → vérifie, ouvre la session, redirige vers l'accueil
  GET  /logout    → ferme la session
  GET  /register  → page d'inscription
  POST /register  → crée le compte + son profil vide, connecte, redirige
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from database.connexion import SessionLocal
from database.models import User, Profil
from auth.securite import authentifier, hacher_mot_de_passe

router = APIRouter()
templates = Jinja2Templates(directory="templates")


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
@router.get("/register")
def page_register(request: Request):
    return templates.TemplateResponse(request, "register.html", {"erreur": None})


@router.post("/register")
def traiter_register(request: Request,
                     email: str = Form(...),
                     mot_de_passe: str = Form(...),
                     prenom: str = Form(""),
                     nom: str = Form("")):
    email = email.lower().strip()
    db = SessionLocal()
    try:
        if db.query(User).filter_by(email=email).first():
            return templates.TemplateResponse(
                request, "register.html",
                {"erreur": "Un compte existe déjà avec cet email."},
            )
        if len(mot_de_passe) < 6:
            return templates.TemplateResponse(
                request, "register.html",
                {"erreur": "Mot de passe trop court (6 caractères minimum)."},
            )
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
