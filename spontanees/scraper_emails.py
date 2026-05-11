"""
scraper_emails.py v6
====================
Fixes v6 :
  - Remonte toujours à la racine du site si DDG donne une sous-page
    (ex: wel-com.fr/services/ → scrape aussi wel-com.fr)
  - Autorise les sous-domaines du même site parent
    (ex: support.wel-com.fr reconnu comme faisant partie de wel-com.fr)
  - stop_event + log_fn pour intégration Flask
"""

import json
import re
import time
import os
import random
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from ddgs.exceptions import RatelimitException
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ─── Gemini ───────────────────────────────────────────────────────────────────

gemini_client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location="us-central1"
)
MODELE_GEMINI = "gemini-2.5-flash"

# ─── Config ───────────────────────────────────────────────────────────────────

FICHIER_ENTREE  = "data/entreprises_raw.json"
FICHIER_SORTIE  = "data/entreprises_enrichies.json"
SAUVEGARDE_TOUS = 5

DEBUG = os.getenv("DEBUG_SCRAPER", "false").lower() == "true"

PAUSE_DDG        = (3, 6)
PAUSE_LONGUE_N   = 15
PAUSE_LONGUE     = 45
PAUSE_RATELIMIT  = 90
PAUSE_GEMINI     = 5

MAX_HTML_GEMINI  = 8000

PAGES_CONTACT = [
    "/contact", "/contacts", "/nous-contacter",
    "/recrutement", "/recrutements", "/rejoindre-nous",
    "/carrieres", "/carrières", "/careers",
    "/jobs", "/offres", "/nous-rejoindre",
    "/rh", "/equipe", "/about", "/a-propos",
]

PREFIXES_RH      = ["recrutement", "rh", "alternance", "stage", "emploi", "jobs", "career", "cv"]
PREFIXES_CONTACT = ["contact", "info", "accueil", "administration", "bonjour"]

DOMAINES_IGNORES = {
    "example.com", "test.com", "sentry.io", "github.com", "w3.org",
    "google.com", "linkedin.com", "facebook.com", "twitter.com",
    "societe.com", "pappers.fr", "infogreffe.fr", "verif.com",
}

