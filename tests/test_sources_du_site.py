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
    brancher(monkeypatch, FauxWeb(site(nom="Toshiba Bureautique", siren_dans_mentions=False)))
    e = {"nom": "TIDF", "siren": "123456789", "autres_noms": ["Toshiba Bureautique"]}
    assert "toshiba bureautique" in S.variantes_du_nom(e)
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


# ─── A3 : domaines devinés (D168) ─────────────────────────────────────────────
def test_domaines_devines():
    # « et » retiré : puceplume.fr, le vrai site de Groupe Puce et Plume
    assert S.domaines_devines({"nom": "PUCE ET PLUME"})[:4] == [
        "https://puceplume.fr", "https://puceplume.com", "https://puceplume.eu", "https://puceplume.io"]
    assert "https://puce-plume.fr" in S.domaines_devines({"nom": "PUCE ET PLUME"})
    assert len(S.domaines_devines({"nom": "GROUPE PUCE ET PLUME SAS", "nom_commercial": "PUCE ET PLUME"})) == 8
    assert S.domaines_devines({"nom": "LE JU"}) == []               # aucun mot distinctif
    assert S.domaines_devines({"nom": "CARTADIS"})[0] == "https://cartadis.fr"


def test_domaine_devine_verifie_avant_la_recherche(monkeypatch):
    brancher(monkeypatch, FauxWeb(site(racine="https://www.cartadis.com", nom="CARTADIS")))
    e = {"nom": "CARTADIS", "siren": "123456789"}
    v, essais = S.identifier(e, {}, lambda e: iter(["https://www.societe.com/x"]), sites_export={})
    assert v.source == S.DEVINE and v.url == "https://www.cartadis.com" and v.preuve == "siren"
    assert all(x["source"] == S.DEVINE for x in essais)            # domaines inexistants non notés


def test_redirection_vers_un_autre_domaine_suivie(monkeypatch):
    """cartadis.fr redirige vers cartadis.com : le site retenu est cartadis.com,
    ses mentions légales sont lues (SIREN), ses emails sont du bon domaine."""
    pages = site(racine="https://www.cartadis.com", nom="CARTADIS")
    pages["https://cartadis.fr"] = ("redirection", "https://www.cartadis.com")
    brancher(monkeypatch, FauxWeb(pages))
    v = S.verifier("https://cartadis.fr", {"nom": "CARTADIS", "siren": "123456789"}, S.DEVINE)
    assert v.verifie and v.preuve == "siren" and v.url == "https://www.cartadis.com" and v.domaine == "cartadis.com"


# ─── D173 : nom d'un seul mot, domaine au nom et adresse sur le site ─────────
def _site_sans_siren(racine, nom, adresse_page):
    pages = site(racine=racine, nom=nom, siren_dans_mentions=False)
    pages[f"{racine}/nous-joindre"] = f"<html><body><h1>Contact</h1><p>{adresse_page}</p></body></html>"
    return pages


def test_domaine_au_nom_et_code_postal(monkeypatch):
    brancher(monkeypatch, FauxWeb(_site_sans_siren("https://www.cartadis.com", "Cartadis",
                                                   "12 avenue du Maréchal Joffre, 94120 Fontenay-sous-Bois")))
    e = {"nom": "CARTADIS", "siren": "123456789", "code_postal": "94120", "_extra": {"adresse": "12 AV DU MARECHAL JOFFRE"}}
    v = S.verifier("https://www.cartadis.com", e, S.DEVINE)
    assert v.verifie and v.preuve == "domaine_adresse" and "94120" in v.detail and "page contact" in v.detail


def test_domaine_au_nom_et_voie_du_siege(monkeypatch):
    brancher(monkeypatch, FauxWeb(_site_sans_siren("https://murex.com", "Murex", "8 rue Bellini, Paris")))
    e = {"nom": "MUREX", "siren": "123456789", "code_postal": "75999",
         "adresse_siege": {"code_postal": "75116", "voie": "RUE BELLINI"}}
    assert S.verifier("https://murex.com", e, S.DEVINE).preuve == "domaine_adresse"


def test_adresse_sans_domaine_au_nom_ne_suffit_pas(monkeypatch):
    """fermat.app : domaine au nom, mais l'adresse de Fermat (92800) n'y est pas."""
    brancher(monkeypatch, FauxWeb(_site_sans_siren("https://www.fermat.app", "Fermat", "Contact : hello@fermat.app")))
    e = {"nom": "FERMAT", "siren": "123456789", "code_postal": "92800", "_extra": {"adresse": "1 RUE DE PUTEAUX"}}
    assert not S.verifier("https://www.fermat.app", e, S.DEVINE).verifie
    # Adresse présente mais domaine différent du nom : refusé
    brancher(monkeypatch, FauxWeb(_site_sans_siren("https://fondation-x.org", "Fermat", "92800 Puteaux")))
    assert not S.verifier("https://fondation-x.org", e, S.RECHERCHE).verifie


def test_domaine_au_nom():
    assert S.domaine_au_nom("https://www.lexmark.com", {"nom": "LEXMARK INTERNATIONAL SAS"})
    assert S.domaine_au_nom("https://wetradelocal.io", {"nom": "WETRADELOCAL"})
    assert not S.domaine_au_nom("https://olympic.fermat.edu.vn", {"nom": "FERMAT"})     # domaine principal : edu
    assert not S.domaine_au_nom("https://fondationpierrebellon.org", {"nom": "BELLON SA"})
