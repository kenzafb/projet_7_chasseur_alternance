"""Dédoublonnage en base, par utilisateur : offres vues, adresses contactées,
insertions idempotentes."""

import pytest

import france_travail.analyseur
import france_travail.scraper as scraper
import spontanees.envoyeur as envoyeur
from database.candidatures_db import ajouter_candidature, lire_candidatures
from database.connexion import SessionLocal
from database.dedup_db import (ajouter_emails_contactes, lire_emails_contactes,
                               lire_offres_vues, marquer_offres_vues)
from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
from database.models import Candidature, EmailContacte, OffreVue
from france_travail.main import lancer_recherche
from tests.conftest import en_parallele


def _brut_ft(id_ft, titre="Développeur"):
    """Offre au format brut de l'API France Travail, en Île-de-France."""
    return {"id": id_ft, "intitule": titre, "lieuTravail": {"libelle": "75 - Paris 10e"},
            "entreprise": {"nom": "ACME"}, "dateCreation": "2026-10-01T08:00:00.000Z"}


@pytest.fixture
def france_travail_simule(monkeypatch):
    """L'API France Travail renvoie toujours les mêmes offres, sans réseau."""
    bruts = [_brut_ft("FT1"), _brut_ft("FT2")]
    monkeypatch.setattr(scraper, "_paginer", lambda params: list(bruts))
    monkeypatch.setattr(france_travail.analyseur, "PAUSE_MISTRAL", 0)
    return bruts


@pytest.fixture
def a_et_b(utilisateur):
    _, id_a = utilisateur("a@test.fr", prenom="Alice", nom="A")
    _, id_b = utilisateur("b@test.fr", prenom="Bob", nom="B")
    return id_a, id_b


# ─── Offres vues ──────────────────────────────────────────────────────────────
def test_offre_vue_par_a_proposee_a_b(a_et_b, france_travail_simule):
    id_a, id_b = a_et_b
    assert len(scraper.chercher_offres(id_a, mode="alternance")) == 2
    assert scraper.chercher_offres(id_a, mode="alternance") == []   # déjà vues par A
    assert len(scraper.chercher_offres(id_b, mode="alternance")) == 2   # B les voit
    assert len(lire_offres_vues(id_a, "alternance")) == 2


def test_offres_vues_separees_par_mode(a_et_b, france_travail_simule):
    """Bug 1 : un run job n'efface plus la mémoire du mode alternance."""
    id_a, _ = a_et_b
    scraper.chercher_offres(id_a, mode="alternance")
    assert len(scraper.chercher_offres(id_a, mode="job", filtrer_domaines=False)) == 2
    assert scraper.chercher_offres(id_a, mode="alternance") == []
    assert lire_offres_vues(id_a, "alternance") == lire_offres_vues(id_a, "job")


def test_recherche_complete_ecrit_les_candidatures_de_chacun(a_et_b, france_travail_simule):
    id_a, id_b = a_et_b
    for uid in (id_a, id_b):
        lancer_recherche(uid, {"prenom": "X"}, on_offre=lambda o, u=uid: ajouter_candidature(u, o))
    assert {c["id"] for c in lire_candidatures(id_a)} == {c["id"] for c in lire_candidatures(id_b)}
    assert len(lire_candidatures(id_a)) == 2


def test_plus_aucun_fichier_json_de_dedoublonnage():
    assert not hasattr(scraper, "charger_offres_vues")
    assert not hasattr(scraper, "sauvegarder_offres_vues")
    assert not hasattr(envoyeur, "FICHIER_EMAILS_ENVOYES")
    assert not hasattr(envoyeur, "charger_emails_deja_envoyes")


# ─── Adresses contactées ──────────────────────────────────────────────────────
def _entreprise_avec_email(user_id, email):
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}])
    liste = lire_entreprises(user_id)
    liste[0]["emails_trouves"] = [email]
    sauvegarder_enrichissement(user_id, liste)


@pytest.fixture
def envoi_simule(monkeypatch):
    """SMTP remplacé : enregistre (destinataires) au lieu d'envoyer."""
    envois = []
    monkeypatch.setattr(envoyeur, "GMAIL_SENDER", "expediteur@test.fr")
    monkeypatch.setattr(envoyeur, "GMAIL_PASSWORD", "factice")
    monkeypatch.setattr(envoyeur, "envoyer_mail",
                        lambda dest, corps, pieces_jointes=None, log_fn=print: envois.append(list(dest)) or True)
    return envois


def test_adresse_contactee_par_a_ne_bloque_pas_b(a_et_b, envoi_simule):
    id_a, id_b = a_et_b
    ajouter_emails_contactes(id_a, ["RH@acme.fr"])
    _entreprise_avec_email(id_a, "rh@acme.fr")
    _entreprise_avec_email(id_b, "rh@acme.fr")

    envoyeur.main(id_a, limite=5)
    assert envoi_simule == []   # A l'a déjà contactée
    assert lire_entreprises(id_a)[0]["mail_note"].startswith("skip")

    envoyeur.main(id_b, limite=5)
    assert envoi_simule == [["rh@acme.fr"]]
    assert lire_emails_contactes(id_b) == {"rh@acme.fr"}
    assert lire_emails_contactes(id_a) == {"rh@acme.fr"}


# ─── Doublons ignorés sans erreur ─────────────────────────────────────────────
def _compter(modele):
    db = SessionLocal()
    try:
        return db.query(modele).count()
    finally:
        db.close()


def test_doublons_ignores(a_et_b):
    id_a, _ = a_et_b
    assert ajouter_candidature(id_a, {"id": "R1", "titre": "Un"}) is True
    assert ajouter_candidature(id_a, {"id": "R1", "titre": "Deux"}) is False
    assert lire_candidatures(id_a)[0]["titre"] == "Un"
    assert ajouter_candidature(id_a, {"id": "R1"}, mode="job") is True   # autre mode

    assert marquer_offres_vues(id_a, "alternance", ["R1", "R2"]) == 2
    assert marquer_offres_vues(id_a, "alternance", ["R2", "R3", "R3"]) == 1
    assert _compter(OffreVue) == 3

    assert ajouter_emails_contactes(id_a, ["x@a.fr", " X@A.FR ", ""]) == 1
    assert ajouter_emails_contactes(id_a, ["x@a.fr"]) == 0
    assert _compter(EmailContacte) == 1


def test_insertions_simultanees_d_une_meme_candidature(a_et_b):
    id_a, _ = a_et_b
    resultats = []
    erreurs = en_parallele(lambda: resultats.append(ajouter_candidature(id_a, {"id": "SIMUL"})), 8)
    assert erreurs == []
    assert sorted(resultats) == [False] * 7 + [True]
    assert _compter(Candidature) == 1
