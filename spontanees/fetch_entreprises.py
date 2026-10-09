"""
spontanees/fetch_entreprises.py
===============================
Étape « Récupérer » des candidatures spontanées : entreprises à fort
potentiel de La Bonne Alternance, puis entreprises de l'API Sirene de
l'INSEE (3.11), sans priorité de l'une sur l'autre (décision D44).

Sirene (SPEC_SOURCES section 4, phase 5d) :
  - codes NAF du profil (shared.naf) : secteurs cœurs des domaines, toutes
    les tailles choisies ; secteurs choisis directement pour un profil
    indifférent ou un domaine sans correspondance ; secteurs transverses
    pour les unités légales de 250 salariés et plus seulement (tranche, ou
    catégorie ETI ou GE) ;
  - tailles du profil converties en tranches INSEE de l'unité légale, avec
    l'option « effectifs inconnus » (unités sans tranche, requête à part) ; « sans
    salarié » (NN, unités non employeuses) seulement si elle est cochée ;
    rien de coché : toutes les tailles sauf elle (D55) ;
  - départements du profil (rien de coché : toute l'Île-de-France) ;
  - la limite se remplit dans l'ordre du plan : cœurs, secteurs choisis,
    transverses seulement pour compléter ; répartition dans les logs ;
  - sièges actifs ; nomenclature NAF de shared.config.nomenclature_naf ;
  - pagination par curseur, sans plafond de résultats ;
  - une entreprise déjà en base (même SIRET, LBA comprise) n'est pas
    dupliquée : Sirene ajoute seulement sa source.

Ce qui dépend du comportement de l'API est lu dans
spontanees/parametres_sirene.py (vérifié par scripts/verifier_sirene.py).
"""

import os
import time

import requests

from database.entreprises_db import ajouter_entreprises, noter_source
from shared.config import DEPTS_IDF
from shared.criteres import normaliser_recherche
from shared.domaines import domaines_du_profil
from shared.modes import MODE_DEFAUT
from shared.naf import avertissement_sirene, secteurs_sirene
from shared.tailles import TAILLES_250_PLUS, tranches_insee
from spontanees import parametres_sirene as P

# Catégorie d'entreprise de chaque taille de 250 salariés et plus
CATEGORIES_PAR_TAILLE = {"250_4999": "ETI", "5000_plus": "GE"}

TRANCHES_EFFECTIF = {
    "NN": "0", "00": "0", "01": "1-2", "02": "3-5", "03": "6-9",
    "11": "10-19", "12": "20-49", "21": "50-99", "22": "100-199",
    "31": "200-249", "32": "250-499", "41": "500-999", "42": "1000-1999",
    "51": "2000-4999", "52": "5000-9999", "53": "10000+",
}



def _cle() -> str:
    return os.getenv("INSEE_API_KEY", "")


# ─── Requêtes ─────────────────────────────────────────────────────────────────
def _ou(variable: str, valeurs) -> str:
    valeurs = list(valeurs)
    return f"{variable}:{valeurs[0]}" if len(valeurs) == 1 else f"{variable}:({' OR '.join(valeurs)})"


def _paquets(valeurs: list, taille: int | None) -> list[list]:
    taille = taille or len(valeurs) or 1
    return [valeurs[i:i + taille] for i in range(0, len(valeurs), taille)]


def filtre_tailles(tailles) -> str:
    """Clause de taille des secteurs cœurs : tranches des tailles cochées,
    ou toutes sauf « sans salarié » (NN) si rien n'est coché (D55)."""
    return _ou(P.VARIABLE_TRANCHE, tranches_insee(tailles))


def filtre_inconnus(tailles, inconnue: bool) -> str | None:
    """Clause des unités sans tranche (effectif inconnu), cherchées par une
    requête à part si l'option est cochée (ou si rien n'est coché). Jamais
    dans un OU avec les tranches : en Lucene, « (tranche:(11 OR 12) OR
    -tranche:*) » exclut toute unité qui a une tranche, et la requête ne
    rendait plus rien (essai réel de la phase 6a : 0 cœur)."""
    return P.ABSENTS_PAR if (inconnue or not tailles) and P.ABSENTS_PAR else None


