"""
france_travail/scraper_lba.py
=============================
Recherche La Bonne Alternance (mode alternance), SPEC_SOURCES.md section 3.

- Codes métiers déduits des domaines du profil (shared.domaines.codes_metiers,
  référentiel metiers), envoyés par lots de parametres_lba.CODES_PAR_REQUETE ;
  profil « indifférent » : recherche sans code (décision D37).
- Niveau de diplôme : jamais envoyé à l'API, qui écarterait les offres sans
  niveau ; offres d'un autre niveau que le niveau visé du profil écartées
  après récupération, offres sans niveau gardées (D38).
- Géographie : chaque lot est cherché autour de chacun des centres de
  shared.config.LBA_CENTRES, à rayon réduit ; résultats dédoublonnés.
- Rien de tronqué en silence : un cercle dont la réponse atteint le plafond
  (150 par source, 450 offres) est redécoupé en sept cercles de rayon
  moitié, jusqu'à LBA_RAYON_MIN_KM, puis le lot de codes en deux ; ce qui
  reste au plafond est écrit dans les logs (D36). Les entreprises, au
  plafond presque partout, ne déclenchent ce redécoupage que dans l'étape
  « Récupérer » des spontanées ; la recherche d'offres ignore les
  entreprises (D46).
- Deux types de résultats : les offres, et les entreprises à fort
  potentiel d'embauche (sans offre publiée), destinées aux candidatures
  spontanées, filtrées par la taille et les départements du profil (D40,
  D58). Les offres relayées
  depuis France Travail sont exclues (déjà récupérées par l'API France
  Travail).

Ce qui dépend du comportement de l'API est lu dans
france_travail/parametres_lba.py (vérifié par scripts/verifier_lba.py).
"""

import math
import os
import re
import time
import unicodedata
from collections import deque

import requests

from database.dates import instant_depuis_api
from france_travail import parametres_lba as P
from shared.config import DEPTS_IDF, DEPTS_PETITE_COURONNE, LBA_CENTRES, LBA_RAYON_MIN_KM, LBA_REQUETES_MAX
from shared.criteres import normaliser_recherche
from shared.domaines import codes_metiers, domaines_du_profil
from shared.niveaux import NIVEAUX, niveau_europeen
from shared.offres import detecter_zone, generer_id
from shared.tailles import SANS_SALARIE, garder_selon_taille, taille_depuis_tranche

PAUSE_S = 0.5           # entre deux requêtes
DELAI_S = 20
ATTENTE_429_S = 5       # une nouvelle tentative sur 429
RE_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
RE_CP_VILLE = re.compile(r"\b(\d{5})\b\s*(.*)$")
MESSAGE_INDIFFERENT = ("LBA ignorée : aucun domaine choisi dans le profil (« indifférent »). "
                       "Choisis des domaines pour chercher sur La Bonne Alternance.")


class ErreurLBA(Exception):
    """Réponse inattendue pour une requête (les autres continuent)."""


class CleRefusee(ErreurLBA):
    """Clé absente ou refusée : inutile de continuer."""


def _sans_accents(texte) -> str:
    texte = unicodedata.normalize("NFD", str(texte or ""))
    return "".join(c for c in texte if unicodedata.category(c) != "Mn").lower()


def relayee_de_france_travail(offre: dict) -> bool:
    partenaire = _sans_accents(P.lire(offre, P.CHAMP_PARTENAIRE))
    return any(nom in partenaire for nom in P.PARTENAIRES_FRANCE_TRAVAIL)


def _localiser(adresse: str):
    """(zone, code postal, département, ville) d'une adresse, None hors IDF."""
    m = RE_CP_VILLE.search(adresse or "")
    if m:
        cp, ville = m.group(1), m.group(2).strip()
        dept = cp[:2]
        if dept not in DEPTS_IDF:
            return None
        zone = "Paris" if dept == "75" else ("Petite couronne" if dept in DEPTS_PETITE_COURONNE
                                             else "Grande couronne")
        return zone, cp, dept, ville
    zone = detecter_zone(adresse or "")
    return (zone, "", "", "") if zone else None


