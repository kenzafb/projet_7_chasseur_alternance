"""Liens venus de l'extérieur : seulement http(s) (audit phase 12, D132) ;
erreur de jeton France Travail sans le corps de la réponse."""

import pytest

import france_travail.scraper as scraper
import france_travail.scraper_lba as lba
from database.candidatures_db import ajouter_candidature, lire_candidatures
from shared.liens import lien_http
from tests.faux_france_travail import Reponse, offre
from tests.faux_lba import offre as offre_lba


@pytest.mark.parametrize("url,attendu", [
    ("https://exemple.fr/offre?id=1", "https://exemple.fr/offre?id=1"),
    ("  http://exemple.fr  ", "http://exemple.fr"),
    ("javascript:alert(1)", ""), ("JavaScript:alert(1)", ""), ("data:text/html,<b>x</b>", ""),
    ("//exemple.fr", ""), ("exemple.fr", ""), ('https://x.fr/"onmouseover="a()', ""),
    ("https://x.fr/<script>", ""), ("https://x.fr/\nSet-Cookie:a", ""), (None, ""), ("", ""),
])
def test_lien_http(url, attendu):
    assert lien_http(url) == attendu


def test_offre_france_travail_lien_javascript_remplace():
    o = offre(1)
    o["origineOffre"] = {"urlOrigine": "javascript:alert(1)"}
    assert scraper._normaliser_une(o)["lien"] == "https://candidat.francetravail.fr/offres/recherche/detail/FT1"
    o["origineOffre"] = {"urlOrigine": "https://partenaire.fr/o/1"}
    assert scraper._normaliser_une(o)["lien"] == "https://partenaire.fr/o/1"


def test_offre_lba_lien_javascript_vide():
    o = offre_lba(1)
    o["apply"]["url"] = "javascript:alert(1)"
    assert lba._normaliser_offre_lba(o)["lien"] == ""


def test_lien_deja_en_base_filtre_a_la_lecture(utilisateur):
    client, uid = utilisateur("a@test.fr")
    ajouter_candidature(uid, {"id": "X", "titre": "t", "entreprise": "e", "description": "d",
                              "lien": "javascript:alert(1)", "source": "France Travail"})
    assert lire_candidatures(uid)[0]["lien"] == ""
    assert client.get("/api/candidatures").json()[0]["lien"] == ""


def test_jeton_refuse_sans_corps_de_reponse(monkeypatch):
    monkeypatch.setattr(scraper, "_token_cache", {"token": None, "expire": 0})
    corps = {"error": "invalid_client", "error_description": "client_secret=SECRET-QUI-FUIT"}
    monkeypatch.setattr(scraper.requests, "post", lambda *a, **k: Reponse(401, corps))
    journal = []
    assert scraper.get_token(journal.append) is None
    assert journal == ["  ⚠️  France Travail : jeton refusé (401, invalid_client), vérifier FT_CLIENT_ID et "
                       "FT_CLIENT_SECRET dans .env"]
    assert "QUI-FUIT" not in " ".join(journal)


def test_jeton_injoignable_journalise(monkeypatch):
    def panne(*a, **k):
        raise scraper.requests.ConnectionError("x")
    monkeypatch.setattr(scraper, "_token_cache", {"token": None, "expire": 0})
    monkeypatch.setattr(scraper.requests, "post", panne)
    journal = []
    assert scraper.recuperer_offres({"filtres": {}, "domaines": []}, log=journal.append) == []
    assert "injoignable (ConnectionError)" in journal[0]