def filtre_grandes(tailles) -> str | None:
    """Clause des secteurs transverses : 250 salariés et plus (tranche) ou
    catégorie ETI ou GE, restreint aux tailles choisies ; None si le profil
    n'en choisit aucune de 250 salariés et plus."""
    grandes = [t for t in TAILLES_250_PLUS if not tailles or t in tailles]
    if not grandes:
        return None
    return (f"({_ou(P.VARIABLE_TRANCHE, tranches_insee(grandes))} OR "
            f"{_ou(P.VARIABLE_CATEGORIE, [CATEGORIES_PAR_TAILLE[t] for t in grandes])})")


def construire_query(codes, departements, variable_naf: str, filtre: str | None = None) -> str:
    clauses = ["etablissementSiege:true", "etatAdministratifUniteLegale:A", _ou(variable_naf, codes),
               _ou(P.VARIABLE_CODE_POSTAL, [f"{d}*" for d in departements])]
    return " AND ".join(clauses + ([filtre] if filtre else []))


def plan_sirene(profil: dict, log=print) -> list[tuple[str, str]]:
    """(groupe, requête) à faire pour un profil : groupes « cœurs »,
    « secteurs », « transverses ». Vide si rien n'est à chercher (raison
    écrite dans les logs)."""
    rech = normaliser_recherche((profil or {}).get("recherche") or {})
    domaines, secteurs = domaines_du_profil(profil or {}), rech.get("secteurs") or []
    if avertissement := avertissement_sirene(domaines, secteurs):
        log(f"ℹ️  {avertissement}")
    codes = secteurs_sirene(domaines, secteurs)
    variable = P.VARIABLE_NAF.get(codes["nomenclature"])
    if not variable:
        log(f"⚠️  Sirene : variable du code {codes['nomenclature']} inconnue (scripts/verifier_sirene.py), "
            "recherche en NAF rév. 2")
        codes = secteurs_sirene(domaines, secteurs, "NAFRev2")
        variable = P.VARIABLE_NAF["NAFRev2"]
    # Tailles des candidatures spontanées, distinctes de celles des offres (D63)
    tailles = rech.get("tailles_spontanees") or []
    inconnue = rech.get("taille_inconnue_spontanees", True)
    departements = rech.get("departements") or sorted(DEPTS_IDF)
    # Ordre du plan = ordre de remplissage de la limite : cœurs d'abord,
    # secteurs choisis, transverses seulement pour compléter
    inconnus = filtre_inconnus(tailles, inconnue)
    groupes = []
    for nom in ("cœurs", "secteurs"):
        groupes.append((nom, codes["coeurs" if nom == "cœurs" else "secteurs"], filtre_tailles(tailles)))
        if inconnus:
            groupes.append((nom, codes["coeurs" if nom == "cœurs" else "secteurs"], inconnus))
    if codes["transverses"]:
        grandes = filtre_grandes(tailles)
        if grandes:
            groupes.append(("transverses", codes["transverses"], grandes))
        else:
            log("ℹ️  Sirene : secteurs transverses non cherchés (aucune taille de 250 salariés et plus choisie)")
    plan = [(nom, construire_query(paquet, depts, variable, filtre))
            for nom, liste, filtre in groupes if liste
            for paquet in _paquets(liste, P.NAF_PAR_REQUETE)
            for depts in _paquets(departements, P.DEPARTEMENTS_PAR_REQUETE)]
    log(f"  Sirene ({codes['nomenclature']}) : "
        f"{len(codes['coeurs'])} codes cœurs, {len(codes['secteurs'])} codes de secteurs choisis, "
        f"{len(codes['transverses'])} codes transverses ; départements {', '.join(departements)} ; "
        f"tailles {', '.join(tailles) or 'toutes sauf sans salarié'}{' et inconnues' if tailles and inconnue else ''} ; "
        f"{len(plan)} recherches")
    return plan


# ─── Pagination ───────────────────────────────────────────────────────────────
class ErreurSirene(Exception):
    pass


