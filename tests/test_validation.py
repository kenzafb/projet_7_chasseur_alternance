"""/api/maj_statut et /api/offre/archivage : entrées validées par Pydantic."""

import pytest

from database.candidatures_db import ajouter_candidature, lire_candidature


@pytest.fixture
def ada(utilisateur):
    client, user_id = utilisateur("ada@test.fr", prenom="Ada", nom="L")
    ajouter_candidature(user_id, {"id": "R1", "titre": "Dev"})
    return client, user_id


@pytest.mark.parametrize("corps", [
    {"id": "R1", "statut": "pirate"},
    {"id": "R1", "statut": ""},
    {"id": "R1"},
    {"statut": "envoye"},
    {"id": "", "statut": "envoye"},
    {"id": "R1", "statut": "envoye", "notes": "champ en trop"},
    {"id": ["R1"], "statut": "envoye"},
])
def test_maj_statut_refuse_les_entrees_invalides(ada, corps):
    client, user_id = ada
    r = client.post("/api/maj_statut", json=corps)
    assert r.status_code == 422
    assert r.json()["erreur"].startswith("Requête invalide")
    assert lire_candidature(user_id, "R1")["statut"] == "nouveau"


def test_maj_statut_valide(ada):
    client, user_id = ada
    assert client.post("/api/maj_statut", json={"id": "R1", "statut": "entretien"}).json() == {"ok": True}
    offre = lire_candidature(user_id, "R1")
    assert offre["statut"] == "entretien" and offre["date_candidature"]


@pytest.mark.parametrize("corps", [
    {"id": "R1", "raison": "pirate"},
    {"id": "R1", "raison": ""},
    {"id": "R1"},                                          # ni raison ni désarchivage
    {"id": "R1", "desarchiver": False},
    {"id": "R1", "desarchiver": True, "raison": "manuel"},  # les deux à la fois
    {"raison": "manuel"},
    {"id": "R1", "raison": "manuel", "statut": "envoye"},
])
def test_archivage_refuse_les_entrees_invalides(ada, corps):
    client, user_id = ada
    r = client.post("/api/offre/archivage", json=corps)
    assert r.status_code == 422
    assert "erreur" in r.json()
    offre = lire_candidature(user_id, "R1")
    assert (offre["statut"], offre["raison_archivage"]) == ("nouveau", "")


def test_archivage_puis_desarchivage(ada):
    client, user_id = ada
    assert client.post("/api/offre/archivage", json={"id": "R1", "raison": "hors_domaine"}).status_code == 200
    offre = lire_candidature(user_id, "R1")
    assert (offre["statut"], offre["raison_archivage"]) == ("archive", "hors_domaine")
    assert client.post("/api/offre/archivage", json={"id": "R1", "desarchiver": True}).status_code == 200
    offre = lire_candidature(user_id, "R1")
    assert (offre["statut"], offre["raison_archivage"]) == ("nouveau", "")


def test_corps_non_json(ada):
    client, _ = ada
    r = client.post("/api/maj_statut", content=b"pas du json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
