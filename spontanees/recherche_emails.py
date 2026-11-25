"""
spontanees/recherche_emails.py
==============================
Étape « Trouver leurs emails » des candidatures spontanées (phase 15) :

  1. site de l'entreprise identifié et vérifié (spontanees/site_officiel.py,
     D160) : site fourni par La Bonne Alternance, site donné par une offre
     France Travail ou LBA, puis recherche web (DuckDuckGo) ; retenu
     seulement si le SIREN ou le nom de l'entreprise y figure, sinon « site
     non vérifié » et aucun email gardé ;
  2. lecture du site vérifié (spontanees/lecture_site.py, D161) : pages
     choisies parmi les liens réels de l'accueil et du sitemap (contact,
     mentions légales, recrutement, carrières, à propos), robots.txt
     respecté, au plus lecture_site.MAX_PAGES pages ; formulaires de contact
     relevés ;
  3. adresses lues dans les pages (regex, déobfuscation), puis triées
     (shared/validation_emails.py, D162) : domaine du site vérifié exigé,
     sauf messagerie grand public trouvée sur le site ; IA seulement pour
     les douteuses.

Corrections reprises des versions précédentes : faux TLD de la
déobfuscation (FIX 9), adresses inutiles au recrutement (FIX 10).
"""

import re
import time
import os
import random
from urllib.parse import urlparse


from shared.emails_exclus import email_exclu
from bs4 import BeautifulSoup
from ddgs import DDGS
from shared.config import MESSAGE_IA_DESACTIVEE, analyse_ia_active, modele_ia
from shared.validation_emails import emails_douteux, emails_valides, site_verifie, trier
from database.candidatures_db import sites_des_offres
from database.dates import maintenant_utc
from database.entreprises_db import a_scraper, lire_entreprises, sauvegarder_enrichissement
from spontanees.lecture_site import MAX_PAGES, categorie, formulaires, liens_du_sitemap, liens_utiles
from spontanees.noms_entreprise import completer as completer_noms
from spontanees.site_officiel import SOURCES, autres_noms, domaine_interdit, identifier
from shared.journal import journaliser
from shared.modes import MODE_DEFAUT

# ─── Config ───────────────────────────────────────────────────────────────────

SAUVEGARDE_TOUS = 5

DEBUG = os.getenv("DEBUG_SCRAPER", "false").lower() == "true"

PAUSE_DDG        = (3, 6)
PAUSE_LONGUE_N   = 15
PAUSE_LONGUE     = 45

# Recherche web (D187) : moteurs de ddgs essayés dans l'ordre, le suivant
# seulement si le précédent échoue ou ne trouve rien ; RECHERCHE_BACKENDS
# (.env) remplace l'ordre par défaut. Après ECHECS_AVANT_ARRET requêtes
# d'affilée sans réponse d'aucun moteur, la recherche web s'arrête pour le
# lancement (plus d'attente de 90 s par requête).
BACKENDS_DEFAUT    = "brave, mojeek, duckduckgo, yahoo, yandex"
REGION_RECHERCHE   = "fr-fr"
TIMEOUT_MOTEUR     = 10
ECHECS_AVANT_ARRET = 5

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
erreurs_ddg = 0      # requêtes de recherche web en échec (aucun moteur) depuis le démarrage
_echecs_affilee = 0  # requêtes en échec d'affilée, remis à zéro par un succès
recherche_arretee = False   # vrai après ECHECS_AVANT_ARRET échecs d'affilée, jusqu'au lancement suivant
echecs_par_moteur: dict[str, int] = {}


def dbg(msg):
    if DEBUG:
        journaliser(f"    [dbg] {msg}")


