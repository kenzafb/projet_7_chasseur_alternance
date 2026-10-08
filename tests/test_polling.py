"""Polling de l'état des pipelines : une route pour les deux, interrogée
seulement pendant qu'un pipeline tourne, absente du journal d'accès."""

import logging
import re

import pytest

import main
from shared import config


def _ligne_acces(chemin, methode="GET"):
    """Enregistrement tel qu'uvicorn le produit pour une requête."""
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                             '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:5000", methode, chemin, "1.1", 200), None)


@pytest.mark.parametrize("chemin", ["/api/statut_pipelines", "/api/statut_recherche",
                                    "/api/spontanees/statut", "/api/statut_pipelines?t=1"])
def test_requetes_de_statut_filtrees(chemin):
    assert main.FILTRE_STATUT.filter(_ligne_acces(chemin)) is False


@pytest.mark.parametrize("chemin", ["/", "/api/recherche", "/api/logs", "/api/spontanees/stats",
                                    "/api/statut_pipelines_x", "/login"])
def test_autres_requetes_gardees(chemin):
    assert main.FILTRE_STATUT.filter(_ligne_acces(chemin)) is True


def test_filtre_pose_sur_le_journal_d_acces(caplog):
    journal = logging.getLogger("uvicorn.access")
    assert main.FILTRE_STATUT in journal.filters
    with caplog.at_level(logging.INFO, logger="uvicorn.access"):
        for chemin in ("/api/statut_pipelines", "/api/recherche"):
            journal.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "GET", chemin, "1.1", 200)
    messages = [r.getMessage() for r in caplog.records]
    assert any("/api/recherche" in m for m in messages)
    assert not any("statut_pipelines" in m for m in messages)


@pytest.fixture
def logs_uvicorn_restaures():
    """Remet les loggers d'uvicorn dans leur état après le test."""
    noms = ("uvicorn", "uvicorn.error", "uvicorn.access")
    avant = {n: (lambda l: (l.level, list(l.handlers), l.propagate, l.disabled))(logging.getLogger(n))
             for n in noms}
    yield
    for nom, (niveau, handlers, propage, desactive) in avant.items():
        journal = logging.getLogger(nom)
        journal.setLevel(niveau)
        journal.handlers[:] = handlers
        journal.propagate, journal.disabled = propage, desactive


def test_le_filtre_survit_a_la_configuration_d_uvicorn(logs_uvicorn_restaures):
    """uvicorn configure ses logs par dictConfig : le filtre du logger reste."""
    import logging.config
    from uvicorn.config import LOGGING_CONFIG
    logging.config.dictConfig(LOGGING_CONFIG)
    assert main.FILTRE_STATUT in logging.getLogger("uvicorn.access").filters


def test_statut_des_deux_pipelines_par_utilisateur(utilisateur, pipelines_neufs):
    client_a, id_a = utilisateur("a@test.fr")
    client_b, _ = utilisateur("b@test.fr")
    pipelines_neufs.demarrer("spontanees", id_a, etape="scraper", message="en cours")
    etats = client_a.get("/api/statut_pipelines").json()
    assert etats["recherche"]["en_cours"] is False
    assert etats["spontanees"]["en_cours"] is True and etats["spontanees"]["etape"] == "scraper"
    assert client_b.get("/api/statut_pipelines").json()["spontanees"]["en_cours"] is False


def test_statut_reserve_aux_connectes(client):
    assert client.get("/api/statut_pipelines").status_code == 401


def test_front_ne_poll_que_pendant_un_pipeline():
    app = (config.STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    assert "setInterval" not in app
    assert int(re.search(r"const POLL_MS = (\d+);", app).group(1)) >= 5000
    # Le prochain poll n'est programmé que si un pipeline est actif
    assert "if (actif) minuteur = setTimeout(pollEtat, POLL_MS);" in app
    # Une seule requête de statut par poll
    assert app.count("api.statutPipelines()") == 1
    assert "statutRecherche" not in app and "spStatut" not in app
