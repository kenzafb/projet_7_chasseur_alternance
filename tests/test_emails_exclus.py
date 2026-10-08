"""Adresses techniques ou factices (décision D47) : règles du fichier de
données, scraper, enregistrement en base."""

import pytest

import france_travail.scraper_lba as lba
import main
from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
from shared import emails_exclus
from spontanees.scraper_emails import est_email_valide, meilleurs_emails

SENTRY = "aa4c3f2b9d1e4f6a8b7c5d3e2f1a0b9c@o4506196830715904.ingest.us.sentry.io"


@pytest.mark.parametrize("email", [
    SENTRY, "votre@email.com", "email@exemple.fr", "nom@domaine.fr", "Votre@Societe.fr",
    "x@sentry-next.wixpress.com", "contact@example.com", "a@b.example.org", "prenom.nom@entreprise.fr",
    "john.doe@acme.com", "info@yourdomain.com",
])
def test_adresses_exclues(email):
    assert emails_exclus.email_exclu(email)
    assert not est_email_valide(email)


@pytest.mark.parametrize("email", [
    "recrutement@acme.fr", "rh@groupe-sentry.fr", "contact@monsite-pro.fr", "jean.martin@acme.fr",
    "nom.famille@acme.fr", "email.rh@acme.fr", "votreservice@acme.fr",
])
def test_adresses_gardees(email):
    assert not emails_exclus.email_exclu(email)


def test_fichier_de_regles_facile_a_completer(tmp_path, monkeypatch):
    fichier = tmp_path / "regles.txt"
    fichier.write_text("# commentaire\n@faux.fr   # domaine\nbidon@\nexact@vrai.fr\n\nsans arobase\n",
                       encoding="utf-8")
    monkeypatch.setattr(emails_exclus, "FICHIER", fichier)
    emails_exclus.regles.cache_clear()
    try:
        assert emails_exclus.regles() == ({"faux.fr"}, {"bidon"}, {"exact@vrai.fr"})
        assert emails_exclus.email_exclu("a@sous.faux.fr") and emails_exclus.email_exclu("bidon@vrai.fr")
        assert emails_exclus.email_exclu("EXACT@vrai.fr") and not emails_exclus.email_exclu("autre@vrai.fr")
    finally:
        emails_exclus.regles.cache_clear()


def test_scraper_ne_garde_pas_les_adresses_factices():
    assert meilleurs_emails([SENTRY, "votre@email.com", "recrutement@acme.fr"]) == ["recrutement@acme.fr"]


def test_rien_d_exclu_n_est_enregistre(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": "S1", "nom": "Acme"}])
    e = lire_entreprises(uid)[0]
    sauvegarder_enrichissement(uid, [{"_id": e["_id"], "emails_trouves": [SENTRY, "rh@acme.fr", "votre@email.com"],
                                      "traite": True}])
    assert lire_entreprises(uid)[0]["emails_trouves"] == ["rh@acme.fr"]


def test_recherche_d_offres_utilise_lba_sans_entreprises():
    assert main.rechercher_lba is lba.rechercher_offres_pour_profil