DOMAINES_ANNUAIRES = {
    "societe.com", "pappers.fr", "infogreffe.fr", "verif.com",
    "manageo.fr", "sirene.fr", "annuaire-entreprises.data.gouv.fr",
    "kompass.com", "europages.fr", "linkedin.com", "viadeo.com",
    "leboncoin.fr", "indeed.fr", "welcometothejungle.com",
    "francetravail.fr", "pole-emploi.fr",
    "lefigaro.fr", "ameli.fr", "baidu.com",
    "ecdc.europa.eu", "rs-online.com", "skybet.com",
    "wikipedia.org", "wikimedia.org",
    "youtube.com", "instagram.com", "twitter.com", "facebook.com",
    "association.tel", "pages-jaunes.fr", "pagesjaunes.fr",
    "yelp.com", "tripadvisor.fr", "studyrama.com", "capital.fr",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

MOTS_IGNORES_DOMAINE = {
    "sa", "sas", "sarl", "eurl", "sasu", "sci", "scop", "holding",
    "groupe", "group", "france", "services", "solutions", "technologies",
    "informatique", "info", "systemes", "systèmes", "consulting",
    "conseil", "tech", "digital", "numerique", "numérique",
    "de", "du", "la", "le", "les", "et", "en", "pour",
    "centre", "association", "societe", "société", "production",
}

MOTS_IGNORES_RECHERCHE = {
    "sa", "sas", "sarl", "eurl", "sasu", "sci", "scop", "holding",
    "de", "du", "la", "le", "les", "et", "en", "pour",
}

_compteur_ddg = 0


def dbg(msg):
    if DEBUG:
        print(f"    [dbg] {msg}")


def pause_ddg():
    global _compteur_ddg
    _compteur_ddg += 1
    if _compteur_ddg % PAUSE_LONGUE_N == 0:
        print(f"\n  [⏸️  Pause {PAUSE_LONGUE}s — {_compteur_ddg} recherches DDG]")
        time.sleep(PAUSE_LONGUE)
    else:
        time.sleep(random.uniform(*PAUSE_DDG))


def extraire_domaine(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def domaine_parent(domaine):
    """
    Extrait les deux derniers morceaux du domaine.
    support.wel-com.fr → wel-com.fr
    www.acme.com       → acme.com
    acme.com           → acme.com
    """
    parts = domaine.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return domaine


def meme_site(url1, url2):
    """
    Vérifie si deux URLs appartiennent au même site parent.
    wel-com.fr et support.wel-com.fr → True
    acme.fr et autre.fr              → False
    """
    return domaine_parent(extraire_domaine(url1)) == domaine_parent(extraire_domaine(url2))


def est_email_valide(email):
    email = email.lower().strip()
    if re.search(r'@[\da-f]{4,}\.', email):
        return False
    if re.search(r'\.(png|jpg|jpeg|gif|svg|ico|webp|pdf|zip)$', email):
        return False
    if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
        return False
    domaine = email.split("@")[-1]
    if domaine in DOMAINES_IGNORES:
        return False
    if any(x in email for x in ["noreply", "no-reply", "donotreply", "bounce", "postmaster", "mailer"]):
        return False
    return True


def scorer_email(email):
    local = email.split("@")[0].lower()
    domaine = email.split("@")[-1].lower()
    if domaine in {"gmail.com", "hotmail.com", "hotmail.fr", "yahoo.fr", "yahoo.com", "outlook.com"}:
        return 1
    for i, p in enumerate(PREFIXES_RH):
        if p in local:
            return 100 - i
    for i, p in enumerate(PREFIXES_CONTACT):
        if p in local:
            return 50 - i
    return 10


def extraire_emails_html(html, domaine_entreprise=None):
    emails_texte  = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html)
    emails_mailto = re.findall(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html)
    tous = list(set(e.lower() for e in emails_texte + emails_mailto))
    valides = [e for e in tous if est_email_valide(e)]
    if domaine_entreprise:
        parent = domaine_parent(domaine_entreprise)
        meme   = [e for e in valides if domaine_parent(e.split("@")[-1]) == parent]
        autres = [e for e in valides if domaine_parent(e.split("@")[-1]) != parent]
        return meme + autres
    return valides


def gemini_extraire_contact(texte_page, nom_entreprise, emails_bruts):
    texte_tronque = texte_page[:MAX_HTML_GEMINI]
    emails_str = ", ".join(emails_bruts) if emails_bruts else "aucun trouvé par regex"

    prompt = (
        f"Tu analyses une page web pour trouver les coordonnées de contact de l'entreprise '{nom_entreprise}'.\n\n"
        f"Emails détectés par regex : {emails_str}\n\n"
        f"=== CONTENU DE LA PAGE ===\n{texte_tronque}\n\n"
        "=== MISSION ===\n"
        "1. EMAILS : garde TOUS les emails de contact utiles — recrutement, RH, contact général, "
        "direction, accueil, info. Ne garde que les vrais emails humains. "
        "Rejette uniquement les emails techniques évidents (CDN, tracking, images, noreply, bounce). "
        "Si tu trouves des emails dans le texte que la regex a manqués, ajoute-les. "
        "Objectif : avoir le maximum d'emails valides, même si certains ne sont pas RH.\n\n"
        "2. TELEPHONES : liste TOUS les numéros de téléphone trouvés sur la page.\n\n"
        "3. CONTACT_RH : nom du contact RH ou recruteur si explicitement mentionné, sinon null.\n\n"
        f"4. FIABLE : indique si cette page appartient bien à l'entreprise '{nom_entreprise}'.\n"
        "   fiable = false UNIQUEMENT si le site est clairement un autre secteur ou un annuaire.\n"
        "   En cas de doute, mets fiable = true.\n\n"
        "Réponds UNIQUEMENT en JSON valide, sans backticks :\n"
        '{"emails": ["contact@example.fr"], "telephones": ["01 23 45 67 89"], '
        '"contact_rh": null, "fiable": true}'
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODELE_GEMINI,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Tu es un expert en extraction de données de contact. "
                    "Tu réponds UNIQUEMENT en JSON valide sans backticks."
                ),
                response_mime_type="application/json",
            )
        )
        texte = re.sub(r'```json\s*', '', response.text)
        texte = re.sub(r'```\s*', '', texte)
        result = json.loads(texte)
        dbg(f"Gemini → {result}")
        time.sleep(PAUSE_GEMINI)
        return result
    except Exception as e:
        dbg(f"Gemini erreur : {e}")
        time.sleep(PAUSE_GEMINI)
        return {"emails": emails_bruts, "telephones": [], "contact_rh": None, "fiable": True}


