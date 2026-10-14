"""Scraper : emails lus directement dans les pages, triés par les règles
(validés ou écartés d'office), l'IA seulement pour les douteux ; si l'IA
échoue ou est coupée, les douteux restent non validés ; une erreur
bloquante ne donne qu'un message pour tout le lancement."""

import time
from types import SimpleNamespace

import pytest

import shared.ia
import spontanees.scraper_emails as se
from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
from shared.validation_emails import emails_douteux
from tests.test_ia import INTROUVABLE, echouer, erreur_http, texte_envoye

# Adresses du domaine du site, de contact : validées par les règles
PAGE = ('<html><body><h1>ACME</h1><p>Écrivez-nous : <a href="mailto:recrutement@{d}">recrutement</a> '
        'ou contact [at] {d}</p></body></html>')
# Adresses douteuses : agence qui a fait le site, messagerie grand public
PAGE_DOUTEUSE = ('<html><body><h1>ACME</h1><p>Site réalisé par Pixel Agence, contact@pixel-agence.fr.</p>'
                 '<p>Pour nous joindre, écrivez au gérant : acme.gerant@gmail.com</p></body></html>')


@pytest.fixture
def sites(monkeypatch, ia):
    """Pages simulées : la page d'accueil de chaque site contient ses adresses
    (PAGE, ou PAGE_DOUTEUSE pour les domaines de sites.douteux)."""
    monkeypatch.setattr(se, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(shared.ia, "time", SimpleNamespace(sleep=lambda s: None, monotonic=time.monotonic))
    monkeypatch.setattr(se, "lire_sitemap", lambda url: [])
    etat = SimpleNamespace(douteux=set())

    def get_page(url, timeout=8):
        domaine = url.split("://", 1)[1].split("/", 1)[0].removeprefix("www.")
        if url.rstrip("/") == f"https://{domaine}":
            return (PAGE_DOUTEUSE if domaine in etat.douteux else PAGE.format(d=domaine)), url
        return None, None

    monkeypatch.setattr(se, "get_page", get_page)
    ia.reponse = '{"valides": ["contact@pixel-agence.fr", "acme.gerant@gmail.com"], "meilleur_contact": null}'
    return etat


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


def test_regles_valident_sans_ia(sites, user_id, ia):
    entreprises, _ = _lancer(user_id, max_scrapees=1)
    e = entreprises["ACME 1"]
    assert set(e["emails_trouves"]) == {"recrutement@acme1.fr", "contact@acme1.fr"}   # mailto et déobfusqué
    assert e["emails_non_valides"] is False and emails_douteux(e) == []
    assert ia.appels == []


def test_douteux_tranches_par_l_ia(sites, user_id, ia):
    sites.douteux = {"acme1.fr"}
    ia.reponse = '{"valides": ["acme.gerant@gmail.com"], "meilleur_contact": "acme.gerant@gmail.com"}'
    entreprises, logs = _lancer(user_id, max_scrapees=1)
    e = entreprises["ACME 1"]
    assert e["emails_trouves"] == ["acme.gerant@gmail.com"] and e["emails_non_valides"] is False
    assert e["meilleur_contact"] == "acme.gerant@gmail.com"
    assert len(ia.appels) == 1 and ia.appels[0]["model"] == "ministral-3:3b"   # un appel pour l'entreprise
    assert "Pixel Agence" in texte_envoye(ia.appels[0])
    assert "contact@pixel-agence.fr (écartée par l'IA" in logs


def test_erreur_passagere_douteux_gardes(sites, user_id, ia):
    sites.douteux = {"acme1.fr"}
    echouer(ia, erreur_http(503))
    entreprises, logs = _lancer(user_id, max_scrapees=1)
    e = entreprises["ACME 1"]
    assert set(e["emails_trouves"]) == set(e["emails_douteux"]) == {"contact@pixel-agence.fr", "acme.gerant@gmail.com"}
    assert e["emails_non_valides"] is True and e["traite"] is True
    assert set(e["contextes_emails"]) == set(e["emails_douteux"])        # gardés pour plus tard
    assert "écrivez au gérant" in e["contextes_emails"]["acme.gerant@gmail.com"]
    assert "non validés" in logs and "Aucun email" not in logs


def test_erreur_bloquante_un_seul_message(sites, user_id, ia):
    sites.douteux = {"acme1.fr", "acme2.fr", "acme3.fr"}
    echouer(ia, erreur_http(404, INTROUVABLE))
    entreprises, logs = _lancer(user_id)
    assert len(ia.demarrages) == 1 and ia.appels == []   # plus d'appel après le refus
    assert logs.count("IA indisponible") == 1
    assert "ollama pull" in logs
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