# ─── Normalisation ────────────────────────────────────────────────────────────
def _normaliser_offre_lba(offre: dict) -> dict | None:
    """Offre au format des candidatures ; None hors IDF ou sans titre."""
    workplace = offre.get("workplace") or {}
    adresse = ((workplace.get("location") or {}).get("address")) or ""
    lieu = _localiser(adresse)
    if lieu is None:
        return None
    offer = offre.get("offer") or {}
    titre = offer.get("title") or ""
    if not titre or titre == "Sans titre":
        return None
    identifier = offre.get("identifier") or {}
    partner_id = identifier.get("partner_job_id") or identifier.get("id") or (titre + adresse)
    lien = ((offre.get("apply") or {}).get("url")
            or f"https://labonnealternance.apprentissage.beta.gouv.fr/emploi/{identifier.get('id', '')}")
    return {
        "id":           generer_id(f"lba_{partner_id}"),
        "titre":        titre,
        "entreprise":   workplace.get("name") or workplace.get("legal_name") or "Inconnue",
        "lieu":         adresse,
        "zone":         lieu[0],
        "domaine":      "Non analysé",
        "lien":         lien,
        "source":       "La Bonne Alternance",
        "description":  (offer.get("description") or "")[:5000],
        "date_trouvee": instant_depuis_api((offer.get("publication") or {}).get("creation")),
        "score":        0,
        "lettre":       "",
        "statut":       "nouveau",
        "_niveau":      _niveau(P.lire(offre, P.CHAMP_NIVEAU_OFFRE)),
    }


def _niveau(valeur) -> int | None:
    """Niveau européen lu dans une offre (« 6 »), None si absent ou illisible."""
    m = re.search(r"[3-8]", str(valeur or ""))
    return int(m.group(0)) if m else None


def normaliser_entreprise(brut: dict) -> dict | None:
    """Entreprise à fort potentiel au format de database.entreprises_db
    (ajouter_entreprises_lba) ; None hors IDF ou sans nom."""
    champs = {nom: P.premier(brut, chemins) for nom, chemins in P.CHAMPS_ENTREPRISE.items()}
    adresse = str(champs["adresse"] or "")
    lieu = _localiser(adresse)
    nom = str(champs["nom"] or champs["raison_sociale"] or "").strip()
    if lieu is None or not nom:
        return None
    siret = re.sub(r"\D", "", str(champs["siret"] or ""))
    siret = siret if len(siret) == 14 else ""
    email = str(champs["email"] or "").strip().lower()
    return {
        "siret":           siret,
        "siren":           siret[:9],
        "nom":             str(champs["raison_sociale"] or nom),
        "nom_commercial":  nom,
        "adresse":         adresse,
        "code_postal":     lieu[1],
        "departement":     lieu[2],
        "ville":           lieu[3],
        "taille":          str(champs["effectif"] or ""),
        "code_naf":        str(champs["code_naf"] or ""),
        "libelle_naf":     str(champs["libelle_naf"] or ""),
        "site_web":        str(champs["site_web"] or ""),
        "email":           email if RE_EMAIL.match(email) else "",
        "telephone":       str(champs["telephone"] or ""),
        "candidature_id":  str(champs["candidature_id"] or ""),
        "candidature_url": str(champs["candidature_url"] or ""),
        "identifiant":     str(champs["identifiant"] or ""),
    }


def _cle_entreprise(e: dict) -> str:
    return e["siret"] or e["identifiant"] or f"{e['nom_commercial']}|{e['adresse']}".lower()


# ─── Collecte ─────────────────────────────────────────────────────────────────
def centres() -> list[tuple]:
    """(nom, latitude, longitude, rayon) de la config, rayon ramené au maximum de l'API."""
    return [(nom, lat, lon, min(rayon, P.RAYON_MAX_KM)) for nom, lat, lon, rayon in LBA_CENTRES]


def sous_cercles(cercle: tuple) -> list[tuple]:
    """Sept cercles de rayon moitié qui recouvrent entièrement le cercle :
    un au centre, six autour à sqrt(3)/2 du rayon (recouvrement hexagonal)."""
    nom, lat, lon, rayon = cercle
    r, d = rayon / 2, rayon * math.sqrt(3) / 2
    km_lat, km_lon = 111.32, 111.32 * math.cos(math.radians(lat))
    out = [(nom, lat, lon, r)]
    for k in range(6):
        a = math.radians(60 * k)
        out.append((nom, round(lat + d * math.sin(a) / km_lat, 5), round(lon + d * math.cos(a) / km_lon, 5), r))
    return out


def decrire_cercle(cercle: tuple) -> str:
    nom, lat, lon, rayon = cercle
    return f"{nom} {rayon:g} km ({lat:.3f}, {lon:.3f})"


def _lots(codes: list[str]) -> list[list[str]]:
    taille = P.CODES_PAR_REQUETE or len(codes) or 1
    return [codes[i:i + taille] for i in range(0, len(codes), taille)] or [[]]