def analyser_nom(nom):
    nom_clean = re.sub(r"[^a-z0-9\s]", " ", nom.lower())
    tous_mots = nom_clean.split()
    mots_longs  = [m for m in tous_mots if len(m) >= 4 and m not in MOTS_IGNORES_DOMAINE]
    mots_courts = [m for m in tous_mots if 2 <= len(m) <= 3 and m not in MOTS_IGNORES_DOMAINE]
    acronymes = re.findall(r'\b([A-Z]{2,6})\b', nom)
    acronyme = acronymes[0].lower() if acronymes else None
    if not acronyme and not mots_longs and mots_courts:
        acronyme = "".join(mots_courts)
    return {"mots": mots_longs, "acronyme": acronyme, "mots_courts": mots_courts}


def domaine_correspond(domaine, analyse):
    domaine_clean = re.sub(r"[^a-z0-9]", "", domaine.lower())
    for mot in analyse["mots"]:
        if mot in domaine_clean:
            return True, f"mot '{mot}' dans domaine"
    if analyse["acronyme"] and analyse["acronyme"] in domaine_clean:
        return True, f"acronyme '{analyse['acronyme']}' dans domaine"
    domaine_sans_tld = domaine_clean.rsplit(".", 1)[0] if "." in domaine_clean else domaine_clean
    for mot in analyse["mots_courts"]:
        if mot == domaine_sans_tld or domaine_sans_tld.startswith(mot):
            return True, f"mot court '{mot}' = début domaine"
    return False, "aucun mot du nom trouvé dans le domaine"


def est_url_valide(url, nom, analyse):
    domaine = extraire_domaine(url)
    if not domaine:
        return False, "URL invalide"
    for annuaire in DOMAINES_ANNUAIRES:
        if annuaire in domaine:
            return False, f"annuaire ({annuaire})"
    tld = domaine.rsplit(".", 1)[-1] if "." in domaine else ""
    if tld in {"cn", "ru", "ua", "in", "br", "mx"}:
        return False, f"TLD suspect ({tld})"
    return domaine_correspond(domaine, analyse)


def construire_requetes(entreprise, analyse):
    nom = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    ville = entreprise.get("ville") or ""
    cp = entreprise.get("code_postal") or ""
    dept = cp[:2] if cp else ""
    lieu = f"{ville} {dept}".strip()

    nom_clean = re.sub(r"[^a-z0-9\s]", " ", nom.lower())
    mots_recherche = [m for m in nom_clean.split() if m not in MOTS_IGNORES_RECHERCHE and len(m) >= 2]
    nom_court = re.sub(r'\s*[\(\;].*', '', nom).strip()

    requetes = []
    if mots_recherche:
        mots_str = " ".join(mots_recherche[:4])
        if len(mots_str) < 5:
            requetes.append(f'{nom_court} {lieu} site officiel')
        else:
            requetes.append(f'"{mots_str}" {lieu} site officiel')
    if analyse["acronyme"]:
        requetes.append(f'"{analyse["acronyme"]}" informatique {lieu} site officiel')
    requetes.append(f'{nom_court} {lieu} recrutement contact')
    return requetes


def chercher_site_duckduckgo(entreprise):
    nom = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    analyse = analyser_nom(nom)
    requetes = construire_requetes(entreprise, analyse)
    for requete in requetes:
        try:
            pause_ddg()
            with DDGS() as ddg:
                resultats = list(ddg.text(requete, max_results=5))
            for r in resultats:
                url = r.get("href", "")
                if not url:
                    continue
                valide, _ = est_url_valide(url, nom, analyse)
                if valide:
                    return url
        except RatelimitException:
            print(f"  [⚠️  Rate limit DDG — attente {PAUSE_RATELIMIT}s...]")
            time.sleep(PAUSE_RATELIMIT)
            try:
                with DDGS() as ddg:
                    resultats = list(ddg.text(requete, max_results=5))
                for r in resultats:
                    url = r.get("href", "")
                    valide, _ = est_url_valide(url, nom, analyse)
                    if url and valide:
                        return url
            except Exception:
                pass
        except Exception as e:
            dbg(f"DDG erreur : {e}")
    return None


