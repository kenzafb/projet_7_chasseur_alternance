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
DEVINE = "domaine_devine"
WIKIDATA = "wikidata"
SOURCES = {LBA: "La Bonne Alternance", FRANCE_TRAVAIL: "offre France Travail", RECHERCHE: "recherche web",
           VERIFIE: "site déjà vérifié", DEVINE: "domaine deviné d'après le nom", WIKIDATA: "Wikidata"}
# Domaines devinés (D168) : nom simplifié + extension, avant toute recherche
EXTENSIONS_DEVINEES = (".fr", ".com", ".eu", ".io")
MAX_DOMAINES_DEVINES = 8
PREUVES = {"siren": "SIREN", "siret": "SIRET", "tva": "numéro de TVA", "nom_titre": "nom dans le titre du site",
           "nom_mentions": "nom dans les mentions légales",
           "titre_adresse": "nom dans le titre et adresse Sirene sur le site",
           "domaine_adresse": "domaine au nom de l'entreprise et adresse sur le site",
           "wikidata": "site officiel déclaré dans Wikidata pour le SIREN"}
PREUVES_NUMERO = ("siren", "siret", "tva")
MAX_CANDIDATS_RECHERCHE = 8      # domaines de la recherche web essayés au plus (4 avant D171)
MOTS_DISTINCTIFS_MIN = 2         # preuve par le nom : au moins 2 mots distinctifs, sinon SIREN (D172)

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
    Sigle, dénominations usuelles et enseignes de Sirene compris (D167).
    Seulement ceux qui ont un mot distinctif d'au moins 4 lettres (« LE JU »,
    « 1964 » ne prouvent rien : SIREN exigé)."""
    noms = [entreprise.get("nom_commercial"), entreprise.get("nom"), entreprise.get("raison_sociale"),
            (entreprise.get("_extra") or {}).get("nom"), *autres_noms(entreprise)]
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


def autres_noms(entreprise: dict) -> list[str]:
    """Sigle, dénominations usuelles et enseignes (Sirene, D167), enregistrés
    à la récupération ou complétés par spontanees/noms_entreprise.py."""
    v = entreprise.get("autres_noms")
    if v is None:
        v = (entreprise.get("_extra") or {}).get("autres_noms")
    return [str(x) for x in v or [] if x]


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
    if not L.meme_site(finale, url):
        # Redirigé vers un autre domaine (cartadis.fr -> cartadis.com) : c'est
        # lui qu'on vérifie, qu'on lit et qu'on retient (D168)
        p = urlparse(finale)
        v.url = f"{p.scheme}://{p.netloc}"
        nouveau = lecteur_cls(v.url, max_pages=lecteur.reste + 1)
        nouveau._vues.add(finale.split("#")[0])
        nouveau.lues.append((finale, 200))
        v.lecteur = lecteur = nouveau
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
    # Nom d'un seul mot distinctif (Fermat, Bellon, Ithis) : il ne prouve rien,
    # trop d'autres sites le portent ; SIREN obligatoire (D172)
    variantes = [x for x in variantes_du_nom(entreprise) if len(mots_distinctifs(x)) >= MOTS_DISTINCTIFS_MIN]
    if n := nom_present(L.titre_de(html), variantes):
        v.verifie, v.preuve, v.detail = True, "nom_titre", f"« {n} » dans le titre du site"
        # Le titre seul ne suffit pas pour envoyer, avec l'adresse Sirene oui (D216)
        if trouve := adresse_sur_le_site(v, entreprise, textes, liens, lecteur):
            v.preuve, v.detail = "titre_adresse", f"{v.detail} et {trouve}"
    elif "mentions" in textes and (n := nom_present(textes["mentions"], variantes)):
        v.verifie, v.preuve, v.detail = True, "nom_mentions", f"« {n} » dans les mentions légales"
    elif not variantes and variantes_du_nom(entreprise):
        # Assouplissement (D173) : domaine principal = le nom, et adresse Sirene sur le site
        preuve = preuve_domaine_adresse(v, entreprise, textes, liens, lecteur)
        if preuve:
            v.verifie, v.preuve, v.detail = True, "domaine_adresse", preuve
        else:
            v.detail = ("nom d'un seul mot distinctif : SIREN exigé (ou domaine au nom et adresse sur le site), "
                        "absent de l'accueil et des mentions légales")
    else:
        v.detail = ("ni SIREN ni nom dans l'accueil et les mentions légales" if "mentions" in textes
                    else "ni SIREN dans l'accueil ni nom dans le titre, pas de lien vers des mentions légales")
    return v


def domaine_principal(url: str) -> str:
    """Partie principale du domaine, sans sous-domaine ni extension : www.cartadis.com -> cartadis."""
    parties = L.domaine(url).split(".")
    return parties[-2] if len(parties) >= 2 else parties[0]


def domaine_au_nom(url: str, entreprise: dict) -> bool:
    """Le domaine principal est exactement le nom distinctif (simplifié, sans espace ni tiret)."""
    d = re.sub(r"[^a-z0-9]", "", domaine_principal(url))
    for nom in variantes_du_nom(entreprise):
        mots = mots_distinctifs(nom)
        if mots and d in {"".join(mots), "".join(nom.split())}:
            return True
    return False


def adresses_connues(entreprise: dict) -> list[dict]:
    """Adresses Sirene de l'entreprise : établissement francilien (code postal,
    voie) et siège (annuaire, D167)."""
    extra = entreprise.get("_extra") or {}
    voie = re.sub(r"^\s*\d+\s*(?:bis|ter|b|t)?\s*", "", str(extra.get("adresse") or entreprise.get("adresse") or ""),
                  flags=re.I)
    out = [{"code_postal": str(entreprise.get("code_postal") or ""), "voie": voie}]
    siege = entreprise.get("adresse_siege") or extra.get("adresse_siege")
    if siege:
        out.append({"code_postal": str(siege.get("code_postal") or ""), "voie": str(siege.get("voie") or "")})
    return [a for a in out if a["code_postal"] or a["voie"]]


def adresse_presente(texte: str, adresses: list[dict]) -> str | None:
    """« code postal 94120 » ou « rue … » si le texte porte l'une des adresses."""
    simple = f" {simplifier(texte)} "
    for a in adresses:
        if re.fullmatch(r"\d{5}", a["code_postal"]) and re.search(rf"(?<!\d){a['code_postal']}(?!\d)", texte or ""):
            return f"code postal {a['code_postal']}"
        voie = simplifier(a["voie"])
        if len(voie) >= 8 and f" {voie} " in simple:
            return f"« {a['voie'].lower()} »"
    return None


