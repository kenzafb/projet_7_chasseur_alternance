"""Pipelines par utilisateur : états, logs et arrêt isolés, un seul pipeline
de chaque type à la fois par utilisateur, logs bornés. Les vrais pipelines
(France Travail, LBA, scraper) sont remplacés par des faux qui attendent."""

import threading
import time

import pytest

import main
import spontanees.scraper_emails
from shared.pipelines import Pipelines, RECHERCHE
from tests.conftest import en_parallele


def attendre(condition, delai=5.0):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(0.01)
    raise AssertionError("condition jamais remplie")


@pytest.fixture
def a_et_b(utilisateur):
    client_a, id_a = utilisateur("a@test.fr", prenom="Alice", nom="A")
    client_b, id_b = utilisateur("b@test.fr", prenom="Bob", nom="B")
    return client_a, id_a, client_b, id_b


@pytest.fixture
def faux_travaux(monkeypatch):
    """Faux pipelines : écrivent un log à leur nom puis attendent `liberer`
    (ou leur événement d'arrêt). `demarres` : user_id -> Event."""
    liberer = threading.Event()
    demarres = {}
    arretes = set()

    def fausse_recherche(user_id, profil, on_offre=None, mode="alternance", **_):
        main.pipelines.log(user_id, f"recherche de {user_id}")
        demarres.setdefault(("recherche", user_id), threading.Event()).set()
        liberer.wait(5)

    def faux_scraper(user_id, stop_event=None, log_fn=print, on_progress=None):
        log_fn(f"scraper de {user_id}")
        on_progress(10, f"progression de {user_id}")
        demarres.setdefault(("scraper", user_id), threading.Event()).set()
        fin = time.monotonic() + 5
        while time.monotonic() < fin and not liberer.is_set():
            if stop_event.is_set():
                arretes.add(user_id)
                return
            time.sleep(0.01)

    monkeypatch.setattr(main, "lancer_recherche", fausse_recherche)
    monkeypatch.setattr(main, "chercher_offres_lba", lambda romes: [])
    monkeypatch.setattr(spontanees.scraper_emails, "main", faux_scraper)
    yield liberer, demarres, arretes
    # Laisser finir les threads AVANT que les faux soient retirés : sinon un
    # thread attardé appellerait le vrai LBA une fois les barrières levées.
    liberer.set()
    attendre(lambda: not any(e["en_cours"] for etats in main.pipelines._etats.values()
                             for e in etats.values()))


def _demarre(demarres, cle):
    attendre(lambda: cle in demarres)


def test_deux_recherches_en_parallele_isolees(a_et_b, faux_travaux):
    client_a, id_a, client_b, id_b = a_et_b
    liberer, demarres, _ = faux_travaux

    assert client_a.post("/api/recherche").status_code == 200
    assert client_b.post("/api/recherche").status_code == 200
    _demarre(demarres, ("recherche", id_a))
    _demarre(demarres, ("recherche", id_b))

    # Chacun voit son état et ses logs, pas ceux de l'autre
    assert client_a.get("/api/statut_recherche").json()["en_cours"] is True
    assert client_b.get("/api/statut_recherche").json()["en_cours"] is True
    logs_a = [l["msg"] for l in client_a.get("/api/logs").json()]
    logs_b = [l["msg"] for l in client_b.get("/api/logs").json()]
    assert f"recherche de {id_a}" in logs_a and f"recherche de {id_b}" not in logs_a
    assert f"recherche de {id_b}" in logs_b and f"recherche de {id_a}" not in logs_b

    # Une seule recherche à la fois par utilisateur
    r = client_a.post("/api/recherche")
    assert r.status_code == 400 and "déjà en cours" in r.json()["erreur"]

    liberer.set()
    attendre(lambda: not client_a.get("/api/statut_recherche").json()["en_cours"])
    attendre(lambda: not client_b.get("/api/statut_recherche").json()["en_cours"])
    assert client_a.get("/api/statut_recherche").json()["message"] == "Terminé !"
    assert client_a.post("/api/recherche").status_code == 200   # de nouveau permis


def test_a_ne_peut_pas_arreter_b(a_et_b, faux_travaux):
    client_a, id_a, client_b, id_b = a_et_b
    liberer, demarres, arretes = faux_travaux

    assert client_a.post("/api/spontanees/scraper").status_code == 200
    assert client_b.post("/api/spontanees/scraper").status_code == 200
    _demarre(demarres, ("scraper", id_a))
    _demarre(demarres, ("scraper", id_b))
    assert client_a.post("/api/spontanees/scraper").status_code == 400
    assert client_a.post("/api/spontanees/fetch").status_code == 400   # même type : spontanées

    assert client_a.post("/api/spontanees/stop").json() == {"ok": True, "en_cours": True}
    attendre(lambda: id_a in arretes)
    attendre(lambda: not client_a.get("/api/spontanees/statut").json()["en_cours"])
    assert client_a.get("/api/spontanees/statut").json()["message"] == "Arrêté — données sauvegardées"

    # B tourne toujours, avec son propre message, et n'a pas vu l'arrêt de A
    etat_b = client_b.get("/api/spontanees/statut").json()
    assert etat_b["en_cours"] is True and etat_b["message"] == f"progression de {id_b}"
    assert id_b not in arretes
    assert client_b.get("/api/spontanees/stats").json()["en_cours"] is True
    assert client_a.get("/api/spontanees/stats").json()["en_cours"] is False
    logs_b = [l["msg"] for l in client_b.get("/api/logs").json()]
    assert not any("Arrêt demandé" in m for m in logs_b)
    assert not any(str(id_a) in m for m in logs_b if "scraper de" in m)

    liberer.set()
    attendre(lambda: not client_b.get("/api/spontanees/statut").json()["en_cours"])
    assert id_b not in arretes


def test_arret_sans_pipeline_en_cours(a_et_b):
    client_a, _, _, _ = a_et_b
    assert client_a.post("/api/spontanees/stop").json() == {"ok": True, "en_cours": False}
    assert client_a.get("/api/spontanees/statut").json()["message"] == "Prêt"


def test_recherche_et_spontanees_peuvent_tourner_ensemble(a_et_b, faux_travaux):
    client_a, id_a, _, _ = a_et_b
    _, demarres, _ = faux_travaux
    assert client_a.post("/api/recherche").status_code == 200
    assert client_a.post("/api/spontanees/scraper").status_code == 200
    _demarre(demarres, ("recherche", id_a))
    _demarre(demarres, ("scraper", id_a))


def test_logs_bornes_par_utilisateur():
    p = Pipelines(logs_max=3)
    for i in range(5):
        p.log(1, f"a{i}")
    p.log(2, "b0")
    assert [l["msg"] for l in p.logs(1)] == ["a2", "a3", "a4"]
    assert [l["msg"] for l in p.logs(2)] == ["b0"]
    assert p.logs(3) == []


def test_demarrage_atomique():
    """Vingt demandes simultanées pour le même utilisateur : une seule passe."""
    p = Pipelines()
    acceptes = []
    assert en_parallele(lambda: acceptes.append(p.demarrer(RECHERCHE, 1)), 20) == []
    assert acceptes.count(True) == 1
    assert p.demarrer(RECHERCHE, 2) is True   # un autre utilisateur peut démarrer
