"""L'utilisateur A ne lit ni ne modifie le profil ou les candidatures de B."""

import pytest

from database.candidatures_db import ajouter_candidature, lire_candidature
from database.entreprises_db import ajouter_entreprises, lire_entreprises
from database.profil_db import lire_profil

OFFRE_B = {"id": "OFFRE-B", "titre": "Développeur", "entreprise": "ACME",
           "description": "Poste de B", "statut": "nouveau", "lettre": "Lettre de B"}


@pytest.fixture
def a_et_b(utilisateur):
    client_a, id_a = utilisateur("a@test.fr", prenom="Alice", nom="A")
    client_b, id_b = utilisateur("b@test.fr", prenom="Bob", nom="B")
    ajouter_candidature(id_b, dict(OFFRE_B))
    ajouter_entreprises(id_b, [{"siret": "123", "nom": "Entreprise de B"}])
    return client_a, id_a, client_b, id_b


def test_profil_lu_est_le_sien(a_et_b):
    client_a, _, client_b, _ = a_et_b
    assert client_a.get("/api/profil").json()["prenom"] == "Alice"
    assert client_b.get("/api/profil").json()["prenom"] == "Bob"


def test_modifier_son_profil_ne_touche_pas_celui_de_b(a_et_b):
    client_a, id_a, _, id_b = a_et_b
    r = client_a.post("/api/profil", json={"prenom": "Pirate", "lettre_type": "x {paragraphe_entreprise}"})
    assert r.json() == {"ok": True}
    assert lire_profil(id_a)["prenom"] == "Pirate"
    assert lire_profil(id_b)["prenom"] == "Bob"
    assert lire_profil(id_b)["lettre_type"] == ""


def test_candidatures_de_b_invisibles(a_et_b):
    client_a, _, client_b, _ = a_et_b
    assert client_a.get("/api/candidatures").json() == []
    assert [c["id"] for c in client_b.get("/api/candidatures").json()] == ["OFFRE-B"]


@pytest.mark.parametrize("chemin,corps", [
    ("/api/maj_statut", {"id": "OFFRE-B", "statut": "refus"}),
    ("/api/archiver", {"id": "OFFRE-B"}),
    ("/api/offre/archivage", {"id": "OFFRE-B", "raison": "manuel"}),
    ("/api/sauvegarder", {"id": "OFFRE-B", "lettre": "Écrasée par A"}),
])
def test_candidature_de_b_non_modifiable(a_et_b, chemin, corps):
    client_a, _, _, id_b = a_et_b
    client_a.post(chemin, json=corps)
    offre = lire_candidature(id_b, "OFFRE-B")
    assert offre["statut"] == "nouveau"
    assert offre["lettre"] == "Lettre de B"
    assert offre["raison_archivage"] == ""


@pytest.mark.parametrize("chemin", ["/api/generer_lettre", "/api/analyser", "/api/telecharger_pdf"])
def test_candidature_de_b_introuvable_pour_a(a_et_b, mistral, chemin):
    client_a, _, _, _ = a_et_b
    assert client_a.post(chemin, json={"id": "OFFRE-B"}).status_code == 404
    assert mistral.appels == []


def test_suivi_spontanees_de_b_inaccessible(a_et_b):
    client_a, _, _, id_b = a_et_b
    entreprise_b = lire_entreprises(id_b)[0]
    assert client_a.get("/api/spontanees/suivi").json() == []
    r = client_a.post("/api/spontanees/suivi/statut", json={"id": entreprise_b["_id"], "statut": "refus"})
    assert r.json() == {"ok": False}
    assert lire_entreprises(id_b)[0].get("statut_suivi") != "refus"
    assert client_a.get("/api/spontanees/stats").json()["raw"] == 0
