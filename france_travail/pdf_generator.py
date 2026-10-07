"""
france_travail/pdf_generator.py
===============================
Lettre de motivation -> PDF (WeasyPrint).

Sécurité :
  - tout ce qui vient de l'utilisateur ou de Mistral (lettre, profil, offre)
    est échappé avant d'entrer dans le HTML : une balise tapée dans la lettre
    s'imprime comme du texte, elle n'est jamais interprétée ;
  - le gabarit n'a besoin d'aucune ressource (styles en ligne, polices du
    système) : le url_fetcher refuse tout, fichier local comme réseau.

Rangement : un fichier au nom unique par génération, dans le dossier de
l'utilisateur (LETTRES_PDF_DIR/user_<id>/), donc aucun écrasement entre
homonymes. Le chemin relatif est gardé en base ; le fichier est servi par
une route qui vérifie le propriétaire.
"""

import html
import os
import re
import tempfile
import unicodedata
import uuid
from pathlib import Path

from weasyprint import HTML as WeasyHTML

from database.dates import maintenant_affichage
from shared import config
from shared.erreurs import exiger_profil, CHAMPS_IDENTITE

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


class RessourceInterdite(ValueError):
    """Le PDF a tenté de charger une ressource (image, feuille de style...)."""


def refuser_ressource(url, *args, **kwargs):
    """url_fetcher de WeasyPrint : aucune ressource n'est chargée, ni fichier
    local ni réseau. WeasyPrint ignore la ressource et continue le rendu."""
    raise RessourceInterdite(f"ressource externe refusée : {url[:200]}")


def rendre_pdf(document_html: str, chemin_pdf) -> None:
    """Rend du HTML en PDF sans aucun accès aux fichiers ni au réseau."""
    WeasyHTML(string=document_html, base_url=None,
              url_fetcher=refuser_ressource).write_pdf(chemin_pdf)


def _e(valeur) -> str:
    """Échappe un texte pour l'insérer dans le HTML."""
    return html.escape(str(valeur or ""), quote=True)


def _corps(lettre: str) -> str:
    """Ne garde que le corps de la lettre (à partir de "Madame, Monsieur") :
    l'en-tête (contact entreprise, date, objet) est déjà dans le gabarit,
    l'inclure créerait un doublon."""
    for marqueur in ["Madame, Monsieur", "Madame,\nMonsieur", "Madame"]:
        if marqueur in lettre:
            return lettre[lettre.index(marqueur):]
    # Pas de formule d'appel : on saute les 3 premiers blocs (contact, date, objet)
    return "\n\n".join(lettre.strip().split("\n\n")[3:])


def construire_html(offre: dict, lettre: str, profil: dict) -> str:
    """HTML de la lettre, chaque valeur variable échappée."""
    p = {c: _e(profil.get(c)) for c in ("prenom", "nom", "ville", "telephone", "email", "github")}
    now = maintenant_affichage()
    date_str = f"{now.day} {MOIS[now.month - 1]} {now.year}"
    # Lieu : la ville du profil (rien de codé en dur) ; objet : le titre de l'offre
    lieu_date = f"{p['ville']}, le {date_str}" if p["ville"] else f"Le {date_str}"
    titre = (offre.get("titre") or "").strip()
    objet = f"Candidature — {_e(titre)}" if titre else "Candidature"

    entreprise_brute = offre.get("entreprise", "") or ""
    if entreprise_brute.lower() in ["inconnue", "inconnu", "", "none"]:
        entreprise_affichee = "À l'attention du service recrutement"
    else:
        entreprise_affichee = entreprise_brute

    paragraphes = "".join(
        f"<p>{_e(para.strip()).replace(chr(10), '<br>')}</p>\n"
        for para in _corps(lettre).strip().split("\n\n") if para.strip())

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"/>
<style>
  @page {{ size: A4; margin: 2cm 2cm 2cm 2cm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Helvetica', 'Arial', sans-serif; font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; }}
  .entete {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid #ccc; }}
  .expediteur .nom {{ font-size: 12pt; font-weight: bold; margin-bottom: 4px; }}
  .expediteur .info {{ font-size: 8.5pt; color: #444; line-height: 1.6; }}
  .destinataire {{ text-align: right; }}
  .destinataire .entreprise {{ font-size: 10.5pt; font-weight: bold; margin-bottom: 4px; }}
  .destinataire .info {{ font-size: 8.5pt; color: #444; line-height: 1.6; }}
  .date-lieu {{ text-align: right; font-size: 9.5pt; color: #555; margin-bottom: 16px; }}
  .objet {{ font-size: 10pt; margin-bottom: 20px; }}
  .corps p {{ margin-bottom: 11px; text-align: justify; font-size: 10.5pt; }}
</style>
</head>
<body>
<div class="entete">
  <div class="expediteur">
    <div class="nom">{p['prenom']} {p['nom']}</div>
    <div class="info">{p['ville']}<br>{p['telephone']}<br>{p['email']}<br>{p['github']}</div>
  </div>
  <div class="destinataire">
    <div class="entreprise">{_e(entreprise_affichee)}</div>
    <div class="info">{_e(offre.get("lieu"))}</div>
  </div>
</div>
<div class="date-lieu">{lieu_date}</div>
<div class="objet"><strong>Objet :</strong> {objet}</div>
<div class="corps">{paragraphes}</div>
</body>
</html>"""


def _ascii(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9-]+", "_", texte).strip("_")


def nom_telechargement(offre: dict, profil: dict) -> str:
    """Nom proposé au navigateur : Lettre_Prenom_Nom_Entreprise.pdf (ASCII)."""
    parties = [_ascii(profil.get("prenom")), _ascii(profil.get("nom")),
               _ascii(offre.get("entreprise"))[:40]]
    return "_".join(["Lettre", *[x for x in parties if x]]) + ".pdf"


def generer_pdf_lettre(offre, lettre, profil, user_id: int, dossier_output=None) -> str:
    """Génère le PDF dans le dossier de l'utilisateur, sous un nom unique.
    Retourne son chemin relatif à dossier_output (défaut LETTRES_PDF_DIR),
    à stocker en base : "user_<id>/lettre_<hex>.pdf"."""
    # Profil obligatoire : lève ProfilIncomplet (400) si l'identité manque
    exiger_profil(profil, CHAMPS_IDENTITE)
    racine = Path(dossier_output or config.LETTRES_PDF_DIR)
    relatif = f"user_{int(user_id)}/lettre_{uuid.uuid4().hex}.pdf"
    chemin_pdf = racine / relatif
    chemin_pdf.parent.mkdir(parents=True, exist_ok=True)

    # Écriture dans un fichier temporaire puis renommage : jamais de PDF à moitié écrit
    fd, temporaire = tempfile.mkstemp(dir=chemin_pdf.parent, suffix=".tmp")
    os.close(fd)
    try:
        rendre_pdf(construire_html(offre, lettre, profil), temporaire)
        os.replace(temporaire, chemin_pdf)
    finally:
        if os.path.exists(temporaire):
            os.remove(temporaire)
    return relatif