class CollecteLBA:
    """Résultats dédoublonnés de toutes les requêtes d'une recherche.

    Les requêtes (lot de codes, cercle) sont traitées en largeur : tous les
    centres de départ d'abord, puis les redécoupages, pour que la limite de
    requêtes (LBA_REQUETES_MAX) n'épuise pas tout sur Paris. Une réponse au
    plafond est redécoupée en sept cercles de rayon moitié, jusqu'à
    LBA_RAYON_MIN_KM, puis en deux moitiés du lot de codes ; ce qui reste au
    plafond est noté (self.au_plafond)."""

    def __init__(self, cle: str, log=print, avec_entreprises=True, redecouper_entreprises=False,
                 garder_entreprise=None, objectif_entreprises=None, connus=frozenset()):
        self.cle = cle
        self.log = log
        # Sans entreprises (recherche d'offres, D46) : elles sont ignorées
        self.avec_entreprises = avec_entreprises
        # Entreprises au plafond : redécoupées seulement si demandé (étape
        # « Récupérer » des spontanées) ; sinon seulement comptées
        self.redecouper_entreprises = redecouper_entreprises
        self.garder_entreprise = garder_entreprise or (lambda e: True)
        self.objectif_entreprises = objectif_entreprises
        self.connus = connus          # SIRET déjà en base : pas « nouvelles »
        self.offres = {}              # id -> offre normalisée
        self.entreprises = {}         # SIRET (ou identifiant) -> entreprise normalisée
        self.ecartees_taille = set()
        self.requetes = 0
        self.erreurs = 0
        self.hors_idf = set()
        self.relayees_ft = set()
        self.au_plafond = []          # (cercle, codes, « offres » ou « entreprises »), non redécoupables
        self.entreprises_non_redecoupees = []   # cercles au plafond d'entreprises laissés tels quels
        self.non_explores = 0         # requêtes laissées faute de budget

    def nouvelles_entreprises(self) -> int:
        """Entreprises reçues dont ni le SIRET ni le SIREN n'est déjà en base (D59)."""
        return sum(1 for cle, e in self.entreprises.items()
                   if cle not in self.connus and not (e.get("siren") and e["siren"] in self.connus))

    def _get(self, params: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.cle}", "Accept": "application/json"}
        for essai in (1, 2):
            if self.requetes:
                time.sleep(PAUSE_S)
            self.requetes += 1
            try:
                r = requests.get(P.URL_RECHERCHE, params=params, headers=headers, timeout=DELAI_S)
            except requests.RequestException as e:
                raise ErreurLBA(f"LBA injoignable ({type(e).__name__})") from None
            if r.status_code == 429 and essai == 1:
                time.sleep(ATTENTE_429_S)
                continue
            break
        if r.status_code in (401, 403):
            raise CleRefusee(f"clé refusée ({r.status_code}), vérifier LBA_API_KEY dans .env")
        if r.status_code != 200:
            raise ErreurLBA(f"LBA {r.status_code} : {r.text[:200]}")
        try:
            return r.json()
        except ValueError:
            raise ErreurLBA("réponse illisible") from None

    def parcourir(self, lots: list[list[str]], stop_event=None) -> None:
        file = deque((lot, c) for lot in lots for c in centres())
        while file:
            if stop_event and stop_event.is_set():
                self.log("  ⏹️  LBA : arrêt demandé, résultats déjà reçus gardés")
                return
            if self.objectif_entreprises is not None and self.nouvelles_entreprises() >= self.objectif_entreprises:
                self.log(f"  LBA : {self.objectif_entreprises} nouvelles entreprises atteintes, recherche arrêtée")
                return
            if self.requetes >= LBA_REQUETES_MAX:
                self.non_explores = len(file)
                self.log(f"  ⚠️  LBA : limite de {LBA_REQUETES_MAX} requêtes atteinte, "
                         f"{len(file)} recherches redécoupées non faites")
                return
            codes, cercle = file.popleft()
            file.extend(self.recuperer(codes, cercle))

    def recuperer(self, codes: list[str], cercle: tuple) -> list[tuple]:
        """Une requête ; retourne les requêtes de redécoupage à faire."""
        nom, lat, lon, rayon = cercle
        params = {P.PARAM_LATITUDE: lat, P.PARAM_LONGITUDE: lon, P.PARAM_RAYON: rayon, **P.PARAMS_EXCLUSION}
        if codes:
            params[P.PARAM_CODES] = ",".join(codes)
        try:
            corps = self._get(params)
        except CleRefusee:
            raise
        except ErreurLBA as e:
            self.erreurs += 1
            self.log(f"  ⚠️  LBA, requête abandonnée ({decrire_cercle(cercle)}, {len(codes)} codes) : {e}")
            return []
        par_source, total_offres, nb_entreprises = self._ajouter(corps)
        offres_pleines = (total_offres >= P.PLAFOND_TOTAL_OFFRES
                          or any(n >= P.PLAFOND_PAR_SOURCE for n in par_source.values()))
        entreprises_pleines = self.avec_entreprises and nb_entreprises >= P.PLAFOND_PAR_SOURCE
        if entreprises_pleines and not self.redecouper_entreprises and not offres_pleines:
            self.entreprises_non_redecoupees.append(cercle)
        if not (offres_pleines or (entreprises_pleines and self.redecouper_entreprises)):
            return []
        quoi = "offres" if offres_pleines else "entreprises"
        if rayon / 2 >= LBA_RAYON_MIN_KM:
            return [(codes, c) for c in sous_cercles(cercle)]
        if len(codes) > 1:
            moitie = len(codes) // 2
            return [(codes[:moitie], cercle), (codes[moitie:], cercle)]
        self.au_plafond.append((cercle, codes, quoi))
        return []

    def _ajouter(self, corps: dict) -> tuple[dict, int, int]:
        """Ajoute une réponse ; retourne (offres par source, offres, entreprises) reçues."""
        par_source = {}
        offres = corps.get(P.CLE_OFFRES) or []
        for brut in offres:
            source = str(P.lire(brut, P.CHAMP_PARTENAIRE) or "?")
            par_source[source] = par_source.get(source, 0) + 1
            ident = str(P.lire(brut, "identifier.id") or id(brut))
            if relayee_de_france_travail(brut):
                self.relayees_ft.add(ident)
                continue
            offre = _normaliser_offre_lba(brut)
            if offre is None:
                self.hors_idf.add(ident)
                continue
            self.offres.setdefault(offre["id"], offre)
        bruts = corps.get(P.CLE_ENTREPRISES) or []
        for brut in bruts if self.avec_entreprises else []:
            ent = normaliser_entreprise(brut)
            if ent is None:
                self.hors_idf.add(f"e{P.lire(brut, 'identifier.id') or id(brut)}")
                continue
            cle = _cle_entreprise(ent)
            if not self.garder_entreprise(ent):
                self.ecartees_taille.add(cle)
                continue
            self.entreprises.setdefault(cle, ent)
        return par_source, len(offres), len(bruts)


