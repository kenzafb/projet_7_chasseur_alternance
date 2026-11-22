"""Entreprises des candidatures spontanées : résultats du scraper conservés
(bug 5), 5 dernières candidatures par date (bug 13), contact_rh normalisé
partout de la même façon (bug 14)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

import spontanees.recherche_emails as scraper_emails
from shared import config
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


# ─── Bug 5 : le scraper garde site, page scrapée, source ; site vérifié (D160) ─
def _resultat(verification, emails=("rh@acme.fr",), contact=None, formulaires=()):
    return {"emails": list(emails), "telephones": ["01 23 45 67 89"], "contact_rh": contact,
            "url_finale": verification.url + "/contact", "formulaires": list(formulaires)}


def _identifier(url, source="recherche"):
    """identifier() simulé : site vérifié url."""
    from spontanees.site_officiel import Verification

    def faux(e, sites, recherche=None, log=None, **_):
        if url is None:
            return None, [{"url": "https://faux.fr", "source": source, "verifie": False, "detail": "ni SIREN ni nom"}]
        v = Verification(url=url, source=source, verifie=True, preuve="siren", detail="SIREN dans les mentions légales")
        return v, [v.resume()]
    return faux


def test_scraper_conserve_site_page_et_source(user_id, monkeypatch):
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}])
    monkeypatch.setattr(scraper_emails, "identifier", _identifier("https://acme.fr"))
    monkeypatch.setattr(scraper_emails, "scraper_et_extraire", lambda v, nom, dirigeant=None, **_: _resultat(v))
    scraper_emails.main(user_id, log_fn=lambda m: None)

    e = lire_entreprises(user_id)[0]
    assert e["site_web"] == "https://acme.fr"
    assert e["url_scrapee"] == "https://acme.fr/contact"
    assert e["source_recherche"] == "recherche"
    assert e["site_verifie"]["domaine"] == "acme.fr" and e["site_verifie"]["preuve"] == "siren"
    assert e["emails_trouves"] == ["rh@acme.fr"] and e["traite"] is True


def test_site_non_verifie_rien_garde(user_id, monkeypatch):
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}])
    monkeypatch.setattr(scraper_emails, "identifier", _identifier(None))
    monkeypatch.setattr(scraper_emails, "scraper_et_extraire", lambda *a, **k: pytest.fail("rien à lire"))
    logs = []
    scraper_emails.main(user_id, log_fn=logs.append)
    e = lire_entreprises(user_id)[0]
    assert e["emails_trouves"] == [] and e["traite"] is True and e["site_verifie"]["verifie"] is False
    assert any("Site non vérifié" in m for m in logs)
    from database.entreprises_db import calculer_stats
    assert calculer_stats(user_id)["prochaines"][0]["site_non_verifie"] is True
    js = (config.STATIC_DIR / "js" / "spontanees.js").read_text(encoding="utf-8")
    assert "Site non vérifié" in js and "formulaire de contact" in js


def test_formulaire_de_contact_enregistre(user_id, monkeypatch, utilisateur):
    """Sans email, le formulaire de contact du site vérifié est gardé et montré (D161)."""
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}])
    formulaire = {"page": "https://acme.fr/contact", "action": "https://acme.fr/envoi", "candidature": False}
    monkeypatch.setattr(scraper_emails, "identifier", _identifier("https://acme.fr"))
    monkeypatch.setattr(scraper_emails, "scraper_et_extraire", lambda v, nom, dirigeant=None, **_: _resultat(
        v, emails=(), formulaires=[formulaire]))
    scraper_emails.main(user_id, log_fn=lambda m: None)
    assert lire_entreprises(user_id)[0]["formulaires_contact"] == [formulaire]
    from database.entreprises_db import calculer_stats
    prochaine = calculer_stats(user_id)["prochaines"][0]
    assert prochaine["formulaire"] == "https://acme.fr/contact" and prochaine["site"] == "https://acme.fr"


def test_site_deja_verifie_reutilise_sans_nouvelle_recherche(user_id, monkeypatch):
    """Le site vérifié enregistré sert au lancement suivant : plus de recherche web."""
    from tests.faux_web import FauxWeb, brancher, site
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME", "siren": "123456789"}])
    liste = lire_entreprises(user_id)
    liste[0]["site_verifie"] = {"url": "https://acme.fr", "domaine": "acme.fr", "preuve": "siren"}
    sauvegarder_enrichissement(user_id, liste)
    brancher(monkeypatch, FauxWeb(site()))
    monkeypatch.setattr(scraper_emails, "urls_recherche", lambda e: pytest.fail("recherche du site inutile"))
    scraper_emails.main(user_id, log_fn=lambda m: None)
    e = lire_entreprises(user_id)[0]
    assert e["source_recherche"] == "deja_verifie" and e["emails_trouves"] == ["contact@acme.fr"]


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
    monkeypatch.setattr(scraper_emails, "identifier", _identifier("https://acme.fr"))
    monkeypatch.setattr(scraper_emails, "scraper_et_extraire", lambda v, nom, dirigeant=None, **_: _resultat(
        v, contact=[{"prenom": "Ana", "nom": "Lopez", "poste": "DRH"}]))
    scraper_emails.main(user_id, log_fn=lambda m: None)
    assert _brut(user_id, "contact_rh") == ["Ana Lopez (DRH)"]
