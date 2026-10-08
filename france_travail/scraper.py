"""
france_travail/scraper.py
=========================
Recherche d'offres France Travail (API Offres d'emploi v2) en Île-de-France,
selon les critères du profil et du mode (shared.criteres).

Plafond de l'API (mesuré le 8 octobre 2026) : 150 offres par page, début de
plage au plus 3000, donc au plus 3150 offres par requête. Rien n'est tronqué
en silence : une requête qui dépasse est redécoupée par date de création
seulement (décision D31), en coupant la période en deux tant qu'une tranche
dépasse, jusqu'à l'heure ; les offres sont dédoublonnées par identifiant.
Départements et domaines ne servent qu'aux filtres choisis par l'utilisateur :
découper par eux perdait les offres sans département ou sans domaine. Ce qui
dépend du comportement de l'API (paramètres de domaine, valeurs multiples,
champ de tranche d'effectif, fenêtre de dates) est lu dans
france_travail/parametres_api.py.
"""

import itertools
import os
import time
from datetime import datetime, timedelta, timezone

import requests

from database.dates import instant_depuis_api
from database.dedup_db import lire_offres_vues, marquer_offres_vues
from france_travail import parametres_api
from shared.config import FT_REGION
from shared.criteres import criteres_france_travail
from shared.domaines import domaines_du_grand_domaine, est_grand_domaine
from shared.offres import detecter_zone, generer_id
from shared.tailles import garder_selon_taille, taille_depuis_tranche

URL_RECHERCHE = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
TAILLE_PAGE = 150
DEBUT_MAX = 3000
PLAFOND_REQUETE = DEBUT_MAX + TAILLE_PAGE      # 3150 offres au plus par requête
PAUSE_S = 0.4                                  # entre deux requêtes
ATTENTE_429_S = 5                              # une nouvelle tentative sur 429
FORMAT_DATE = "%Y-%m-%dT%H:%M:%SZ"


_token_cache = {"token": None, "expire": 0}


def get_token():
    if time.time() < _token_cache["expire"]:
        return _token_cache["token"]
    r = requests.post(
        "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire",
        data={
            "grant_type":    "client_credentials",
            "client_id":     os.getenv("FT_CLIENT_ID"),
            "client_secret": os.getenv("FT_CLIENT_SECRET"),
            "scope":         "api_offresdemploiv2 o2dsoffre",
        },
    )
    if r.status_code == 200:
        data = r.json()
        _token_cache["token"]  = data["access_token"]
        _token_cache["expire"] = time.time() + data["expires_in"] - 60
        return _token_cache["token"]
    print(f"Erreur token France Travail : {r.status_code} – {r.text}")
    return None


class ErreurFT(Exception):
    """Réponse inattendue de l'API pour une requête (les autres continuent)."""


def _page(params: dict, debut: int, token: str) -> tuple[int, list]:
    """(total, offres) d'une page de TAILLE_PAGE offres à partir de debut."""
    params = {**params, "range": f"{debut}-{debut + TAILLE_PAGE - 1}"}
    headers = {"Authorization": f"Bearer {token}"}
    for essai in (1, 2):
        try:
            r = requests.get(URL_RECHERCHE, params=params, headers=headers, timeout=15)
        except requests.RequestException as e:
            raise ErreurFT(f"France Travail injoignable ({type(e).__name__})") from None
        if r.status_code == 429 and essai == 1:
            time.sleep(float(r.headers.get("Retry-After") or ATTENTE_429_S))
            continue
        break
    if r.status_code == 204:
        return 0, []
    if r.status_code not in (200, 206):
        raise ErreurFT(f"FT {r.status_code} : {r.text[:200]}")
    try:
        resultats = r.json().get("resultats") or []
    except ValueError:
        raise ErreurFT("réponse illisible") from None
    try:
        total = int(r.headers.get("Content-Range", "").rsplit("/", 1)[1])
    except (IndexError, ValueError):
        total = debut + len(resultats)
    return total, resultats