def pause_ddg():
    global _compteur_ddg
    _compteur_ddg += 1
    if _compteur_ddg % PAUSE_LONGUE_N == 0:
        journaliser(f"\n  [⏸️  Pause {PAUSE_LONGUE}s — {_compteur_ddg} recherches DDG]")
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
    """Domaine interdit comme site d'entreprise (shared/referentiels/domaines_interdits.txt, D160)."""
    return domaine_interdit(domaine)


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
    # Adresses techniques ou factices (shared/referentiels/emails_exclus.txt)
    if email_exclu(email):
        dbg(f"Adresse technique ou factice écartée : {email}")
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
        requetes.append(f'"{mots_str}" site officiel')           # sans ville (D171)
        requetes.append(f'"{mots_str}" {lieu} site officiel'.strip())

    if analyse["acronyme"]:
        requetes.append(f'"{analyse["acronyme"]}" informatique {lieu} site officiel')

    if siren and not nom_ambigu:
        requetes.append(f'SIREN {siren} site officiel')
        requetes.append(f'SIREN {siren}')

    requetes.append(f'{nom_court} {lieu} recrutement contact')
    # Sigle, dénominations usuelles, enseignes (D167)
    for autre in autres_noms(entreprise)[:3]:
        if autre.lower() != nom.lower():
            requetes.append(f'"{autre}" {lieu} site officiel'.strip())
    return requetes


# ─── DuckDuckGo ──────────────────────────────────────────────────────────────

def backends_recherche() -> list[str]:
    """Moteurs de ddgs à essayer, dans l'ordre : RECHERCHE_BACKENDS du .env
    (« brave, mojeek, duckduckgo »), sinon BACKENDS_DEFAUT. Un nom inconnu
    de ddgs est ignoré (journalisé) ; aucun nom valable : l'ordre par défaut."""
    from ddgs.engines import ENGINES
    connus = ENGINES["text"]
    demandes = [b.strip().lower() for b in (os.getenv("RECHERCHE_BACKENDS") or "").split(",") if b.strip()]
    gardes = [b for b in dict.fromkeys(demandes) if b in connus]
    if inconnus := [b for b in demandes if b not in connus]:
        journaliser(f"  [⚠️  RECHERCHE_BACKENDS : moteur(s) inconnu(s) ignoré(s) : {', '.join(inconnus)} ; "
                    f"connus : {', '.join(sorted(connus))}]")
    return gardes or [b.strip() for b in BACKENDS_DEFAUT.split(",")]


def reinitialiser_recherche():
    """Début d'un lancement : la recherche web est de nouveau permise."""
    global _echecs_affilee, recherche_arretee
    _echecs_affilee, recherche_arretee = 0, False


def _resultats_ddg(requete):
    """Résultats d'une requête de recherche web ({href, title, body}) : le
    premier moteur de backends_recherche() qui répond ; aucun : requête en
    échec (journalisée), et la recherche s'arrête pour le lancement après
    ECHECS_AVANT_ARRET échecs d'affilée (D187)."""
    global erreurs_ddg, _echecs_affilee, recherche_arretee
    if recherche_arretee:
        return []
    pause_ddg()
    moteurs, raisons = backends_recherche(), []
    for moteur in moteurs:
        try:
            with DDGS(timeout=TIMEOUT_MOTEUR) as ddg:
                resultats = [r for r in ddg.text(requete, region=REGION_RECHERCHE, backend=moteur, max_results=10)
                             if r.get("href")]
            if resultats:
                _echecs_affilee = 0
                dbg(f"{moteur} : {len(resultats)} résultat(s)")
                return resultats
            raisons.append(f"{moteur} : aucun résultat")
        except Exception as e:   # refus pour excès de requêtes, moteur injoignable, aucun résultat...
            echecs_par_moteur[moteur] = echecs_par_moteur.get(moteur, 0) + 1
            raisons.append(f"{moteur} : {type(e).__name__} {str(e)[:60]}".strip())
    # Jamais en silence : à l'audit, une panne du moteur laissait 13
    # entreprises de suite sans aucun candidat, comptées « sans site »
    erreurs_ddg += 1
    _echecs_affilee += 1
    journaliser(f"  [⚠️  Recherche web en échec ({' ; '.join(raisons)}) : {requete}]")
    if _echecs_affilee >= ECHECS_AVANT_ARRET:
        recherche_arretee = True
        journaliser(f"  [⛔ Recherche web arrêtée pour ce lancement : {_echecs_affilee} requêtes d'affilée sans "
                    f"réponse de {', '.join(moteurs)}. Les autres sources du site (LBA, offres, "
                    "domaines devinés) restent essayées.]")
    return []


