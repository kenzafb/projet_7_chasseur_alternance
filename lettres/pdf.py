"""
lettres/pdf.py
===============================
Lettre de motivation -> PDF (WeasyPrint).

Sécurité :
  - tout ce qui vient de l'utilisateur ou de l'IA (lettre, profil, offre)
    est échappé avant d'entrer dans le HTML : une balise tapée dans la lettre
    s'imprime comme du texte, elle n'est jamais interprétée ;
  - le gabarit n'a besoin d'aucune ressource (styles en ligne, polices du
    système, Carlito de préférence : README) : le url_fetcher refuse tout,
    fichier local comme réseau.

Mise en page (D138) : celle d'une lettre Word, et le texte même de la
lettre affichée dans la page (decouper_lettre).

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

from lettres.redaction import contact_entreprise, date_du_jour
from shared import config
from shared.offres import entreprise_connue
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


# Rôles des paragraphes de l'en-tête d'une lettre (avant la formule d'appel)
_APPEL = re.compile(r"^(madame|monsieur|mesdames|bonjour|à qui de droit)\b", re.IGNORECASE)
_OBJET = re.compile(r"^objet\s*:", re.IGNORECASE)
_DATE = re.compile(r"\b\d{1,2}(er)?\s+(" + "|".join(MOIS) + r")\s+\d{4}\b", re.IGNORECASE)

# Police : Carlito (paquet Fedora google-carlito-fonts, mêmes métriques que
# Calibri), installée sur le système et trouvée par fontconfig (aucun fichier
# chargé par le PDF lui-même) ; Liberation Sans à défaut (D141, remplace
# Inter de D138)
POLICES = "'Carlito', 'Liberation Sans', sans-serif"


def _paragraphes(texte: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", (texte or "").strip()) if p.strip()]


def _role(paragraphe: str, destinataire: str) -> str | None:
    """destinataire, date ou objet pour un paragraphe d'en-tête, sinon None."""
    if paragraphe == destinataire:
        return "destinataire"
    if _OBJET.match(paragraphe):
        return "objet"
    if "\n" not in paragraphe and len(paragraphe) <= 80 and _DATE.search(paragraphe):
        return "date"
    return None


def decouper_lettre(offre: dict, lettre: str, profil: dict) -> dict:
    """La lettre telle que la page l'affiche, rangée pour la mise en page :
    {destinataire, autres, date, objet, corps}. Ce que la lettre contient
    est repris tel quel ; ce qui lui manque (lettre type commençant à
    « Madame, Monsieur ») est ajouté avec les mêmes règles que la page :
    destinataire de contact_entreprise (« À l'attention du service
    recrutement » si l'entreprise est inconnue), date du jour, objet
    « Candidature : <intitulé> », en gras (D138)."""
    destinataire = contact_entreprise(offre)
    paras = _paragraphes(lettre)
    fin = next((i for i, p in enumerate(paras) if _APPEL.match(p)), None)
    if fin is None:   # sans formule d'appel : l'en-tête s'arrête au premier paragraphe sans rôle
        fin = next((i for i, p in enumerate(paras) if _role(p, destinataire) is None), len(paras))
    tete, corps = paras[:fin], paras[fin:]
    parties = {"destinataire": None, "date": None, "objet": None, "autres": [], "corps": corps}
    for p in tete:
        role = _role(p, destinataire)
        if role and parties[role] is None:
            parties[role] = p
        else:
            parties["autres"].append(p)
    ville = (profil.get("ville") or "").strip()
    titre = (offre.get("titre") or "").strip()
    parties["destinataire"] = parties["destinataire"] or destinataire
    parties["date"] = parties["date"] or (f"{ville}, le {date_du_jour()}" if ville else f"Le {date_du_jour()}")
    parties["objet"] = parties["objet"] or (f"Candidature : {titre}" if titre else "Candidature")
    return parties


def _bloc(texte: str, classe: str = "") -> str:
    attribut = f' class="{classe}"' if classe else ""
    return f"<p{attribut}>{_e(texte).replace(chr(10), '<br>')}</p>\n"


# Aperçu dans la page (D149) : Carlito livrée dans static/fonts (licence
# OFL), pour un rendu fidèle même sans la police installée ; le PDF, lui,
# prend toujours la police du système
_STYLES_FONTE = (("Regular", 400, "normal"), ("Bold", 700, "normal"), ("Italic", 400, "italic"),
                 ("BoldItalic", 700, "italic"))