def _decrire(params: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in params.items() if k != "sort")


# ─── Découpage par date de création (décision D31) ────────────────────────────
def _date(texte: str) -> datetime:
    return datetime.strptime(texte, FORMAT_DATE).replace(tzinfo=timezone.utc)


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _par_fenetre(params):
    """Les deux moitiés de la fenêtre de création de params (au départ :
    DATE_PLUS_ANCIENNE à maintenant plus la marge de fuseau), None sous
    une heure. Les moitiés partagent leur borne : une offre publiée à cette
    seconde-là est lue deux fois (dédoublonnée) plutôt que zéro, que l'API
    traite les bornes comme incluses ou exclues."""
    if "minCreationDate" in params:
        debut, fin = _date(params["minCreationDate"]), _date(params["maxCreationDate"])
    else:
        debut = _date(parametres_api.DATE_PLUS_ANCIENNE)
        fin = (_maintenant().replace(microsecond=0)
               + timedelta(hours=parametres_api.MARGE_FIN_FENETRE_HEURES))
    if fin - debut <= timedelta(hours=parametres_api.FENETRE_MIN_HEURES):
        return None
    milieu = (debut + (fin - debut) / 2).replace(microsecond=0)
    return [{**params, "minCreationDate": a.strftime(FORMAT_DATE), "maxCreationDate": b.strftime(FORMAT_DATE)}
            for a, b in ((debut, milieu), (milieu, fin))]


class Collecte:
    """Récupération d'un ensemble de requêtes, dédoublonnée.

    Avec un objectif (nombre d'offres retenues par le prédicat retenir :
    nouvelles, en IDF, de la bonne taille...), la récupération s'arrête dès
    qu'il est atteint : plus aucune page ni tranche demandée. Les pages
    arrivent des plus récentes aux plus anciennes (sort=1) et la tranche de
    dates la plus récente est lue d'abord : les offres obtenues sont les plus
    récentes de la requête."""

    def __init__(self, token: str, log=print, retenir=None, objectif: int | None = None):
        self.token = token
        self.log = log
        self.offres = {}          # identifiant -> offre brute
        self.requetes = 0
        self.non_recuperees = 0   # tranches d'une heure encore au-delà du plafond
        self.erreurs = 0
        self.retenir = retenir
        self.objectif = objectif
        self.retenues = set()     # identifiants des offres retenues

    @property
    def complet(self) -> bool:
        return self.objectif is not None and len(self.retenues) >= self.objectif

    def _page(self, params, debut):
        if self.requetes:
            time.sleep(PAUSE_S)
        self.requetes += 1
        return _page(params, debut, self.token)

    def _premiere_page(self, params):
        """(total, offres) de la première page, None si la requête échoue."""
        try:
            return self._page(params, 0)
        except ErreurFT as e:
            self.erreurs += 1
            self.log(f"  ⚠️  France Travail, requête abandonnée ({_decrire(params)}) : {e}")
            return None

    def recuperer(self, params: dict) -> None:
        """Récupère toutes les offres de params. Si la requête a dû être
        découpée, écrit le total annoncé par l'API, le nombre d'offres
        distinctes récupérées et l'écart."""
        if self.complet:
            return
        page = self._premiere_page(params)
        if page is None:
            return
        ids = set()
        if page[0] <= PLAFOND_REQUETE:
            self._recuperer(params, page, ids)
            return
        self._recuperer(params, page, ids)
        if self.complet:
            self.log(f"  Recherche découpée par date ({_decrire(params)}) : {page[0]} annoncées par l'API, "
                     f"arrêtée dès {self.objectif} nouvelles offres obtenues ({len(ids)} reçues)")
            return
        ecart = page[0] - len(ids)
        self.log(f"  Recherche découpée par date ({_decrire(params)}) : {page[0]} annoncées par l'API, "
                 f"{len(ids)} récupérées, écart {ecart}"
                 + (" (offres publiées ou retirées pendant la recherche si l'écart est faible)" if ecart else ""))

    def _recuperer(self, params: dict, page, ids: set) -> None:
        total, premiere = page
        if total > PLAFOND_REQUETE:
            sous = _par_fenetre(params)
            if sous:
                pages = [self._premiere_page(s) for s in sous]
                # Garde-fou : deux moitiés qui ont chacune le total entier =
                # dates ignorées par l'API ; continuer multiplierait les requêtes
                if not all(p and p[0] == total for p in pages):
                    # Tranche la plus récente d'abord, pour pouvoir s'arrêter tôt
                    for s, p in reversed(list(zip(sous, pages))):
                        if p and not self.complet:
                            self._recuperer(s, p, ids)
                    return
                self.log(f"  ⚠️  Découpage par date sans effet ({_decrire(sous[0])} renvoie les {total} "
                         "offres) : dates ignorées par l'API ? Voir scripts/verifier_france_travail.py")
            self.non_recuperees += total - PLAFOND_REQUETE
            self.log(f"  ⚠️  {total} offres ({_decrire(params)}), découpage impossible : "
                     f"{total - PLAFOND_REQUETE} non récupérées")
        self._ajouter(premiere, ids)
        debut = TAILLE_PAGE
        while (debut < min(total, PLAFOND_REQUETE) and len(premiere) == TAILLE_PAGE
               and not self.complet):
            try:
                _, resultats = self._page(params, debut)
            except ErreurFT as e:
                self.erreurs += 1
                self.log(f"  ⚠️  France Travail, page {debut} abandonnée ({_decrire(params)}) : {e}")
                break
            self._ajouter(resultats, ids)
            if len(resultats) < TAILLE_PAGE:
                break
            debut += TAILLE_PAGE

    def _ajouter(self, resultats, ids: set):
        for o in resultats:
            cle = o.get("id") or id(o)
            ids.add(cle)
            if cle not in self.offres:
                self.offres[cle] = o
                if self.retenir and self.retenir(o):
                    self.retenues.add(cle)