def preuve_domaine_adresse(v, entreprise: dict, textes: dict, liens: dict, lecteur) -> str | None:
    """D173 : nom d'un seul mot distinctif, sans SIREN sur le site. Accepté si le
    domaine principal est exactement ce nom ET si l'accueil, le contact ou les
    mentions légales portent le code postal ou la voie de l'adresse Sirene."""
    if not domaine_au_nom(v.url, entreprise):
        return None
    trouve = adresse_sur_le_site(v, entreprise, textes, liens, lecteur)
    return f"domaine au nom de l'entreprise et {trouve}" if trouve else None


def adresse_sur_le_site(v, entreprise: dict, textes: dict, liens: dict, lecteur) -> str | None:
    """« code postal 94120 dans l'accueil » : adresse Sirene dans l'accueil, les
    mentions légales ou la page contact ; None sinon."""
    adresses = adresses_connues(entreprise)
    if not adresses:
        return None
    pages = dict(textes)
    for lien in liens.get("contact", [])[:1]:
        h, f = lecteur.lire(lien)
        if h:
            v.pages[f or lien] = h
            pages["contact"] = L.texte_de(h)
    for ou, texte in pages.items():
        if trouve := adresse_presente(texte, adresses):
            lieu = {"accueil": "l'accueil", "mentions": "les mentions légales", "contact": "la page contact"}[ou]
            return f"{trouve} dans {lieu}"
    return None


def mots_distinctifs(nom: str) -> list[str]:
    """Mots d'au moins 4 lettres, ni généraux ni formes juridiques ni nombres."""
    return [m for m in nom.split() if len(m) >= 4 and m not in GENERIQUES | FORMES and not m.isdigit()]


# ─── Candidats ────────────────────────────────────────────────────────────────
def site_lba(entreprise: dict, sites_export=None) -> str:
    """Site fourni par La Bonne Alternance (workplace.website) : celui de
    l'entreprise LBA, sinon celui de l'export pour son SIREN (D166) ; vide sinon."""
    extra = entreprise.get("_extra") or {}
    site = str((extra.get("lba") or {}).get("site_web") or "").strip()
    if site:
        return site
    siren = entreprise.get("siren") or str(extra.get("siret") or "")[:9]
    if sites_export is None:
        from offres.export_lba import sites_par_siren
        sites_export = sites_par_siren()
    return str(sites_export.get(siren) or "") if siren else ""


def site_deja_verifie(entreprise: dict) -> str:
    """URL du site vérifié lors d'un passage précédent ({"verifie": False} : aucun)."""
    v = (entreprise.get("_extra") or {}).get("site_verifie") or {}
    return str(v.get("url") or "") if v.get("verifie", True) else ""


def domaines_devines(entreprise: dict) -> list[str]:
    """Accueils devinés d'après le nom (D168) : nom simplifié, mots collés
    puis séparés d'un tiret ; sigle et autres noms ensuite. Le .fr de chaque
    forme d'abord, puis leurs .com, .eu, .io (D215) : sinon deux formes
    longues prenaient toutes les places. Seulement des noms d'au moins
    4 caractères qui ont un mot distinctif (« groupe-services.fr » n'est pas
    deviné). Sans moteur de recherche : aucune limite de requêtes, un domaine
    qui n'existe pas échoue tout de suite."""
    formes = []
    for nom in variantes_du_nom(entreprise) + [simplifier(n) for n in autres_noms(entreprise)]:
        mots = [m for m in nom.split() if m not in FORMES]
        for forme in ("".join(mots), "-".join(mots)):
            if 4 <= len(forme) <= 40 and forme not in formes:
                formes.append(forme)
    out = [f"https://{forme}{EXTENSIONS_DEVINEES[0]}" for forme in formes]
    out += [f"https://{forme}{ext}" for forme in formes for ext in EXTENSIONS_DEVINEES[1:]]
    return out[:MAX_DOMAINES_DEVINES]


