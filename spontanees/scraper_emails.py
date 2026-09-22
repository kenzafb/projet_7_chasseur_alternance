"""
scraper_emails.py v15
=====================
Corrections v15 :
  - FIX 9 — Faux positifs déobfuscation : filtre les TLDs non standards
    (He, His, Mr, She, With, In, As, You, The, Will, Here…) qui
    apparaissaient quand la regex "at" attrapait du texte normal comme
    "positions at Alcatel. He..." → positions@Alcatel.He.
  - FIX 10 — Emails inutiles pour le recrutement : dpo@, gdpr@, ir@,
    media@, press@, privacy@, legal@, webmaster@, investor@ sont désormais
    scorés à 0 et exclus du résultat final.
  - FIX 11 — Retry non fiable : si la deuxième recherche DDG retourne la
    même URL que celle qui a échoué, on ne retente pas et on marque
    l'entreprise comme non fiable directement.
  - FIX 12 — Troncature texte Mistral à 2000 chars et HTML contact à
    3000 chars pour éviter les dépassements de rate limit.
  - Tous les correctifs v14 conservés.
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
from mistralai.client import Mistral
from dotenv import load_dotenv

load_dotenv()

# ─── Client Mistral ───────────────────────────────────────────────────────────

mistral_client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
MODELE_MISTRAL = "mistral-large-latest"

# ─── Config ───────────────────────────────────────────────────────────────────

FICHIER_ENTREE  = "/home/kenza/Bureau/chasseur_alternance/data/entreprises_raw.json"
FICHIER_SORTIE  = "/home/kenza/Bureau/chasseur_alternance/data/entreprises_enrichies.json"
SAUVEGARDE_TOUS = 5

DEBUG = os.getenv("DEBUG_SCRAPER", "false").lower() == "true"

PAUSE_DDG        = (3, 6)
PAUSE_LONGUE_N   = 15
PAUSE_LONGUE     = 45
PAUSE_RATELIMIT  = 90
PAUSE_MISTRAL    = 30

PAGES_CONTACT = [
    "/contact", "/contact/",
    "/contacts", "/contacts/",
    "/nous-contacter", "/nous-contacter/",
    "/contactez-nous", "/contactez-nous/",
    "/recrutement", "/recrutement/",
    "/recrutements", "/recrutements/",
    "/rejoindre-nous", "/rejoindre-nous/",
    "/nous-rejoindre", "/nous-rejoindre/",
    "/carrieres", "/carrieres/",
    "/carrières", "/carrières/",
    "/careers", "/careers/",
    "/career", "/career/",
    "/jobs", "/jobs/",
    "/offres", "/offres/",
    "/offres-emploi", "/offres-emploi/",
    "/offres-d-emploi", "/offres-d-emploi/",
    "/rh", "/rh/",
    "/ressources-humaines", "/ressources-humaines/",
    "/equipe", "/equipe/",
    "/team", "/team/",
    "/about", "/about/",
    "/a-propos", "/a-propos/",
    "/qui-sommes-nous", "/qui-sommes-nous/",
    "/apropos", "/apropos/",
    "/footer", "/footer/",
    "/mentions-legales", "/mentions-legales/",
]

PREFIXES_RH      = ["recrutement", "rh", "alternance", "stage", "emploi", "jobs", "career", "cv"]
PREFIXES_CONTACT = ["contact", "info", "accueil", "administration", "bonjour", "hello"]

# FIX 10 — Préfixes d'emails inutiles pour le recrutement
PREFIXES_INUTILES = {
    "dpo", "gdpr", "rgpd", "ir", "media", "press", "privacy",
    "legal", "webmaster", "investor", "relations", "compliance",
}

DOMAINES_IGNORES = {
    "example.com", "test.com", "sentry.io", "github.com", "w3.org",
    "google.com", "linkedin.com", "facebook.com", "twitter.com",
    "societe.com", "pappers.fr", "infogreffe.fr", "verif.com",
}

DOMAINES_ANNUAIRES = {
    # ── Registres légaux / financiers ──────────────────────────────────────
    "societe.com", "pappers.fr", "infogreffe.fr", "verif.com",
    "manageo.fr", "sirene.fr", "annuaire-entreprises.data.gouv.fr",
    "kompass.com", "europages.fr", "infonet.fr", "societe.ninja",
    "dirigeant.fr", "corporama.com", "annuairefrancais.fr",
    "societe-info.com", "bilan-gratuit.fr", "kaspr.io",
    "francebilan.fr",
    "bodacc.fr", "legifrance.gouv.fr", "journal-officiel.gouv.fr",
    "data.gouv.fr", "echanges.dila.gouv.fr",
    "juripresse.fr", "mesinfos.fr", "repreneurs.com",
    "infranat.fr", "annonces-legales.fr", "societe-juridique.fr",
    # ── Réseaux sociaux / pro ───────────────────────────────────────────────
    "linkedin.com", "viadeo.com", "xing.com",
    "youtube.com", "instagram.com", "twitter.com", "facebook.com", "tiktok.com",
    "wikipedia.org", "wikimedia.org",
    # ── Emploi / recrutement ────────────────────────────────────────────────
    "leboncoin.fr", "indeed.fr", "indeed.com", "welcometothejungle.com",
    "francetravail.fr", "pole-emploi.fr", "apec.fr",
    "cadremploi.fr", "meteojob.com", "jobijoba.com", "monster.fr",
    "regionsjob.com", "hellowork.com", "l-expert-comptable.com",
    "studyrama.com", "letudiant.fr", "alternance.emploi.gouv.fr",
    "jobteaser.com", "stagefr.com", "choosemycompany.com",
    "glassdoor.com", "glassdoor.fr", "jobboard.io",
    "optioncarriere.com", "emploi-collectivites.fr",
    "talent.io", "welcomejungle.com",
    # ── Sites éducatifs / formation ─────────────────────────────────────────
    "axamformation.fr", "ecoleinformatiqueinfo.com",
    "polytech-angers.fr", "education.gouv.fr", "onisep.fr",
    # ── Cartographie / annuaires locaux ────────────────────────────────────
    "mappy.com", "mappy.fr", "pages-jaunes.fr", "pagesjaunes.fr",
    "yelp.com", "tripadvisor.fr",
    "annuaire.laposte.fr", "118000.fr", "118712.fr",
    "association.tel", "fr.mappy.com",
    # ── Médias / divers ────────────────────────────────────────────────────
    "lefigaro.fr", "capital.fr", "bfmtv.com", "lemonde.fr",
    "ameli.fr", "baidu.com", "ecdc.europa.eu",
    "rs-online.com", "skybet.com",
    "calameo.com", "hal.science", "pastel.hal.science",
    "scribd.com", "slideshare.net", "issuu.com",
    # ── Sites collectivités / services publics ──────────────────────────────
    "gagny.fr", "ville-sevran.fr", "plainecommune.fr", "seine-et-marne.fr",
    # ── Hébergeurs de blogs / sites génériques ─────────────────────────────
    "blogspot.com", "wordpress.com", "over-blog.com", "overblog.com",
    "wixsite.com", "jimdo.com", "webnode.fr", "e-monsite.com",
    "cataloxy.org", "b2bhint.com", "cylex-locale.fr", "infobel.com",
    "northdata.de", "rubypayeur.com", "entreprises.lefigaro.fr",
    # ── Divers catch-all ────────────────────────────────────────────────────
    "informatique.e-pro.fr",
}

# FIX 9 — TLDs qui ne sont pas de vrais TLDs (mots anglais courants)
# Apparaissent quand la regex "at" attrape du texte normal :
# "positions at Alcatel. He..." → positions@Alcatel.He
FAUX_TLDS = {
    "he", "his", "her", "she", "they", "mr", "ms", "dr",
    "with", "in", "at", "as", "on", "or", "by", "to", "of",
    "you", "the", "and", "for", "are", "was", "will", "here",
    "this", "that", "from", "has", "had", "have", "its",
    "inc", "llc", "ltd", "corp", "plc",  # formes légales sans point
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
    "etude", "etudes",
}

MOTS_IGNORES_RECHERCHE = {
    "sa", "sas", "sarl", "eurl", "sasu", "sci", "scop", "holding",
    "de", "du", "la", "le", "les", "et", "en", "pour",
}

_EXTENSIONS_FICHIERS_NON_HTML = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".rtf", ".csv", ".txt",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".mp4", ".mp3", ".avi", ".mov", ".mkv",
    ".woff", ".woff2", ".ttf", ".eot",
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


# ─── Utilitaires URL / domaine ────────────────────────────────────────────────

def extraire_domaine(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def domaine_parent(domaine):
    parts = domaine.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domaine


def est_sous_domaine(domaine):
    return len(domaine.split(".")) > 2


def meme_site(url1, url2):
    return domaine_parent(extraire_domaine(url1)) == domaine_parent(extraire_domaine(url2))


def est_annuaire(domaine):
    parent = domaine_parent(domaine)
    for annuaire in DOMAINES_ANNUAIRES:
        if annuaire == domaine or annuaire == parent:
            return True
        if domaine.endswith("." + annuaire):
            return True
    return False


# ─── Validation / scoring emails ─────────────────────────────────────────────

def est_email_valide(email):
    email = email.lower().strip()
    if re.search(r'@[\da-f]{4,}\.', email):
        return False
    if re.search(r'\.(png|jpg|jpeg|gif|svg|ico|webp|pdf|zip|woff|ttf|eot)$', email):
        return False
    if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
        return False
    # FIX 9 — rejeter les faux TLDs issus de texte normal déobfusqué
    tld = email.rsplit(".", 1)[-1].lower()
    if tld in FAUX_TLDS:
        dbg(f"Faux TLD rejeté : {email}")
        return False
    domaine = email.split("@")[-1]
    if domaine in DOMAINES_IGNORES or est_annuaire(domaine):
        return False
    if any(x in email for x in ["noreply", "no-reply", "donotreply", "bounce",
                                  "postmaster", "mailer", "daemon", "abuse"]):
        return False
    return True


def scorer_email(email):
    local   = email.split("@")[0].lower()
    domaine = email.split("@")[-1].lower()
    if domaine in {"gmail.com", "hotmail.com", "hotmail.fr", "yahoo.fr", "yahoo.com", "outlook.com"}:
        return 1
    # FIX 10 — emails inutiles pour le recrutement → score 0 (exclus)
    for p in PREFIXES_INUTILES:
        if local == p or local.startswith(p + ".") or local.startswith(p + "-") or local.startswith(p + "_"):
            dbg(f"Email inutile pour recrutement (score 0) : {email}")
            return 0
    for i, p in enumerate(PREFIXES_RH):
        if p in local:
            return 100 - i
    for i, p in enumerate(PREFIXES_CONTACT):
        if p in local:
            return 50 - i
    return 10


# ─── Déobfuscation emails ─────────────────────────────────────────────────────

def decoder_cfemail(encoded):
    try:
        r = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i:i+2], 16) ^ r) for i in range(2, len(encoded), 2))
    except Exception:
        return None


def extraire_emails_cf_protection(html):
    emails = []
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(attrs={"data-cfemail": True}):
        decoded = decoder_cfemail(tag["data-cfemail"])
        if decoded and est_email_valide(decoded):
            emails.append(decoded.lower())
            dbg(f"CF decode: {decoded}")
    for script in soup.find_all("script"):
        for m in re.findall(r'__cf_email__["\s]*:["\s]*"([a-f0-9]+)"', script.get_text()):
            decoded = decoder_cfemail(m)
            if decoded and est_email_valide(decoded):
                emails.append(decoded.lower())
    return emails


def deobfusquer_emails_texte(texte):
    emails = []
    for local, domaine_raw in re.findall(
        r'([a-zA-Z0-9._%+\-]+)\s*(?:\[at\]|\[@\]|\(at\)|\{at\}|\s+at\s+|@)\s*'
        r'([a-zA-Z0-9.\-]+\s*(?:\[dot\]|\(dot\)|\s+dot\s+|\.)\s*[a-zA-Z]{2,})',
        texte, re.IGNORECASE
    ):
        domaine_clean = re.sub(
            r'\s*(?:\[dot\]|\(dot\)|\s+dot\s+)\s*', '.', domaine_raw,
            flags=re.IGNORECASE
        ).strip()
        email = re.sub(r'\s+', '', f"{local.strip()}@{domaine_clean}")
        if est_email_valide(email):
            emails.append(email.lower())
            dbg(f"Déobfus at: {email}")
    for local, domaine in re.findall(
        r'([a-zA-Z0-9._%+\-]+)\s*(?:\[arobase\]|\(arobase\))\s*([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
        texte, re.IGNORECASE
    ):
        email = f"{local.strip()}@{domaine.strip()}"
        if est_email_valide(email):
            emails.append(email.lower())
    return emails


def extraire_emails_html(html, domaine_entreprise=None):
    emails_texte  = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html)
    emails_mailto = re.findall(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html)
    emails_cf     = extraire_emails_cf_protection(html)
    emails_obfs   = deobfusquer_emails_texte(html)
    tous    = list(set(e.lower() for e in emails_texte + emails_mailto + emails_cf + emails_obfs))
    valides = [e for e in tous if est_email_valide(e)]
    if domaine_entreprise:
        parent = domaine_parent(domaine_entreprise)
        meme   = [e for e in valides if domaine_parent(e.split("@")[-1]) == parent]
        autres = [e for e in valides if domaine_parent(e.split("@")[-1]) != parent]
        return meme + autres
    return valides


# ─── Mistral ──────────────────────────────────────────────────────────────────

def mistral_extraire_contact(texte_page, nom_entreprise, emails_bruts,
                              html_contact=None):
    emails_str   = ", ".join(emails_bruts) if emails_bruts else "aucun trouvé par regex"
    html_section = f"\n\n=== HTML BRUT PAGE CONTACT ===\n{html_contact}\n" if html_contact else ""

    prompt = (
        f"Tu analyses le contenu d'une page web pour trouver les coordonnées de '{nom_entreprise}'.\n"
        f"Emails déjà détectés par regex : {emails_str}\n\n"
        "=== CONTENU DE LA PAGE ===\n"
        f"{texte_page}\n"
        f"{html_section}"
        "=== INSTRUCTIONS ===\n"
        "1. EMAILS : tous les emails professionnels utiles (contact, rh, recrutement, info, alternance).\n"
        "   - Cherche aussi les obfuscations : 'contact [at] site.fr', 'info(at)site.fr'.\n"
        "   - Cherche dans les liens mailto: si présents dans le HTML brut.\n"
        "   - Rejette : noreply, postmaster, bounce, emails techniques.\n"
        "   - Si aucun email trouvé dans le contenu → liste vide [] (NE PAS INVENTER).\n\n"
        "2. TELEPHONES : numéros français uniquement (format 01 23 45 67 89 ou +33...).\n\n"
        "3. CONTACT_RH : prénom + nom du contact RH si EXPLICITEMENT mentionné, sinon null.\n\n"
        f"4. FIABLE : cette page appartient-elle bien à '{nom_entreprise}' ?\n"
        "   Réponds false si :\n"
        "   - C'est clairement un annuaire, site d'emploi tiers, ou secteur totalement différent.\n"
        "   - Les emails trouvés ont un domaine qui ne correspond PAS du tout au nom de l'entreprise.\n"
        "   - La page concerne une entreprise d'un autre pays sans lien avec la France.\n"
        "   En cas de doute → true.\n\n"
        "Réponds UNIQUEMENT en JSON valide, sans backticks :\n"
        '{"emails": ["contact@example.fr"], "telephones": ["01 23 45 67 89"], '
        '"contact_rh": null, "fiable": true}'
    )

    def _appel_mistral():
        return mistral_client.chat.complete(
            model=MODELE_MISTRAL,
            messages=[
                {"role": "system", "content": (
                    "Tu es un expert en extraction de données de contact. "
                    "Tu réponds UNIQUEMENT en JSON valide sans backticks ni markdown. "
                    "Tu ne génères JAMAIS d'emails si tu n'en trouves pas dans le contenu fourni."
                )},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

    response    = None
    attente     = 60
    MAX_RETRIES = 20

    for tentative in range(1, MAX_RETRIES + 1):
        try:
            response = _appel_mistral()
            break

        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower() or "rate limited" in err.lower():
                print(f"    ⚠️  Rate limit Mistral (tentative {tentative}/{MAX_RETRIES}) — attente {attente}s...")
                time.sleep(attente)
                attente = min(attente * 2, 300)
            else:
                print(f"    ⚠️  Erreur Mistral non-récupérable : {e}")
                time.sleep(PAUSE_MISTRAL)
                return {"emails": [], "telephones": [], "contact_rh": None, "fiable": True}

    if response is None:
        print(f"    ⚠️  Mistral inaccessible après {MAX_RETRIES} tentatives — entreprise ignorée")
        return {"emails": [], "telephones": [], "contact_rh": None, "fiable": True}

    try:
        texte  = re.sub(r'```(?:json)?\s*', '', response.choices[0].message.content).strip()
        result = json.loads(texte)
        dbg(f"Mistral → {result}")
        time.sleep(PAUSE_MISTRAL)
        return result
    except Exception as e:
        print(f"    ⚠️  Mistral parse erreur : {e}")
        time.sleep(PAUSE_MISTRAL)
        return {"emails": [], "telephones": [], "contact_rh": None, "fiable": True}


# ─── Analyse du nom / correspondance domaine ─────────────────────────────────

def analyser_nom(nom):
    nom_clean   = re.sub(r"[^a-z0-9\s]", " ", nom.lower())
    tous_mots   = nom_clean.split()
    mots_longs  = [m for m in tous_mots if len(m) >= 3 and m not in MOTS_IGNORES_DOMAINE]
    mots_courts = [m for m in tous_mots if 2 <= len(m) <= 3 and m not in MOTS_IGNORES_DOMAINE]
    acronymes   = re.findall(r'\b([A-Z]{2,6})\b', nom)
    acronyme    = acronymes[0].lower() if acronymes else None
    if not acronyme and not mots_longs and mots_courts:
        acronyme = "".join(mots_courts)
    return {"mots": mots_longs, "acronyme": acronyme, "mots_courts": mots_courts}


def domaine_correspond(domaine, analyse):
    domaine_clean = re.sub(r"[^a-z0-9]", "", domaine.lower())
    for mot in analyse["mots"]:
        mot_clean = re.sub(r"[^a-z0-9]", "", mot.lower())
        if len(mot_clean) >= 4 and mot_clean in domaine_clean:
            return True, f"mot '{mot}' ∈ domaine"
    if analyse["acronyme"]:
        acronyme_clean = re.sub(r"[^a-z0-9]", "", analyse["acronyme"].lower())
        if len(acronyme_clean) >= 3 and acronyme_clean in domaine_clean:
            return True, f"acronyme '{analyse['acronyme']}' ∈ domaine"
    domaine_sans_tld = domaine_clean.rsplit(".", 1)[0] if "." in domaine_clean else domaine_clean
    for mot in analyse["mots_courts"]:
        mot_clean = re.sub(r"[^a-z0-9]", "", mot.lower())
        if mot_clean and len(mot_clean) >= 3 and domaine_sans_tld.startswith(mot_clean):
            return True, f"mot court '{mot}' = début domaine"
    return False, f"aucun mot {analyse['mots']} / acr '{analyse['acronyme']}' dans '{domaine}'"


def est_url_valide(url, nom, analyse, strict=True):
    domaine = extraire_domaine(url)
    if not domaine:
        return False, "URL invalide"
    if est_annuaire(domaine):
        return False, f"annuaire ({domaine_parent(domaine)})"
    _path = urlparse(url).path.lower()
    if any(_path.endswith(ext) for ext in _EXTENSIONS_FICHIERS_NON_HTML):
        _ext = _path.rsplit(".", 1)[-1] if "." in _path else "?"
        return False, f"fichier non-HTML (.{_ext})"
    tld = domaine.rsplit(".", 1)[-1] if "." in domaine else ""
    if tld in {"cn", "ru", "ua", "in", "br", "mx", "wf", "gp", "mq", "re", "pm", "yt", "nc", "pf"}:
        return False, f"TLD suspect ({tld})"
    if not strict:
        return True, "mode tentative"
    return domaine_correspond(domaine, analyse)


# ─── Requêtes DDG ────────────────────────────────────────────────────────────

def construire_requetes(entreprise, analyse):
    nom   = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    ville = entreprise.get("ville") or ""
    cp    = entreprise.get("code_postal") or ""
    dept  = cp[:2] if cp else ""
    lieu  = f"{ville} {dept}".strip()
    siren = entreprise.get("siren", "")

    nom_clean      = re.sub(r"[^a-z0-9\s]", " ", nom.lower())
    mots_recherche = [m for m in nom_clean.split() if m not in MOTS_IGNORES_RECHERCHE and len(m) >= 2]
    nom_court      = re.sub(r'\s*[\(\;].*', '', nom).strip()

    nom_ambigu = (
        len(analyse["mots"]) <= 1
        or all(len(m) < 5 for m in analyse["mots"])
    )

    requetes = []

    if siren and nom_ambigu:
        requetes.append(f'SIREN {siren}')
        requetes.append(f'SIREN {siren} site officiel')

    if mots_recherche:
        mots_str = " ".join(mots_recherche[:4])
        requetes.append(f'"{mots_str}" {lieu}'.strip())
        requetes.append(f'"{mots_str}" {lieu} site officiel'.strip())

    if analyse["acronyme"]:
        requetes.append(f'"{analyse["acronyme"]}" informatique {lieu} site officiel')

    if siren and not nom_ambigu:
        requetes.append(f'SIREN {siren} site officiel')
        requetes.append(f'SIREN {siren}')

    requetes.append(f'{nom_court} {lieu} recrutement contact')
    return requetes


# ─── DuckDuckGo ──────────────────────────────────────────────────────────────

def chercher_site_duckduckgo(entreprise, url_exclue=None):
    """FIX 11 : url_exclue permet d'ignorer une URL déjà échouée au retry."""
    nom      = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    analyse  = analyser_nom(nom)
    requetes = construire_requetes(entreprise, analyse)

    if DEBUG:
        print(f"    🔎 Analyse nom : mots={analyse['mots']} | acronyme={analyse['acronyme']} | ambigu={'oui' if (len(analyse['mots']) <= 1 or all(len(m) < 5 for m in analyse['mots'])) else 'non'}")
        if url_exclue:
            print(f"    🚫 URL exclue (déjà non fiable) : {url_exclue}")

    for i, requete in enumerate(requetes, 1):
        dbg(f"┌─ Requête DDG [{i}/{len(requetes)}] : {requete}")
        try:
            pause_ddg()
            with DDGS() as ddg:
                resultats = list(ddg.text(requete, max_results=10))

            if not resultats:
                dbg(f"│  (aucun résultat DDG)")
                continue

            for r in resultats:
                url = r.get("href", "")
                if not url:
                    continue
                # FIX 11 — ignorer l'URL qui a déjà échoué
                if url_exclue and extraire_domaine(url) == extraire_domaine(url_exclue):
                    dbg(f"│  🚫 {url[:80]}  [même domaine que l'URL exclue]")
                    continue
                valide, raison = est_url_valide(url, nom, analyse, strict=True)
                dbg(f"│  {'✅' if valide else '✗ '} {url[:80]}  [{raison}]")
                if valide:
                    dbg(f"└─ → SÉLECTIONNÉ")
                    return url

            dbg(f"└─ (aucune URL valide)")

        except RatelimitException:
            print(f"  [⚠️  Rate limit DDG — attente {PAUSE_RATELIMIT}s...]")
            time.sleep(PAUSE_RATELIMIT)
            try:
                with DDGS() as ddg:
                    resultats = list(ddg.text(requete, max_results=10))
                for r in resultats:
                    url = r.get("href", "")
                    if not url:
                        continue
                    if url_exclue and extraire_domaine(url) == extraire_domaine(url_exclue):
                        continue
                    if est_url_valide(url, nom, analyse, strict=True)[0]:
                        return url
            except Exception:
                pass
        except Exception as e:
            dbg(f"DDG erreur : {e}")

    return None


