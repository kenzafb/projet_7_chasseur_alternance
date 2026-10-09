"""Erreurs 400 lisibles de la lettre : profil incomplet, accolade dans la lettre type."""

import pytest

from database.candidatures_db import ajouter_candidature

PROFIL_COMPLET = {"prenom": "Ada", "nom": "Lovelace", "email": "ada@test.fr"}


@pytest.fixture
def ada(utilisateur):
    """Client connecté, profil sans prénom ni nom, une offre en base."""
    client, user_id = utilisateur("ada@test.fr")
    ajouter_candidature(user_id, {"id": "OFFRE-1", "titre": "Développeuse", "entreprise": "ACME",
                                  "lieu": "75 - Paris", "description": "Une offre"})
    return client


def test_lettre_profil_incomplet(ada, mistral):
    r = ada.post("/api/generer_lettre", json={"id": "OFFRE-1"})
    assert r.status_code == 400
    assert r.json()["erreur"] == "Profil incomplet : renseigne prénom, nom dans l'onglet Profil."
    assert mistral.appels == []   # refus avant tout appel à l'IA


def test_recherche_profil_absent_en_mode_job(ada):
    ada.mode = "job"
    r = ada.post("/api/recherche")   # refusée avant le lancement du thread
    assert r.status_code == 400
    assert "Aucun profil pour ce mode" in r.json()["erreur"]


def test_pdf_profil_incomplet(ada):
    ada.post("/api/profil", json={"prenom": "Ada", "nom": "", "email": ""})
    r = ada.post("/api/telecharger_pdf", json={"id": "OFFRE-1", "lettre": "Madame, Monsieur,"})
    assert r.status_code == 400
    assert r.json()["erreur"] == "Profil incomplet : renseigne nom, email dans l'onglet Profil."


@pytest.mark.parametrize("lettre_type,attendu", [
    ("Bonjour {paragraphe_entreprise} et { isolée", "accolade { ou } isolée"),
    ("Bonjour {paragraphe_entreprise} }", "accolade { ou } isolée"),
    ("Bonjour {prenom} {paragraphe_entreprise}", "balise inconnue : {prenom}"),
    ("Bonjour {} {paragraphe_entreprise}", "balise inconnue : {}"),
    ("{date.__class__} {paragraphe_entreprise}", "balise inconnue : {date.__class__}"),
    ("{date!r} {paragraphe_entreprise}", "balise inconnue : {date}"),
])
def test_lettre_type_avec_accolade(ada, mistral, lettre_type, attendu):
    ada.post("/api/profil", json={**PROFIL_COMPLET, "lettre_type": lettre_type})
    r = ada.post("/api/generer_lettre", json={"id": "OFFRE-1"})
    assert r.status_code == 400
    assert attendu in r.json()["erreur"]
    assert mistral.appels == []


def test_lettre_type_valide_balises_avec_espaces(ada, mistral):
    ada.post("/api/profil", json={**PROFIL_COMPLET,
                                  "lettre_type": "{ contact_entreprise }\nLe {date}\n{paragraphe_entreprise}"})
    r = ada.post("/api/generer_lettre", json={"id": "OFFRE-1"})
    assert r.status_code == 200
    lettre = r.json()["lettre"]
    assert lettre.startswith("ACME\n75010 Paris\nLe ")
    assert "ACME, votre contexte me parle." in lettre
    assert len(mistral.appels) == 1   # le faux client a bien servi


def test_pdf_profil_complet(ada, tmp_path):
    ada.post("/api/profil", json=PROFIL_COMPLET)
    r = ada.post("/api/telecharger_pdf", json={"id": "OFFRE-1", "lettre": "Madame, Monsieur,\n\nTexte."})
    assert r.status_code == 200
    assert r.json()["url"] == "/api/lettre_pdf/OFFRE-1?mode=alternance"
    assert r.json()["nom"] == "Lettre_Ada_Lovelace_ACME.pdf"
    assert len(list((tmp_path / "pdf").glob("user_*/lettre_*.pdf"))) == 1
