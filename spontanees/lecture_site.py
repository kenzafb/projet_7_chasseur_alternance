"""
spontanees/lecture_site.py
==========================
Lecture d'un site d'entreprise par le scraper (phase 15, D161) :

  - robots.txt respecté (urllib.robotparser), comme le dit la RFC 9309 :
    une page interdite n'est pas demandée ; robots.txt indisponible (4xx,
    403 compris) : tout est permis ; erreur du serveur (5xx) ou site
    injoignable : rien ne l'est ;
  - pages choisies parmi les liens réels de l'accueil et du sitemap
    (contact, mentions légales, recrutement, carrières, à propos), jamais
    devinées (« /contact », « /careers »... donnaient 594 réponses 404 sur
    849 requêtes à l'audit du 22 novembre 2026) ;
  - au plus MAX_PAGES pages HTML par site, accueil compris ;
  - formulaires de contact relevés (moyen de candidature à montrer).

Rien ici ne décide de l'identité du site (spontanees/site_officiel.py) ni de
la validité des adresses (shared/validation_emails.py).
"""

import random
import re
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

MAX_PAGES = 8                  # pages HTML lues par site, accueil compris
MAX_LIENS_SITEMAP = 200        # adresses du sitemap examinées
PAUSE_S = (0.6, 1.5)           # entre deux pages d'un même site
DELAI_S = 8
AGENT = "ChasseurBot"          # nom cherché dans robots.txt (règles « * » sinon)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36 ChasseurBot",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# Pages utiles, par ordre de priorité : mots cherchés dans l'adresse ou le
# texte du lien (minuscules, sans accents)
CATEGORIES = {
    "mentions": ("mentions-legales", "mentions legales", "mentions", "legal-notice", "legal notice", "impressum",
                 "informations legales", "infos legales"),
    "contact": ("contact", "nous-ecrire", "nous ecrire"),
    "recrutement": ("recrutement", "recrute", "carriere", "careers", "career", "emploi", "jobs", "rejoindre",
                    "rejoignez", "join-us", "join us", "talent", "alternance", "stage"),
    "a_propos": ("a-propos", "a propos", "qui-sommes-nous", "qui sommes-nous", "qui sommes nous", "about",
                 "notre-histoire", "societe", "entreprise"),
}
_EXT_NON_HTML = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|odt|zip|rar|jpe?g|png|gif|svg|webp|ico|mp4|mp3|xml|css|js)$")


def _simple(texte: str) -> str:
    import unicodedata
    texte = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in texte if not unicodedata.combining(c)).lower()


def domaine(url: str) -> str:
    return urlparse(url or "").netloc.lower().removeprefix("www.")