def get_page(url, timeout=8):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code < 400 and "text/html" in r.headers.get("content-type", ""):
            return r.text, r.url
    except Exception:
        pass
    return None, None


def html_vers_texte(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def trouver_liens_contact(soup, base_url):
    """
    Trouve les liens de contact dans la page.
    FIX v6 : accepte les sous-domaines du même site parent
    (support.wel-com.fr reconnu comme appartenant à wel-com.fr)
    """
    liens = set()
    mots_cles = ["contact", "recrutement", "carriere", "carrieres", "emploi",
                 "job", "jobs", "rejoindre", "rh", "about", "equipe", "team"]
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        texte = a.get_text(strip=True).lower()
        href_lower = href.lower()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if any(href_lower.endswith(ext) for ext in (".pdf", ".jpg", ".png", ".zip")):
            continue
        if any(m in href_lower for m in mots_cles) or any(m in texte for m in mots_cles):
            lien = urljoin(base_url, href)
            # FIX : meme_site() au lieu de == domaine strict
            if meme_site(lien, base_url):
                liens.add(lien)
    return list(liens)[:6]


def scraper_et_extraire(url_site, nom_entreprise):
    """
    FIX v6 : si DDG a donné une sous-page (ex: /services/),
    on remonte à la racine et on scrape les deux.
    """
    url_site = url_site.strip().rstrip("/")
    if not url_site.startswith("http"):
        url_site = "https://" + url_site

    parsed    = urlparse(url_site)
    url_racine = f"{parsed.scheme}://{parsed.netloc}"
    domaine   = extraire_domaine(url_site)

    tous_emails_bruts = []
    pages_texte       = []

    # ── Scraper la racine EN PREMIER (toujours) ───────────────────────────────
    if url_racine != url_site:
        dbg(f"DDG a donné une sous-page — scrape aussi la racine : {url_racine}")
        html_racine, url_racine_finale = get_page(url_racine)
        if html_racine:
            tous_emails_bruts.extend(extraire_emails_html(html_racine, domaine))
            pages_texte.append(html_vers_texte(html_racine))

    # ── Scraper l'URL donnée par DDG ──────────────────────────────────────────
    html, url_finale = get_page(url_site)
    if not html:
        alt = url_site.replace("://www.", "://") if "://www." in url_site \
              else url_site.replace("://", "://www.")
        html, url_finale = get_page(alt)

    if not html and not pages_texte:
        return {"emails": [], "telephones": [], "contact_rh": None, "url_finale": None, "fiable": True}

    if html:
        soup = BeautifulSoup(html, "html.parser")
        tous_emails_bruts.extend(extraire_emails_html(html, domaine))

        # Liens de contact depuis la page DDG
        base = url_finale or url_site
        liens = trouver_liens_contact(soup, base)
        for chemin in PAGES_CONTACT:
            liens.append(urljoin(url_racine, chemin))  # depuis la racine

        vus = {url_racine, url_site, url_finale or url_site}
        pages_texte.insert(0, html_vers_texte(html))

        for lien in liens[:8]:
            if lien in vus:
                continue
            vus.add(lien)
            time.sleep(random.uniform(0.8, 2.0))
            html_page, _ = get_page(lien)
            if html_page:
                tous_emails_bruts.extend(extraire_emails_html(html_page, domaine))
                mots_contact = ["contact", "recrutement", "rh", "emploi", "carriere"]
                if any(m in lien.lower() for m in mots_contact):
                    pages_texte.insert(0, html_vers_texte(html_page))
    elif pages_texte:
        # Racine scrapée mais URL DDG inaccessible — on continue avec ce qu'on a
        soup = None

    emails_bruts_uniques = list(set(tous_emails_bruts))
    dbg(f"Emails bruts BS4 : {emails_bruts_uniques}")

    texte_pour_gemini = "\n\n---\n\n".join(pages_texte[:2])
    resultat_gemini = gemini_extraire_contact(texte_pour_gemini, nom_entreprise, emails_bruts_uniques)

    emails_finals = resultat_gemini.get("emails", [])
    emails_finals = [e for e in emails_finals if est_email_valide(e)]
    emails_finals = sorted(emails_finals, key=scorer_email, reverse=True)[:5]

    return {
        "emails": emails_finals,
        "telephones": resultat_gemini.get("telephones", []),
        "contact_rh": resultat_gemini.get("contact_rh"),
        "url_finale": url_finale or url_racine,
        "fiable": resultat_gemini.get("fiable", True),
    }


def charger_entreprises():
    fichier = FICHIER_SORTIE if os.path.exists(FICHIER_SORTIE) else FICHIER_ENTREE
    with open(fichier, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[Chargement] {fichier} → {len(data)} entreprises")
    return data


def sauvegarder(entreprises):
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(entreprises, f, ensure_ascii=False, indent=2)


def main(stop_event=None, log_fn=None):
    _log = log_fn or print

    _log(f"Scraper Emails v6 | Gemini = {MODELE_GEMINI}")

    entreprises = charger_entreprises()
    a_traiter = [e for e in entreprises if not e.get("traite")]
    deja_faits = len(entreprises) - len(a_traiter)
    _log(f"Queue : {len(a_traiter)} à traiter | {deja_faits} déjà traités")

    if not a_traiter:
        _log("✅ Tout traité !")
        return

    traites_ce_run = 0

    for e in entreprises:
        if stop_event and stop_event.is_set():
            _log("⏹️  Arrêt — sauvegarde en cours...")
            sauvegarder(entreprises)
            return

        if e.get("traite"):
            continue

        nom = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
        idx = deja_faits + traites_ce_run + 1
        _log(f"[{idx}/{len(entreprises)}] {nom}")

        url = e.get("site_web")
        if not url:
            url = chercher_site_duckduckgo(e)
            if url:
                e["site_web"] = url
                _log(f"  🌐 {url}")
            else:
                _log(f"  ❌ Site introuvable")
                e["emails_trouves"] = []
                e["telephones"]     = []
                e["telephone"]      = None
                e["contact_rh"]     = None
                e["traite"]         = True
                traites_ce_run += 1
                continue

        resultat = scraper_et_extraire(url, nom)

        if not resultat.get("fiable", True):
            tentatives = e.get("tentatives_site", 0)
            if tentatives < 2:
                _log(f"  ⚠️  Site non fiable — retry DDG ({tentatives + 1}/2)")
                e["site_web"] = None
                e["tentatives_site"] = tentatives + 1
                url = chercher_site_duckduckgo(e)
                if url:
                    e["site_web"] = url
                    resultat = scraper_et_extraire(url, nom)
                    if not resultat.get("fiable", True):
                        _log(f"  ❌ Toujours non fiable")
                        e["emails_trouves"] = []; e["telephones"] = []
                        e["telephone"] = None; e["contact_rh"] = None
                        e["traite"] = True; traites_ce_run += 1; continue
                else:
                    _log(f"  ❌ Aucune nouvelle URL")
                    e["emails_trouves"] = []; e["telephones"] = []
                    e["telephone"] = None; e["contact_rh"] = None
                    e["traite"] = True; traites_ce_run += 1; continue
            else:
                _log(f"  ❌ Non fiable après {tentatives} tentatives")
                e["emails_trouves"] = []; e["telephones"] = []
                e["telephone"] = None; e["contact_rh"] = None
                e["traite"] = True; traites_ce_run += 1; continue

        emails     = resultat["emails"]
        telephones = resultat.get("telephones", [])
        contact    = resultat.get("contact_rh")

        if emails:
            _log(f"  ✅ {', '.join(emails[:2])}")
        else:
            _log(f"  ⚠️  Aucun email")

        e["emails_trouves"] = emails
        e["telephones"]     = telephones
        e["telephone"]      = telephones[0] if telephones else None
        e["contact_rh"]     = contact
        e["url_scrapee"]    = resultat.get("url_finale") or url
        e["traite"]         = True
        traites_ce_run += 1

        if traites_ce_run % SAUVEGARDE_TOUS == 0:
            sauvegarder(entreprises)
            avec = sum(1 for x in entreprises if x.get("emails_trouves"))
            _log(f"  💾 Sauvegarde — {idx}/{len(entreprises)} | {avec} avec email")

    sauvegarder(entreprises)
    avec_email = sum(1 for e in entreprises if e.get("emails_trouves"))
    _log(f"✅ Scraping terminé — {avec_email}/{len(entreprises)} avec email")


if __name__ == "__main__":
    main()