def resultat_pertinent(resultat: dict, entreprise: dict, analyse: dict) -> bool:
    """Un résultat de recherche vaut d'être vérifié si son domaine ressemble au
    nom, ou si son titre ou son extrait cite le nom (ou le SIREN) : les
    résultats sans rapport (moteur dégradé : jeux, paroles, films) ne coûtent
    pas de vérification."""
    if domaine_correspond(extraire_domaine(resultat.get("href", "")), analyse)[0]:
        return True
    from spontanees.site_officiel import simplifier, variantes_du_nom
    texte = f" {simplifier(resultat.get('title', '') + ' ' + resultat.get('body', ''))} "
    siren = entreprise.get("siren") or ""
    return any(f" {v} " in texte for v in variantes_du_nom(entreprise)) or bool(siren and siren in texte.replace(" ", ""))


def urls_recherche(entreprise):
    """URLs candidates proposées par la recherche web, requête après requête
    (générateur : les requêtes suivantes ne partent que si besoin), seulement
    les résultats pertinents (resultat_pertinent), ceux dont le domaine
    ressemble au nom d'abord. Le site n'est retenu qu'après vérification
    (spontanees/site_officiel.py)."""
    nom = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    analyse = analyser_nom(nom)
    for requete in construire_requetes(entreprise, analyse):
        dbg(f"Requête DDG : {requete}")
        resultats = [r for r in _resultats_ddg(requete) if est_url_valide(r["href"], nom, analyse, strict=False)[0]
                     and resultat_pertinent(r, entreprise, analyse)]
        resultats.sort(key=lambda r: not domaine_correspond(extraire_domaine(r["href"]), analyse)[0])
        yield from (r["href"] for r in resultats)


# ─── Lecture du site vérifié ──────────────────────────────────────────────────

def meilleurs_emails(emails, domaine=None):
    """Emails valides et utiles au recrutement, les 5 meilleurs : ceux du
    domaine du site d'abord, puis par préfixe (recrutement, contact...)."""
    valides = [e for e in emails if est_email_valide(e)]
    # FIX 10 — exclure les emails scorés à 0 (inutiles pour le recrutement)
    valides = [e for e in valides if scorer_email(e) > 0]
    parent = domaine_parent(domaine) if domaine else None
    return sorted(dict.fromkeys(valides),
                  key=lambda e: (domaine_parent(e.split("@")[-1]) == parent, scorer_email(e)), reverse=True)[:5]


ORDRE_PAGES = ("contact", "recrutement", "mentions", "a_propos")


def pages_a_lire(verification) -> list[str]:
    """Pages utiles du site, liens réels de l'accueil puis du sitemap, par
    catégorie (contact, recrutement et carrières, mentions légales, à propos)."""
    accueil, html = next(iter(verification.pages.items()))
    liens = liens_utiles(html, accueil)
    plan = liens_du_sitemap(verification.lecteur)
    ordre = []
    for cat in ORDRE_PAGES:
        for url in liens[cat][:2] + plan[cat][:2]:
            if url not in ordre and url not in verification.pages:
                ordre.append(url)
    return ordre


