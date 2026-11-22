"""Site d'une entreprise (phase 15) : identification et vérification (D160),
lecture par les liens réels, robots.txt, plafond de pages, formulaires
(D161)."""

import pytest

import spontanees.lecture_site as L
import spontanees.site_officiel as S
from tests.faux_web import FauxWeb, brancher, site

ACME = {"nom": "ACME", "nom_commercial": "ACME", "siren": "123456789"}


@pytest.fixture
def web(monkeypatch):
    return brancher(monkeypatch, FauxWeb())


# ─── Preuves ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("texte, preuve", [
    ("RCS Paris 123 456 789", "siren"),
    ("SIREN : 123456789", "siren"),
    ("Siret 123 456 789 00012", "siret"),
    ("TVA intracommunautaire FR 12 123456789", "tva"),
    ("SIREN 123.456.789", "siren"),
    ("Tél. 01 23 45 67 89", None),
    ("RCS Paris 987 654 321", None),
    ("1234567890", None),                       # dix chiffres : pas un SIREN
])
def test_preuve_siren(texte, preuve):
    assert S.preuve_siren(texte, "123456789") == preuve


@pytest.mark.parametrize("entreprise, attendues", [
    ({"nom": "THE BODY SHOP ( FRANCE )"}, ["the body shop"]),           # parenthèses retirées
    ({"nom": "PENTALOG FRANCE"}, ["pentalog france", "pentalog"]),
    ({"nom": "LE JU"}, []),                     # aucun mot distinctif : SIREN exigé
    ({"nom": "1964"}, []),
    ({"nom": "DAM'S"}, []),
    ({"nom": "SARL Dupuis Plomberie"}, ["dupuis plomberie", "sarl dupuis plomberie"]),
])
def test_variantes_du_nom(entreprise, attendues):
    assert S.variantes_du_nom(entreprise) == attendues


@pytest.mark.parametrize("url, interdit", [
    ("https://companyfrance.fr/fr/130021256/x", True),
    ("https://www.societe.com/societe/acme", True),
    ("https://gnius.esante.gouv.fr/fr/x", True),
    ("https://annonces-legales.liberation.fr/annonces", True),
    ("https://fr.linkedin.com/company/acme", True),
    ("https://www.pagesjaunes.fr/pros/1", True),
    ("https://acme.fr", False),
    ("https://www.esante.gouv.fr", False),      # seul le sous-domaine gnius est interdit
    ("https://liberation.fr", False),
])
def test_domaines_interdits(url, interdit):
    assert S.domaine_interdit(url) is interdit


def test_racines_d_un_sous_domaine():
    assert S.racines("https://support.lexmark.com/fr/page") == ["https://support.lexmark.com", "https://lexmark.com"]
    assert S.racines("https://www.acme.fr/a/b") == ["https://www.acme.fr"]


# ─── Vérification ─────────────────────────────────────────────────────────────
def test_verifie_par_le_siren_des_mentions_legales(web):
    web.pages.update(site(titre="Bienvenue"))
    v = S.verifier("https://acme.fr", ACME, S.RECHERCHE)
    assert v.verifie and v.preuve == "siren" and "mentions légales" in v.detail
    assert set(v.pages) == {"https://acme.fr", "https://acme.fr/infos/mentions-legales"}


ACME_ROBOTIQUE = {"nom": "ACME ROBOTIQUE", "nom_commercial": "ACME ROBOTIQUE", "siren": "123456789"}


def test_verifie_par_le_nom_dans_le_titre(web):
    web.pages.update(site(nom="Acme Robotique", siren_dans_mentions=False))
    v = S.verifier("https://acme.fr", ACME_ROBOTIQUE, S.RECHERCHE)
    assert v.verifie and v.preuve == "nom_titre"


def test_verifie_par_le_nom_dans_les_mentions(web):
    web.pages.update(site(nom="Acme Robotique", titre="Accueil", siren_dans_mentions=False))
    v = S.verifier("https://acme.fr", ACME_ROBOTIQUE, S.RECHERCHE)
    assert v.verifie and v.preuve == "nom_mentions"


def test_non_verifie_sans_siren_ni_nom(web):
    web.pages.update(site(nom="Autre Société", titre="Restaurant Bora Bora", siren="987654321"))
    v = S.verifier("https://acme.fr", ACME_ROBOTIQUE, S.RECHERCHE)
    assert not v.verifie and "ni SIREN ni nom" in v.detail