def _paquets(valeurs: list, taille: int | None) -> list[str]:
    """Valeurs réunies par paquets de taille (séparées par des virgules)."""
    if not taille or taille >= len(valeurs):
        return [",".join(valeurs)]
    return [",".join(valeurs[i:i + taille]) for i in range(0, len(valeurs), taille)]


def requetes_initiales(filtres: dict, domaines: list[str]) -> list[dict]:
    """Requêtes couvrant les critères : une valeur d'un même filtre ou une
    autre (OU), les filtres entre eux (ET). Grands domaines et domaines
    passent par des paramètres distincts, donc par des requêtes distinctes."""
    p_grand, p_dom = parametres_api.PARAM_GRAND_DOMAINE, parametres_api.PARAM_DOMAINE
    groupes = [None]
    if domaines:
        lettres = [c for c in domaines if est_grand_domaine(c)]
        codes = [c for c in domaines if not est_grand_domaine(c)]
        if lettres and not p_grand:
            codes += [d for lettre in lettres for d in domaines_du_grand_domaine(lettre)]
            lettres = []
        groupes = [(p, v) for p, v in ((p_grand, lettres), (p_dom, codes)) if v]
    requetes = []
    for groupe in groupes:
        axes = [(p, v) for p, v in filtres.items() if v] + ([groupe] if groupe else [])
        choix = [[(p, paquet) for paquet in _paquets(list(v), parametres_api.valeurs_par_requete(p))]
                 for p, v in axes]
        for combinaison in itertools.product(*choix):
            requetes.append({"region": FT_REGION, "sort": "1", **dict(combinaison)})
    return requetes


