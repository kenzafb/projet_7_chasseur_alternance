"""
scripts/explorer_france_travail.py
==================================
Exploration de l'API Offres d'emploi v2 de France Travail, à lancer par
l'humain avec ses identifiants (FT_CLIENT_ID, FT_CLIENT_SECRET du .env) :

    venv/bin/python scripts/explorer_france_travail.py

1. Télécharge chaque référentiel de ROUTES_REFERENTIELS dans
   docs/referentiels/france_travail/<nom>.json. Une route absente (404) est
   notée et l'exploration continue. Un référentiel trop volumineux
   (communes, plus de TAILLE_MAX_OCTETS) n'est enregistré qu'en résumé :
   nombre d'éléments et premiers éléments.
2. Recherche sans autre filtre que la région Île-de-France : nombre total
   de résultats et filtres possibles renvoyés par l'API (types et natures
   de contrat avec leurs effectifs) dans repartition_idf.json.
3. Teste le plafond de pagination : demande les plages de
   PLAGES_PAGINATION sur cette même recherche et enregistre la réponse de
   l'API (code, en-têtes de plage, message) dans test_pagination.json.

Les fichiers produits ne contiennent que des données de l'API : ni
identifiant, ni secret, ni token (chaque texte écrit est en outre purgé de
ces valeurs). Un résumé est affiché à la fin. Code de sortie 1 si le token
ne peut pas être obtenu, 0 sinon.

La documentation officielle (francetravail.io, application JavaScript) n'a
pas pu être lue au moment de l'écriture : la liste des routes ci-dessous
vient des référentiels connus de l'API v2. La corriger ici au besoin.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import config  # noqa: E402  (charge le .env)

# ─── Configuration ────────────────────────────────────────────────────────────
URL_TOKEN = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
SCOPE = "api_offresdemploiv2 o2dsoffre"
URL_API = "https://api.francetravail.io/partenaire/offresdemploi/v2"

# Référentiels : nom du fichier -> route (relative à URL_API)
ROUTES_REFERENTIELS = {
    "metiers":            "/referentiel/metiers",
    "domaines":           "/referentiel/domaines",
    "appellations":       "/referentiel/appellations",
    "secteurs_activites": "/referentiel/secteursActivites",
    "natures_contrats":   "/referentiel/naturesContrats",
    "types_contrats":     "/referentiel/typesContrats",
    "niveaux_formations": "/referentiel/niveauxFormations",
    "themes":             "/referentiel/themes",
    "nafs":               "/referentiel/nafs",
    "permis":             "/referentiel/permis",
    "langues":            "/referentiel/langues",
    "regions":            "/referentiel/regions",
    "departements":       "/referentiel/departements",
    "continents":         "/referentiel/continents",
    "pays":               "/referentiel/pays",
    "communes":           "/referentiel/communes",
}
# Au-delà, seul un résumé est écrit (nombre d'éléments, premiers éléments)
TAILLE_MAX_OCTETS = 1_000_000
ELEMENTS_DANS_RESUME = 20

ROUTE_RECHERCHE = "/offres/search"
PARAMS_IDF = {"region": config.FT_REGION}
# Plages demandées pour le test de pagination (taille maximale annoncée : 150)
PLAGES_PAGINATION = [
    "0-149",       # référence
    "0-199",       # taille au-delà de 150
    "1000-1149",
    "1050-1199",   # franchit 1150
    "1150-1299",
    "2000-2149",
    "3000-3149",
    "3150-3299",
]

PAUSE_S = 0.5          # entre deux requêtes
DELAI_S = 30           # délai d'une requête
ATTENTE_429_S = 5      # une seule nouvelle tentative sur 429
DOSSIER_SORTIE = config.BASE_DIR / "docs" / "referentiels" / "france_travail"


# ─── Outils ───────────────────────────────────────────────────────────────────
class ErreurToken(Exception):
    pass


def _secrets() -> list[str]:
    return [v for v in (os.getenv("FT_CLIENT_ID"), os.getenv("FT_CLIENT_SECRET")) if v]


def purger(texte: str, secrets: list[str]) -> str:
    """Retire du texte toute valeur secrète (identifiants, token)."""
    texte = str(texte)
    for s in secrets:
        if s:
            texte = texte.replace(s, "***")
    return texte


def _message(reponse, secrets) -> str:
    """Message d'erreur de l'API, court et purgé."""
    try:
        corps = reponse.json()
        texte = corps.get("message") or corps.get("error_description") or corps.get("error") or json.dumps(corps)
    except (ValueError, AttributeError):
        texte = reponse.text or ""
    return purger(" ".join(str(texte).split())[:500], secrets)


def _total(content_range: str) -> int | None:
    """« offres 0-149/3456 » -> 3456."""
    try:
        return int(content_range.rsplit("/", 1)[1])
    except (IndexError, ValueError):
        return None


class Explorateur:
    def __init__(self, session=None, sortie: Path = DOSSIER_SORTIE, pause: float = PAUSE_S, afficher=print):
        self.session = session or requests.Session()
        self.sortie = Path(sortie)
        self.pause = pause
        self.afficher = afficher
        self.token = None
        self.secrets = _secrets()

    # ── HTTP ──
    def obtenir_token(self):
        identifiant, secret = os.getenv("FT_CLIENT_ID"), os.getenv("FT_CLIENT_SECRET")
        if not identifiant or not secret:
            raise ErreurToken("FT_CLIENT_ID ou FT_CLIENT_SECRET absent du .env.")
        try:
            r = self.session.post(URL_TOKEN, data={"grant_type": "client_credentials", "client_id": identifiant,
                                                   "client_secret": secret, "scope": SCOPE}, timeout=DELAI_S)
        except requests.RequestException as e:
            raise ErreurToken(f"Serveur d'authentification injoignable : {type(e).__name__}") from None
        if r.status_code != 200:
            raise ErreurToken(f"Token refusé ({r.status_code}) : {_message(r, self.secrets)}")
        self.token = r.json()["access_token"]
        self.secrets.append(self.token)

    def get(self, route: str, params: dict | None = None, entetes: dict | None = None):
        """GET authentifié ; une nouvelle tentative sur 429. None si injoignable."""
        for essai in (1, 2):
            time.sleep(self.pause)
            try:
                r = self.session.get(URL_API + route, params=params, timeout=DELAI_S,
                                     headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json",
                                              **(entetes or {})})
            except requests.RequestException as e:
                self.afficher(f"  {route} : injoignable ({type(e).__name__})")
                return None
            if r.status_code == 429 and essai == 1:
                attente = float(r.headers.get("Retry-After") or ATTENTE_429_S)
                self.afficher(f"  {route} : 429, nouvelle tentative dans {attente:.0f} s")
                time.sleep(attente)
                continue
            return r

    def ecrire(self, nom: str, donnees) -> Path:
        self.sortie.mkdir(parents=True, exist_ok=True)
        chemin = self.sortie / f"{nom}.json"
        texte = purger(json.dumps(donnees, ensure_ascii=False, indent=2), self.secrets)
        chemin.write_text(texte + "\n", encoding="utf-8")
        return chemin

    # ── 1. Référentiels ──
    def referentiels(self) -> dict:
        bilan = {}
        for nom, route in ROUTES_REFERENTIELS.items():
            r = self.get(route)
            if r is None:
                bilan[nom] = {"etat": "injoignable"}
            elif r.status_code == 404:
                bilan[nom] = {"etat": "absent (404)"}
            elif r.status_code != 200:
                bilan[nom] = {"etat": f"erreur {r.status_code}", "message": _message(r, self.secrets)}
            else:
                try:
                    donnees = r.json()
                except ValueError:
                    bilan[nom] = {"etat": "réponse illisible"}
                    self.afficher(f"  {nom} : réponse illisible")
                    continue
                nombre = len(donnees) if isinstance(donnees, list) else None
                contenu = {"route": route, "telecharge_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "nombre": nombre, "donnees": donnees}
                if len(r.content or b"") > TAILLE_MAX_OCTETS and isinstance(donnees, list):
                    contenu.update(donnees=donnees[:ELEMENTS_DANS_RESUME], resume_seulement=True,
                                   raison=f"liste de plus de {TAILLE_MAX_OCTETS} octets, seuls les "
                                          f"{ELEMENTS_DANS_RESUME} premiers éléments sont gardés")
                    bilan[nom] = {"etat": "résumé (trop volumineux)", "nombre": nombre}
                else:
                    bilan[nom] = {"etat": "ok", "nombre": nombre}
                self.ecrire(nom, contenu)
            self.afficher(f"  {nom:<20} {bilan[nom]['etat']}"
                          + (f", {bilan[nom]['nombre']} éléments" if bilan[nom].get("nombre") is not None else ""))
        return bilan

    # ── 2. Répartition Île-de-France ──
    def _libelles(self, nom: str) -> dict:
        """Code -> libellé d'un référentiel déjà téléchargé (vide sinon)."""
        chemin = self.sortie / f"{nom}.json"
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8")).get("donnees") or []
            return {d.get("code"): d.get("libelle") for d in donnees if isinstance(d, dict)}
        except (OSError, ValueError, AttributeError):
            return {}

    def repartition_idf(self) -> dict:
        r = self.get(ROUTE_RECHERCHE, params={**PARAMS_IDF, "range": "0-149"})
        if r is None or r.status_code not in (200, 206):
            resultat = {"parametres": PARAMS_IDF, "statut": getattr(r, "status_code", None),
                        "message": _message(r, self.secrets) if r is not None else "injoignable"}
            self.ecrire("repartition_idf", resultat)
            return resultat
        content_range = r.headers.get("Content-Range", "")
        try:
            corps = r.json()
        except ValueError:
            corps = {}
        filtres = corps.get("filtresPossibles") or []
        libelles = {"typeContrat": self._libelles("types_contrats"),
                    "natureContrat": self._libelles("natures_contrats")}
        par_filtre = {}
        for f in filtres:
            nom = f.get("filtre", "?")
            par_filtre[nom] = [
                {"valeur": a.get("valeurPossible"), "nombre": a.get("nbResultats"),
                 **({"libelle": libelles[nom].get(a.get("valeurPossible"))}
                    if libelles.get(nom, {}).get(a.get("valeurPossible")) else {})}
                for a in (f.get("agregation") or [])]
        resultat = {
            "parametres": PARAMS_IDF,
            "interroge_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "statut": r.status_code,
            "content_range": content_range,
            "accept_range": r.headers.get("Accept-Range", ""),
            "total": _total(content_range),
            "filtres": par_filtre,
            "filtres_possibles_bruts": filtres,
        }
        self.ecrire("repartition_idf", resultat)
        return resultat

    # ── 3. Plafond de pagination ──
    def test_pagination(self) -> dict:
        essais = []
        for plage in PLAGES_PAGINATION:
            r = self.get(ROUTE_RECHERCHE, params={**PARAMS_IDF, "range": plage})
            if r is None:
                essais.append({"range": plage, "statut": None, "message": "injoignable"})
                continue
            essai = {"range": plage, "statut": r.status_code,
                     "content_range": r.headers.get("Content-Range", ""),
                     "accept_range": r.headers.get("Accept-Range", "")}
            if r.status_code in (200, 206):
                try:
                    essai["nombre_resultats"] = len(r.json().get("resultats") or [])
                except ValueError:
                    essai["message"] = "réponse illisible"
            elif r.status_code != 204:
                essai["message"] = _message(r, self.secrets)
            essais.append(essai)
            self.afficher(f"  range {plage:<10} {r.status_code}"
                          + (f" : {essai['message'][:100]}" if essai.get("message") else "")
                          + (f", {essai['nombre_resultats']} résultats" if "nombre_resultats" in essai else ""))
        acceptees = [e["range"] for e in essais if e.get("statut") in (200, 206)]
        fin_max = max((int(p.split("-")[1]) for p in acceptees), default=None)
        resultat = {"parametres": PARAMS_IDF,
                    "teste_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "essais": essais, "plages_acceptees": acceptees,
                    "dernier_index_obtenu": fin_max}
        self.ecrire("test_pagination", resultat)
        return resultat


