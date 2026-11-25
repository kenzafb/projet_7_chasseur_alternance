"""
offres/export_lba.py
====================
Entreprises à fort potentiel de La Bonne Alternance tirées de l'export
complet (/job/v1/export), plus de la recherche par cercles (D163) ; la
recherche reste pour les offres.

Mesuré le 22 novembre 2026 (scripts/audit_lba_export.py, profil
alternance M18, 75 92 93 94) : 3888 entreprises après les filtres du
profil par l'export, 2933 par la recherche, 955 en plus, 0 en moins.

  - Téléchargement en flux : l'export (environ 820 Mo, 420000 objets, offres
    et recruteurs mêlés) n'est jamais chargé en entier ni écrit tel quel ;
    il est décodé objet par objet pendant la réception (objets_en_flux), et
    seules les entreprises « recruteurs_lba » d'Île-de-France sont gardées,
    normalisées (la_bonne_alternance.normaliser_entreprise) avec leurs codes
    métiers, dans un fichier compact (JSON Lines compressé,
    DATA_DIR/lba_recruteurs_idf.jsonl.gz, quelques Mo).
  - Rafraîchi au plus une fois par semaine (FRAICHEUR_JOURS) : l'export est
    refait chaque nuit par LBA, deux appels par minute, URL valable deux
    minutes. Export injoignable : l'ancien fichier sert, avec un message.
  - Pour un profil : le fichier compact est relu ligne à ligne, filtré par
    les codes métiers du profil (indifférent : tous) puis par la taille et
    les départements des spontanées (filtre_entreprise).
"""

import codecs
import gzip
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from offres import la_bonne_alternance as lba
from offres import parametres_lba as P
from shared.config import DATA_DIR
from shared.domaines import codes_metiers, domaines_du_profil
from shared.journal import journaliser
from shared.liens import lien_http

FICHIER = DATA_DIR / "lba_recruteurs_idf.jsonl.gz"
META = DATA_DIR / "lba_recruteurs_idf.json"
# Sites web de l'export (workplace.website, offres et recruteurs), par SIREN :
# source sûre du scraper (D166) ; 328 offres et aucun recruteur en ont un
# dans l'export du 22 novembre 2026
SITES = DATA_DIR / "lba_sites_par_siren.json"
FRAICHEUR_JOURS = 7
PARTENAIRE_RECRUTEURS = "recruteurs_lba"
BLOC = 1 << 20
_verrou = threading.Lock()   # un seul téléchargement à la fois (plusieurs utilisateurs)


# ─── Lecture en flux ──────────────────────────────────────────────────────────
def objets_en_flux(morceaux):
    """Objets d'une liste JSON « [{...},{...}] » reçue par morceaux de texte,
    un à un ; le tampon ne garde que l'objet en cours."""
    dec = json.JSONDecoder()
    tampon, i = "", 0
    morceaux = iter(morceaux)
    fin = False
    while True:
        while i < len(tampon) and tampon[i] in " \t\r\n[,":
            i += 1
        if i < len(tampon) and tampon[i] == "]":
            return
        try:
            if i >= len(tampon):
                raise json.JSONDecodeError("fin du tampon", tampon, i)
            objet, i = dec.raw_decode(tampon, i)
        except json.JSONDecodeError:
            if fin:
                if i >= len(tampon):
                    return
                raise
            lu = next(morceaux, None)
            fin = lu is None
            tampon, i = tampon[i:] + (lu or ""), 0
            continue
        yield objet


def morceaux_de_fichier(chemin, bloc=BLOC):
    with open(chemin, encoding="utf-8") as f:
        while lu := f.read(bloc):
            yield lu


def morceaux_http(reponse, bloc=BLOC):
    dec = codecs.getincrementaldecoder("utf-8")()
    for octets in reponse.iter_content(bloc):
        if octets:
            yield dec.decode(octets)
    yield dec.decode(b"", final=True)


def recruteur_idf(brut: dict) -> dict | None:
    """Entreprise « recruteurs_lba » d'IDF normalisée, avec ses codes métiers ; None sinon."""
    if str(P.lire(brut, P.CHAMP_PARTENAIRE) or "") != PARTENAIRE_RECRUTEURS:
        return None
    ent = lba.normaliser_entreprise(brut)
    if ent is None:
        return None
    ent["romes"] = sorted(set(P.lire(brut, "offer.rome_codes") or []))
    return ent