def meme_site(url: str, racine: str) -> bool:
    """Même domaine, ou sous-domaine l'un de l'autre (www, fr., carrieres.)."""
    a, b = domaine(url), domaine(racine)
    return bool(a and b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


class LecteurSite:
    """Pages d'un site lues dans la limite de MAX_PAGES, robots.txt respecté.
    Journal : self.lues (url, statut), self.interdites (robots),
    self.erreurs, self.robots (état de robots.txt)."""

    def __init__(self, url: str, max_pages: int | None = None, session=None, pause=None, dormir=None):
        p = urlparse(url if "://" in url else "https://" + url)
        self.racine = f"{p.scheme}://{p.netloc}"
        self.max_pages = MAX_PAGES if max_pages is None else max_pages
        self.http = session or requests
        self.pause = PAUSE_S if pause is None else pause
        self.dormir = dormir or time.sleep
        self.lues, self.interdites, self.erreurs = [], [], []
        self.robots = None
        self._regles = None
        self._vues = set()

    # ── robots.txt ──
    def _charger_robots(self):
        rp = RobotFileParser()
        try:
            r = self.http.get(urljoin(self.racine, "/robots.txt"), headers=HEADERS, timeout=DELAI_S,
                              allow_redirects=True)
        except requests.RequestException as e:
            self.robots = f"injoignable ({type(e).__name__}) : aucune page"
            rp.parse(["User-agent: *", "Disallow: /"])
        else:
            if r.status_code >= 500:
                self.robots = f"erreur du serveur ({r.status_code}) : aucune page"
                rp.parse(["User-agent: *", "Disallow: /"])
            elif r.status_code >= 400:
                self.robots = f"absent ({r.status_code})"
                rp.parse([])
            else:
                self.robots = "lu"
                rp.parse(r.text.splitlines())
        self._regles = rp

    def permis(self, url: str) -> bool:
        if self._regles is None:
            self._charger_robots()
        return self._regles.can_fetch(AGENT, url)

    def sitemaps(self) -> list[str]:
        if self._regles is None:
            self._charger_robots()
        return list(self._regles.site_maps() or [])

    # ── Pages ──
    @property
    def reste(self) -> int:
        return self.max_pages - len(self.lues)

    def lire(self, url: str) -> tuple[str | None, str | None]:
        """(html, url finale) d'une page du site ; (None, None) si hors du
        site, interdite, au-delà du plafond, déjà lue, ou pas du HTML."""
        url = url.split("#")[0]
        if url in self._vues or not meme_site(url, self.racine) or self.reste <= 0:
            return None, None
        self._vues.add(url)
        if not self.permis(url):
            self.interdites.append(url)
            return None, None
        if self.lues:
            self.dormir(random.uniform(*self.pause))
        try:
            r = self.http.get(url, headers=HEADERS, timeout=DELAI_S, allow_redirects=True)
        except requests.RequestException as e:
            self.erreurs.append((url, type(e).__name__))
            self.lues.append((url, type(e).__name__))
            return None, None
        self.lues.append((url, r.status_code))
        if r.status_code >= 400 or "text/html" not in r.headers.get("content-type", ""):
            return None, None
        return r.text, r.url

    def lire_brut(self, url: str) -> str | None:
        """Texte d'un fichier du site (sitemap) : robots respecté, hors plafond de pages HTML."""
        if not meme_site(url, self.racine) or not self.permis(url):
            return None
        try:
            r = self.http.get(url, headers=HEADERS, timeout=DELAI_S, allow_redirects=True)
        except requests.RequestException:
            return None
        return r.text if r.status_code == 200 else None


# ─── Liens utiles ─────────────────────────────────────────────────────────────
def categorie(url: str, texte: str = "") -> str | None:
    """Catégorie d'une page d'après son adresse et le texte du lien, None si aucune."""
    chemin = _simple(urlparse(url).path.replace("_", "-"))
    texte = _simple(texte)
    for cat, mots in CATEGORIES.items():
        if any(m in chemin or (texte and m in texte) for m in mots):
            return cat
    return None


def liens_utiles(html: str, base: str) -> dict[str, list[str]]:
    """{catégorie: [url]} des liens de la page vers le même site, dans l'ordre de la page."""
    soup = BeautifulSoup(html, "html.parser")
    out = {c: [] for c in CATEGORIES}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base, href).split("#")[0]
        if not meme_site(url, base) or _EXT_NON_HTML.search(urlparse(url).path.lower()):
            continue
        cat = categorie(url, a.get_text(" ", strip=True) or a.get("title", ""))
        if cat and url not in out[cat]:
            out[cat].append(url)
    return out


def liens_du_sitemap(lecteur: LecteurSite) -> dict[str, list[str]]:
    """{catégorie: [url]} du sitemap (robots.txt, puis /sitemap.xml), index suivis sur un niveau."""
    out = {c: [] for c in CATEGORIES}
    a_lire = lecteur.sitemaps() or [urljoin(lecteur.racine, "/sitemap.xml")]
    vus = 0
    for i, url in enumerate(a_lire[:5]):
        texte = lecteur.lire_brut(url)
        if not texte:
            continue
        locs = [x.strip() for x in re.findall(r"<loc>\s*(.*?)\s*</loc>", texte, re.IGNORECASE)]
        if "<sitemapindex" in texte.lower() and i == 0:
            a_lire.extend(locs[:4])
            continue
        for loc in locs:
            vus += 1
            if vus > MAX_LIENS_SITEMAP:
                return out
            cat = categorie(loc)
            if cat and meme_site(loc, lecteur.racine) and loc not in out[cat]:
                out[cat].append(loc)
    return out


# ─── Formulaires de contact ───────────────────────────────────────────────────
_MOTS_RECHERCHE = ("search", "recherche", "query", "newsletter", "login", "connexion", "password", "mot de passe")


def formulaires(html: str, url: str) -> list[dict]:
    """Formulaires de contact ou de candidature de la page : un champ de
    message (textarea) ou de fichier, pas une recherche, une connexion ni
    une inscription à une lettre d'information."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for f in soup.find_all("form"):
        attributs = _simple(" ".join(str(v) for v in [f.get("id"), f.get("class"), f.get("action"), f.get("name"),
                                                       f.get("role")] if v))
        champs = f.find_all(["input", "textarea", "select"])
        types = {(c.get("type") or c.name).lower() for c in champs}
        if any(m in attributs for m in _MOTS_RECHERCHE) or "password" in types:
            continue
        if f.find("textarea") or "file" in types:
            out.append({"page": url, "action": urljoin(url, f.get("action") or url),
                        "candidature": "file" in types or categorie(url) == "recrutement"})
    return out


def texte_de(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def titre_de(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    titre = soup.title.get_text(" ", strip=True) if soup.title else ""
    og = soup.find("meta", attrs={"property": "og:site_name"})
    return " ".join(filter(None, [titre, og.get("content", "") if og else ""]))