def chercher_lba(codes: list[str], log=print, stop_event=None, **options) -> dict | None:
    """Offres et entreprises à fort potentiel pour des codes métiers ([] :
    recherche sans code). options : celles de CollecteLBA
    (redecouper_entreprises, garder_entreprise, objectif_entreprises,
    connus). None si la clé manque ou est refusée avant tout résultat.
    stop_event : arrêt demandé, les résultats déjà reçus sont gardés."""
    cle = os.getenv("LBA_API_KEY")
    if not cle:
        log("  ⚠️  LBA ignorée : LBA_API_KEY manquante dans .env")
        return None
    lots = _lots(codes)
    log(f"  LBA : {len(codes) or 'aucun'} code(s) métier en {len(lots)} lot(s) × {len(LBA_CENTRES)} centres"
        + (", cercles au plafond d'entreprises redécoupés" if options.get("redecouper_entreprises") else ""))
    collecte = CollecteLBA(cle, log, **options)
    debut = time.monotonic()
    try:
        collecte.parcourir(lots, stop_event)
    except CleRefusee as e:
        log(f"  ⚠️  LBA arrêtée : {e}")
        if not (collecte.offres or collecte.entreprises):
            return None
    duree = time.monotonic() - debut
    log(f"  LBA : {len(collecte.offres)} offres"
        + (f" et {len(collecte.entreprises)} entreprises à fort potentiel" if options.get("avec_entreprises", True)
           else "")
        + f" distinctes en {collecte.requetes} requêtes ({duree:.0f} s)"
        + (f" ; {len(collecte.relayees_ft)} offres relayées de France Travail écartées" if collecte.relayees_ft else "")
        + (f" ; {len(collecte.ecartees_taille)} entreprises écartées par la taille ou le département"
           if collecte.ecartees_taille else "")
        + (f" ; {len(collecte.hors_idf)} résultats hors IDF écartés" if collecte.hors_idf else "")
        + (f" ; {collecte.erreurs} requêtes en erreur" if collecte.erreurs else ""))
    if collecte.au_plafond:
        exemples = ", ".join(f"{decrire_cercle(c)} [{q}]" for c, _, q in collecte.au_plafond[:5])
        log(f"  ⚠️  LBA : {len(collecte.au_plafond)} cercle(s) encore au plafond de {P.PLAFOND_PAR_SOURCE} "
            f"au rayon minimal ({LBA_RAYON_MIN_KM:g} km), peut-être incomplets : {exemples}")
    if collecte.entreprises_non_redecoupees:
        exemples = ", ".join(decrire_cercle(c) for c in collecte.entreprises_non_redecoupees[:5])
        log(f"  ℹ️  LBA : {len(collecte.entreprises_non_redecoupees)} cercle(s) au plafond de "
            f"{P.PLAFOND_PAR_SOURCE} entreprises, non redécoupés : {exemples}")
    return {"offres": list(collecte.offres.values()), "entreprises": list(collecte.entreprises.values()),
            "requetes": collecte.requetes, "au_plafond": len(collecte.au_plafond), "duree_s": duree}


