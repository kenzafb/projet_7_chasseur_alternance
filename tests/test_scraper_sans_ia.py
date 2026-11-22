"""Scraper : emails lus directement dans les pages, triés par les règles
(validés ou écartés d'office), l'IA seulement pour les douteux ; si l'IA
échoue ou est coupée, les douteux restent non validés ; une erreur
bloquante ne donne qu'un message pour tout le lancement."""

import time
from types import SimpleNamespace

import pytest

import shared.ia
import spontanees.recherche_emails as se
from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
from shared.validation_emails import emails_douteux
from tests.faux_web import FauxWeb, brancher
from tests.test_ia import INTROUVABLE, echouer, erreur_http, texte_envoye

# Accueil d'ACME n : titre au nom de l'entreprise, « Acme Robotique N » (deux mots
# distinctifs : un seul ne prouverait rien, D172 ; site vérifié, D160)
# Adresses du domaine du site, de contact : validées par les règles
PAGE = ('<html><head><title>{nom}</title></head><body><h1>ACME</h1><p>Écrivez-nous : '
        '<a href="mailto:recrutement@{d}">recrutement</a> ou contact [at] {d}</p></body></html>')
# Adresses d'un autre domaine (écartée par les règles, D162) et messagerie grand public (douteuse)
PAGE_DOUTEUSE = ('<html><head><title>{nom}</title></head><body><h1>ACME</h1><p>Site réalisé par Pixel Agence, '
                 'contact@pixel-agence.fr.</p><p>Pour nous joindre, écrivez au gérant : acme.gerant@gmail.com</p>'
                 '</body></html>')


@pytest.fixture
def sites(monkeypatch, ia):
    """Sites simulés : l'accueil de acmeN.fr porte le nom « ACME N » et ses
    adresses (PAGE, ou PAGE_DOUTEUSE pour les domaines de sites.douteux) ;
    la recherche web propose acmeN.fr."""
    monkeypatch.setattr(se, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(shared.ia, "time", SimpleNamespace(sleep=lambda s: None, monotonic=time.monotonic))
    etat = SimpleNamespace(douteux=set())

    class Web(FauxWeb):
        def get(self, url, **kw):
            d = url.split("://", 1)[1].split("/", 1)[0].removeprefix("www.")
            self.pages[f"https://{d}"] = (PAGE_DOUTEUSE if d in etat.douteux else PAGE).format(
                d=d, nom=f"ACME Robotique {d[4:-3]}")
            return super().get(url, **kw)

    brancher(monkeypatch, Web())
    monkeypatch.setattr(se, "urls_recherche", lambda e: iter([f"https://acme{e['nom'].split()[-1]}.fr"]))
    import spontanees.site_officiel as S
    monkeypatch.setattr(S, "domaines_devines", lambda e: [])
    ia.reponse = '{"valides": ["acme.gerant@gmail.com"], "meilleur_contact": null}'
    return etat


@pytest.fixture
def user_id(utilisateur):
    uid = utilisateur("a@test.fr", prenom="Alice")[1]
    ajouter_entreprises(uid, [{"siret": f"S{i}", "nom": f"ACME Robotique {i}"} for i in range(1, 4)])
    return uid


def _lancer(user_id, **kw):
    logs = []
    se.main(user_id, log_fn=logs.append, **kw)
    return {e["nom"]: e for e in lire_entreprises(user_id)}, "\n".join(logs)


def test_regles_valident_sans_ia(sites, user_id, ia):
    entreprises, _ = _lancer(user_id, max_scrapees=1)
    e = entreprises["ACME Robotique 1"]
    assert set(e["emails_trouves"]) == {"recrutement@acme1.fr", "contact@acme1.fr"}   # mailto et déobfusqué
    assert e["emails_non_valides"] is False and emails_douteux(e) == []
    assert ia.appels == []


def test_douteux_tranches_par_l_ia(sites, user_id, ia):
    sites.douteux = {"acme1.fr"}
    ia.reponse = '{"valides": ["acme.gerant@gmail.com"], "meilleur_contact": "acme.gerant@gmail.com"}'
    entreprises, logs = _lancer(user_id, max_scrapees=1)
    e = entreprises["ACME Robotique 1"]
    assert e["emails_trouves"] == ["acme.gerant@gmail.com"] and e["emails_non_valides"] is False
    assert e["meilleur_contact"] == "acme.gerant@gmail.com"
    assert len(ia.appels) == 1 and ia.appels[0]["model"] == "ministral-3:3b"   # un appel pour l'entreprise
    assert "écrivez au gérant" in texte_envoye(ia.appels[0])
    assert "contact@pixel-agence.fr (autre domaine que le site vérifié)" in logs   # règles, pas l'IA (D162)
    assert e["site_verifie"]["preuve"] == "nom_titre" and e["site_web"] == "https://acme1.fr"


def test_erreur_passagere_douteux_gardes(sites, user_id, ia):
    sites.douteux = {"acme1.fr"}
    echouer(ia, erreur_http(503))
    entreprises, logs = _lancer(user_id, max_scrapees=1)
    e = entreprises["ACME Robotique 1"]
    assert e["emails_trouves"] == e["emails_douteux"] == ["acme.gerant@gmail.com"]
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
    for nom in ("ACME Robotique 1", "ACME Robotique 2", "ACME Robotique 3"):
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


def test_site_non_verifie_aucun_email(sites, user_id, ia, monkeypatch):
    """Un site sans le SIREN ni le nom de l'entreprise : rien n'est gardé (D160)."""
    monkeypatch.setattr(se, "urls_recherche", lambda e: iter(["https://bora-bora.fr"]))
    import spontanees.site_officiel as S
    monkeypatch.setattr(S, "domaines_devines", lambda e: [])   # sinon acme1.fr, deviné, est le bon (D168)
    entreprises, logs = _lancer(user_id, max_scrapees=1)
    e = entreprises["ACME Robotique 1"]
    assert e["emails_trouves"] == [] and e["traite"] is True and e["site_verifie"]["verifie"] is False
    assert "Site non vérifié" in logs and ia.appels == []
    assert e["_extra"]["essais_site"][0]["url"] == "https://bora-bora.fr"