class Collecte:
    def __init__(self, cle: str, log=print, sirens_connus=frozenset()):
        self.cle, self.log = cle, log
        self.requetes = 0
        self.erreurs = 0
        self.sirens_connus = sirens_connus   # entreprises déjà en base (D59)
        self.sirens_vus = set()
        self.annonce = None                  # total annoncé par la dernière requête

    def _page(self, q: str, curseur: str) -> dict | None:
        """Corps d'une page, None si aucun résultat (404)."""
        for essai in (1, 2):
            if self.requetes:
                time.sleep(P.PAUSE_S)
            self.requetes += 1
            try:
                r = requests.get(P.URL_RECHERCHE, params={"q": q, "nombre": P.PAR_PAGE, "curseur": curseur},
                                 headers={P.ENTETE_CLE: self.cle, "Accept": "application/json"}, timeout=30)
            except requests.RequestException as e:
                raise ErreurSirene(f"Sirene injoignable ({type(e).__name__})") from None
            if r.status_code == 429 and essai == 1:
                time.sleep(P.ATTENTE_429_S)
                continue
            break
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403):
            raise ErreurSirene(f"clé refusée ({r.status_code}), vérifier INSEE_API_KEY dans .env")
        if r.status_code != 200:
            raise ErreurSirene(f"Sirene {r.status_code} : {r.text[:200]}")
        try:
            return r.json()
        except ValueError:
            raise ErreurSirene("réponse illisible") from None

    def recuperer(self, q: str, entreprises: dict, plafond=None) -> int:
        """Toutes les pages d'une requête (curseur) ; nouvelles entreprises
        ajoutées à entreprises (SIRET -> infos). Les SIRET déjà en base sont
        notés vus par Sirene (D44), de même qu'un SIREN déjà en base (D59).
        Retourne le nombre de nouvelles."""
        curseur, nouvelles = "*", 0
        self.annonce = 0
        while True:
            corps = self._page(q, curseur)
            if corps is None:
                return nouvelles
            if curseur == "*":
                self.annonce = (corps.get("header") or {}).get("total")
            for etab in corps.get("etablissements") or []:
                if plafond is not None and len(entreprises) >= plafond:
                    return nouvelles
                infos = extraire_infos(etab)
                siret = infos["siret"]
                if siret and (entreprises.get(siret) or {}).get("_deja_en_base"):
                    entreprises[siret]["_vue_par_sirene"] = True
                elif infos["siren"] and infos["siren"] in self.sirens_connus:
                    self.sirens_vus.add(infos["siren"])     # autre établissement déjà en base (D59)
                elif siret and siret not in entreprises:
                    entreprises[siret] = infos
                    nouvelles += 1
            suivant = (corps.get("header") or {}).get("curseurSuivant")
            if not suivant or suivant == curseur or (plafond is not None and len(entreprises) >= plafond):
                return nouvelles
            curseur = suivant


# ─── Extraction des infos depuis un établissement Sirene ─────────────────────

