"""Page Ma lettre (D149) : aperçu fidèle au PDF (même HTML, police livrée,
paragraphe surligné), sans rien enregistrer ; le PDF ne change pas."""

from lettres.pdf import construire_html
from shared import config
from tests.test_lettre import PROFIL_COMPLET, ada  # noqa: F401  (fixture)


def test_apercu_avec_le_paragraphe_surligne(ada):  # noqa: F811
    ada.post("/api/profil", json=PROFIL_COMPLET)
    r = ada.post("/api/lettre/apercu", json={"id": "OFFRE-1", "paragraphe": "Mon paragraphe <b>à moi</b>."}).json()
    assert '<span class="surligne">Mon paragraphe &lt;b&gt;à moi&lt;/b&gt;.</span>' in r["html"]
    assert "@font-face" in r["html"] and "/static/fonts/carlito/Carlito-Regular.ttf?v=" in r["html"]
    assert "Mon paragraphe <b>à moi</b>." in r["lettre"]
    assert ada.get("/api/candidatures").json()[0]["lettre"] == ""   # rien d'enregistré


def test_apercu_sans_paragraphe_montre_sa_place(ada):  # noqa: F811
    ada.post("/api/profil", json=PROFIL_COMPLET)
    r = ada.post("/api/lettre/apercu", json={"id": "OFFRE-1", "paragraphe": ""}).json()
    assert '<span class="surligne">[Le paragraphe pour cette offre viendra ici.]</span>' in r["html"]
    assert r["lettre"] == ""


def test_apercu_d_une_lettre_entiere_modifiee(ada):  # noqa: F811
    ada.post("/api/profil", json=PROFIL_COMPLET)
    r = ada.post("/api/lettre/apercu", json={"id": "OFFRE-1", "paragraphe": "P.",
                                              "lettre": "Madame,\n\nLettre réécrite.\n\nP."}).json()
    assert "Lettre réécrite." in r["html"] and '<p class="surligne">P.</p>' in r["html"]


def test_apercu_refuse_sans_lettre_type_ou_offre(ada):  # noqa: F811
    assert ada.post("/api/lettre/apercu", json={"id": "OFFRE-1"}).status_code == 400
    assert ada.post("/api/lettre/apercu", json={"id": "INCONNUE"}).status_code == 404


def test_le_pdf_ne_prend_ni_la_police_livree_ni_le_surlignage():
    offre = {"id": "X", "titre": "Dev", "entreprise": "ACME"}
    profil = {"prenom": "Ada", "nom": "L", "ville": "Paris"}
    pdf = construire_html(offre, "Madame,\n\nP.", profil, surligner="P.")
    assert "@font-face" not in pdf and "surligne" not in pdf


def test_police_livree_avec_sa_licence():
    dossier = config.STATIC_DIR / "fonts" / "carlito"
    for style in ("Regular", "Bold", "Italic", "BoldItalic"):
        assert (dossier / f"Carlito-{style}.ttf").stat().st_size > 100_000
    licence = (dossier / "OFL.txt").read_text(encoding="utf-8")
    assert 'Reserved Font Name "Carlito"' in licence and "SIL OPEN FONT LICENSE Version 1.1" in licence


def test_paragraphe_seul_dans_son_bloc_surligne_en_entier():
    html = construire_html({"id": "X", "titre": "Dev"}, "Madame,\n\nMon   paragraphe.\n\nFin.", {"prenom": "A"},
                           apercu=True, surligner="Mon paragraphe.")
    assert '<p class="surligne">Mon   paragraphe.</p>' in html
