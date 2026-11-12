"""
shared/lba.py
=============
Pages du site La Bonne Alternance où l'on candidate (phase 11, D126 à D131).
Seul endroit qui décide si un lien LBA est fiable : jamais de lien construit
au hasard (D128).

Formats observés :
  - entreprise : https://labonnealternance.apprentissage.beta.gouv.fr/emploi/recruteurs_lba/<SIRET>/<slug>
    (apply.url de l'API, 4148 entreprises sur 4148) ; la page dépend du seul
    SIRET, le slug est indifférent (vérifié avec un slug quelconque).
  - offre : apply.url de l'API, page /emploi/<type>/<identifiant>[/<slug>]
    du même site ; une apply.url hors du site (partenaire) n'est pas une page
    de candidature LBA.
Formulaire de candidature sur la page d'une entreprise : seulement avec un
contact LBA (apply.recipient_id, gardé dans extra.lba.candidature_id) ;
sans, la page dit « Nous n'avons pas de contact pour cette entreprise »
(D127, hypothèse à confirmer avec scripts/verifier_lba.py).
"""

import re
import unicodedata

HOTE = "labonnealternance.apprentissage.beta.gouv.fr"
BASE = f"https://{HOTE}"

# Page d'une offre ou d'une entreprise : /emploi/<type>/<identifiant>, slug facultatif
_PAGE = re.compile(rf"^https://{re.escape(HOTE)}/emploi/[a-z0-9_]+/[A-Za-z0-9_-]+(/[^/?#\s]*)?/?(\?[^\s#]*)?$")
_PAGE_ENTREPRISE = re.compile(rf"^https://{re.escape(HOTE)}/emploi/recruteurs_lba/(\d{{14}})(/[^/?#\s]*)?/?$")
# Ancien repli du scraper quand l'offre n'avait pas d'apply.url : /emploi/<id>,
# format jamais observé (D128) ; ni affiché ni proposé
_LIEN_INVENTE = re.compile(rf"^https://{re.escape(HOTE)}/emploi/[^/?#]*$")


def est_source_lba(source: str) -> bool:
    return "bonne alternance" in (source or "").lower()


def lien_invente(lien: str) -> bool:
    """Lien construit par l'ancien repli (/emploi/<id>), jamais fourni par l'API."""
    return bool(_LIEN_INVENTE.match((lien or "").strip()))


def page_offre(offre: dict) -> str:
    """Page de candidature LBA d'une offre (son apply.url, gardée dans
    « lien »), ou "" si l'offre n'en a pas : autre source, lien hors du site
    LBA (partenaire), ou ancien lien inventé."""
    lien = (offre.get("lien") or "").strip()
    if not est_source_lba(offre.get("source")) or lien_invente(lien):
        return ""
    return lien if _PAGE.match(lien) else ""


def _slug(nom: str) -> str:
    texte = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", texte).strip("-") or "entreprise"


def page_entreprise(siret: str, nom: str, url_api: str = "") -> str:
    """Page LBA d'une entreprise : l'apply.url de l'API si elle a le format
    observé et le même SIRET ; sinon construite d'après ce format, à partir
    d'un SIRET valide (le slug ne compte pas pour le site). "" sans SIRET
    valide. À n'appeler que pour une entreprise trouvée par LBA."""
    siret = re.sub(r"\D", "", siret or "")
    url_api = (url_api or "").strip()
    m = _PAGE_ENTREPRISE.match(url_api)
    if m and (not siret or m.group(1) == siret):
        return url_api
    if len(siret) != 14:
        return ""
    return f"{BASE}/emploi/recruteurs_lba/{siret}/{_slug(nom)}"
