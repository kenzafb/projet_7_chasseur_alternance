"""
spontanees/site_officiel.py
===========================
Identification du site d'une entreprise (phase 15, D160), avant toute
lecture d'email :

  1. sources, dans l'ordre : site fourni par La Bonne Alternance, site de
     l'entreprise dans une offre France Travail (même nom), puis recherche
     web ; un site déjà en base n'est repris que s'il vient de l'une de ces
     sources ou a déjà été vérifié ;
  2. domaines interdits (annuaires, registres, agrégateurs, réseaux
     sociaux, emploi : shared/referentiels/domaines_interdits.txt) : jamais
     candidats ;
  3. un candidat n'est retenu que si son accueil ou ses mentions légales
     (obligatoires en France) portent le SIREN de l'entreprise (seul, dans
     un SIRET ou dans le numéro de TVA), ou à défaut son nom dans le titre du
     site ou dans les mentions légales ; sinon « site non vérifié » et aucun
     email n'est gardé.

La lecture des pages passe par spontanees/lecture_site.py (robots.txt,
plafond de pages) ; les pages lues pour vérifier servent ensuite au scraper.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from shared.liens import est_preproduction, sans_preproduction
from spontanees import lecture_site as L

FICHIER_INTERDITS = Path(__file__).resolve().parent.parent / "shared" / "referentiels" / "domaines_interdits.txt"

LBA, FRANCE_TRAVAIL, RECHERCHE, VERIFIE = "lba", "france_travail", "recherche", "deja_verifie"
SOURCES = {LBA: "La Bonne Alternance", FRANCE_TRAVAIL: "offre France Travail", RECHERCHE: "recherche web",
           VERIFIE: "site déjà vérifié"}
PREUVES = {"siren": "SIREN", "siret": "SIRET", "tva": "numéro de TVA", "nom_titre": "nom dans le titre du site",
           "nom_mentions": "nom dans les mentions légales"}
MAX_CANDIDATS_RECHERCHE = 4      # domaines de la recherche web essayés au plus

# Formes juridiques et mots trop généraux pour prouver un nom
FORMES = {"sa", "sas", "sasu", "sarl", "eurl", "sci", "scop", "snc", "gie", "selarl", "selas", "scp", "sem",
          "spl", "scic", "earl", "gaec", "ste", "societe", "ets", "etablissements", "cie", "et", "compagnie"}
GENERIQUES = {"groupe", "group", "france", "services", "service", "solutions", "informatique", "conseil",
              "consulting", "technologies", "technology", "international", "systemes", "systems", "digital",
              "numerique", "paris", "agence", "centre", "association", "entreprise", "holding", "partners",
              "management", "developpement", "production", "distribution", "the", "les", "des", "aux", "pour",
              "sur", "ville", "office", "national", "nationale", "institut"}


def simplifier(texte) -> str:
    """Minuscules, sans accents, ponctuation en espaces."""
    texte = unicodedata.normalize("NFKD", str(texte or "")).replace("’", "'")
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texte).split())


def nom_normalise(nom: str) -> str:
    """Nom sans parenthèses ni forme juridique (« The Body Shop ( France ) SAS » -> « the body shop france »)."""
    nom = re.sub(r"\(.*?\)", " ", str(nom or ""))
    return " ".join(m for m in simplifier(nom).split() if m not in FORMES)


def variantes_du_nom(entreprise: dict) -> list[str]:
    """Noms qui prouvent le site : nom commercial et raison sociale, avec et
    sans le contenu des parenthèses et les mots généraux de fin (« France »).
    Seulement ceux qui ont un mot distinctif d'au moins 4 lettres (« LE JU »,
    « 1964 » ne prouvent rien : SIREN exigé)."""
    noms = [entreprise.get("nom_commercial"), entreprise.get("nom"), entreprise.get("raison_sociale"),
            (entreprise.get("_extra") or {}).get("nom")]
    out = []
    for nom in filter(None, noms):
        for v in (nom_normalise(nom), simplifier(re.sub(r"\(.*?\)", " ", nom))):
            mots = v.split()
            while mots and mots[-1] in GENERIQUES | FORMES:
                mots = mots[:-1]
            for x in (v, " ".join(mots)):
                if x and x not in out and any(len(m) >= 4 and m not in GENERIQUES and not m.isdigit()
                                              for m in x.split()):
                    out.append(x)
    return out


# ─── Domaines interdits ───────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def domaines_interdits() -> frozenset:
    lignes = FICHIER_INTERDITS.read_text(encoding="utf-8").splitlines()
    return frozenset(x.split("#", 1)[0].strip().lower() for x in lignes if x.split("#", 1)[0].strip())


def domaine_interdit(domaine_ou_url: str) -> bool:
    d = L.domaine(domaine_ou_url) if "/" in (domaine_ou_url or "") else (domaine_ou_url or "").lower()
    d = d.removeprefix("www.")
    parties = d.split(".")
    return any(".".join(parties[i:]) in domaines_interdits() for i in range(len(parties) - 1))


def racines(url: str) -> list[str]:
    """Accueil(s) à vérifier pour une URL : celui de son domaine, puis celui
    du domaine parent pour un sous-domaine (support.lexmark.com -> lexmark.com).
    Jamais un sous-domaine de préproduction ou de test : la même adresse sur
    le domaine principal à la place (D165)."""
    p = urlparse(sans_preproduction(url if "://" in url else "https://" + url))
    if not p.netloc:
        return []
    out = [f"{p.scheme or 'https'}://{p.netloc}"]
    hote = p.netloc.lower().removeprefix("www.")
    parties = hote.split(".")
    if len(parties) > 2:
        out.append(f"https://{'.'.join(parties[-2:])}")
    return out


# ─── Preuves ──────────────────────────────────────────────────────────────────
_NUMEROS = re.compile(r"\d(?:[   .\-]?\d){8,13}")


def preuve_siren(texte: str, siren: str) -> str | None:
    """« siren », « siret » ou « tva » si le texte porte le SIREN, None sinon."""
    siren = re.sub(r"\D", "", siren or "")
    if len(siren) != 9:
        return None
    for m in _NUMEROS.finditer(texte or ""):
        chiffres = re.sub(r"\D", "", m.group(0))
        if chiffres == siren:
            return "siren"
        if len(chiffres) == 14 and chiffres.startswith(siren):
            return "siret"
        if len(chiffres) == 11 and chiffres.endswith(siren):
            return "tva"          # FR + clé à 2 chiffres + SIREN
    return None


def nom_present(texte: str, variantes: list[str]) -> str | None:
    t = f" {simplifier(texte)} "
    return next((v for v in variantes if f" {v} " in t), None)


@dataclass
class Verification:
    url: str                          # accueil essayé
    source: str
    verifie: bool = False
    preuve: str | None = None
    detail: str = ""
    lecteur: "L.LecteurSite | None" = None
    pages: dict = field(default_factory=dict)       # url finale -> html, déjà lues

    @property
    def domaine(self) -> str:
        return L.domaine(self.url)

    def resume(self) -> dict:
        return {"url": self.url, "domaine": self.domaine, "source": self.source, "verifie": self.verifie,
                "preuve": self.preuve, "detail": self.detail}


def verifier(url: str, entreprise: dict, source: str, lecteur_cls=L.LecteurSite) -> Verification:
    """Vérifie un accueil : SIREN dans l'accueil ou les mentions légales,
    sinon nom dans le titre ou les mentions légales."""
    v = Verification(url=url, source=source)
    if domaine_interdit(url):
        v.detail = "domaine interdit (annuaire ou agrégateur)"
        return v
    v.lecteur = lecteur = lecteur_cls(url)
    html, finale = lecteur.lire(url)
    if not html:
        v.detail = ("accueil interdit par robots.txt" if lecteur.interdites else
                    f"accueil illisible ({lecteur.lues[-1][1] if lecteur.lues else 'rien lu'})")
        return v
    finale = finale or url
    if est_preproduction(L.domaine(finale)):
        v.detail = f"redirigé vers un sous-domaine de préproduction ({L.domaine(finale)})"
        return v
    if not L.meme_site(finale, url) and domaine_interdit(finale):
        v.detail = f"redirigé vers un domaine interdit ({L.domaine(finale)})"
        return v
    v.pages[finale] = html
    liens = L.liens_utiles(html, finale)
    mentions = liens["mentions"] or L.liens_du_sitemap(lecteur)["mentions"]
    textes = {"accueil": L.texte_de(html)}
    for lien in mentions[:2]:
        h, f = lecteur.lire(lien)
        if h:
            v.pages[f or lien] = h
            textes["mentions"] = textes.get("mentions", "") + "\n" + L.texte_de(h)
            if preuve_siren(textes["mentions"], entreprise.get("siren") or ""):
                break
    siren = entreprise.get("siren") or ((entreprise.get("_extra") or {}).get("siret") or "")[:9]
    for ou, texte in textes.items():
        if p := preuve_siren(texte, siren):
            v.verifie, v.preuve, v.detail = True, p, f"{PREUVES[p]} {siren} dans {'les mentions légales' if ou == 'mentions' else 'l’accueil'}"
            return v
    variantes = variantes_du_nom(entreprise)
    if n := nom_present(L.titre_de(html), variantes):
        v.verifie, v.preuve, v.detail = True, "nom_titre", f"« {n} » dans le titre du site"
    elif "mentions" in textes and (n := nom_present(textes["mentions"], variantes)):
        v.verifie, v.preuve, v.detail = True, "nom_mentions", f"« {n} » dans les mentions légales"
    else:
        v.detail = ("ni SIREN ni nom dans l'accueil et les mentions légales" if "mentions" in textes
                    else "ni SIREN dans l'accueil ni nom dans le titre, pas de lien vers des mentions légales")
    return v


# ─── Candidats ────────────────────────────────────────────────────────────────
def site_lba(entreprise: dict) -> str:
    """Site fourni par La Bonne Alternance (workplace.website), vide sinon."""
    extra = entreprise.get("_extra") or {}
    return str((extra.get("lba") or {}).get("site_web") or "").strip()


def site_deja_verifie(entreprise: dict) -> str:
    """URL du site vérifié lors d'un passage précédent ({"verifie": False} : aucun)."""
    v = (entreprise.get("_extra") or {}).get("site_verifie") or {}
    return str(v.get("url") or "") if v.get("verifie", True) else ""


