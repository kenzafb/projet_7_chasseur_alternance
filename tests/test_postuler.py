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
    """D110 : une offre postulée sort de la page Offres ; date et annulation se
    font dans le tableau Candidatures ; les spontanées envoyées sortent de leur liste."""
    page = (config.TEMPLATES_DIR / "partials" / "offres.html").read_text(encoding="utf-8")
    assert 'data-foffre="statut"' not in page and "Postulées" not in page
    js = (config.STATIC_DIR / "js" / "offres.js").read_text(encoding="utf-8")
    assert "J'ai postulé" in js and "if (estPostulee(o)) return false;" in js
    assert "Annuler la candidature" not in js and 'data-act="desarchiver"' in js
    cand = (config.STATIC_DIR / "js" / "candidatures.js").read_text(encoding="utf-8")
    assert "data-cand-date" in cand and "data-annuler" in cand and "{ annuler: true }" in cand
    assert 'new Event("offres:maj")' in cand and '"Postulée"' in cand
    sp = (config.STATIC_DIR / "js" / "spontanees.js").read_text(encoding="utf-8")
    assert "stats.dernieres" not in sp
    assert 'data-filter="envoye"' not in (config.TEMPLATES_DIR / "partials" / "spontanees.html").read_text(encoding="utf-8")
