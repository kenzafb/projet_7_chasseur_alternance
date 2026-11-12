"""Lettre et PDF (D138) : entreprise inconnue adressée au service
recrutement, même texte dans la page et dans le PDF, mise en page d'une
lettre Word, nom du fichier."""

import re
import shutil
import subprocess

import pytest

from lettres import redaction as generateur
from lettres import pdf

PROFIL = {"prenom": "Hélène", "nom": "Dupont", "email": "helene@exemple.fr", "telephone": "06 12 34 56 78",
          "ville": "Paris", "linkedin": "linkedin.com/in/helene", "portfolio": "https://helene.exemple.fr",
          "lettre_type": generateur.lettre_par_defaut("alternance")}
OFFRE = {"titre": "Alternance Business Analyst", "entreprise": "ACME Conseil", "lieu": "75 - Paris"}
INCONNUE = {**OFFRE, "entreprise": "Inconnue"}


def _texte_html(html: str) -> str:
    """Texte visible du HTML (sans la feuille de style)."""
    html = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    return re.sub(r"<[^>]+>", "\n", html.replace("<br>", "\n"))


# ─── Même texte dans la page et dans le PDF ───────────────────────────────────
@pytest.mark.parametrize("offre", [OFFRE, INCONNUE])
def test_le_pdf_reprend_la_lettre_de_la_page(offre):
    lettre = generateur.assembler_lettre(offre, PROFIL, "Votre projet m'attire.")
    parties = pdf.decouper_lettre(offre, lettre, PROFIL)
    assert parties["destinataire"] == generateur.contact_entreprise(offre)
    assert parties["objet"] == "Objet : Candidature en alternance, Alternance Business Analyst"
    assert parties["date"] == f"Le {generateur.date_du_jour()}"
    assert parties["corps"][0] == "Madame, Monsieur," and parties["autres"] == []
    html = pdf.construire_html(offre, lettre, PROFIL)
    # Chaque paragraphe de la lettre de la page est dans le PDF, une seule fois
    paragraphes_html = re.findall(r"<p[^>]*>(.*?)</p>", html, re.S)
    for paragraphe in re.split(r"\n\s*\n", lettre.strip()):
        assert paragraphes_html.count(pdf._e(paragraphe.strip()).replace("\n", "<br>")) == 1, paragraphe


def test_entreprise_inconnue_meme_formulation_partout():
    lettre = generateur.assembler_lettre(INCONNUE, PROFIL, "P.")
    assert lettre.startswith("À l'attention du service recrutement\n\nLe ")
    assert "rejoindre votre entreprise." in lettre and "Inconnue" not in lettre
    html = pdf.construire_html(INCONNUE, lettre, PROFIL)
    assert html.count("À l&#x27;attention du service recrutement") == 1
    assert "Inconnue" not in html and "{" not in _texte_html(html)


def test_lettre_type_sans_en_tete_le_pdf_l_ajoute():
    """Lettre type qui commence à « Madame, Monsieur » : destinataire, date et
    objet ajoutés, avec les mêmes règles que la page."""
    lettre = "Madame, Monsieur,\n\nTexte de la lettre.\n\nCordialement."
    parties = pdf.decouper_lettre(INCONNUE, lettre, PROFIL)
    assert parties["destinataire"] == "À l'attention du service recrutement"
    assert parties["date"] == f"Paris, le {generateur.date_du_jour()}"
    assert parties["objet"] == "Candidature : Alternance Business Analyst"
    assert pdf.decouper_lettre({"titre": ""}, lettre, {})["objet"] == "Candidature"


def test_aucun_tiret_cadratin_produit():
    for offre in (OFFRE, INCONNUE):
        html = pdf.construire_html(offre, "Madame, Monsieur,\n\nTexte.", PROFIL)
        assert "—" not in html and "–" not in html