def police_web() -> str:
    """CSS de l'aperçu : @font-face de Carlito (URL versionnées), page A4,
    paragraphe surligné."""
    from shared.statique import url_statique
    fontes = "".join(
        f"\n  @font-face {{ font-family: 'Carlito'; src: url('{url_statique(f'fonts/carlito/Carlito-{nom}.ttf')}'); "
        f"font-weight: {graisse}; font-style: {style}; }}" for nom, graisse, style in _STYLES_FONTE)
    return fontes + """
  html { background: #EEF1F0; }
  body { width: 21cm; min-height: 29.7cm; margin: 0 auto; padding: 2.5cm; background: #FFFFFF; }
  .surligne { background: #E3F1EF; box-shadow: 0 0 0 4pt #E3F1EF; border-radius: 2pt; }
"""


def _bloc_apercu(texte: str, surligner: str) -> str:
    """Bloc de l'aperçu : surligné s'il est le paragraphe personnalisé, ou
    paragraphe surligné dans le bloc qui le contient."""
    cible = " ".join((surligner or "").split())
    if not cible:
        return _bloc(texte)
    if " ".join(texte.split()) == cible:
        return _bloc(texte, "surligne")
    bloc = _bloc(texte)
    marque = _e(cible)
    return bloc.replace(marque, f'<span class="surligne">{marque}</span>', 1) if marque in bloc else bloc


def construire_html(offre: dict, lettre: str, profil: dict, apercu: bool = False, surligner: str = "") -> str:
    """HTML de la lettre, mise en page d'une lettre Word (D138, D141) : nom,
    ville, téléphone et email en haut à gauche, destinataire en dessous à
    droite, date puis objet en gras de même taille, corps aligné à gauche,
    Carlito 11 pt. Chaque valeur variable est échappée. apercu : page A4
    dessinée à l'écran avec la police livrée, et le paragraphe surligner
    (s'il est dans la lettre) surligné (D149) ; le PDF ne s'en sert pas."""
    parties = decouper_lettre(offre, lettre, profil)
    nom = " ".join(x for x in ((profil.get("prenom") or "").strip(), (profil.get("nom") or "").strip()) if x)
    # En-tête : nom, ville, téléphone, email seulement (D141) ; liens et
    # portfolio s'écrivent dans le texte de la lettre si on le souhaite
    coordonnees = [(profil.get(c) or "").strip() for c in ("ville", "telephone", "email")]
    lignes = "".join(f"<div>{_e(c)}</div>" for c in coordonnees if c)
    corps = "".join(_bloc_apercu(p, surligner) if apercu else _bloc(p) for p in parties["autres"] + parties["corps"])
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"/>
<style>
  @page {{ size: A4; margin: 2.5cm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: {POLICES}; font-size: 11pt; line-height: 1.3; color: #000; text-align: left; }}
  p {{ margin-bottom: 8pt; }}
  .coordonnees {{ margin-bottom: 18pt; }}
  .coordonnees .nom {{ font-weight: bold; }}
  .destinataire {{ text-align: right; margin-bottom: 18pt; }}
  .objet {{ font-size: 11pt; font-weight: bold; margin-bottom: 14pt; }}{police_web() if apercu else ""}
</style>
</head>
<body>
<div class="coordonnees"><div class="nom">{_e(nom)}</div>{lignes}</div>
{_bloc(parties["destinataire"], "destinataire")}{_bloc(parties["date"], "date")}{_bloc(parties["objet"], "objet")}<div class="corps">
{corps}</div>
</body>
</html>"""


def _pour_nom_de_fichier(texte: str) -> str:
    """Lettres (accents compris), chiffres et tirets ; le reste devient « _ »."""
    texte = unicodedata.normalize("NFC", str(texte or "")).strip()
    return re.sub(r"[^\w-]+", "_", texte).strip("_")


def nom_telechargement(offre: dict, profil: dict) -> str:
    """Lettre_de_motivation_<Prénom>_<Nom>.pdf, suivi de _<Entreprise> si son
    nom est connu (jamais « Inconnue », D138)."""
    parties = [_pour_nom_de_fichier(profil.get("prenom")), _pour_nom_de_fichier(profil.get("nom"))]
    if entreprise_connue(offre):
        parties.append(_pour_nom_de_fichier(offre.get("entreprise"))[:40].strip("_"))
    return "_".join(["Lettre_de_motivation", *[x for x in parties if x]]) + ".pdf"


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