def candidats(entreprise: dict, sites_france_travail: dict, recherche=None, sites_export=None):
    """(url, source) dans l'ordre : déjà vérifié, Wikidata (D188), LBA,
    France Travail, domaines devinés (D168), recherche web (générateur)."""
    from spontanees.wikidata import sites_wikidata
    vus = set()

    def nouveau(url):
        d = L.domaine(url if "://" in url else "https://" + url)
        if not d or d in vus:
            return False
        vus.add(d)
        return True

    url = site_deja_verifie(entreprise)
    if url and nouveau(url):
        yield (url if "://" in url else "https://" + url), VERIFIE
    for url in sites_wikidata(entreprise):
        if not domaine_interdit(url) and nouveau(url):
            yield url, WIKIDATA
    url = site_lba(entreprise, sites_export)
    if url and nouveau(url):
        yield (url if "://" in url else "https://" + url), LBA
    for nom in {nom_normalise(entreprise.get(c) or "") for c in ("nom_commercial", "nom")} - {""}:
        for url in sites_france_travail.get(nom, []):
            if nouveau(url):
                yield url, FRANCE_TRAVAIL
    for url in domaines_devines(entreprise):
        if not domaine_interdit(url) and nouveau(url):
            yield url, DEVINE
    if recherche:
        # Domaines interdits écartés AVANT de compter : seuls les candidats
        # possibles prennent une des MAX_CANDIDATS_RECHERCHE places (D171)
        essayes = 0
        for url in recherche(entreprise):
            if domaine_interdit(url) or not nouveau(url):
                continue
            essayes += 1
            yield url, RECHERCHE
            if essayes >= MAX_CANDIDATS_RECHERCHE:
                return


# ─── Le même domaine en .fr (D215) ────────────────────────────────────────────
_SECONDS_NIVEAUX = {"com", "co", "org", "net", "gov", "edu", "ac"}      # acme.com.au, acme.co.uk


def domaine_en_fr(url: str) -> str:
    """konicaminolta.eu, www.konicaminolta.co.uk -> konicaminolta.fr ; "" si c'est déjà un .fr."""
    parties = L.domaine(url).split(":")[0].split(".")
    if len(parties) < 2 or parties[-1] == "fr":
        return ""
    if len(parties) >= 3 and len(parties[-1]) == 2 and parties[-2] in _SECONDS_NIVEAUX:
        parties = parties[:-1]
    return f"{parties[-2]}.fr"


def preferer_fr(v: Verification, entreprise: dict, essais: list[dict], lecteur_cls=L.LecteurSite) -> Verification:
    """Site retenu hors .fr : le même domaine en .fr à la place, s'il porte le
    SIREN (SIRET, TVA). Sinon v, inchangée."""
    fr = domaine_en_fr(v.url)
    if not fr or domaine_interdit(fr) or any(x["domaine"] == fr for x in essais):
        return v
    for racine in (f"https://{fr}", f"https://www.{fr}"):
        w = verifier(racine, entreprise, v.source, lecteur_cls)
        if w.pages:
            essais.append(w.resume())
            return w if w.preuve in PREUVES_NUMERO and w.domaine.endswith(".fr") else v
    return v


def identifier(entreprise: dict, sites_france_travail: dict | None = None, recherche=None,
               lecteur_cls=L.LecteurSite, log=None, sites_export=None) -> tuple[Verification | None, list[dict]]:
    """(vérification retenue ou None, toutes les vérifications essayées)."""
    essais = []
    for url, source in candidats(entreprise, sites_france_travail or {}, recherche, sites_export):
        # Domaine deviné : aussi avec « www. » (certains n'existent que sous ce nom)
        a_essayer = racines(url) + ([url.replace("https://", "https://www.", 1)] if source == DEVINE else [])
        for racine in a_essayer:
            if domaine_interdit(racine):
                continue
            v = verifier(racine, entreprise, source, lecteur_cls)
            if source == WIKIDATA and not v.verifie and v.pages:
                # Site déclaré dans Wikidata pour ce SIREN : vérifié dès que
                # son accueil se lit, sans autre preuve (D188)
                v.verifie, v.preuve, v.detail = True, "wikidata", "site officiel déclaré dans Wikidata pour le SIREN"
            if source == DEVINE and not v.verifie and v.detail.startswith(("accueil illisible", "accueil interdit")):
                continue          # domaine inexistant : pas noté parmi les essais, il y en a beaucoup
            essais.append(v.resume())
            if log:
                log(f"    {'✔' if v.verifie else '✗'} {racine} ({SOURCES[source]}) : {v.detail}")
            if v.verifie:
                return preferer_fr(v, entreprise, essais, lecteur_cls), essais
    return None, essais
