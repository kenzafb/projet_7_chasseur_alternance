"""
main.py — Chasseur d'Alternance (FastAPI)
=========================================
Création de l'application : middlewares (session, contrôle de l'origine),
gestion des erreurs, journal d'accès, inclusion des routeurs de routes/.

Lancement :
    uvicorn main:app --reload --port 5002
    → http://localhost:5002
    → doc API auto-générée : http://localhost:5002/docs

Les pipelines longs (recherche, analyse, spontanées) tournent dans des
threads avec stop_event (routes/) : les fonctions métier sont synchrones.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from auth.origine import ControleOrigine
from auth.routes import router as auth_router
from auth.securite import MotDePasseTemporaire, NonConnecte
from routes import (analyse, candidatures, documentation, lettre, offres, pages, parametres, profil,
                    spontanees)
from routes.commun import mode_requis  # noqa: F401  (dépendance des routes du mode, citée par les tests)
from shared.chiffrement import ChiffrementIndisponible, raison_indisponible
from shared.config import COOKIE_SECURE, STATIC_DIR, secret_key
from shared.erreurs import ErreurUtilisateur
from shared.ia import ErreurIA, ErreurIABloquante
from shared.journal import journaliser

# Documentation automatique désactivée ici : elle est servie par des routes
# privées (/docs, /openapi.json, routes/documentation.py), réservées aux
# utilisateurs connectés.
app = FastAPI(title="Chasseur d'Alternance", version="15",
              docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Sessions signées (cookie de connexion). secret_key() lève une erreur si
# SECRET_KEY est absente ou trop courte : l'app ne démarre pas sans elle.
app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key(),
    max_age=60 * 60 * 24 * 14,   # session valable 14 jours
    same_site="lax",
    https_only=COOKIE_SECURE,
)
# Requêtes non sûres d'une autre origine refusées (D134)
app.add_middleware(ControleOrigine)
app.include_router(auth_router)   # /login, /logout, /register : publiques

# Routeurs privés : chaque route exige une session (routes.commun.routeur_prive)
ROUTEURS_PRIVES = [pages.router, offres.router, profil.router, parametres.router, analyse.router,
                   lettre.router, candidatures.router, spontanees.router, documentation.router]
for routeur in ROUTEURS_PRIVES:
    app.include_router(routeur)


@app.exception_handler(NonConnecte)
def non_connecte(request: Request, exc: NonConnecte):
    """Sans session : 401 JSON pour l'API, redirection vers /login pour les pages."""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(MotDePasseTemporaire)
def mot_de_passe_temporaire(request: Request, exc: MotDePasseTemporaire):
    """Mot de passe temporaire à changer d'abord (D123) : 403 JSON pour
    l'API, redirection vers la page de changement pour les pages."""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"erreur": "Change d'abord ton mot de passe temporaire."}, status_code=403)
    return RedirectResponse(url="/mot-de-passe-temporaire", status_code=303)


@app.exception_handler(RequestValidationError)
def requete_invalide(request: Request, exc: RequestValidationError):
    """Corps de requête refusé par son modèle Pydantic : 422, avec un message
    lisible dans "erreur" (affiché par le front) et le détail habituel."""
    # Sans "input" : la valeur reçue (un mot de passe, par exemple) n'est
    # jamais renvoyée ; "ctx" peut contenir l'exception d'origine.
    erreurs = jsonable_encoder([{k: v for k, v in e.items() if k not in ("input", "ctx")}
                                for e in exc.errors()])
    premiere = erreurs[0] if erreurs else {}
    champ = ".".join(str(x) for x in premiere.get("loc", []) if x != "body")
    message = f"Requête invalide : {champ + ' : ' if champ else ''}{premiere.get('msg', '')}"
    return JSONResponse({"erreur": message, "detail": erreurs}, status_code=422)


@app.exception_handler(ErreurUtilisateur)
def erreur_utilisateur(request: Request, exc: ErreurUtilisateur):
    """Profil incomplet, lettre type invalide... : 400 avec un message lisible."""
    return JSONResponse({"erreur": str(exc)}, status_code=400)


@app.exception_handler(ChiffrementIndisponible)
def chiffrement_indisponible(request: Request, exc: ChiffrementIndisponible):
    """CLE_CHIFFREMENT absente ou invalide : l'app tourne, mais configuration
    et envoi de mails sont désactivés (503, message lisible)."""
    return JSONResponse({"erreur": str(exc)}, status_code=503)


@app.exception_handler(ErreurIA)
def erreur_ia(request: Request, exc: ErreurIA):
    """Échec de l'IA sur une route directe (lettre, réanalyse) : rien n'est
    enregistré. 503 si la configuration est en cause, 502 sinon."""
    statut = 503 if isinstance(exc, ErreurIABloquante) else 502
    return JSONResponse({"erreur": str(exc)}, status_code=statut)


if raison_indisponible():
    journaliser(f"⚠️  {raison_indisponible()}")


# ─── Journal d'accès : sans les requêtes de statut ───────────────────────────
# Le front interroge l'état des pipelines toutes les quelques secondes tant
# qu'ils tournent : ces lignes noieraient le journal d'accès d'uvicorn.
ROUTES_DE_STATUT = frozenset({"/api/statut_pipelines", "/api/analyse/statut"})


class SansRequetesDeStatut(logging.Filter):
    """Écarte du journal « uvicorn.access » les requêtes vers ROUTES_DE_STATUT.
    uvicorn journalise (client, méthode, chemin avec requête, version, code)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            return str(args[2]).split("?", 1)[0] not in ROUTES_DE_STATUT
        return True


FILTRE_STATUT = SansRequetesDeStatut()
# Le filtre est posé sur le logger : la configuration des logs d'uvicorn
# (dictConfig, appelée avant l'import de l'app) ne le retire pas
logging.getLogger("uvicorn.access").addFilter(FILTRE_STATUT)


if __name__ == "__main__":
    import uvicorn
    journaliser("\n🚀 Chasseur Alternance (FastAPI) sur http://localhost:5002\n")
    uvicorn.run("main:app", host="0.0.0.0", port=5002, reload=True)
