"""
scraper_emails.py v4
====================
CHANGELOG v4 :
  - Intégration Gemini (même config que analyseur.py) pour :
      1. Filtrer les faux positifs (favicon, mauvais domaine...)
      2. Extraire email + téléphone + nom du contact RH depuis le HTML
  - Gemini est appelé APRÈS le scraping BS4, seulement si des emails suspects
    sont trouvés OU si aucun email n'est trouvé mais qu'une page contact existe
  - Rate limit gratuit respecté : 1 appel Gemini max par entreprise + pause 4s

Installation : pip install ddgs beautifulsoup4 requests google-genai python-dotenv
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
SAUVEGARDE_TOUS = 20

# ← Passe à False pour désactiver le debug une fois que tout tourne bien
DEBUG = os.getenv("DEBUG_SCRAPER", "false").lower() == "true"

PAUSE_DDG        = (3, 6)
PAUSE_LONGUE_N   = 15
PAUSE_LONGUE     = 45
PAUSE_RATELIMIT  = 90
PAUSE_GEMINI     = 5      # secondes entre chaque appel Gemini (limite gratuite)

# Taille max du HTML envoyé à Gemini (en caractères) — évite de dépasser le contexte
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

_compteur_ddg = 0


# ─── Debug helper ─────────────────────────────────────────────────────────────

def dbg(msg):
    if DEBUG:
        print(f"    [dbg] {msg}")


# ─── Utilitaires ──────────────────────────────────────────────────────────────

def pause_ddg():
    global _compteur_ddg
    _compteur_ddg += 1
    if _compteur_ddg % PAUSE_LONGUE_N == 0:
        print(f"\n  [⏸️  Pause {PAUSE_LONGUE}s — {_compteur_ddg} recherches DDG effectuées]")
        time.sleep(PAUSE_LONGUE)
    else:
        time.sleep(random.uniform(*PAUSE_DDG))


def extraire_domaine(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


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
    # Emails perso : valides mais score très bas
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
        meme   = [e for e in valides if e.split("@")[-1] == domaine_entreprise]
        autres = [e for e in valides if e.split("@")[-1] != domaine_entreprise]
        return meme + autres
    return valides


# ─── Gemini : extraction intelligente ────────────────────────────────────────

def gemini_extraire_contact(texte_page, nom_entreprise, emails_bruts):
    """
    Envoie le texte d'une page contact à Gemini.
    Retourne un dict : {email, telephone, contact_rh, fiable}
    """
    # Tronquer le texte pour ne pas exploser le contexte
    texte_tronque = texte_page[:MAX_HTML_GEMINI]

    emails_str = ", ".join(emails_bruts) if emails_bruts else "aucun trouvé par regex"

    prompt = (
        f"Tu analyses la page de contact/recrutement de l'entreprise '{nom_entreprise}'.\n\n"
        f"Emails détectés par regex (peuvent contenir des faux positifs) : {emails_str}\n\n"
        f"=== CONTENU DE LA PAGE ===\n{texte_tronque}\n\n"
        "=== MISSION ===\n"
        "1. Parmi les emails détectés, garde UNIQUEMENT les vrais emails de contact humains "
        "(recrutement, RH, contact général). Rejette les emails techniques (CDN, images, tracking...).\n"
        "2. Si tu trouves un email de recrutement/RH dans le texte que la regex a manqué, ajoute-le.\n"
        "3. Extrais le numéro de téléphone de l'entreprise si présent (format français de préférence).\n"
        "4. Extrais le nom du contact RH/recruteur si mentionné.\n\n"
        "Réponds UNIQUEMENT en JSON valide, sans backticks, sans texte autour :\n"
        '{"emails": ["contact@example.fr"], "telephone": "01 23 45 67 89", '
        '"contact_rh": "Marie Dupont", "fiable": true}\n\n'
        "Si aucun email valide trouvé : emails = []\n"
        "Si pas de téléphone : telephone = null\n"
        "Si pas de contact nommé : contact_rh = null\n"
        "fiable = false si la page ne semble pas être celle de cette entreprise."
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
        texte = response.text
        texte = re.sub(r'```json\s*', '', texte)
        texte = re.sub(r'```\s*', '', texte)
        result = json.loads(texte)
        dbg(f"Gemini → {result}")
        time.sleep(PAUSE_GEMINI)  # respecter la limite gratuite
        return result
    except Exception as e:
        dbg(f"Gemini erreur : {e}")
        time.sleep(PAUSE_GEMINI)
        return {"emails": emails_bruts, "telephone": None, "contact_rh": None, "fiable": True}


# ─── Analyse du nom d'entreprise ──────────────────────────────────────────────

MOTS_IGNORES = {
    "sa", "sas", "sarl", "eurl", "sasu", "sci", "scop", "holding",
    "groupe", "group", "france", "services", "solutions", "technologies",
    "informatique", "info", "systemes", "systèmes", "consulting",
    "conseil", "tech", "digital", "numerique", "numérique",
    "de", "du", "la", "le", "les", "et", "en", "pour",
    "centre", "association", "societe", "société", "production",
}


def analyser_nom(nom):
    nom_clean = re.sub(r"[^a-z0-9\s]", " ", nom.lower())
    tous_mots = nom_clean.split()
    mots_longs  = [m for m in tous_mots if len(m) >= 4 and m not in MOTS_IGNORES]
    mots_courts = [m for m in tous_mots if 2 <= len(m) <= 3 and m not in MOTS_IGNORES]
    acronymes = re.findall(r'\b([A-Z]{2,6})\b', nom)
    acronyme = acronymes[0].lower() if acronymes else None
    if not acronyme and not mots_longs and mots_courts:
        acronyme = "".join(mots_courts)
    dbg(f"Analyse '{nom}' → mots={mots_longs}, acronyme={acronyme}, courts={mots_courts}")
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


# ─── Requêtes DDG ─────────────────────────────────────────────────────────────

def construire_requetes(entreprise, analyse):
    nom = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    ville = entreprise.get("ville") or ""
    cp = entreprise.get("code_postal") or ""
    dept = cp[:2] if cp else ""
    lieu = f"{ville} {dept}".strip()
    requetes = []
    if analyse["mots"]:
        mots_str = " ".join(analyse["mots"][:3])
        requetes.append(f'"{mots_str}" {lieu} site officiel')
    if analyse["acronyme"]:
        requetes.append(f'"{analyse["acronyme"]}" informatique {lieu} site officiel')
    nom_court = re.sub(r'\s*[\(\;].*', '', nom).strip()
    requetes.append(f'{nom_court} {lieu} recrutement contact')
    dbg(f"Requêtes : {requetes}")
    return requetes


def chercher_site_duckduckgo(entreprise):
    nom = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    analyse = analyser_nom(nom)
    requetes = construire_requetes(entreprise, analyse)
    for i, requete in enumerate(requetes):
        dbg(f"Requête {i+1}/{len(requetes)} : {requete}")
        try:
            pause_ddg()
            with DDGS() as ddg:
                resultats = list(ddg.text(requete, max_results=5))
            dbg(f"  → {len(resultats)} résultats")
            for r in resultats:
                url = r.get("href", "")
                if not url:
                    continue
                valide, raison = est_url_valide(url, nom, analyse)
                dbg(f"  {'✅' if valide else '❌'} {extraire_domaine(url)} — {raison}")
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


# ─── Scraping + Gemini ────────────────────────────────────────────────────────

def get_page(url, timeout=8):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code < 400 and "text/html" in r.headers.get("content-type", ""):
            return r.text, r.url
    except Exception:
        pass
    return None, None


def html_vers_texte(html):
    """Extrait le texte lisible d'une page HTML pour l'envoyer à Gemini."""
    soup = BeautifulSoup(html, "html.parser")
    # Supprimer scripts, styles, nav, footer qui polluent
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def trouver_liens_contact(soup, base_url):
    domaine_base = extraire_domaine(base_url)
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
            if extraire_domaine(lien) == domaine_base:
                liens.add(lien)
    return list(liens)[:6]


def scraper_et_extraire(url_site, nom_entreprise):
    """
    Scrape le site, collecte emails bruts avec BS4,
    puis appelle Gemini pour nettoyer et enrichir.
    Retourne : {emails, telephone, contact_rh, url_finale}
    """
    url_site = url_site.strip().rstrip("/")
    if not url_site.startswith("http"):
        url_site = "https://" + url_site

    domaine = extraire_domaine(url_site)
    tous_emails_bruts = []

    html, url_finale = get_page(url_site)
    if not html:
        alt = url_site.replace("://www.", "://") if "://www." in url_site \
              else url_site.replace("://", "://www.")
        html, url_finale = get_page(alt)

    if not html:
        return {"emails": [], "telephone": None, "contact_rh": None, "url_finale": None}

    soup = BeautifulSoup(html, "html.parser")
    tous_emails_bruts.extend(extraire_emails_html(html, domaine))

    # Trouver les pages contact
    liens = trouver_liens_contact(soup, url_finale or url_site)
    for chemin in PAGES_CONTACT:
        liens.append(urljoin(url_finale or url_site, chemin))

    vus = {url_finale or url_site}
    pages_texte = [html_vers_texte(html)]  # page d'accueil en premier

    for lien in liens[:8]:
        if lien in vus:
            continue
        vus.add(lien)
        time.sleep(random.uniform(0.8, 2.0))
        html_page, _ = get_page(lien)
        if html_page:
            tous_emails_bruts.extend(extraire_emails_html(html_page, domaine))
            # Garder le texte des pages contact pour Gemini
            mots_contact = ["contact", "recrutement", "rh", "emploi", "carriere"]
            if any(m in lien.lower() for m in mots_contact):
                pages_texte.insert(0, html_vers_texte(html_page))  # priorité aux pages contact

    # Dédupliquer les emails bruts
    emails_bruts_uniques = list(set(tous_emails_bruts))
    dbg(f"Emails bruts BS4 : {emails_bruts_uniques}")

    # Texte à envoyer à Gemini : page contact en priorité, sinon accueil
    texte_pour_gemini = "\n\n---\n\n".join(pages_texte[:2])  # max 2 pages

    # Appel Gemini
    dbg("→ Appel Gemini pour extraction intelligente...")
    resultat_gemini = gemini_extraire_contact(texte_pour_gemini, nom_entreprise, emails_bruts_uniques)

    emails_finals = resultat_gemini.get("emails", [])
    # Validation finale : s'assurer que les emails Gemini passent quand même le filtre de base
    emails_finals = [e for e in emails_finals if est_email_valide(e)]
    emails_finals = sorted(emails_finals, key=scorer_email, reverse=True)[:5]

    return {
        "emails": emails_finals,
        "telephone": resultat_gemini.get("telephone"),
        "contact_rh": resultat_gemini.get("contact_rh"),
        "url_finale": url_finale,
        "fiable": resultat_gemini.get("fiable", True),
    }


# ─── Pipeline principal ───────────────────────────────────────────────────────

def charger_entreprises():
    fichier = FICHIER_SORTIE if os.path.exists(FICHIER_SORTIE) else FICHIER_ENTREE
    with open(fichier, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[Chargement] {fichier} → {len(data)} entreprises")
    return data


def sauvegarder(entreprises):
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(entreprises, f, ensure_ascii=False, indent=2)


def main():
    print("=" * 60)
    print("  Chasseur d'Alternance — Scraper Emails v4")
    print(f"  DEBUG = {DEBUG}  |  Gemini = {MODELE_GEMINI}")
    print("=" * 60)

    entreprises = charger_entreprises()
    a_traiter = [e for e in entreprises if not e.get("traite")]
    deja_faits = len(entreprises) - len(a_traiter)
    print(f"[Queue] {len(a_traiter)} à traiter | {deja_faits} déjà traités\n")

    if not a_traiter:
        print("✅ Tout traité ! Lance : python export_excel.py")
        return

    traites_ce_run = 0

    for i, e in enumerate(entreprises):
        if e.get("traite"):
            continue

        nom = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
        idx = deja_faits + traites_ce_run + 1
        print(f"\n[{idx}/{len(entreprises)}] {nom}")

        # Étape 1 : trouver le site
        url = e.get("site_web")
        if not url:
            url = chercher_site_duckduckgo(e)
            if url:
                e["site_web"] = url
                print(f"  🌐 {url}")
            else:
                print(f"  ❌ Site introuvable")
                e["emails_trouves"] = []
                e["telephone"] = None
                e["contact_rh"] = None
                e["traite"] = True
                traites_ce_run += 1
                continue

        # Étape 2 : scraper + Gemini
        resultat = scraper_et_extraire(url, nom)

        # Ignorer si Gemini juge la page non fiable (mauvais site)
        if not resultat.get("fiable", True):
            print(f"  ⚠️  Page non fiable selon Gemini — site ignoré")
            e["site_web"] = None  # reset pour réessayer plus tard si besoin
            e["emails_trouves"] = []
            e["telephone"] = None
            e["contact_rh"] = None
            e["traite"] = True
            traites_ce_run += 1
            continue

        emails    = resultat["emails"]
        telephone = resultat.get("telephone")
        contact   = resultat.get("contact_rh")

        # Affichage résultat
        if emails:
            print(f"  ✅ {', '.join(emails[:3])}")
        else:
            print(f"  ⚠️  Aucun email")
        if telephone:
            print(f"  📞 {telephone}")
        if contact:
            print(f"  👤 {contact}")

        e["emails_trouves"] = emails
        e["telephone"]      = telephone
        e["contact_rh"]     = contact
        e["url_scrapee"]    = resultat.get("url_finale") or url
        e["traite"]         = True
        traites_ce_run += 1

        if traites_ce_run % SAUVEGARDE_TOUS == 0:
            sauvegarder(entreprises)
            avec = sum(1 for x in entreprises if x.get("emails_trouves"))
            print(f"\n  [💾 Sauvegarde — {idx}/{len(entreprises)} | {avec} avec email]\n")

    sauvegarder(entreprises)

    avec_email = sum(1 for e in entreprises if e.get("emails_trouves"))
    avec_tel   = sum(1 for e in entreprises if e.get("telephone"))
    avec_site  = sum(1 for e in entreprises if e.get("site_web"))
    print("\n" + "=" * 60)
    print(f"  Total          : {len(entreprises)}")
    print(f"  Avec site      : {avec_site}")
    print(f"  Avec emails    : {avec_email}")
    print(f"  Avec téléphone : {avec_tel}")
    print(f"  Fichier        : {FICHIER_SORTIE}")
    print("=" * 60)
    print("\n→ Lance : python -m spontanees.export_excel.py")


if __name__ == "__main__":
    main()