@pytest.mark.parametrize("nom", ["FERMAT", "BELLON SA", "ITHIS", "ACME"])
def test_nom_d_un_seul_mot_exige_le_siren(web, nom):
    """D172 : Fermat, Bellon, Ithis avaient été retenus sur leur seul nom dans un titre."""
    web.pages.update(site(nom=nom.title(), siren_dans_mentions=False))
    v = S.verifier("https://acme.fr", {"nom": nom, "siren": "123456789"}, S.RECHERCHE)
    assert not v.verifie and "SIREN exigé" in v.detail
    web.pages.update(site(nom=nom.title()))
    assert S.verifier("https://acme.fr", {"nom": nom, "siren": "123456789"}, S.RECHERCHE).preuve == "siren"


def test_interdits_ecartes_avant_de_compter(web):
    """D171 : les domaines interdits ne prennent pas de place parmi les 8 candidats."""
    def recherche(e):
        for i in range(20):
            yield f"https://www.doctrine.fr/{i}"
        for i in range(12):
            yield f"https://candidat{i}.fr"
    _, essais = S.identifier({"nom": "LE JU"}, {}, recherche)
    assert [x["url"] for x in essais] == [f"https://candidat{i}.fr" for i in range(8)]


def test_nom_ambigu_exige_le_siren(web):
    """« LE JU » dans un titre ne prouve rien : sans SIREN, non vérifié."""
    web.pages.update(site(nom="LE JU", siren_dans_mentions=False))
    v = S.verifier("https://acme.fr", {"nom": "LE JU", "siren": "123456789"}, S.RECHERCHE)
    assert not v.verifie
    web.pages.update(site(nom="LE JU"))
    assert S.verifier("https://acme.fr", {"nom": "LE JU", "siren": "123456789"}, S.RECHERCHE).verifie


def test_domaine_interdit_jamais_lu(web):
    v = S.verifier("https://www.societe.com", ACME, S.RECHERCHE)
    assert not v.verifie and "interdit" in v.detail and web.demandes == []


# ─── Ordre des sources ────────────────────────────────────────────────────────
def test_sources_dans_l_ordre(web):
    web.pages.update(site(racine="https://recherche-acme.fr"))
    web.pages.update(site(racine="https://acme-ft.fr"))
    entreprise = {**ACME, "_extra": {"lba": {"site_web": "https://acme-lba.fr"}}}
    recherches = []

    def recherche(e):
        recherches.append(e["nom"])
        yield "https://www.societe.com/acme"          # interdit : jamais essayé
        yield "https://recherche-acme.fr/page"

    # LBA d'abord (illisible ici), puis l'offre France Travail, vérifiée : pas de recherche web
    v, essais = S.identifier(entreprise, {"acme": ["https://acme-ft.fr"]}, recherche)
    assert v.source == S.FRANCE_TRAVAIL and [e["source"] for e in essais] == [S.LBA, S.FRANCE_TRAVAIL]
    assert recherches == []
    # Sans offre : la recherche web, le domaine interdit sauté
    v, essais = S.identifier(entreprise, {}, recherche)
    assert v.source == S.RECHERCHE and v.url == "https://recherche-acme.fr"
    assert [e["url"] for e in essais] == ["https://acme-lba.fr", "https://recherche-acme.fr"]


def test_au_plus_huit_domaines_de_la_recherche(web):
    def recherche(e):
        for i in range(10):
            yield f"https://faux{i}.fr"
    v, essais = S.identifier(ACME, {}, recherche)
    assert v is None and len(essais) == S.MAX_CANDIDATS_RECHERCHE


def test_site_deja_verifie_repris_d_abord(web):
    web.pages.update(site())
    entreprise = {**ACME, "_extra": {"site_verifie": {"url": "https://acme.fr", "domaine": "acme.fr"}}}
    v, _ = S.identifier(entreprise, {}, lambda e: iter(["https://autre.fr"]))
    assert v.source == S.VERIFIE and v.url == "https://acme.fr"


# ─── Lecture du site ──────────────────────────────────────────────────────────
def test_robots_txt_respecte(web):
    web.pages.update(site())
    web.robots["https://acme.fr"] = "User-agent: *\nDisallow: /infos/\n"
    lecteur = L.LecteurSite("https://acme.fr")
    assert lecteur.lire("https://acme.fr")[0]
    assert lecteur.lire("https://acme.fr/infos/mentions-legales") == (None, None)
    assert lecteur.interdites == ["https://acme.fr/infos/mentions-legales"]
    assert "https://acme.fr/infos/mentions-legales" not in web.demandes