def chercher_site(entreprise, url_exclue=None):
    url = chercher_site_duckduckgo(entreprise, url_exclue=url_exclue)
    if url:
        dbg(f"Site via DDG : {url}")
        return url, "ddg"
    return None, None


# ─── Scraping HTTP ────────────────────────────────────────────────────────────

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
    liens = set()
    mots_cles = [
        "contact", "recrutement", "carriere", "carrieres", "emploi",
        "job", "jobs", "rejoindre", "rh", "about", "equipe", "team",
        "alternance", "stage", "nous-rejoindre",
    ]
    for a in soup.find_all("a", href=True):
        href       = a["href"].strip()
        texte      = a.get_text(strip=True).lower()
        href_lower = href.lower()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if any(href_lower.endswith(ext) for ext in (".pdf", ".jpg", ".png", ".zip")):
            continue
        if any(m in href_lower for m in mots_cles) or any(m in texte for m in mots_cles):
            lien = urljoin(base_url, href)
            if meme_site(lien, base_url):
                liens.add(lien)
    return list(liens)[:8]


def lire_sitemap(url_racine):
    mots_contact  = ["contact", "recrutement", "rh", "carriere", "emploi", "rejoindre", "alternance"]
    urls_trouvees = []
    for chemin in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/"]:
        try:
            r = requests.get(urljoin(url_racine, chemin), headers=HEADERS, timeout=5, allow_redirects=True)
            if r.status_code != 200:
                continue
            locs = re.findall(r'<loc>(.*?)</loc>', r.text, re.IGNORECASE)
            for loc in locs:
                loc = loc.strip()
                if meme_site(loc, url_racine) and any(m in loc.lower() for m in mots_contact):
                    urls_trouvees.append(loc)
            if urls_trouvees:
                dbg(f"Sitemap → {len(urls_trouvees)} pages contact")
                break
        except Exception:
            pass
    return urls_trouvees[:5]