def candidats(entreprise: dict, sites_france_travail: dict, recherche=None):
    """(url, source) dans l'ordre : déjà vérifié, LBA, France Travail, recherche web (générateur)."""
    vus = set()

    def nouveau(url):
        d = L.domaine(url if "://" in url else "https://" + url)
        if not d or d in vus:
            return False
        vus.add(d)
        return True

    for url, source in ((site_deja_verifie(entreprise), VERIFIE), (site_lba(entreprise), LBA)):
        if url and nouveau(url):
            yield (url if "://" in url else "https://" + url), source
    for nom in {nom_normalise(entreprise.get(c) or "") for c in ("nom_commercial", "nom")} - {""}:
        for url in sites_france_travail.get(nom, []):
            if nouveau(url):
                yield url, FRANCE_TRAVAIL
    if recherche:
        essayes = 0
        for url in recherche(entreprise):
            if essayes >= MAX_CANDIDATS_RECHERCHE:
                return
            if not domaine_interdit(url) and nouveau(url):
                essayes += 1
                yield url, RECHERCHE


def identifier(entreprise: dict, sites_france_travail: dict | None = None, recherche=None,
               lecteur_cls=L.LecteurSite, log=None) -> tuple[Verification | None, list[dict]]:
    """(vérification retenue ou None, toutes les vérifications essayées)."""
    essais = []
    for url, source in candidats(entreprise, sites_france_travail or {}, recherche):
        for racine in racines(url):
            if domaine_interdit(racine):
                continue
            v = verifier(racine, entreprise, source, lecteur_cls)
            essais.append(v.resume())
            if log:
                log(f"    {'✔' if v.verifie else '✗'} {racine} ({SOURCES[source]}) : {v.detail}")
            if v.verifie:
                return v, essais
    return None, essais