@pytest.mark.parametrize("statut, permis", [(403, True), (401, True), (404, True), (503, False)])
def test_robots_selon_la_rfc_9309(web, statut, permis):
    """4xx : robots.txt indisponible, tout est permis ; 5xx : rien (RFC 9309)."""
    web.pages.update(site())
    web.robots["https://acme.fr"] = statut
    lecteur = L.LecteurSite("https://acme.fr")
    assert bool(lecteur.lire("https://acme.fr")[0]) is permis
    assert (web.demandes_de("https://acme.fr") != []) is permis


def test_robots_injoignable_rien_n_est_lu(web):
    web.erreurs.add("https://acme.fr/robots.txt")
    web.pages.update(site())
    lecteur = L.LecteurSite("https://acme.fr")
    assert lecteur.lire("https://acme.fr") == (None, None) and lecteur.robots.startswith("injoignable")


def test_robots_absent_tout_permis(web):
    web.pages.update(site())
    lecteur = L.LecteurSite("https://acme.fr")
    assert lecteur.lire("https://acme.fr")[0] and lecteur.robots == "absent (404)"


def test_plafond_de_pages(web):
    liens = "".join(f'<a href="/contact-{i}">Contact {i}</a>' for i in range(20))
    web.pages["https://acme.fr"] = f"<html><body>{liens}</body></html>"
    for i in range(20):
        web.pages[f"https://acme.fr/contact-{i}"] = "<html><body>x</body></html>"
    lecteur = L.LecteurSite("https://acme.fr", max_pages=3)
    lus = [u for u in [f"https://acme.fr/contact-{i}" for i in range(20)] if lecteur.lire(u)[0]]
    assert len(lus) == 3 and lecteur.reste == 0


def test_liens_reels_et_categories():
    html = ('<a href="/infos/mentions-legales">Mentions légales</a><a href="/nous-joindre">Contact</a>'
            '<a href="https://acme.fr/jobs/">Nous rejoindre</a><a href="/qui-sommes-nous">Qui sommes-nous</a>'
            '<a href="https://autre.fr/contact">Contact partenaire</a><a href="/plaquette.pdf">Contact (PDF)</a>'
            '<a href="mailto:x@acme.fr">écrire</a>')
    liens = L.liens_utiles(html, "https://acme.fr")
    assert liens == {"mentions": ["https://acme.fr/infos/mentions-legales"], "contact": ["https://acme.fr/nous-joindre"],
                     "recrutement": ["https://acme.fr/jobs/"], "a_propos": ["https://acme.fr/qui-sommes-nous"]}


def test_liens_du_sitemap(web):
    web.pages["https://acme.fr/sitemap.xml"] = ("<urlset><url><loc>https://acme.fr/carrieres</loc></url>"
                                                "<url><loc>https://acme.fr/produits</loc></url></urlset>")
    lecteur = L.LecteurSite("https://acme.fr")
    assert L.liens_du_sitemap(lecteur)["recrutement"] == ["https://acme.fr/carrieres"]


@pytest.mark.parametrize("html, attendu", [
    ('<form action="/envoi"><input type="email"><textarea></textarea></form>', 1),
    ('<form><input type="file" name="cv"></form>', 1),
    ('<form role="search"><input name="q"><textarea></textarea></form>', 0),
    ('<form class="newsletter"><input type="email"></form>', 0),
    ('<form><input type="password"><textarea></textarea></form>', 0),
    ('<form><input type="email"></form>', 0),          # inscription seule
])
def test_formulaires(html, attendu):
    assert len(L.formulaires(f"<html><body>{html}</body></html>", "https://acme.fr/contact")) == attendu


@pytest.mark.parametrize("resultat, pertinent", [
    ({"href": "https://www.neurones.net/fr", "title": "Accueil", "body": ""}, True),          # domaine
    ({"href": "https://groupe-n.fr", "title": "Neurones, conseil et services", "body": ""}, True),   # titre
    ({"href": "https://x.fr", "title": "Fiche", "body": "SIREN 331 408 336"}, True),            # SIREN
    ({"href": "https://www.roblox.com", "title": "Roblox", "body": "Play games"}, False),
])
def test_resultat_de_recherche_pertinent(resultat, pertinent):
    import spontanees.recherche_emails as se
    e = {"nom": "NEURONES", "nom_commercial": "NEURONES", "siren": "331408336"}
    assert se.resultat_pertinent(resultat, e, se.analyser_nom("NEURONES")) is pertinent