def scraper_et_extraire(verification, nom_entreprise, dirigeant=None, ia=True):
    """Emails d'une entreprise au site vérifié (spontanees/site_officiel.py) :
    pages déjà lues pour la vérification, puis pages utiles du site dans la
    limite du lecteur (robots.txt, MAX_PAGES), adresses triées
    (shared/validation_emails.py) : règles d'abord, l'IA (ia=True) seulement
    pour les douteuses. Retourne "emails" (validées puis douteuses),
    "douteux", "contextes", "ecartes", "formulaires" (contact ou
    candidature), le journal de lecture ; une erreur de l'IA est signalée
    dans "ia_bloquee" ou "erreur_ia" au lieu d'être levée."""
    lecteur, pages = verification.lecteur, dict(verification.pages)
    for url in pages_a_lire(verification):
        if lecteur.reste <= 0:
            break
        html, finale = lecteur.lire(url)
        if html:
            pages[finale or url] = html
    domaine = verification.domaine
    bruts, textes, formes = [], [], {}
    for url, html in pages.items():
        bruts.extend(extraire_emails_html(html, domaine))
        texte = html_vers_texte(html)
        textes.insert(0, texte) if categorie(url) in ("contact", "recrutement") else textes.append(texte)
        for f in formulaires(html, url):
            formes.setdefault(f["page"], f)
    dbg(f"Emails bruts : {sorted(set(bruts))}")
    tri = trier(meilleurs_emails(list(set(bruts)), domaine), domaine, nom_entreprise, "\n\n".join(textes),
                ia=ia, log=dbg, verifie=True)
    resultat = {
        "emails":     tri["valides"] + tri["douteux"],
        "douteux":    tri["douteux"],
        "contextes":  tri["contextes"],
        "ecartes":    tri["ecartes"],
        "meilleur_contact": tri["meilleur_contact"],
        "provenance": tri["provenance"],
        "ecartes_ia": tri["ecartes_ia"],
        "telephones": [],
        "contact_rh": None,
        "url_finale": next(iter(pages)),
        "formulaires": list(formes.values()),
        "pages_lues": [u for u, _ in lecteur.lues],
        "interdites_robots": list(lecteur.interdites),
        "robots": lecteur.robots,
    }
    for cle in ("ia_bloquee", "erreur_ia"):
        if cle in tri:
            resultat[cle] = tri[cle]
    return resultat