def extraire_infos(etab):
    ul      = etab.get("uniteLegale") or {}
    adresse = etab.get("adresseEtablissement") or {}

    # Période courante = première période avec dateFin == null
    periodes = etab.get("periodesEtablissement") or {}
    periode  = next((p for p in periodes if p.get("dateFin") is None), periodes[0] if periodes else {})

    # Nom
    nom = (ul.get("denominationUniteLegale") or  "").strip()

    # Nom commercial : enseigne ou dénomination usuelle de l'établissement
    nom_commercial = (
        periode.get("enseigne1Etablissement")
        or periode.get("denominationUsuelleEtablissement")
        or None
    )

    # Adresse
    num         = adresse.get("numeroVoieEtablissement") or ""
    type_voie   = adresse.get("typeVoieEtablissement") or ""
    libelle_voie = adresse.get("libelleVoieEtablissement") or ""
    adresse_str = " ".join(filter(None, [num, type_voie, libelle_voie])).strip()

    code_postal = adresse.get("codePostalEtablissement", "") or ""
    ville       = adresse.get("libelleCommuneEtablissement", "") or ""
    departement = code_postal[:2] if len(code_postal) >= 2 else ""

    # Taille
    code_effectif = (
        ul.get("trancheEffectifsUniteLegale")
        or etab.get("trancheEffectifsEtablissement")
        or ""
    )
    taille = TRANCHES_EFFECTIF.get(code_effectif, code_effectif)

    # NAF de la période courante
    code_naf = periode.get("activitePrincipaleEtablissement", "")

    # Identifiants
    siret = etab.get("siret", "")
    siren = ul.get("siren") or (siret[:9] if siret else "")

    return {
        "nom":            nom,
        "nom_commercial": nom_commercial,
        "siret":          siret,
        "siren":          siren,
        "code_naf":       code_naf,
        "adresse":        adresse_str,
        "ville":          ville,
        "code_postal":    code_postal,
        "departement":    departement,
        "site_web":       None,
        "taille":         taille,
        "categorie":      ul.get("categorieEntreprise", ""),
        "ca":             None,   # Non disponible dans l'API Sirene
        "dirigeant":      "",     # Non disponible dans l'API Sirene
        "traite":         False,
        "emails_trouves": [],
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def enregistrer(user_id, entreprises: dict, sirens_vus=(), mode=MODE_DEFAUT) -> int:
    """Nouvelles entreprises du mode en base (une entreprise déjà connue
    dans un autre mode y est sélectionnée, sans doublon), et source
    « sirene » notée sur les entreprises du mode déjà connues (LBA) que
    Sirene a retrouvées, par SIRET ou par SIREN."""
    noter_source(user_id, [s for s, e in entreprises.items() if e.get("_vue_par_sirene")], "sirene",
                 sirens=sirens_vus)
    return ajouter_entreprises(user_id, [e for e in entreprises.values() if not e.get("_deja_en_base")], mode)


def entreprises_lba(user_id, profil, max_entreprises=None, stop_event=None, log_fn=print,
                    mode=MODE_DEFAUT) -> int:
    """Entreprises à fort potentiel de La Bonne Alternance (SPEC_SOURCES
    section 3). Retourne le nombre de nouvelles entreprises ajoutées (au
    plus max_entreprises)."""
    from france_travail.scraper_lba import rechercher_pour_profil
    from database.entreprises_db import ajouter_entreprises_lba, cles_connues
    from shared.config import LBA_RAYON_MIN_KM, LBA_REQUETES_MAX
    log_fn("🔍 La Bonne Alternance : entreprises à fort potentiel d'embauche d'alternants "
           f"(rayon minimal {LBA_RAYON_MIN_KM:g} km, au plus {LBA_REQUETES_MAX} requêtes, "
           "réglables dans shared/config.py)")
    # Cercles au plafond de 150 entreprises redécoupés (D36), jusqu'à
    # max_entreprises nouvelles
    lba = rechercher_pour_profil(profil, log=log_fn, stop_event=stop_event, redecouper_entreprises=True,
                                 objectif_entreprises=max_entreprises, connus=cles_connues(user_id, mode))
    if lba is not None:
        log_fn(f"⏱️  La Bonne Alternance terminée : {lba['requetes']} requêtes en "
               f"{int(lba['duree_s']) // 60} min {int(lba['duree_s']) % 60:02d} s")
    if not lba or not lba["entreprises"]:
        if lba is not None:
            log_fn("ℹ️  Aucune entreprise à fort potentiel trouvée sur LBA")
        return 0
    b = ajouter_entreprises_lba(user_id, lba["entreprises"], maximum=max_entreprises, mode=mode)
    log_fn(f"🏢 LBA : {b['ajoutees']} nouvelles entreprises à fort potentiel"
           + (f" (dont {b['avec_email']} avec un email fourni par LBA)" if b["avec_email"] else "")
           + (f", {b['deja_connues']} déjà connues" if b["deja_connues"] else "")
           + (f" dont {b['deux_sources']} trouvées aussi par Sirene" if b["deux_sources"] else "")
           + (f", {b['non_ajoutees']} laissées pour le prochain lancement (limite)" if b["non_ajoutees"] else ""))
    return b["ajoutees"]


def main(user_id, stop_event=None, on_progress=None, max_entreprises=None, log_fn=None, mode=MODE_DEFAUT):
    """Sélectionne dans le mode au plus max_entreprises NOUVELLES entreprises
    (None : toutes), de La Bonne Alternance (modes qui l'utilisent) et de
    Sirene, sans priorité de l'une sur l'autre (D44) : LBA a droit à la
    moitié de la limite, Sirene au reste (plus ce que LBA n'a pas utilisé).
    Une entreprise déjà connue dans un autre mode compte comme nouvelle
    pour ce mode ; ses données déjà scrapées sont reprises."""
    _log = log_fn if log_fn is not None else print
    from database.profil_db import lire_profil
    from shared.modes import get_mode
    profil = lire_profil(user_id, mode=mode)

    ajoutees_lba = 0
    if "lba" in get_mode(mode)["sources"]:
        part_lba = None if max_entreprises is None else (max_entreprises + 1) // 2
        ajoutees_lba = entreprises_lba(user_id, profil, part_lba, stop_event, _log, mode)
    if max_entreprises is not None:
        max_entreprises -= ajoutees_lba
        if max_entreprises <= 0:
            _log("⏹️  Limite de nouvelles entreprises atteinte : Sirene non interrogé.")
            return
    if stop_event and stop_event.is_set():
        return

    cle = _cle()
    if not cle:
        _log("❌  INSEE_API_KEY manquante dans le .env : Sirene non interrogé.")
        return
    plan = plan_sirene(profil, _log)
    if not plan:
        _log("ℹ️  Sirene : rien à chercher pour ce profil.")
        return

    # SIRET déjà dans le mode (Sirene ou LBA) : pas de doublon, seulement la source
    # notée ; une entreprise connue dans un autre mode sera sélectionnée dans celui-ci
    from database.entreprises_db import lire_entreprises
    existantes = lire_entreprises(user_id, mode)
    entreprises = {(e.get("_extra") or {}).get("siret"): {"_deja_en_base": True}
                   for e in existantes if (e.get("_extra") or {}).get("siret")}
    sirens = frozenset(e.get("siren") or ((e.get("_extra") or {}).get("siret") or "")[:9] for e in existantes) - {""}
    au_depart = len(entreprises)
    plafond = au_depart + max_entreprises if max_entreprises else None
    collecte, debut = Collecte(cle, _log, sirens), time.monotonic()
    # Tous les groupes du plan, dans l'ordre, même ceux qui ne donnent rien
    par_groupe = dict.fromkeys((g for g, _ in plan), 0)
    _log(f"🔍 Sirene : {len(plan)} recherches, cœurs d'abord, transverses pour compléter")
    for i, (groupe, q) in enumerate(plan, 1):
        if stop_event and stop_event.is_set():
            _log("⏹️  Arrêt demandé : entreprises déjà reçues enregistrées")
            break
        if plafond is not None and len(entreprises) >= plafond:
            _log(f"⏹️  Limite de {max_entreprises} nouvelles entreprises atteinte.")
            break
        try:
            n = collecte.recuperer(q, entreprises, plafond)
            par_groupe[groupe] += n
            inconnus = " (effectif inconnu)" if P.ABSENTS_PAR and P.ABSENTS_PAR in q else ""
            _log(f"  Sirene, {groupe}{inconnus} : {collecte.annonce or 0} établissements annoncés, {n} nouvelles")
        except ErreurSirene as e:
            collecte.erreurs += 1
            _log(f"  ⚠️  Sirene, recherche abandonnée ({groupe}) : {e}")
            if "clé refusée" in str(e):
                break
        if on_progress:
            on_progress(round(i / len(plan) * 100), f"{i}/{len(plan)} recherches · {len(entreprises) - au_depart} nouvelles")

    nb_ajoutees = enregistrer(user_id, entreprises, collecte.sirens_vus, mode)
    deja = sum(1 for e in entreprises.values() if e.get("_vue_par_sirene")) + len(collecte.sirens_vus)
    duree = time.monotonic() - debut
    _log(f"🏢 Sirene : {nb_ajoutees} nouvelles entreprises ("
         + ", ".join(f"{n} {g}" for g, n in par_groupe.items()) + ")"
         + (f", {deja} déjà en base retrouvées" if deja else "")
         + f" ; {collecte.requetes} requêtes en {int(duree) // 60} min {int(duree) % 60:02d} s"
         + (f", {collecte.erreurs} en erreur" if collecte.erreurs else ""))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=int, required=True,
                        help="ID de l'utilisateur pour lequel récupérer les entreprises")
    parser.add_argument("--mode", default=MODE_DEFAUT, help="mode où sélectionner les entreprises")
    args = parser.parse_args()
    main(user_id=args.user, mode=args.mode)
