"""Cas limites (audit phase 12, D135) : profil vide, offre sans titre,
entreprise ni description, IA en panne, corps de requête de mauvais type
sur chaque route POST : toujours une erreur gérée avec un message, jamais
de 500."""

import httpx
import pytest
from fastapi.routing import APIRoute

import main
from database.candidatures_db import ajouter_candidature

OFFRE_VIDE = {"id": "VIDE", "titre": None, "entreprise": None, "description": None, "lieu": None,
              "statut": "nouveau", "source": "France Travail", "lien": None}


@pytest.fixture
def vide(utilisateur):
    """Compte sans prénom ni nom, profil jamais rempli, une offre presque vide."""
    client, uid = utilisateur("vide@test.fr")
    ajouter_candidature(uid, dict(OFFRE_VIDE))
    return client, uid


@pytest.mark.parametrize("mode", ["alternance", "job", "stage"])
def test_profil_vide_et_offre_vide(vide, ia, mode):
    client, uid = vide
    client.mode = mode
    if mode != "alternance":
        ajouter_candidature(uid, dict(OFFRE_VIDE), mode=mode)
    resultats = {}
    for chemin, corps in (("/api/analyser", {"id": "VIDE"}), ("/api/lettre/paragraphe", {"id": "VIDE"}),
                          ("/api/lettre/assembler", {"id": "VIDE", "paragraphe": "P."}),
                          ("/api/telecharger_pdf", {"id": "VIDE", "lettre": "Lettre"}),
                          ("/api/offre/postuler", {"id": "VIDE"}),
                          ("/api/spontanees/envoyer", {}), ("/api/sauvegarder", {"id": "VIDE", "lettre": "x"})):
        r = client.post(chemin, json=corps)
        resultats[chemin] = (r.status_code, r.text[:160])
        assert r.status_code != 500 and (r.status_code < 400 or r.json().get("erreur")), (chemin, r.text[:300])
    for chemin in ("/api/candidatures", "/api/suivi", "/api/spontanees/stats", "/api/profil", "/api/analyse/statut",
                   "/api/compte", "/api/profil/copie/sections?source=" + ("job" if mode != "job" else "stage")):
        r = client.get(chemin)
        assert r.status_code < 500, (chemin, r.text[:300])


def test_ia_en_panne_messages(vide, ia):
    client, uid = vide
    from database.profil_db import sauvegarder_profil
    sauvegarder_profil(uid, {"prenom": "V", "nom": "V", "email": "v@x.fr", "lettre_type": "{paragraphe}"})
    ia.panne = lambda corps: httpx.ConnectError("refus")
    for chemin in ("/api/analyser", "/api/lettre/paragraphe"):
        r = client.post(chemin, json={"id": "VIDE"})
        assert r.status_code in (502, 503), (chemin, r.status_code, r.text)
        assert r.json().get("erreur"), r.text


def _aplatir(routes):
    for route in routes:
        sous = getattr(route, "original_router", None)
        if sous is not None:
            yield from _aplatir(sous.routes)
        else:
            yield route


LANCEMENTS = {"/api/recherche", "/api/analyse", "/api/spontanees/fetch", "/api/spontanees/scraper",
              "/api/spontanees/envoyer", "/api/spontanees/revalider"}


def test_corps_de_mauvais_type_jamais_500(vide):
    client, _ = vide
    mauvais = [None, [], "texte", 12, {"id": None}, {"id": []}, {"id": {"$ne": 1}}, {"id": "x" * 5000},
               {"sections": "competences", "source": 3}, {"date": "2026-13-45", "id": "VIDE"},
               {"date": "demain", "id": "VIDE"}, {"statut": "inexistant", "id": "VIDE", "type": "offre"},
               {"limite": -5}, {"max_offres": "beaucoup"}, {"email": None, "mot_de_passe": None},
               {"ancien": 1, "nouveau": 2, "confirmation": 3}]
    erreurs = []
    for route in _aplatir(main.app.routes):
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/") or "POST" not in route.methods:
            continue
        if route.path in LANCEMENTS:
            continue
        chemin = route.path.replace("{ref_offre}", "VIDE")
        for corps in mauvais:
            r = client.post(chemin, content=__import__("json").dumps(corps), headers={"content-type": "application/json"})
            if r.status_code == 500 or (r.status_code >= 400 and "erreur" not in r.text and "detail" not in r.text):
                erreurs.append((chemin, corps, r.status_code, r.text[:200]))
        r = client.post(chemin, content=b"{pas du json", headers={"content-type": "application/json"})
        if r.status_code == 500:
            erreurs.append((chemin, "json invalide", r.status_code, r.text[:200]))
    assert not erreurs, "\n".join(map(str, erreurs))