def resume(bilan, repartition, pagination, afficher=print):
    afficher("")
    afficher("══ Résumé ══")
    ok = [n for n, b in bilan.items() if b["etat"] == "ok"]
    autres = {n: b["etat"] for n, b in bilan.items() if b["etat"] != "ok"}
    afficher(f"Référentiels enregistrés : {len(ok)}/{len(bilan)}")
    for nom, etat in autres.items():
        afficher(f"  {nom} : {etat}")
    if repartition.get("total") is not None:
        afficher(f"Île-de-France sans filtre : {repartition['total']} offres")
        for filtre in ("typeContrat", "natureContrat"):
            valeurs = repartition.get("filtres", {}).get(filtre)
            if valeurs:
                afficher(f"  {filtre} : " + ", ".join(
                    f"{v.get('libelle') or v['valeur']} {v['nombre']}" for v in valeurs))
        manquants = [f for f in ("typeContrat", "natureContrat") if f not in repartition.get("filtres", {})]
        if manquants:
            afficher(f"  Filtres non renvoyés par l'API : {', '.join(manquants)}")
    else:
        afficher(f"Île-de-France : échec ({repartition.get('statut')}) {repartition.get('message', '')}")
    afficher(f"Pagination : plages acceptées {', '.join(pagination['plages_acceptees']) or 'aucune'} ; "
             f"dernier index obtenu {pagination['dernier_index_obtenu']}")
    for e in pagination["essais"]:
        if e.get("statut") not in (200, 206):
            afficher(f"  {e['range']} : {e.get('statut')} {e.get('message', '')[:120]}")


def main(session=None, sortie=DOSSIER_SORTIE, pause=PAUSE_S, afficher=print) -> int:
    explorateur = Explorateur(session=session, sortie=sortie, pause=pause, afficher=afficher)
    try:
        explorateur.obtenir_token()
    except ErreurToken as e:
        afficher(f"❌ {e}")
        return 1
    afficher(f"Fichiers écrits dans {explorateur.sortie}")
    afficher("Référentiels :")
    bilan = explorateur.referentiels()
    afficher("Recherche Île-de-France sans filtre :")
    repartition = explorateur.repartition_idf()
    afficher("Test de pagination :")
    pagination = explorateur.test_pagination()
    resume(bilan, repartition, pagination, afficher)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Exploration de l'API Offres d'emploi v2 de France Travail.")
    parser.add_argument("--sortie", type=Path, default=DOSSIER_SORTIE, help="dossier des fichiers produits")
    sys.exit(main(sortie=parser.parse_args().sortie))
