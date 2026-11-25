"""D165 : jamais de page ni d'email d'un sous-domaine de préproduction ou de
test ; la même page est cherchée sur le domaine principal."""
import pytest

import shared.validation_emails as ve
import spontanees.lecture_site as L
import spontanees.site_officiel as S
from shared.liens import est_preproduction, sans_preproduction
from tests.faux_web import FauxWeb, brancher, site


@pytest.mark.parametrize("hote, test", [
    ("prepod.fun.luniversitenumerique.fr", True),
    ("preprod.acme.fr", True), ("pre-prod.acme.fr", True), ("staging2.acme.fr", True),
    ("recette-v2.acme.fr", True), ("dev.acme.fr", True), ("qa.acme.fr", True), ("demo.acme.fr", True),
    ("test.acme.fr", True), ("www.test.acme.fr", True),
    ("acme.fr", False), ("www.acme.fr", False), ("test.fr", False),        # le domaine lui-même
    ("developpement.acme.fr", False), ("testeur.acme.fr", False), ("fun.luniversitenumerique.fr", False),
])
def test_sous_domaine_de_preproduction(hote, test):
    assert est_preproduction(hote) is test


def test_meme_page_sur_le_domaine_principal():
    assert sans_preproduction("https://prepod.fun.luniversitenumerique.fr/mentions") == \
        "https://fun.luniversitenumerique.fr/mentions"
    assert sans_preproduction("https://www.staging.acme.fr/contact?a=1") == "https://acme.fr/contact?a=1"
    assert sans_preproduction("https://www.acme.fr/x") == "https://www.acme.fr/x"


def test_candidat_de_preproduction_verifie_sur_le_domaine_principal():
    assert S.racines("https://prepod.fun.luniversitenumerique.fr/") == [
        "https://fun.luniversitenumerique.fr", "https://luniversitenumerique.fr"]


def test_lien_vers_une_preproduction_lu_sur_le_domaine_principal(monkeypatch):
    web = brancher(monkeypatch, FauxWeb(site()))
    web.pages["https://acme.fr"] = '<html><body><a href="https://recette.acme.fr/nous-joindre">Contact</a></body></html>'
    assert L.liens_utiles(web.pages["https://acme.fr"], "https://acme.fr")["contact"] == ["https://acme.fr/nous-joindre"]
    lecteur = L.LecteurSite("https://acme.fr")
    assert lecteur.lire("https://recette.acme.fr/nous-joindre")[0]
    assert not any("recette." in d for d in web.demandes)


def test_redirection_vers_une_preproduction_refusee(monkeypatch):
    web = brancher(monkeypatch, FauxWeb({"https://acme.fr": ("redirection", "https://staging.acme.fr"),
                                         "https://staging.acme.fr": "<html><title>ACME</title></html>"}))
    v = S.verifier("https://acme.fr", {"nom": "ACME", "siren": "123456789"}, S.RECHERCHE)
    assert not v.verifie
    assert web.demandes


def test_email_de_preproduction_ecarte():
    assert ve.classer("contact@preprod.acme.fr", "acme.fr", True) == (ve.ECARTE, "domaine de préproduction ou de test")
    assert ve.classer("contact@acme.fr", "acme.fr", True)[0] == ve.VALIDE
    assert ve.site_verifie({"_extra": {"site_verifie": {"domaine": "prepod.fun.luniversitenumerique.fr"}}}) == \
        "fun.luniversitenumerique.fr"