# ─── Mise en page Word ────────────────────────────────────────────────────────
def test_mise_en_page():
    html = pdf.construire_html(OFFRE, generateur.assembler_lettre(OFFRE, PROFIL, "P."), PROFIL)
    assert "font-family: 'Carlito', 'Liberation Sans', sans-serif" in html
    assert "font-size: 11pt" in html and "text-align: left" in html
    assert "justify" not in html and not re.search(r"border(-top|-bottom)?\s*:", html)   # aucun trait
    # Coordonnées en haut, puis destinataire, date, objet en gras, corps
    ordre = [html.index(x) for x in ('class="coordonnees"', 'class="destinataire"', 'class="date"',
                                      'class="objet"', 'class="corps"')]
    assert ordre == sorted(ordre)
    assert ".objet { font-size: 11pt; font-weight: bold;" in html and ".destinataire { margin-left: 55%;" in html
    assert "@page { size: A4; margin: 2.5cm; }" in html
    coordonnees = html[html.index('class="coordonnees"'):html.index('class="destinataire"')]
    for valeur in ("Hélène Dupont", "Paris", "06 12 34 56 78", "helene@exemple.fr"):
        assert valeur in coordonnees
    # Ni liens ni portfolio dans l'en-tête, ni ailleurs s'ils ne sont pas écrits dans la lettre (D141)
    for valeur in ("linkedin.com/in/helene", "https://helene.exemple.fr"):
        assert valeur not in html


def test_portfolio_toujours_possible_dans_le_texte():
    profil = {**PROFIL, "lettre_type": "Madame, Monsieur,\n\n{paragraphe}\n\nMon portfolio : {portfolio}"}
    lettre = generateur.assembler_lettre(OFFRE, profil, "P.")
    html = pdf.construire_html(OFFRE, lettre, profil)
    corps = html[html.index('class="corps"'):]
    assert "Mon portfolio : https://helene.exemple.fr" in corps
    assert "https://helene.exemple.fr" not in html[:html.index('class="corps"')]


# ─── Nom du fichier ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("offre,attendu", [
    (OFFRE, "Lettre_de_motivation_Hélène_Dupont_ACME_Conseil.pdf"),
    (INCONNUE, "Lettre_de_motivation_Hélène_Dupont.pdf"),
    ({**OFFRE, "entreprise": ""}, "Lettre_de_motivation_Hélène_Dupont.pdf"),
    ({**OFFRE, "entreprise": "../../etc/passwd"}, "Lettre_de_motivation_Hélène_Dupont_etc_passwd.pdf"),
])
def test_nom_du_fichier(offre, attendu):
    assert pdf.nom_telechargement(offre, PROFIL) == attendu


# ─── Vrai PDF ─────────────────────────────────────────────────────────────────
def test_pdf_genere(tmp_path):
    lettre = generateur.assembler_lettre(INCONNUE, PROFIL, "Votre projet de plateforme m'attire.")
    relatif = pdf.generer_pdf_lettre(INCONNUE, lettre, PROFIL, 1, dossier_output=tmp_path)
    contenu = (tmp_path / relatif).read_bytes()
    assert contenu.startswith(b"%PDF")
    installee = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout \
        if shutil.which("fc-list") else ""
    if re.search(r"^Carlito$", installee, re.M) and shutil.which("pdffonts"):
        polices = subprocess.run(["pdffonts", str(tmp_path / relatif)], capture_output=True, text=True).stdout
        assert "+Carlito " in polices and "+Carlito-Bold" in polices   # embarquées (sous-ensembles)
    if shutil.which("pdftotext"):
        # Objet en gras de même taille que le corps : même hauteur de ligne
        boites = subprocess.run(["pdftotext", "-bbox", str(tmp_path / relatif), "-"],
                                capture_output=True, text=True).stdout
        hauteur = {mot: float(y2) - float(y1) for y1, y2, mot in
                   re.findall(r'yMin="([\d.]+)" xMax="[\d.]+" yMax="([\d.]+)">([^<]+)<', boites)}
        assert abs(hauteur["Objet"] - hauteur["Madame,"]) < 0.01
    if shutil.which("pdftotext"):
        texte = subprocess.run(["pdftotext", "-layout", str(tmp_path / relatif), "-"],
                               capture_output=True, text=True).stdout
        assert "À l'attention du service recrutement" in texte and "Inconnue" not in texte
        assert texte.index("Hélène Dupont") < texte.index("service recrutement") < texte.index("Objet :")