def scraper_et_extraire(url_site, nom_entreprise, dirigeant=None):
    url_site = url_site.strip().rstrip("/")
    if not url_site.startswith("http"):
        url_site = "https://" + url_site

    parsed     = urlparse(url_site)
    url_racine = f"{parsed.scheme}://{parsed.netloc}"
    domaine    = extraire_domaine(url_site)

    tous_emails_bruts = []
    pages_texte       = []
    html_contact_brut = ""
    mots_prio         = ["contact", "recrutement", "rh", "emploi", "carriere", "alternance"]

    if url_racine != url_site:
        dbg(f"Sous-page → scrape racine : {url_racine}")
        html_r, _ = get_page(url_racine)
        if html_r:
            tous_emails_bruts.extend(extraire_emails_html(html_r, domaine))
            pages_texte.append(html_vers_texte(html_r))

    if est_sous_domaine(domaine):
        parent_domaine = domaine_parent(domaine)
        url_parent     = f"{parsed.scheme}://{parent_domaine}"
        dbg(f"Sous-domaine → scrape parent : {url_parent}")
        html_parent, _ = get_page(url_parent)
        if html_parent:
            tous_emails_bruts.extend(extraire_emails_html(html_parent, parent_domaine))
            pages_texte.append(html_vers_texte(html_parent))
            soup_parent  = BeautifulSoup(html_parent, "html.parser")
            liens_parent = trouver_liens_contact(soup_parent, url_parent)
            for lien in liens_parent[:4]:
                time.sleep(random.uniform(0.5, 1.0))
                html_lp, _ = get_page(lien)
                if html_lp:
                    tous_emails_bruts.extend(extraire_emails_html(html_lp, parent_domaine))
                    if any(m in lien.lower() for m in mots_prio):
                        pages_texte.insert(0, html_vers_texte(html_lp))

    html, url_finale = get_page(url_site)
    if not html:
        alt = url_site.replace("://www.", "://") if "://www." in url_site \
              else url_site.replace("://", "://www.")
        html, url_finale = get_page(alt)

    if not html and not pages_texte:
        return {"emails": [], "telephones": [], "contact_rh": None, "url_finale": None, "fiable": True}

    vus = {url_racine, url_site, url_finale or url_site}

    if html:
        soup  = BeautifulSoup(html, "html.parser")
        tous_emails_bruts.extend(extraire_emails_html(html, domaine))
        base  = url_finale or url_site
        liens = list(set(trouver_liens_contact(soup, base) + lire_sitemap(url_racine)))
        pages_texte.insert(0, html_vers_texte(html))
    else:
        dbg("URL principale sans HTML → sitemap seulement")
        liens = lire_sitemap(url_racine)

    for chemin in PAGES_CONTACT:
        liens.append(urljoin(url_racine, chemin))

    for lien in liens[:20]:
        if lien in vus:
            continue
        vus.add(lien)
        time.sleep(random.uniform(0.6, 1.5))
        html_page, _ = get_page(lien)
        if html_page:
            e_page = extraire_emails_html(html_page, domaine)
            tous_emails_bruts.extend(e_page)
            if any(m in lien.lower() for m in mots_prio):
                pages_texte.insert(0, html_vers_texte(html_page))
                if not html_contact_brut:
                    html_contact_brut = html_page

    for chemin_ml in ["/mentions-legales", "/mentions-legales/",
                       "/mentions-legales.html", "/legal", "/legal/"]:
        lien_ml = urljoin(url_racine, chemin_ml)
        if lien_ml in vus:
            continue
        vus.add(lien_ml)
        time.sleep(random.uniform(0.6, 1.5))
        html_ml, _ = get_page(lien_ml)
        if html_ml:
            emails_ml = extraire_emails_html(html_ml, domaine)
            if emails_ml:
                dbg(f"Emails mentions-légales : {emails_ml}")
                tous_emails_bruts.extend(emails_ml)
            pages_texte.insert(0, html_vers_texte(html_ml))
            break

    emails_bruts_uniques = list(set(tous_emails_bruts))
    dbg(f"Emails bruts : {emails_bruts_uniques}")

    # FIX 12 — troncature pour éviter les dépassements de rate limit Mistral
    texte_pour_mistral = "\n\n---\n\n".join(pages_texte)
    texte_pour_mistral = texte_pour_mistral[:2000]
    html_contact_brut_tronque = html_contact_brut[:3000] if html_contact_brut else None

    resultat = mistral_extraire_contact(
        texte_pour_mistral,
        nom_entreprise,
        emails_bruts_uniques,
        html_contact=html_contact_brut_tronque,
    )

    emails_finals = [e for e in resultat.get("emails", []) if est_email_valide(e)]
    # FIX 10 — exclure les emails scorés à 0 (inutiles pour le recrutement)
    emails_finals = [e for e in emails_finals if scorer_email(e) > 0]
    emails_finals = sorted(emails_finals, key=scorer_email, reverse=True)[:5]

    return {
        "emails":     emails_finals,
        "telephones": resultat.get("telephones", []),
        "contact_rh": resultat.get("contact_rh"),
        "url_finale": url_finale or url_racine,
        "fiable":     resultat.get("fiable", True),
    }


