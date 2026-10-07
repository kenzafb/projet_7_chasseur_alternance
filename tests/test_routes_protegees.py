"""Sans session, toutes les routes sont fermées sauf les routes publiques."""

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
    assert {"/", "/docs", "/openapi.json"} <= chemins


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