# ─── Profil ───────────────────────────────────────────────────────────────────
def niveau_du_profil(profil: dict, log=print) -> int | None:
    """Niveau européen (3 à 7) du niveau visé du profil, None : aucun filtre."""
    texte = str((profil or {}).get("niveau_vise") or "").strip()
    if not texte:
        log("  LBA : niveau visé non renseigné dans le profil, aucun filtre de niveau")
        return None
    niveau = niveau_europeen(texte)
    if niveau is None:
        log(f"  LBA : niveau visé « {texte[:40]} » non reconnu, aucun filtre de niveau")
        return None
    log(f"  LBA : niveau visé « {texte[:40]} » : niveau {niveau} ({NIVEAUX[niveau]}), "
        "offres d'un autre niveau écartées, offres sans niveau gardées")
    return niveau


def filtrer_niveau(offres: list[dict], niveau: int | None) -> tuple[list[dict], int]:
    """Offres du niveau visé ou sans niveau indiqué (décision D38) ; (gardées, écartées)."""
    if niveau is None:
        return offres, 0
    gardees = [o for o in offres if o.get("_niveau") is None or o["_niveau"] == niveau]
    return gardees, len(offres) - len(gardees)


def filtre_entreprise(profil: dict):
    """Prédicat sur les entreprises : tailles des spontanées (D40, D55, D56, D63) et
    départements des candidatures spontanées d'après le code postal (D58).
    None si aucun filtre."""
    rech = normaliser_recherche((profil or {}).get("recherche") or {})
    tailles = rech.get("tailles_spontanees") or []
    inconnue = rech.get("taille_inconnue_spontanees", True)
    departements = set(rech.get("departements") or [])

    def garder(e):
        if departements and e.get("departement") not in departements:
            return False
        return garder_selon_taille(taille_entreprise(e.get("taille")), tailles, inconnue)
    return garder


def taille_entreprise(valeur) -> str | None:
    """Taille d'un effectif LBA (« 6-9 », « 50-99 ») ; « 0-0 » : sans
    salarié (D56) ; None si absent."""
    texte = str(valeur or "").strip()
    if not texte:
        return None
    if texte in P.TAILLES_SANS_SALARIE:
        return SANS_SALARIE
    return taille_depuis_tranche(texte)


def ignoree_pour_profil(profil: dict) -> str:
    """Raison pour laquelle LBA ne cherche rien pour ce profil, vide sinon."""
    if not codes_metiers(domaines_du_profil(profil or {})) and not P.ACCEPTE_SANS_CODES:
        return MESSAGE_INDIFFERENT
    return ""


def rechercher_pour_profil(profil: dict, log=print, stop_event=None, **options) -> dict | None:
    """chercher_lba avec les domaines du profil (indifférent : sans code),
    puis offres filtrées par le niveau visé et entreprises par la taille.
    None si LBA est ignorée (raison écrite dans les logs)."""
    if raison := ignoree_pour_profil(profil):
        log(f"ℹ️  {raison}")
        return None
    domaines = domaines_du_profil(profil)
    log(f"  LBA : domaines {', '.join(domaines) or 'indifférent (recherche sans code métier)'}")
    niveau = niveau_du_profil(profil, log)
    if options.get("avec_entreprises", True):
        options.setdefault("garder_entreprise", filtre_entreprise(profil))
    resultat = chercher_lba(codes_metiers(domaines), log, stop_event, **options)
    if resultat:
        resultat["offres"], ecartees = filtrer_niveau(resultat["offres"], niveau)
        if ecartees:
            log(f"  LBA : {ecartees} offres d'un autre niveau que le niveau {niveau} écartées")
    return resultat


def rechercher_offres_pour_profil(profil: dict, log=print) -> dict | None:
    """Recherche d'offres : les entreprises à fort potentiel sont ignorées,
    seule l'étape « Récupérer » des spontanées en ajoute (D46)."""
    return rechercher_pour_profil(profil, log, avec_entreprises=False)