def recuperer_offres(criteres: dict, log=print, retenir=None, objectif: int | None = None) -> list:
    """Offres brutes de France Travail pour des critères, dédoublonnées.
    retenir, objectif : arrêt dès qu'objectif offres satisfont retenir
    (voir Collecte) ; sans objectif, tout est récupéré."""
    token = get_token()
    if not token:
        log("  ⚠️  France Travail : token refusé, aucune offre récupérée")
        return []
    requetes = requetes_initiales(criteres["filtres"], criteres["domaines"])
    collecte = Collecte(token, log, retenir=retenir, objectif=objectif)
    for params in requetes:
        collecte.recuperer(params)
    log(f"  France Travail : {len(collecte.offres)} offres distinctes reçues en {collecte.requetes} requêtes"
        + (f", arrêt dès {objectif} nouvelles offres obtenues" if collecte.complet else "")
        + (f", {collecte.erreurs} en erreur" if collecte.erreurs else "")
        + (f", {collecte.non_recuperees} non récupérées (plafond)" if collecte.non_recuperees else ""))
    return list(collecte.offres.values())


def _normaliser(bruts: list) -> list:
    offres = [o for o in map(_normaliser_une, bruts) if o is not None]
    if len(offres) < len(bruts):
        print(f"  {len(bruts) - len(offres)} offres hors IDF écartées")
    return offres


def _normaliser_une(offre: dict) -> dict | None:
    """Offre au format des candidatures, None hors IDF."""
    lien = offre.get("origineOffre", {}).get("urlOrigine", "")
    if not lien:
        lien = f"https://candidat.francetravail.fr/offres/recherche/detail/{offre.get('id', '')}"

    lieu = offre.get("lieuTravail", {}).get("libelle", "")
    zone = detecter_zone(lieu)
    if zone is None:
        return None

    # --- Enrichissement description ---
    desc = offre.get("description", "")

    # Description entreprise
    desc_entreprise = offre.get("entreprise", {}).get("description", "")
    if desc_entreprise:
        desc += f"\n\nEntreprise : {desc_entreprise}"

    # Infos contrat
    exp     = offre.get("experienceLibelle", "")
    duree   = offre.get("dureeTravailLibelleConverti", "")
    salaire = offre.get("salaire", {}).get("libelle", "")
    qualif  = offre.get("qualificationLibelle", "")
    secteur = offre.get("secteurActiviteLibelle", "")

    if exp:     desc += f"\nExpérience : {exp}"
    if duree:   desc += f"\nDurée : {duree}"
    if salaire: desc += f"\nSalaire : {salaire}"
    if qualif:  desc += f"\nQualification : {qualif}"
    if secteur: desc += f"\nSecteur : {secteur}"

    # Formations (~10% des offres mais critique pour détecter Bac+5)
    for f in offre.get("formations", []):
        niv       = f.get("niveauLibelle", "")
        domaine_f = f.get("domaineLibelle", "")
        exige     = "indispensable" if f.get("exigence") == "E" else "souhaitée"
        label     = " - ".join(filter(None, [domaine_f, niv]))
        if label: desc += f"\nFormation : {label} ({exige})"

    # Compétences (~10% des offres)
    for c in offre.get("competences", []):
        lib   = c.get("libelle", "")
        exige = "indispensable" if c.get("exigence") == "E" else "souhaitée"
        if lib: desc += f"\nCompétence : {lib} ({exige})"

    # Langues (rare mais utile)
    for l in offre.get("langues", []):
        lib   = l.get("libelle", "")
        exige = "indispensable" if l.get("exigence") == "E" else "souhaitée"
        if lib: desc += f"\nLangue : {lib} ({exige})"

    return {
        "id":           generer_id(offre.get("id", lien)),
        "titre":        offre.get("intitule", "Sans titre"),
        "entreprise":   offre.get("entreprise", {}).get("nom", "Inconnue"),
        "lieu":         lieu,
        "zone":         zone,
        "domaine":      "Non analysé",
        "lien":         lien,
        "source":       "France Travail",
        "description":  desc[:10000],
        "date_trouvee": instant_depuis_api(offre.get("dateCreation")),
        "score":        0,
        "lettre":       "",
        "statut":       "nouveau",
        "_alternance":  bool(offre.get("alternance", False)),
        "_taille":      taille_depuis_tranche(parametres_api.tranche_effectif(offre)),
    }


