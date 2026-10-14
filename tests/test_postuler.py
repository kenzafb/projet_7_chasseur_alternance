"""« J'ai postulé » sur une offre (D105) : statut « envoye » (affiché
« Postulée ») et date de candidature, modifiables et annulables, isolés par
utilisateur et par mode ; filtre « Postulées » ; désarchivage."""

from datetime import date, timedelta

import pytest

from database.candidatures_db import ajouter_candidature, lire_candidature
from shared import config


@pytest.fixture
def alice(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_candidature(uid, {"id": "R1", "titre": "Dev", "score": 8, "verdict": "bon", "statut": "nouveau"})
    return client, uid


def test_postuler_aujourd_hui(alice):
    client, uid = alice
    r = client.post("/api/offre/postuler", json={"id": "R1"}).json()
    from database.dates import maintenant_affichage
    assert r == {"ok": True, "statut": "envoye", "date_candidature": maintenant_affichage().date().isoformat()}
    o = lire_candidature(uid, "R1")
    assert (o["statut"], o["date_candidature"]) == ("envoye", r["date_candidature"])


def test_date_modifiable_et_retour_en_arriere(alice):
    client, uid = alice
    client.post("/api/offre/postuler", json={"id": "R1", "date": "2026-10-01"})
    assert lire_candidature(uid, "R1")["date_candidature"] == "2026-10-01"
    client.post("/api/maj_statut", json={"id": "R1", "statut": "entretien"})   # suivi de Mes candidatures
    client.post("/api/offre/postuler", json={"id": "R1", "date": "2026-10-03"})  # changer la date
    o = lire_candidature(uid, "R1")
    assert (o["statut"], o["date_candidature"]) == ("entretien", "2026-10-03")   # le suivi est gardé
    assert client.post("/api/offre/postuler", json={"id": "R1", "annuler": True}).json()["statut"] == "nouveau"
    o = lire_candidature(uid, "R1")
    assert (o["statut"], o["date_candidature"]) == ("nouveau", "")


def test_date_future_ou_illisible_refusee(alice):
    client, uid = alice
    demain = (date.today() + timedelta(days=2)).isoformat()
    r = client.post("/api/offre/postuler", json={"id": "R1", "date": demain})
    assert r.status_code == 400 and "futur" in r.json()["erreur"]
    assert client.post("/api/offre/postuler", json={"id": "R1", "date": "01/10/26"}).status_code == 400
    assert lire_candidature(uid, "R1")["statut"] == "nouveau"


def test_offre_archivee_recuperee_en_postulant(alice):
    client, uid = alice
    client.post("/api/offre/archivage", json={"id": "R1", "raison": "ineligible"})
    client.post("/api/offre/postuler", json={"id": "R1", "date": "2026-10-01"})
    o = lire_candidature(uid, "R1")
    assert (o["statut"], o["raison_archivage"]) == ("envoye", "")


def test_isolation_utilisateur_et_mode(alice, utilisateur):
    client, uid = alice
    client_b, _ = utilisateur("b@test.fr", prenom="Bob")
    assert client_b.post("/api/offre/postuler", json={"id": "R1"}).status_code == 404
    client.mode = "job"
    assert client.post("/api/offre/postuler", json={"id": "R1"}).status_code == 404
    assert lire_candidature(uid, "R1")["statut"] == "nouveau"


def test_interface():
    page = (config.TEMPLATES_DIR / "partials" / "offres.html").read_text(encoding="utf-8")
    assert 'data-foffre="statut"' in page and '<option value="postulees">Postulées</option>' in page
    js = (config.STATIC_DIR / "js" / "offres.js").read_text(encoding="utf-8")
    for attendu in ("J'ai postulé", "Annuler la candidature", "data-postuler-date", "date_candidature || \"\").localeCompare",
                    'data-act="desarchiver"'):
        assert attendu in js, attendu
    assert '"Postulée"' in (config.STATIC_DIR / "js" / "candidatures.js").read_text(encoding="utf-8")
