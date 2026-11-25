"""Grandes entreprises (D191) : page carrières trouvée sur le site vérifié,
moyen de candidature « Postuler sur leur site carrières », l'absence
d'email n'est pas un échec."""

import pytest

import spontanees.recherche_emails as se
import spontanees.site_officiel as S
from database.connexion import SessionLocal
from database.entreprises_db import ajouter_entreprises, calculer_stats
from database.models import Entreprise
from shared.tailles import grande_entreprise
from tests.faux_web import FauxWeb, brancher, site


@pytest.mark.parametrize("taille, categorie, grande", [
    ("500-999", "", True), ("10000+", "", True), ("1000-1999", "ETI", True), ("41", "", True),
    ("250-499", "ETI", False), ("50-99", "", False), ("", "GE", True), ("", "", False), ("0-0", "", False),
])
def test_grande_entreprise(taille, categorie, grande):
    assert grande_entreprise(taille, categorie) is grande


def test_choix_de_la_page_carrieres():
    assert se.page_carrieres(["https://a.fr/stage", "https://a.fr/nous-rejoindre"]) == "https://a.fr/nous-rejoindre"
    assert se.page_carrieres(["https://a.fr/talents"]) == "https://a.fr/talents"
    assert se.page_carrieres([]) == ""


def test_page_carrieres_lue_sur_le_site(monkeypatch):
    brancher(monkeypatch, FauxWeb(site(recrutement=True, emails=())))
    v = S.verifier("https://acme.fr", {"nom": "ACME", "siren": "123456789"}, S.LBA)
    assert v.verifie
    r = se.scraper_et_extraire(v, "ACME", ia=False)
    assert r["emails"] == [] and r["page_carrieres"] == "https://acme.fr/rejoignez-nous"


def test_servie_seulement_pour_les_grandes(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": "S1", "nom": "Grande SA", "taille": "1000-1999"},
                              {"siret": "S2", "nom": "Petite SARL", "taille": "10-19"}])
    with SessionLocal() as db:
        for e in db.query(Entreprise):
            e.extra = {**e.extra, "page_carrieres": "https://x.fr/carrieres"}
            e.traite = True
        db.commit()
    carrieres = {e["nom"]: e["carrieres"] for e in calculer_stats(uid, "alternance")["prochaines"]}
    assert carrieres == {"Grande SA": "https://x.fr/carrieres", "Petite SARL": ""}


def test_page_onglet_carrieres(utilisateur):
    client, _ = utilisateur("a@test.fr")
    assert 'data-filter="carrieres"' in client.get("/alternance").text
