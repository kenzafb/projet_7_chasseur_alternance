"""Isolation sur toutes les routes (audit phase 12, D135) : B appelle CHAQUE
route de l'API avec les identifiants de A (offre, entreprise, pièce jointe,
mode source de la copie...). Les données de A ne doivent ni changer ni
apparaître dans les réponses de B, et aucune route ne doit planter."""

import json
import sqlite3

import pytest
from fastapi.routing import APIRoute

import main
from database.candidatures_db import ajouter_candidature
from database.entreprises_db import ajouter_entreprises_lba
from database.profil_db import ajouter_piece_jointe, sauvegarder_profil
from shared import config
from tests.conftest import compte_verifie

SECRET_A = "SECRET-ALICE-7f3"   # présent dans toutes les données de A


def _instantane(id_a):
    """Toutes les lignes de A, toutes tables, triées (JSON)."""
    chemin = config.DATABASE_URL.replace("sqlite:///", "")
    cx = sqlite3.connect(chemin)
    try:
        out = {}
        for (t,) in cx.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'"):
            cols = [c[1] for c in cx.execute(f"PRAGMA table_info({t})")]
            if t == "users":
                lignes = cx.execute("SELECT * FROM users WHERE id = ?", (id_a,)).fetchall()
            elif "user_id" in cols:
                lignes = cx.execute(f"SELECT * FROM {t} WHERE user_id = ?", (id_a,)).fetchall()
            else:
                continue
            out[t] = sorted(json.dumps(l, default=str) for l in lignes)
        return out
    finally:
        cx.close()


@pytest.fixture
def a_et_b(utilisateur, smtp_simule, monkeypatch):
    client_a, id_a = utilisateur("a@test.fr", prenom="Alice", nom=SECRET_A)
    client_b, id_b = utilisateur("b@test.fr", prenom="Bob", nom="B")
    sauvegarder_profil(id_a, {"competences": [SECRET_A], "lettre_type": f"{SECRET_A} {{paragraphe}}",
                              "email": "alice@exemple.fr"}, mode="alternance")
    sauvegarder_profil(id_a, {"competences": [SECRET_A]}, mode="stage")
    ajouter_candidature(id_a, {"id": "OFFRE-A", "titre": SECRET_A, "entreprise": "ACME", "description": SECRET_A,
                               "statut": "nouveau", "lettre": SECRET_A, "source": "La Bonne Alternance",
                               "lien": "https://labonnealternance.apprentissage.beta.gouv.fr/emploi/offres_emploi_lba/a/b"})
    from tests.faux_lba import entreprise
    import france_travail.scraper_lba as lba
    e = lba.normaliser_entreprise(entreprise(1))
    e["nom_commercial"] = e["nom"] = SECRET_A
    e["email"] = "rh@secret-alice.fr"
    ajouter_entreprises_lba(id_a, [e])
    ajouter_piece_jointe(id_a, "CV", f"user_{id_a}/cv.pdf")
    compte_verifie(smtp_simule, id_a, "alice@exemple.fr")
    return client_a, id_a, client_b, id_b


def _aplatir(routes):
    for route in routes:
        sous = getattr(route, "original_router", None)
        if sous is not None:
            yield from _aplatir(sous.routes)
        else:
            yield route


def _routes():
    for r in _aplatir(main.app.routes):
        if isinstance(r, APIRoute) and r.path.startswith("/api/"):
            for methode in r.methods:
                yield methode, r.path


# Routes qui lancent un pipeline (réseau) : appelées seulement à vide
LANCEMENTS = {"/api/recherche", "/api/analyse", "/api/spontanees/fetch", "/api/spontanees/scraper",
              "/api/spontanees/envoyer", "/api/spontanees/revalider", "/api/compte_envoi/mail_test",
              "/api/compte_envoi/tester"}


def test_b_ne_touche_a_rien_de_a_par_aucune_route(a_et_b, ia, monkeypatch):
    client_a, id_a, client_b, id_b = a_et_b
    from database.entreprises_db import lire_entreprises
    eid_a = lire_entreprises(id_a)[0]["_id"]
    avant = _instantane(id_a)
    corps = [
        {}, {"id": "OFFRE-A"}, {"id": eid_a}, {"id": str(eid_a)},
        {"id": "OFFRE-A", "statut": "refus"}, {"id": "OFFRE-A", "raison": "manuel"},
        {"id": "OFFRE-A", "desarchiver": True}, {"id": "OFFRE-A", "lettre": "écrasée", "email_candidature": "x@y.fr"},
        {"id": "OFFRE-A", "paragraphe": "P."}, {"id": "OFFRE-A", "date": "2026-11-01"},
        {"id": "OFFRE-A", "annuler": True},
        {"type": "offre", "id": "OFFRE-A", "statut": "refus"}, {"type": "spontanee", "id": str(eid_a), "statut": "refus"},
        {"id": eid_a, "statut": "refus"}, {"id": eid_a, "adresse": "rh@secret-alice.fr"},
        {"nom": "CV"}, {"source": "stage", "sections": ["competences"], "ecraser": ["competences"]},
        {"user_id": id_a, "id": "OFFRE-A"},
    ]
    vus = []
    for methode, chemin in sorted(set(_routes())):
        chemin_reel = chemin.replace("{ref_offre}", "OFFRE-A")
        for c in ([{}] if chemin in LANCEMENTS else corps):
            if methode == "GET":
                r = client_b.get(chemin_reel, params={k: v for k, v in c.items() if isinstance(v, (str, int))})
            else:
                r = client_b.post(chemin_reel, json=c)
            vus.append((methode, chemin, r.status_code))
            assert r.status_code < 500, (methode, chemin, c, r.text[:300])
            assert SECRET_A not in r.text, (methode, chemin, c, r.text[:300])
            assert "secret-alice" not in r.text, (methode, chemin, c)
    apres = _instantane(id_a)
    for table in avant:
        assert avant[table] == apres[table], f"données de A modifiées dans {table}"
    assert len({(m, p) for m, p, _ in vus}) >= 45      # toutes les routes de l API sont essayées
