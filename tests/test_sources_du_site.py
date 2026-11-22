"""Étape 3, A1 et A2 : site de l'export LBA par SIREN (D166), autres noms de
Sirene (sigle, dénominations usuelles, enseignes) pour chercher et prouver
le site (D167)."""
import spontanees.noms_entreprise as N
import spontanees.site_officiel as S
from offres import export_lba as X
from tests.faux_web import FauxWeb, brancher, site


def test_sites_de_l_export_par_siren(monkeypatch):
    objets = [{"identifier": {"partner_label": "Hellowork"},
               "workplace": {"siret": "12345678900011", "website": "https://acme.fr"}},
              {"identifier": {"partner_label": "x"}, "workplace": {"siret": "98765432100011", "website": "javascript:x"}}]
    X.construire(iter(objets))
    assert X.sites_par_siren() == {"123456789": "https://acme.fr"}


def test_site_lba_par_siren_en_premier(monkeypatch):
    web = brancher(monkeypatch, FauxWeb(site()))
    e = {"nom": "ACME", "siren": "123456789"}
    v, essais = S.identifier(e, {}, None, sites_export={"123456789": "https://acme.fr"})
    assert v.source == S.LBA and v.url == "https://acme.fr"
    assert web.demandes


def test_autres_noms_de_sirene():
    ul = {"sigleUniteLegale": "TIDF", "denominationUsuelle1UniteLegale": "Toshiba Ile-de-France"}
    assert N.depuis_sirene(ul, {"enseigne1Etablissement": "TOSHIBA TEC", "denominationUsuelleEtablissement": None}) == [
        "TIDF", "Toshiba Ile-de-France", "TOSHIBA TEC"]


def test_autres_noms_prouvent_le_site(monkeypatch):
    brancher(monkeypatch, FauxWeb(site(nom="Toshiba Ile-de-France", siren_dans_mentions=False)))
    e = {"nom": "TIDF", "siren": "123456789", "autres_noms": ["Toshiba Ile-de-France"]}
    assert "toshiba ile de france" in S.variantes_du_nom(e)
    assert S.verifier("https://acme.fr", e, S.RECHERCHE).preuve == "nom_titre"


def test_annuaire_lu_une_fois():
    class Rep:
        status_code = 200

        def json(self):
            return {"results": [{"siren": "123456789", "sigle": "AC", "nom_complet": "ACME SA (ACME SERVICES)",
                                 "siege": {"nom_commercial": "ACME", "liste_enseignes": ["ACME PARIS"]}}]}
    appels = []
    http = type("H", (), {"get": staticmethod(lambda url, **k: appels.append(k["params"]["q"]) or Rep())})
    assert N.depuis_annuaire("123456789", http) == ["AC", "ACME", "ACME PARIS", "ACME SERVICES"]
    assert appels == ["123456789"]                   # seul le SIREN est envoyé
    assert N.completer({"siren": "123456789", "_extra": {"autres_noms": ["X"]}}) == ["X"]   # déjà connus
    e = {"siren": "123456789"}
    assert N.completer(e) == [] and "autres_noms" not in e   # annuaire injoignable : redemandé plus tard