def html_vers_texte(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


# ─── Chargement / sauvegarde ──────────────────────────────────────────────────

def _sans_resultat(e: dict):
    """Entreprise sans site vérifié : rien de gardé, traitée (le scraper n'y
    revient pas)."""
    e["emails_trouves"] = []
    e["emails_douteux"] = []
    e["emails_non_valides"] = False
    e["formulaires_contact"] = []
    e["telephones"] = []
    e["telephone"] = None
    e["contact_rh"] = None
    e["traite"] = True


def charger_entreprises(user_id, mode=MODE_DEFAUT):
    """Lit les entreprises sélectionnées dans le mode depuis la BASE. Leurs
    données (site, emails, contact) sont communes à tous les modes : une
    entreprise déjà scrapée pour un autre mode ne l'est pas deux fois."""
    data = lire_entreprises(user_id, mode)
    journaliser(f"[Chargement] base → {len(data)} entreprises")
    return data


def sauvegarder(user_id, entreprises):
    """Réécrit les enrichissements (emails, téléphones...) en BASE pour l'utilisateur."""
    sauvegarder_enrichissement(user_id, entreprises)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(user_id, stop_event=None, log_fn=None, on_progress=None, max_scrapees=None, mode=MODE_DEFAUT):
    """Cherche site, emails et contact des entreprises pas encore traitées,
    au plus max_scrapees par lancement (None : toutes)."""
    _log = log_fn or journaliser
    reinitialiser_recherche()
    ia_configuree = analyse_ia_active()   # ANALYSE_IA=false : lecture directe seulement
    modele = modele_ia("extraction") if ia_configuree else "désactivée"
    _log(f"Trouver leurs emails | IA pour les emails douteux = {modele} | site vérifié (SIREN ou nom) exigé "
         f"| au plus {MAX_PAGES} pages par site, robots.txt respecté")
    if DEBUG:
        _log("  [Mode DEBUG activé — logs DDG détaillés]")

    entreprises  = charger_entreprises(user_id, mode)
    total        = len(entreprises)
    deja_envoyes = sum(1 for e in entreprises if e.get("mail_envoye"))
    deja_emails  = sum(1 for e in entreprises if e.get("emails_trouves"))
    deja_traites = sum(1 for e in entreprises if e.get("traite"))

    a_traiter = [e for e in entreprises if a_scraper(e)]

    _log(f"Total : {total} | Déjà traités : {deja_traites} | Avec emails : {deja_emails} | Envoyés : {deja_envoyes}")
    _log(f"Queue : {len(a_traiter)} à traiter")
    if max_scrapees and len(a_traiter) > max_scrapees:
        _log(f"Limite du lancement : {max_scrapees} entreprises, les autres au prochain lancement")
        a_traiter = a_traiter[:max_scrapees]
    ids_a_traiter = {id(e) for e in a_traiter}

    if not a_traiter:
        _log("✅ Tout traité !")
        return

    traites_ce_run = 0
    sites_offres = sites_des_offres(user_id)   # sites donnés par les offres France Travail et LBA
    # Coupée pour tout le lancement sur une erreur bloquante de l'IA, ou d'emblée sans IA
    ia_active = ia_configuree
    if not ia_configuree:
        _log(f"ℹ️  {MESSAGE_IA_DESACTIVEE} Emails validés par les règles seules, les douteux restent non validés.")

    def extraire(verification, nom, dirigeant):
        nonlocal ia_active
        resultat = scraper_et_extraire(verification, nom, dirigeant=dirigeant, ia=ia_active)
        if resultat.get("ia_bloquee") and ia_active:
            ia_active = False   # un seul message, pas un par entreprise
            _log(f"❌ IA indisponible : {resultat['ia_bloquee']} Suite du lancement sans IA : "
                 "emails douteux gardés, non validés.")
        elif resultat.get("erreur_ia"):
            _log(f"  ⚠️  IA : {resultat['erreur_ia']} Emails douteux gardés, non validés.")
        return resultat

    try:
        for e in entreprises:
            if stop_event and stop_event.is_set():
                _log("⏹️  Arrêt — sauvegarde en cours...")
                sauvegarder(user_id, entreprises)
                return

            if id(e) not in ids_a_traiter:
                continue   # déjà traitée, ou au-delà de la limite du lancement

            nom       = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
            dirigeant = e.get("dirigeant", "")
            idx       = deja_traites + traites_ce_run + 1
            _log(f"[{idx}/{total}] {nom}")
            if on_progress and a_traiter:
                fait = traites_ce_run + 1
                pct = round(fait / len(a_traiter) * 100)
                on_progress(min(pct, 100), f"{fait}/{len(a_traiter)} entreprises analysées")

            completer_noms(e)   # sigle, dénominations usuelles, enseignes (D167)
            verification, essais = identifier(e, sites_offres, recherche=urls_recherche,
                                              log=_log if DEBUG else None)
            e["essais_site"] = essais[-6:]
            if verification is None:
                _log(f"  ❌ Site non vérifié ({len(essais)} essayé(s)) : aucun email gardé")
                _sans_resultat(e)
                # Écrit même vide (une valeur None ne le serait pas) : l'interface dit « site non vérifié »
                e["site_verifie"] = {"verifie": False, "essais": len(essais),
                                     "le": maintenant_utc().isoformat(timespec="seconds")}
                traites_ce_run += 1
                continue
            e["site_web"] = verification.url
            e["site_verifie"] = {**verification.resume(), "le": maintenant_utc().isoformat(timespec="seconds")}
            _log(f"  🌐 {verification.url} [{SOURCES[verification.source]}, {verification.detail}]")
            resultat = extraire(verification, nom, dirigeant)
            source_site = verification.source

            emails     = resultat["emails"]
            douteux    = resultat.get("douteux", [])
            telephones = resultat.get("telephones", [])
            contact    = resultat.get("contact_rh")

            valides = [a for a in emails if a not in douteux]
            if valides:
                _log(f"  ✅ {', '.join(valides)}")
            if douteux:
                _log(f"  ❔ {', '.join(douteux)} (non validés : à valider)")
            if resultat.get("ecartes"):
                _log("  🚫 Écartés : " + ", ".join(f"{a} ({r})" for a, r in resultat["ecartes"]))
            if not emails:
                _log("  ⚠️  Aucun email")

            e["emails_trouves"]   = emails
            e["telephones"]       = telephones
            e["telephone"]        = telephones[0] if telephones else None
            e["contact_rh"]       = contact
            e["emails_non_valides"] = bool(douteux)
            e["emails_douteux"]   = douteux
            e["contextes_emails"] = resultat.get("contextes", {})
            e["meilleur_contact"] = resultat.get("meilleur_contact")
            e["validation_emails"] = resultat.get("provenance", {})
            e["emails_ecartes_ia"] = resultat.get("ecartes_ia", [])
            e["url_scrapee"]      = resultat.get("url_finale") or verification.url
            e["source_recherche"] = source_site
            e["formulaires_contact"] = resultat.get("formulaires", [])
            if e["formulaires_contact"] and not emails:
                _log(f"  📝 Formulaire de contact : {e['formulaires_contact'][0]['page']}")
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
    _log(f"   Recherche web : {_compteur_ddg} requêtes" + (f", {erreurs_ddg} en échec" if erreurs_ddg else "")
         + (" (arrêtée en cours de lancement après des échecs d'affilée)" if recherche_arretee else ""))


def revalider(user_id, stop_event=None, log_fn=None, on_progress=None, max_n=None, mode=MODE_DEFAUT):
    """Repasse aux règles puis à l'IA les adresses douteuses des entreprises
    du mode (D15), sans relire les sites : le texte gardé autour de chaque
    adresse sert à l'IA. Une adresse validée part avec les autres, une
    adresse écartée est retirée ; un échec passager la laisse à valider.
    Erreur bloquante : arrêt du lancement, un seul message."""
    _log = log_fn or journaliser
    if not analyse_ia_active():
        _log(f"❌ {MESSAGE_IA_DESACTIVEE} Validation non lancée.")
        return
    entreprises = charger_entreprises(user_id, mode)
    cibles = [e for e in entreprises if emails_douteux(e) and not e.get("mail_envoye")]
    if max_n:
        cibles = cibles[:max_n]
    _log(f"Validation IA | modèle = {modele_ia('extraction')} | {len(cibles)} entreprise(s)")
    validees = 0
    for i, e in enumerate(cibles, 1):
        if stop_event and stop_event.is_set():
            _log("⏹️  Arrêt — sauvegarde en cours...")
            break
        nom = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
        if on_progress:
            on_progress(round(i / len(cibles) * 100), f"{i}/{len(cibles)} entreprises revalidées")
        site = site_verifie(e)   # domaine du site vérifié (D160), None sinon : tout est écarté
        deja = emails_valides(e)
        tri = trier(emails_douteux(e), site, nom, ia=True,
                    contextes=e.get("contextes_emails"), deja_valides=deja, verifie=bool(site))
        e["emails_trouves"]     = deja + tri["valides"] + tri["douteux"]
        e["emails_douteux"]     = tri["douteux"]
        e["contextes_emails"]   = tri["contextes"]
        e["emails_non_valides"] = bool(tri["douteux"])
        e["validation_emails"] = {**(e.get("validation_emails") or {}), **tri["provenance"]}
        e["emails_ecartes_ia"] = list(dict.fromkeys([*(e.get("emails_ecartes_ia") or []), *tri["ecartes_ia"]]))
        if tri["meilleur_contact"]:
            e["meilleur_contact"] = tri["meilleur_contact"]
        if tri["ecartes"]:
            _log(f"  🚫 {nom} : " + ", ".join(f"{a} ({r})" for a, r in tri["ecartes"]))
        if tri.get("ia_bloquee"):
            _log(f"❌ IA indisponible : {tri['ia_bloquee']} Validation arrêtée, "
                 "les entreprises restantes attendent toujours.")
            break
        if tri["douteux"]:
            _log(f"  ⚠️  {nom} : {tri.get('erreur_ia') or 'validation impossible'} "
                 f"{', '.join(tri['douteux'])} reste(nt) à valider.")
            continue
        validees += 1
        retenus = ", ".join(e["emails_trouves"]) or "aucun email retenu"
        _log(f"  ✅ {nom} : {retenus}")
    sauvegarder(user_id, entreprises)
    _log(f"✅ Validation IA terminée : {validees}/{len(cibles)} entreprise(s) validée(s)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=int, required=True,
                        help="ID de l'utilisateur pour lequel scraper")
    parser.add_argument("--mode", default=MODE_DEFAUT, help="entreprises sélectionnées dans ce mode")
    args = parser.parse_args()
    main(user_id=args.user, mode=args.mode)
