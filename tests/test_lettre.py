"""Lettre (D106) : erreurs 400 lisibles (profil incomplet, lettre type absente, sans {paragraphe},
accolade), paragraphe par l'IA puis assemblage en Python, enregistré."""

import pytest

from database.candidatures_db import ajouter_candidature

PROFIL_COMPLET = {"prenom": "Ada", "nom": "Lovelace", "email": "ada@test.fr",
                  "lettre_type": "{contact_entreprise}\nLe {date}\nObjet : {poste}\n{paragraphe}\nCordialement."}


@pytest.fixture
def ada(utilisateur):
    """Client connecté, profil sans prénom ni nom, une offre en base."""
    client, user_id = utilisateur("ada@test.fr")
    ajouter_candidature(user_id, {"id": "OFFRE-1", "titre": "Développeuse", "entreprise": "ACME",
                                  "lieu": "75 - Paris", "description": "Une offre"})
    return client


def test_lettre_profil_incomplet(ada, ia):
    r = ada.post("/api/lettre/paragraphe", json={"id": "OFFRE-1"})
    assert r.status_code == 400
    assert r.json()["erreur"] == "Profil incomplet : renseigne prénom, nom dans l'onglet Profil."
    assert ia.appels == []   # refus avant tout appel à l'IA


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
def test_lettre_type_avec_accolade(ada, ia, lettre_type, attendu):
    ada.post("/api/profil", json={**PROFIL_COMPLET, "lettre_type": lettre_type})
    r = ada.post("/api/lettre/paragraphe", json={"id": "OFFRE-1"})
    assert r.status_code == 400
    assert attendu in r.json()["erreur"]
    assert ia.appels == []


def test_lettre_type_valide_balises_avec_espaces(ada, ia):
    ada.post("/api/profil", json={**PROFIL_COMPLET,
                                  "lettre_type": "{ contact_entreprise }\nLe {date}\n{ paragraphe }"})
    r = ada.post("/api/lettre/paragraphe", json={"id": "OFFRE-1"})
    assert r.status_code == 200 and r.json() == {"paragraphe": "ACME, votre contexte me parle."}
    assert len(ia.appels) == 1   # le faux client a bien servi


@pytest.mark.parametrize("lettre_type, message", [
    ("", "Écris d'abord ta lettre type dans Profil"),
    ("Madame, Monsieur, je postule chez {entreprise}.", "n'a pas de balise {paragraphe}"),
])
def test_sans_lettre_type_renvoi_au_profil(ada, ia, lettre_type, message):
    ada.post("/api/profil", json={**PROFIL_COMPLET, "lettre_type": lettre_type})
    for route, corps in (("/api/lettre/paragraphe", {"id": "OFFRE-1"}),
                         ("/api/lettre/assembler", {"id": "OFFRE-1", "paragraphe": "P."})):
        r = ada.post(route, json=corps)
        assert r.status_code == 400 and message in r.json()["erreur"], route
    assert ia.appels == []


def test_paragraphe_modifie_puis_insere_et_enregistre(ada, ia):
    from database.candidatures_db import lire_candidature
    from database.connexion import SessionLocal
    from database.models import User
    ada.post("/api/profil", json=PROFIL_COMPLET)
    assert ada.post("/api/lettre/paragraphe", json={"id": "OFFRE-1"}).json()["paragraphe"]
    db = SessionLocal()
    uid = db.query(User).filter_by(email="ada@test.fr").one().id
    db.close()
    assert lire_candidature(uid, "OFFRE-1")["lettre"] == ""            # rien d'enregistré avant insertion
    r = ada.post("/api/lettre/assembler", json={"id": "OFFRE-1", "paragraphe": "Mon paragraphe relu."})
    lettre = r.json()["lettre"]
    assert lettre.startswith("ACME\n75 - Paris\nLe ") and "Objet : Développeuse\nMon paragraphe relu.\n" in lettre
    o = lire_candidature(uid, "OFFRE-1")
    assert (o["lettre"], o["statut"]) == (lettre, "en_cours")
    assert ada.post("/api/lettre/assembler", json={"id": "OFFRE-1", "paragraphe": "  "}).status_code == 400
    # Une offre postulée garde son statut
    ada.post("/api/offre/postuler", json={"id": "OFFRE-1"})
    ada.post("/api/lettre/assembler", json={"id": "OFFRE-1", "paragraphe": "Autre."})
    assert lire_candidature(uid, "OFFRE-1")["statut"] == "envoye"


def test_profil_lettre_type_dans_les_trois_modes(ada):
    for mode in ("alternance", "stage", "job"):
        page = ada.get(f"/{mode}").text
        i = page.index('<h3 class="profil-card__title">Lettre de motivation type</h3>')
        assert mode in page[:i].rsplit('data-mode-section="', 1)[1].split('"')[0].split()
        assert "{paragraphe}" in page and "data-lettre-exemple" in page


def test_pdf_profil_complet(ada, tmp_path):
    ada.post("/api/profil", json=PROFIL_COMPLET)
    r = ada.post("/api/telecharger_pdf", json={"id": "OFFRE-1", "lettre": "Madame, Monsieur,\n\nTexte."})
    assert r.status_code == 200
    assert r.json()["url"] == "/api/lettre_pdf/OFFRE-1?mode=alternance"
    assert r.json()["nom"] == "Lettre_Ada_Lovelace_ACME.pdf"
    assert len(list((tmp_path / "pdf").glob("user_*/lettre_*.pdf"))) == 1
