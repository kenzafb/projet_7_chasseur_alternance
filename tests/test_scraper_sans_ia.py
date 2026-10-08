"""Scraper : si Mistral échoue, les emails lus directement dans la page
(regex, déobfuscation) sont gardés, marqués non validés par l'IA ; une
erreur bloquante ne donne qu'un message pour tout le lancement."""

import time
from types import SimpleNamespace

import pytest

import shared.ia
import spontanees.scraper_emails as se
from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
from tests.test_mistral import TIER, echouer, erreur_http

PAGE = ('<html><body><h1>ACME</h1><p>Écrivez-nous : <a href="mailto:recrutement@{d}">recrutement</a> '
        'ou contact [at] {d}</p></body></html>')


@pytest.fixture
def sites(monkeypatch, mistral):
    """Pages simulées : la page d'accueil de chaque site contient ses adresses."""
    monkeypatch.setattr(se, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(shared.ia, "time", SimpleNamespace(sleep=lambda s: None, monotonic=time.monotonic))
    monkeypatch.setattr(se, "PAUSE_MISTRAL", 0)
    monkeypatch.setattr(se, "lire_sitemap", lambda url: [])

    def get_page(url, timeout=8):
        domaine = url.split("://", 1)[1].split("/", 1)[0].removeprefix("www.")
        if url.rstrip("/") == f"https://{domaine}":
            return PAGE.format(d=domaine), url
        return None, None

    monkeypatch.setattr(se, "get_page", get_page)
    mistral.reponse = '{"emails": ["recrutement@acme1.fr"], "telephones": [], "contact_rh": null, "fiable": true}'


@pytest.fixture
def user_id(utilisateur):
    uid = utilisateur("a@test.fr", prenom="Alice")[1]
    ajouter_entreprises(uid, [{"siret": f"S{i}", "nom": f"ACME {i}"} for i in range(1, 4)])
    liste = lire_entreprises(uid)
    for i, e in enumerate(liste, 1):
        e["site_web"] = f"https://acme{i}.fr"   # site connu : pas de recherche DuckDuckGo
    sauvegarder_enrichissement(uid, liste)
    return uid


def _lancer(user_id, **kw):
    logs = []
    se.main(user_id, log_fn=logs.append, **kw)
    return {e["nom"]: e for e in lire_entreprises(user_id)}, "\n".join(logs)


def test_avec_ia_emails_valides(sites, user_id):
    entreprises, _ = _lancer(user_id, max_scrapees=1)
    e = entreprises["ACME 1"]
    assert e["emails_trouves"] == ["recrutement@acme1.fr"] and e["emails_non_valides"] is False


def test_erreur_passagere_emails_de_la_page_gardes(sites, user_id, mistral, monkeypatch):
    echouer(mistral, monkeypatch, erreur_http(503))
    entreprises, logs = _lancer(user_id, max_scrapees=1)
    e = entreprises["ACME 1"]
    assert set(e["emails_trouves"]) == {"recrutement@acme1.fr", "contact@acme1.fr"}   # mailto et déobfusqué
    assert e["emails_non_valides"] is True and e["traite"] is True
    assert "non validés par l'IA" in logs and "Aucun email" not in logs


def test_erreur_bloquante_un_seul_message(sites, user_id, mistral, monkeypatch):
    echouer(mistral, monkeypatch, erreur_http(403, TIER))
    entreprises, logs = _lancer(user_id)
    assert len(mistral.appels) == 1                       # plus d'appel après le refus
    assert logs.count("Mistral refuse les appels") == 1
    assert "non autorisé" in logs
    for nom in ("ACME 1", "ACME 2", "ACME 3"):
        assert entreprises[nom]["emails_trouves"] and entreprises[nom]["emails_non_valides"] is True


def test_emails_non_valides_relus_et_effaces_au_besoin(user_id):
    liste = lire_entreprises(user_id)
    liste[0]["emails_non_valides"] = True
    sauvegarder_enrichissement(user_id, liste)
    assert lire_entreprises(user_id)[0]["emails_non_valides"] is True
    liste = lire_entreprises(user_id)
    liste[0]["emails_non_valides"] = False
    sauvegarder_enrichissement(user_id, liste)
    assert lire_entreprises(user_id)[0]["emails_non_valides"] is False