# ─── Chargement / sauvegarde ──────────────────────────────────────────────────

from database.entreprises_db import lire_entreprises, sauvegarder_enrichissement

# Utilisateur pour lequel le scraper travaille (1 = Kenza, surchargeable via --user)
def charger_entreprises(user_id):
    """Lit les entreprises de l'utilisateur depuis la BASE."""
    data = lire_entreprises(user_id)
    print(f"[Chargement] base → {len(data)} entreprises")
    return data


def sauvegarder(user_id, entreprises):
    """Réécrit les enrichissements (emails, téléphones...) en BASE pour l'utilisateur."""
    sauvegarder_enrichissement(user_id, entreprises)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(stop_event=None, log_fn=None, user_id=1, on_progress=None):
    _log = log_fn or print
    _log(f"Scraper Emails v15 | Mistral = {MODELE_MISTRAL} | Moteur = DDG")
    if DEBUG:
        _log("  [Mode DEBUG activé — logs DDG détaillés]")

    entreprises  = charger_entreprises(user_id)
    total        = len(entreprises)
    deja_envoyes = sum(1 for e in entreprises if e.get("mail_envoye"))
    deja_emails  = sum(1 for e in entreprises if e.get("emails_trouves"))
    deja_traites = sum(1 for e in entreprises if e.get("traite"))

    a_traiter = [
        e for e in entreprises
        if not e.get("traite")
        and not e.get("emails_trouves")
        and not e.get("mail_envoye")
    ]

    _log(f"Total : {total} | Déjà traités : {deja_traites} | Avec emails : {deja_emails} | Envoyés : {deja_envoyes}")
    _log(f"Queue : {len(a_traiter)} à traiter")

    if not a_traiter:
        _log("✅ Tout traité !")
        return

    traites_ce_run = 0

    try:
        for e in entreprises:
            if stop_event and stop_event.is_set():
                _log("⏹️  Arrêt — sauvegarde en cours...")
                sauvegarder(user_id, entreprises)
                return

            if e.get("mail_envoye") or e.get("emails_trouves") or e.get("traite"):
                continue

            nom       = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
            dirigeant = e.get("dirigeant", "")
            idx       = deja_traites + traites_ce_run + 1
            _log(f"[{idx}/{total}] {nom}")
            if on_progress and a_traiter:
                fait = traites_ce_run + 1
                pct = round(fait / len(a_traiter) * 100)
                on_progress(min(pct, 100), f"{fait}/{len(a_traiter)} entreprises analysées")

            url         = e.get("site_web")
            source_site = "existant"

            if not url:
                url, source_site = chercher_site(e)
                if url:
                    e["site_web"] = url
                    _log(f"  🌐 {url} [{source_site}]")
                else:
                    _log(f"  ❌ Site introuvable")
                    e["emails_trouves"] = []
                    e["telephones"]     = []
                    e["telephone"]      = None
                    e["contact_rh"]     = None
                    e["traite"]         = True
                    traites_ce_run += 1
                    continue

            resultat = scraper_et_extraire(url, nom, dirigeant=dirigeant)

            if not resultat.get("fiable", True):
                tentatives = e.get("tentatives_site", 0)
                if tentatives < 2:
                    _log(f"  ⚠️  Site non fiable — retry ({tentatives + 1}/2)")
                    url_echouee = url   # FIX 11 — mémoriser l'URL qui a échoué
                    e["site_web"]        = None
                    e["tentatives_site"] = tentatives + 1
                    # FIX 11 — passer url_echouee pour l'exclure de la recherche
                    url, source_site = chercher_site(e, url_exclue=url_echouee)
                    if url:
                        e["site_web"] = url
                        resultat = scraper_et_extraire(url, nom, dirigeant=dirigeant)
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
                _log(f"  ✅ {', '.join(emails)}")
            else:
                _log(f"  ⚠️  Aucun email")

            e["emails_trouves"]   = emails
            e["telephones"]       = telephones
            e["telephone"]        = telephones[0] if telephones else None
            e["contact_rh"]       = contact
            e["url_scrapee"]      = resultat.get("url_finale") or url
            e["source_recherche"] = source_site
            e["traite"]           = True
            traites_ce_run += 1

            if traites_ce_run % SAUVEGARDE_TOUS == 0:
                sauvegarder(user_id, entreprises)
                avec = sum(1 for x in entreprises if x.get("emails_trouves"))
                _log(f"  💾 Sauvegarde — {idx}/{total} | {avec} avec email")

    except KeyboardInterrupt:
        _log("\n⏹️  Ctrl+C — sauvegarde en cours...")
        sauvegarder(user_id, entreprises)
        return

    sauvegarder(user_id, entreprises)
    avec_email = sum(1 for e in entreprises if e.get("emails_trouves"))
    _log(f"✅ Scraping terminé — {avec_email}/{total} avec email")
    _log(f"   DDG : {_compteur_ddg} requêtes")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=int, default=1,
                        help="ID de l'utilisateur pour lequel scraper (défaut: 1)")
    args = parser.parse_args()
    main(user_id=args.user)
