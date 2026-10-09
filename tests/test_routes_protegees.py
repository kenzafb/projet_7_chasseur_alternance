"""Sans session, toutes les routes sont fermées sauf les routes publiques.
Connecté, chaque route de l'API qui dépend du mode exige qu'on le lui donne
(phase 6a : le mode vient de l'URL, plus de la session)."""

import re

import pytest
from fastapi.routing import APIRoute

import main

ROUTES_PUBLIQUES = {"/login", "/register", "/logout"}


def _toutes_les_routes(routes):
    """Aplatit app.routes : FastAPI y range chaque routeur inclus dans un
    objet qui pointe vers lui (original_router)."""
    for route in routes:
        sous_routeur = getattr(route, "original_router", None)
        if sous_routeur is not None:
            yield from _toutes_les_routes(sous_routeur.routes)
        else:
            yield route


ROUTES_APP = list(_toutes_les_routes(main.app.routes))


def _routes_privees():
    """(méthode, chemin) de chaque route de l'app, lues dans app.routes."""
    routes = []
    for route in ROUTES_APP:
        if not isinstance(route, APIRoute) or route.path in ROUTES_PUBLIQUES:
            continue
        chemin = re.sub(r"\{[^}]+\}", "1", route.path)
        for methode in sorted(route.methods - {"HEAD", "OPTIONS"}):
            routes.append((methode, chemin))
    return routes


ROUTES_PRIVEES = _routes_privees()


def test_inventaire_complet():
    """Garde-fou : la liste couvre bien l'app (dont les 4 routes autrefois ouvertes)."""
    chemins = {c for _, c in ROUTES_PRIVEES}
    assert len(ROUTES_PRIVEES) >= 30
    for ancienne_ouverte in ("/api/logs", "/api/statut_recherche",
                             "/api/spontanees/statut", "/api/spontanees/stop"):
        assert ancienne_ouverte in chemins
    assert {"/", "/alternance", "/job", "/stage", "/docs", "/openapi.json"} <= chemins


def test_seules_les_routes_prevues_sont_hors_routeur_prive():
    """Toute route hors du routeur protégé doit être une route publique déclarée."""
    protegees = {r.path for r in main.prive.routes}
    toutes = {r.path for r in ROUTES_APP if isinstance(r, APIRoute)}
    assert toutes - protegees == ROUTES_PUBLIQUES


@pytest.mark.parametrize("methode,chemin", ROUTES_PRIVEES)
def test_route_fermee_sans_session(client, methode, chemin):
    r = client.request(methode, chemin, follow_redirects=False)
    if chemin.startswith("/api/"):
        assert r.status_code == 401
        assert r.json() == {"erreur": "Non connecté"}
    else:
        assert r.status_code == 303
        assert r.headers["location"] == "/login"


def test_session_falsifiee_refusee(client):
    client.cookies.set("session", "eyJ1c2VyX2lkIjogMX0=.faux.signature")
    assert client.get("/api/profil").status_code == 401


@pytest.mark.parametrize("chemin", ["/login", "/register"])
def test_pages_publiques_accessibles(client, chemin):
    assert client.get(chemin).status_code == 200


def test_static_public(client):
    assert client.get("/static/js/api.js").status_code == 200


# ─── Mode explicite ───────────────────────────────────────────────────────────
def _exige_le_mode(route) -> bool:
    return any(d.call is main.mode_requis for d in route.dependant.dependencies)


ROUTES_DU_MODE = sorted((m, re.sub(r"\{[^}]+\}", "1", r.path)) for r in ROUTES_APP
                        if isinstance(r, APIRoute) and _exige_le_mode(r)
                        for m in r.methods - {"HEAD", "OPTIONS"})


def test_inventaire_des_routes_du_mode():
    """Garde-fou : toute route qui lit ou écrit des données d'un mode le reçoit."""
    chemins = {c for _, c in ROUTES_DU_MODE}
    assert {"/api/candidatures", "/api/profil", "/api/profil/upload", "/api/profil/piece",
            "/api/recherche", "/api/lettre_pdf/1", "/api/spontanees/stats", "/api/spontanees/suivi",
            "/api/spontanees/fetch", "/api/spontanees/envoyer", "/api/mode"} <= chemins
    assert all(c.startswith("/api/") for c in chemins)
    # Routes sans mode : compte, état des pipelines, logs, référentiels
    sans = {re.sub(r"\{[^}]+\}", "1", r.path) for r in ROUTES_APP
            if isinstance(r, APIRoute) and r.path.startswith("/api/")} - chemins
    assert sans == {"/api/logs", "/api/statut_recherche", "/api/statut_pipelines", "/api/spontanees/statut",
                    "/api/spontanees/stop", "/api/spontanees/valider", "/api/domaines", "/api/criteres_options",
                    "/api/compte_envoi", "/api/compte_envoi/supprimer", "/api/compte_envoi/tester",
                    "/api/compte_envoi/mode_test", "/api/compte_envoi/mail_test"}


@pytest.mark.parametrize("methode,chemin", ROUTES_DU_MODE)
def test_route_du_mode_refusee_sans_mode(utilisateur, methode, chemin):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    client.mode = None
    r = client.request(methode, chemin, follow_redirects=False)
    assert r.status_code == 400 and r.json()["erreur"].startswith("Mode manquant")
    r = client.request(methode, chemin, params={"mode": "inconnu"}, follow_redirects=False)
    assert r.status_code == 400 and "Mode inconnu" in r.json()["erreur"]


def test_route_du_mode_fermee_sans_session_meme_avec_mode(client):
    for methode, chemin in ROUTES_DU_MODE:
        assert client.request(methode, chemin, params={"mode": "job"}).status_code == 401
