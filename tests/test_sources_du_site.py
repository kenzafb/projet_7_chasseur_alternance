"""Étape 3, A1 et A2 : site de l'export LBA par SIREN (D166), autres noms de
Sirene (sigle, dénominations usuelles, enseignes) pour chercher et prouver
le site (D167)."""
import pytest

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
    # Le .fr de chaque forme d'abord (D215)
    assert S.domaines_devines({"nom": "PUCE ET PLUME"}) == [
        "https://puceplume.fr", "https://puce-plume.fr", "https://puceplume.com", "https://puceplume.eu",
        "https://puceplume.io", "https://puce-plume.com", "https://puce-plume.eu", "https://puce-plume.io"]
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


# ─── D217 : numéro et indice ôtés, jamais la première lettre de la voie ──────
@pytest.mark.parametrize("adresse, voie", [
    ("85 BOULEVARD DU MONTPARNASSE", "BOULEVARD DU MONTPARNASSE"),
    ("85 BIS BOULEVARD DU MONTPARNASSE", "BOULEVARD DU MONTPARNASSE"),
    ("85 B BOULEVARD DU MONTPARNASSE", "BOULEVARD DU MONTPARNASSE"),
    ("85BIS BOULEVARD DU MONTPARNASSE", "BOULEVARD DU MONTPARNASSE"),
    ("12 TER RUE BELLINI", "RUE BELLINI"),
    ("12 ter rue Bellini", "rue Bellini"),
    ("3 T AVENUE DE SUFFREN", "AVENUE DE SUFFREN"),
    ("10 BD DES BOUVETS", "BD DES BOUVETS"),
    ("7 TERRASSE BELLINI", "TERRASSE BELLINI"),
    ("41 RUE DU CAPITAINE GUYNEMER", "RUE DU CAPITAINE GUYNEMER"),
    ("TERRASSE BELLINI", "TERRASSE BELLINI"),
])
def test_voie_sans_numero_ni_indice(adresse, voie):
    assert S.adresses_connues({"_extra": {"adresse": adresse}}) == [{"code_postal": "", "voie": voie}]


def test_voie_en_boulevard_reconnue_sur_le_site(monkeypatch):
    brancher(monkeypatch, FauxWeb(_site_sans_siren("https://murex.com", "Murex", "85 boulevard du Montparnasse, Paris")))
    e = {"nom": "MUREX", "siren": "123456789", "code_postal": "75999", "_extra": {"adresse": "85 BOULEVARD DU MONTPARNASSE"}}
    v = S.verifier("https://murex.com", e, S.DEVINE)
    assert v.preuve == "domaine_adresse" and "boulevard du montparnasse" in v.detail


# ─── D215 : le .fr d'abord ────────────────────────────────────────────────────
KONICA = {"nom": "KONICA MINOLTA BUSINESS SOLUTIONS FRANCE", "nom_commercial": "KONICA MINOLTA BUSINESS SOLUTIONS FRANCE",
          "siren": "123456789", "autres_noms": ["KONICA MINOLTA"]}


def test_fr_du_nom_court_devine_malgre_les_formes_longues():
    devines = S.domaines_devines(KONICA)
    assert "https://konicaminolta.fr" in devines and len(devines) == 8


def test_domaine_en_fr():
    for url, fr in {"https://www.konicaminolta.eu": "konicaminolta.fr", "https://acme.co.uk": "acme.fr",
                    "https://embersgrillandburger.com.au": "embersgrillandburger.fr",
                    "https://inaugurationsage.events.sage.com": "sage.fr", "https://www.acme.fr": "", "https://x.co": "x.fr"}.items():
        assert S.domaine_en_fr(url) == fr


def _eu_et_fr(monkeypatch, **fr):
    pages = site(racine="https://konicaminolta.eu", nom="Konica Minolta", siren_dans_mentions=False)
    if fr:
        pages.update(site(nom="Konica Minolta", **{"racine": "https://konicaminolta.fr", **fr}))
    web = brancher(monkeypatch, FauxWeb(pages))
    monkeypatch.setattr(S, "domaines_devines", lambda e: [])
    return web, S.identifier(KONICA, {}, lambda e: iter(["https://konicaminolta.eu"]), sites_export={})


def test_le_fr_qui_porte_le_siren_est_prefere(monkeypatch):
    _, (v, essais) = _eu_et_fr(monkeypatch, siren_dans_mentions=True)
    assert v.url == "https://konicaminolta.fr" and v.preuve == "siren" and v.source == S.RECHERCHE
    assert [x["domaine"] for x in essais] == ["konicaminolta.eu", "konicaminolta.fr"]


def test_le_fr_sans_siren_n_est_pas_prefere(monkeypatch):
    _, (v, _) = _eu_et_fr(monkeypatch, siren_dans_mentions=False)        # son nom est pourtant dans le titre
    assert v.url == "https://konicaminolta.eu"


def test_le_fr_absent(monkeypatch):
    _, (v, _) = _eu_et_fr(monkeypatch)
    assert v.url == "https://konicaminolta.eu" and v.preuve == "nom_titre"


def test_le_fr_qui_redirige_hors_fr_ne_change_rien(monkeypatch):
    pages = site(racine="https://acme.com", nom="Acme Labo")
    pages["https://acme.fr"] = ("redirection", "https://acme.com")
    brancher(monkeypatch, FauxWeb(pages))
    monkeypatch.setattr(S, "domaines_devines", lambda e: [])
    v, _ = S.identifier({"nom": "ACME LABO", "siren": "123456789"}, {}, lambda e: iter(["https://acme.com"]), sites_export={})
    assert v.url == "https://acme.com" and v.preuve == "siren"


def test_un_fr_deja_essaye_n_est_pas_relu(monkeypatch):
    pages = site(racine="https://konicaminolta.eu", nom="Konica Minolta", siren_dans_mentions=False)
    pages.update(site(racine="https://konicaminolta.fr", nom="Autre", siren_dans_mentions=False, titre="Autre"))
    web = brancher(monkeypatch, FauxWeb(pages))
    monkeypatch.setattr(S, "domaines_devines", lambda e: ["https://konicaminolta.fr"])
    v, _ = S.identifier(KONICA, {}, lambda e: iter(["https://konicaminolta.eu"]), sites_export={})
    assert v.domaine == "konicaminolta.eu" and web.demandes.count("https://konicaminolta.fr") == 1