def chercher_offres(user_id, criteres=None, mode="alternance", limite_lot=None, marquer=True,
                    log=print) -> list:
    """Offres FT pas encore vues par cet utilisateur dans ce mode, les plus
    récentes d'abord. Avec limite_lot, la recherche s'arrête de télécharger
    dès limite_lot offres retenues (nouvelles, de la bonne taille...). criteres : shared.criteres.criteres_france_travail
    (défaut : ceux du mode, profil vide). Si marquer, les offres retenues
    (et, hors lots, toutes celles reçues) sont marquées vues en base ; sinon
    l'appelant les marque une à une après analyse. Les offres écartées par
    la taille ne sont pas marquées : elles reviennent si la taille change."""
    if criteres is None:
        criteres = criteres_france_travail({}, mode)
    print(f"Recherche FT (IDF, domaines : {', '.join(criteres['domaines']) or 'indifférent'}, "
          f"filtres : {criteres['filtres']})...")
    offres_vues = lire_offres_vues(user_id, mode)

    def retenue(brut) -> bool:
        """Offre qui comptera dans le lot : mêmes filtres que ci-dessous."""
        o = _normaliser_une(brut)
        return (o is not None and o["titre"] != "Sans titre" and o["id"] not in offres_vues
                and garder_selon_taille(o["_taille"], criteres["tailles"], criteres["taille_inconnue"])
                and not (criteres.get("exclure_alternance") and o["_alternance"]))

    # Avec un lot : téléchargement arrêté dès limite_lot offres retenues
    candidates = _normaliser(recuperer_offres(criteres, log=log, retenir=retenue, objectif=limite_lot))

    # Taille de l'établissement, filtrée après récupération (l'API ne la filtre pas)
    ecartees = {o["id"] for o in candidates
                if not garder_selon_taille(o["_taille"], criteres["tailles"], criteres["taille_inconnue"])}
    if ecartees:
        sans_info = sum(1 for o in candidates if o["id"] in ecartees and o["_taille"] is None)
        log(f"  {len(ecartees)} offres écartées par la taille d'entreprise"
            + (f" (dont {sans_info} sans information)" if sans_info else ""))
    candidates = [o for o in candidates if o["id"] not in ecartees]

    toutes_offres = [
        o for o in candidates
        if o["id"] not in offres_vues and o["titre"] != "Sans titre"
    ]

    # Mode job : les contrats d'alternance (CDD en apprentissage) sont écartés
    if criteres.get("exclure_alternance"):
        avant = len(toutes_offres)
        toutes_offres = [o for o in toutes_offres if not o.get("_alternance")]
        exclues = avant - len(toutes_offres)
        if exclues:
            print(f"  {exclues} offres d'alternance écartées (mode job)")

    # Le découpage mélange l'ordre de l'API : les plus récentes d'abord
    toutes_offres.sort(key=lambda o: o["date_trouvee"], reverse=True)

    # On traite par LOTS (ex. 100/run) pour ne pas tout analyser d'un coup
    if limite_lot:
        toutes_offres = toutes_offres[:limite_lot]
        if marquer:
            marquer_offres_vues(user_id, mode, {o["id"] for o in toutes_offres})
    elif marquer:
        marquer_offres_vues(user_id, mode, {o["id"] for o in candidates})

    print(f"\n{len(toutes_offres)} nouvelles offres FT trouvées (hors déjà vues) !\n")
    return toutes_offres


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=int, required=True, help="ID de l'utilisateur")
    parser.add_argument("--mode", default="alternance")
    args = parser.parse_args()
    offres = chercher_offres(args.user, mode=args.mode)
    print(f"\n-- Aperçu des 5 premières --")
    for o in offres[:5]:
        print(f"\n[{o['source']}] {o['titre']}")
        print(f"  Zone : {o['zone']} | {o['lieu']}")
        print(f"  Lien : {o['lien']}")