def construire(objets, fichier=None) -> dict:
    """Écrit le fichier compact à partir des objets de l'export ; compteurs."""
    fichier = fichier or FICHIER
    tmp = fichier.with_name(fichier.name + ".tmp")
    lus = recruteurs = idf = 0
    sites = {}
    with gzip.open(tmp, "wt", encoding="utf-8") as sortie:
        for brut in objets:
            lus += 1
            siren = re.sub(r"\D", "", str(P.lire(brut, "workplace.siret") or ""))[:9]
            if len(siren) == 9 and (site := lien_http(P.lire(brut, "workplace.website"))):
                sites.setdefault(siren, site)
            if str(P.lire(brut, P.CHAMP_PARTENAIRE) or "") == PARTENAIRE_RECRUTEURS:
                recruteurs += 1
            if ent := recruteur_idf(brut):
                idf += 1
                sortie.write(json.dumps(ent, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, fichier)
    SITES.write_text(json.dumps(sites, ensure_ascii=False), encoding="utf-8")
    return {"objets_lus": lus, "recruteurs": recruteurs, "recruteurs_idf": idf, "sites_par_siren": len(sites)}


def sites_par_siren() -> dict[str, str]:
    """{SIREN: site web} de l'export (vide si pas encore téléchargé)."""
    try:
        return json.loads(SITES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ─── Fraîcheur et téléchargement ──────────────────────────────────────────────
def meta() -> dict:
    try:
        return json.loads(META.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def a_jour(maintenant=None) -> bool:
    m = meta()
    if not FICHIER.exists() or not m.get("le"):
        return False
    maintenant = maintenant or datetime.now(timezone.utc)
    return maintenant - datetime.fromisoformat(m["le"]) < timedelta(days=FRAICHEUR_JOURS)


def telecharger(cle: str, log=journaliser) -> dict:
    """Export demandé, lu en flux, fichier compact réécrit. ErreurLBA sinon."""
    entetes = {"Authorization": f"Bearer {cle}", "Accept": "application/json"}
    try:
        r = requests.get(P.URL_EXPORT, headers=entetes, timeout=60)
    except requests.RequestException as e:
        raise lba.ErreurLBA(f"export LBA injoignable ({type(e).__name__})") from None
    if r.status_code in (401, 403):
        raise lba.CleRefusee(f"clé refusée ({r.status_code}), vérifier LBA_API_KEY dans .env")
    if r.status_code != 200:
        raise lba.ErreurLBA(f"export LBA {r.status_code} : {r.text[:200]}")
    info = r.json()
    debut = time.monotonic()
    log(f"  LBA : export du {info.get('lastUpdate', '?')} en cours de lecture (en flux, IDF seulement)...")
    try:
        with requests.get(info["url"], stream=True, timeout=(30, 300)) as f:
            f.raise_for_status()
            compte = construire(objets_en_flux(morceaux_http(f)))
    except (requests.RequestException, KeyError, ValueError) as e:
        raise lba.ErreurLBA(f"lecture de l'export LBA interrompue ({type(e).__name__})") from None
    m = {"le": datetime.now(timezone.utc).isoformat(timespec="seconds"), "export_du": info.get("lastUpdate"),
         "duree_s": round(time.monotonic() - debut), **compte}
    META.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  LBA : {compte['recruteurs_idf']} entreprises à fort potentiel en Île-de-France gardées "
        f"sur {compte['recruteurs']} ({compte['objets_lus']} objets lus en {m['duree_s']} s)")
    return m


def preparer(log=journaliser) -> bool:
    """Fichier compact présent et de moins d'une semaine, sinon rafraîchi.
    False s'il n'y a rien d'utilisable (clé absente et aucun fichier)."""
    with _verrou:
        if a_jour():
            return True
        cle = os.getenv("LBA_API_KEY")
        if not cle:
            log("  ⚠️  LBA : LBA_API_KEY manquante dans .env, export non téléchargé")
            return FICHIER.exists()
        try:
            telecharger(cle, log)
            return True
        except lba.ErreurLBA as e:
            if FICHIER.exists():
                log(f"  ⚠️  LBA : {e} ; export du {meta().get('export_du', '?')} gardé")
                return True
            log(f"  ⚠️  LBA : {e}")
            return False


# ─── Profil ───────────────────────────────────────────────────────────────────
def recruteurs(codes=(), garder=None, fichier=None):
    """Entreprises du fichier compact (générateur) : codes métiers en commun
    avec codes (vide : toutes), puis garder(entreprise)."""
    codes = set(codes)
    with gzip.open(fichier or FICHIER, "rt", encoding="utf-8") as f:
        for ligne in f:
            ent = json.loads(ligne)
            if codes and not codes & set(ent.pop("romes", [])):
                continue
            ent.pop("romes", None)
            if garder is None or garder(ent):
                yield ent


def entreprises_pour_profil(profil: dict, log=journaliser):
    """Générateur des entreprises à fort potentiel du profil, ou None si
    l'export n'est pas disponible."""
    if not preparer(log):
        return None
    codes = codes_metiers(domaines_du_profil(profil or {}))
    m = meta()
    log(f"  LBA : entreprises à fort potentiel de l'export du {m.get('export_du', '?')} "
        f"({m.get('recruteurs_idf', '?')} en IDF), codes {len(codes) or 'tous (indifférent)'}, "
        "taille et départements du profil")
    return recruteurs(codes, lba.filtre_entreprise(profil))
