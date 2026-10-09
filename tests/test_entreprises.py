"""Entreprises des candidatures spontanées : résultats du scraper conservés
(bug 5), 5 dernières candidatures par date (bug 13), contact_rh normalisé
partout de la même façon (bug 14)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

import spontanees.scraper_emails as scraper_emails
from database.connexion import SessionLocal
from database.entreprises_db import (ajouter_entreprises, calculer_stats, lire_entreprises,
                                     lire_entreprises_envoyees, normaliser_contact_rh,
                                     sauvegarder_enrichissement, sauvegarder_entreprises)
from database.models import Entreprise


@pytest.fixture
def user_id(utilisateur):
    return utilisateur("a@test.fr", prenom="Alice")[1]


def _brut(user_id, colonne):
    db = SessionLocal()
    try:
        return [getattr(e, colonne) for e in db.query(Entreprise).filter_by(user_id=user_id).order_by(Entreprise.id)]
    finally:
        db.close()


# ─── Bug 5 : le scraper garde site, page scrapée, source et tentatives ───────
def _resultat(url, fiable=True, emails=("rh@acme.fr",), contact=None):
    return {"emails": list(emails), "telephones": ["01 23 45 67 89"], "contact_rh": contact,
            "url_finale": url + "/contact", "fiable": fiable}


def test_scraper_conserve_site_page_et_source(user_id, monkeypatch):
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}])
    monkeypatch.setattr(scraper_emails, "chercher_site", lambda e, url_exclue=None: ("https://acme.fr", "ddg"))
    monkeypatch.setattr(scraper_emails, "scraper_et_extraire", lambda url, nom, dirigeant=None, **_: _resultat(url))
    scraper_emails.main(user_id, log_fn=lambda m: None)

    e = lire_entreprises(user_id)[0]
    assert e["site_web"] == "https://acme.fr"
    assert e["url_scrapee"] == "https://acme.fr/contact"
    assert e["source_recherche"] == "ddg"
    assert e["tentatives_site"] == 0
    assert e["emails_trouves"] == ["rh@acme.fr"] and e["traite"] is True


def test_scraper_conserve_les_tentatives_apres_un_site_non_fiable(user_id, monkeypatch):
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}])
    sites = iter([("https://faux-acme.fr", "ddg"), ("https://acme.fr", "ddg")])
    monkeypatch.setattr(scraper_emails, "chercher_site", lambda e, url_exclue=None: next(sites))
    monkeypatch.setattr(scraper_emails, "scraper_et_extraire",
                        lambda url, nom, dirigeant=None, **_: _resultat(url, fiable="faux" not in url))
    scraper_emails.main(user_id, log_fn=lambda m: None)

    e = lire_entreprises(user_id)[0]
    assert e["site_web"] == "https://acme.fr" and e["tentatives_site"] == 1
    assert e["url_scrapee"] == "https://acme.fr/contact"


def test_site_connu_reutilise_sans_nouvelle_recherche(user_id, monkeypatch):
    """Le site enregistré sert au lancement suivant : plus de recherche DuckDuckGo."""
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}])
    liste = lire_entreprises(user_id)
    liste[0]["site_web"] = "https://acme.fr"
    sauvegarder_enrichissement(user_id, liste)
    monkeypatch.setattr(scraper_emails, "chercher_site",
                        lambda e, url_exclue=None: pytest.fail("recherche du site inutile"))
    monkeypatch.setattr(scraper_emails, "scraper_et_extraire", lambda url, nom, dirigeant=None, **_: _resultat(url))
    scraper_emails.main(user_id, log_fn=lambda m: None)
    assert lire_entreprises(user_id)[0]["source_recherche"] == "existant"


def test_sauvegarde_n_ajoute_pas_de_cles_vides(user_id):
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}])
    avant = _brut(user_id, "extra")[0]
    sauvegarder_enrichissement(user_id, lire_entreprises(user_id))
    assert _brut(user_id, "extra")[0] == avant


def test_envoyeur_ne_perd_pas_les_champs_du_scraper(user_id):
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}])
    liste = lire_entreprises(user_id)
    liste[0].update(site_web="https://acme.fr", url_scrapee="https://acme.fr/contact",
                    source_recherche="ddg", tentatives_site=2)
    sauvegarder_enrichissement(user_id, liste)
    liste = lire_entreprises(user_id)
    liste[0].update(mail_envoye=True, mail_envoye_le=datetime.now(timezone.utc), mail_destinataires=["x@acme.fr"])
    sauvegarder_entreprises(user_id, liste)
    e = lire_entreprises(user_id)[0]
    assert (e["site_web"], e["url_scrapee"], e["source_recherche"], e["tentatives_site"]) == \
           ("https://acme.fr", "https://acme.fr/contact", "ddg", 2)


# ─── Bug 13 : les 5 dernières candidatures par date ─────────────────────────
def test_cinq_dernieres_par_date_d_envoi(user_id):
    ajouter_entreprises(user_id, [{"siret": f"S{i}", "nom": f"Ent {i}", "nom_commercial": f"Ent {i}"}
                                  for i in range(8)])
    base = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)
    # Jours d'envoi volontairement dans le désordre par rapport à l'insertion
    jours = {0: 6, 1: 2, 2: 7, 3: 1, 4: 5, 5: 3, 6: None, 7: 4}
    liste = lire_entreprises(user_id)
    for i, e in enumerate(liste):
        e["mail_envoye"] = True
        e["mail_envoye_le"] = base + timedelta(days=jours[i]) if jours[i] is not None else None
    sauvegarder_entreprises(user_id, liste)

    dernieres = calculer_stats(user_id)["dernieres"]
    assert [d["nom"] for d in dernieres] == ["Ent 2", "Ent 0", "Ent 4", "Ent 7", "Ent 5"]
    assert dernieres[0]["date"] == "2026-10-08 11:00"   # heure de Paris


def test_entreprise_sans_date_en_dernier(user_id):
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "Sans date", "nom_commercial": "Sans date"},
                                  {"siret": "S2", "nom": "Datée", "nom_commercial": "Datée"}])
    liste = lire_entreprises(user_id)
    liste[0]["mail_envoye"] = True
    liste[1].update(mail_envoye=True, mail_envoye_le=datetime(2026, 1, 1, tzinfo=timezone.utc))
    sauvegarder_entreprises(user_id, liste)
    assert [d["nom"] for d in calculer_stats(user_id)["dernieres"]] == ["Datée", "Sans date"]


# ─── Bug 14 : contact_rh normalisé partout ───────────────────────────────────
@pytest.mark.parametrize("valeur, attendu", [
    (None, ""),
    ("", ""),
    ("  Jean   Dupont ", "Jean Dupont"),
    ({"prenom": "Jean", "nom": "Dupont", "poste": "RH"}, "Jean Dupont (RH)"),
    ({"prenom": "Jean", "nom": "Dupont"}, "Jean Dupont"),
    ({"poste": "Responsable RH"}, "Responsable RH"),
    (["Jean Dupont", {"prenom": "Ana", "nom": "Lopez", "poste": "DRH"}], "Jean Dupont, Ana Lopez (DRH)"),
    ([], ""),
    ({}, ""),
    ('{"prenom": "Jean", "nom": "Dupont", "poste": "RH"}', "Jean Dupont (RH)"),   # ancien json.dumps
    ('["Jean Dupont", "Ana Lopez"]', "Jean Dupont, Ana Lopez"),
    ("[pas du json", "[pas du json"),
])
def test_normalisation(valeur, attendu):
    assert normaliser_contact_rh(valeur) == attendu


def test_normalisation_bornee_a_la_colonne():
    assert len(normaliser_contact_rh("x" * 500)) == 200
    assert len(normaliser_contact_rh([f"Nom{i} Prenom{i}" for i in range(50)])) == 200


def test_contact_rh_ecrit_en_texte_lisible(user_id):
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "A"}, {"siret": "S2", "nom": "B"}])
    liste = lire_entreprises(user_id)
    liste[0]["contact_rh"] = {"prenom": "Jean", "nom": "Dupont", "poste": "RH"}
    liste[1]["contact_rh"] = ["Jean Dupont"]
    sauvegarder_enrichissement(user_id, liste)
    assert _brut(user_id, "contact_rh") == ["Jean Dupont (RH)", "Jean Dupont"]


def test_ancien_json_relu_comme_texte(user_id):
    """Les lignes écrites avant la correction (json.dumps) sont lues normalisées."""
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "A"}])
    db = SessionLocal()
    try:
        e = db.query(Entreprise).filter_by(user_id=user_id).one()
        e.contact_rh = json.dumps({"prenom": "Jean", "nom": "Dupont", "poste": "RH"}, ensure_ascii=False)
        e.modes[0].mail_envoye = True
        db.commit()
    finally:
        db.close()
    assert lire_entreprises(user_id)[0]["contact_rh"] == "Jean Dupont (RH)"
    assert lire_entreprises_envoyees(user_id)[0]["contact_rh"] == "Jean Dupont (RH)"


def test_scraper_ecrit_le_contact_normalise(user_id, monkeypatch):
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}])
    monkeypatch.setattr(scraper_emails, "chercher_site", lambda e, url_exclue=None: ("https://acme.fr", "ddg"))
    monkeypatch.setattr(scraper_emails, "scraper_et_extraire", lambda url, nom, dirigeant=None, **_: _resultat(
        url, contact=[{"prenom": "Ana", "nom": "Lopez", "poste": "DRH"}]))
    scraper_emails.main(user_id, log_fn=lambda m: None)
    assert _brut(user_id, "contact_rh") == ["Ana Lopez (DRH)"]
