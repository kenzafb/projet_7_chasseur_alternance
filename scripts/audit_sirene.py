"""
scripts/audit_sirene.py
=======================
Audit A3 (phase 15) : Sirene (INSEE, API 3.11). Ce que coûtent les filtres
de l'étape « Trouver des entreprises » (spontanees/recuperation.py), et la
pagination par curseur jusqu'au bout. Lecture seule, rien n'est enregistré.
À lancer par l'humain (INSEE_API_KEY du .env) :

    venv/bin/python scripts/audit_sirene.py --user 1 --mode alternance
    venv/bin/python scripts/audit_sirene.py --user 1 --mode stage --max-sirens 5000

Mesures, pour les codes NAF du profil (shared.naf.secteurs_sirene, cœurs,
secteurs choisis et transverses) et ses départements :
  1. requêtes réelles de l'application (plan_sirene) et leur total annoncé ;
  2. « siège uniquement » : établissements ACTIFS d'IDF qui ne sont pas des
     sièges (etablissementSiege:false, periode(etatAdministratifEtablissement:A)),
     puis, pour leurs SIREN (au plus --max-sirens), où est le siège : en IDF
     (l'entreprise est déjà trouvée par son siège) ou ailleurs (entreprise
     jamais trouvée, avec ses établissements d'IDF) ; répartition par taille ;
  3. sièges fermés : la requête n'exige que etatAdministratifUniteLegale:A ;
     sièges dont l'établissement n'est pas actif ;
  4. effectif : sièges actifs par tranche de l'unité légale (NN, absente,
     chaque tranche) : ce qu'écarte « toutes sauf sans salarié », chaque
     taille, l'option « effectifs inconnus » ; année de l'effectif
     (anneeEffectifsUniteLegale) sur 1000 sièges lus : ancienneté de
     l'information ;
  5. pagination : la plus grosse requête du plan est lue jusqu'au bout par
     la classe Collecte de l'application (curseur), puis par une boucle
     indépendante ; total annoncé, lus, distincts, pages, condition d'arrêt.

Documentation : API Sirene 3.11 sur portail-api.insee.fr (catalogue « API
Sirene », pages « Requêtes multicritères », « Pagination par curseur ») ;
INSEE, « Sirene Open Data, actualités septembre 2026 »
(https://www.insee.fr/fr/information/9053325) : « La pagination permet de
parcourir l'ensemble des résultats d'une requête », « un changement de la
dateDerniereMiseADisposition en cours de traitement peut entraîner des
incohérences » entre deux pages ; « Il existe dans le répertoire des unités
légales avec un état administratif actif dont tous les établissements sont
fermés » ; « activitePrincipaleNAF25UniteLegale et
activitePrincipaleNAF25Etablissement disparaîtront » (NAF 2025 au 1er
janvier 2027) ; V4 en bêta, 3.11 maintenue jusqu'à la mi-2028. Quota :
30 requêtes par minute (2,1 s entre deux).

Sortie : audit_exports/audit_sirene_<mode>.json.
"""

import argparse
import os
import time
from collections import Counter

import requests

from audit_commun import Chrono, ecrire_json, maintenant, pourcentage, session_lecture  # noqa: E402

from shared.config import DEPTS_IDF  # noqa: E402
from shared.criteres import normaliser_recherche  # noqa: E402
from shared.domaines import domaines_du_profil  # noqa: E402
from shared.naf import secteurs_sirene  # noqa: E402
from shared.tailles import TRANCHES_PAR_TAILLE  # noqa: E402
from spontanees import parametres_sirene as P  # noqa: E402
from spontanees import recuperation as R  # noqa: E402

PAUSE_S = 2.1


class Sirene:
    def __init__(self, cle: str):
        self.cle, self.requetes = cle, 0

    def get(self, q: str, nombre=1, curseur=None, champs=None) -> dict:
        params = {"q": q, "nombre": nombre}
        if curseur:
            params["curseur"] = curseur
        if champs:
            params["champs"] = champs
        for essai in (1, 2):
            time.sleep(PAUSE_S)
            self.requetes += 1
            r = requests.get(P.URL_RECHERCHE, params=params, timeout=60,
                             headers={P.ENTETE_CLE: self.cle, "Accept": "application/json"})
            if r.status_code == 429 and essai == 1:
                time.sleep(30)
                continue
            break
        if r.status_code == 404:
            return {"header": {"total": 0}, "etablissements": []}
        if r.status_code != 200:
            return {"erreur": r.status_code, "message": r.text[:300], "header": {"total": None}}
        return r.json()

    def total(self, q: str):
        corps = self.get(q)
        return corps["header"].get("total") if "erreur" not in corps else f"erreur {corps['erreur']} : {corps['message']}"


def profil(user, mode, base) -> dict:
    from database.models import Profil
    from database.profil_db import profil_vers_dict
    with session_lecture(base) as db:
        p = db.query(Profil).filter_by(user_id=user, mode=mode).first()
        return profil_vers_dict(p) if p else {}


def auditer(args) -> dict:
    cle = os.getenv("INSEE_API_KEY")
    if not cle:
        raise SystemExit("INSEE_API_KEY absente du .env.")
    s = Sirene(cle)
    prof = profil(args.user, args.mode, args.base)
    rech = normaliser_recherche(prof.get("recherche") or {})
    plan = R.plan_sirene(prof, print)
    codes = secteurs_sirene(domaines_du_profil(prof), rech.get("secteurs") or [])
    variable = P.VARIABLE_NAF[codes["nomenclature"]]
    tous_codes = list(dict.fromkeys(codes["coeurs"] + codes["secteurs"] + codes["transverses"]))[:P.NAF_PAR_REQUETE]
    depts = rech.get("departements") or sorted(DEPTS_IDF)
    res = {"le": maintenant(), "user": args.user, "mode": args.mode, "nomenclature": codes["nomenclature"],
           "codes": codes, "departements": depts}
    chrono = Chrono()

    # 1. Plan de l'application
    res["plan"] = [{"groupe": g, "q": q, "total": s.total(q)} for g, q in plan]
    print(f"  plan : {[(p['groupe'], p['total']) for p in res['plan']]}")
    if not tous_codes:
        res["note"] = "aucun code NAF pour ce profil : mesures 2 à 4 sans objet"
        return res

    activite = R._ou(variable, tous_codes)
    lieu = R._ou(P.VARIABLE_CODE_POSTAL, [f"{d}*" for d in depts])
    sieges = f"etablissementSiege:true AND etatAdministratifUniteLegale:A AND {activite} AND {lieu}"
    autres = (f"etablissementSiege:false AND periode(etatAdministratifEtablissement:A) AND "
              f"etatAdministratifUniteLegale:A AND {activite} AND {lieu}")

    # 2. Coût du « siège uniquement »
    total_autres = s.total(autres)
    sirens, curseur, lus = Counter(), "*", 0
    while len(sirens) < args.max_sirens:
        corps = s.get(autres, nombre=1000, curseur=curseur, champs="siren,siret,codePostalEtablissement,"
                                                                     "trancheEffectifsUniteLegale")
        etabs = corps.get("etablissements") or []
        lus += len(etabs)
        for e in etabs:
            sirens[e.get("siren") or (e.get("siret") or "")[:9]] += 1
        suivant = (corps.get("header") or {}).get("curseurSuivant")
        if not etabs or not suivant or suivant == curseur:
            break
        curseur = suivant
    liste = [x for x in sirens if x][:args.max_sirens]
    siege_idf, siege_ailleurs, tranches_ailleurs, sans_siege = set(), set(), Counter(), set(liste)
    for i in range(0, len(liste), 80):
        paquet = liste[i:i + 80]
        corps = s.get(f"etablissementSiege:true AND siren:({' OR '.join(paquet)})", nombre=1000,
                      champs="siren,codePostalEtablissement,trancheEffectifsUniteLegale")
        for e in corps.get("etablissements") or []:
            sans_siege.discard(e.get("siren"))
            cp = str(e.get("codePostalEtablissement") or "")
            if cp[:2] in DEPTS_IDF:
                siege_idf.add(e.get("siren"))
            else:
                siege_ailleurs.add(e.get("siren"))
                tranches_ailleurs[(e.get("uniteLegale") or {}).get("trancheEffectifsUniteLegale") or "absente"] += 1
    res["siege_uniquement"] = {
        "etablissements_actifs_non_sieges_idf": total_autres, "lus": lus, "sirens_distincts_lus": len(sirens),
        "sirens_verifies": len(liste), "siege_en_idf": len(siege_idf),
        "siege_hors_idf_entreprises_jamais_trouvees": pourcentage(len(siege_ailleurs), len(liste)),
        "etablissements_idf_de_ces_entreprises": sum(sirens[x] for x in siege_ailleurs),
        "tranches_unite_legale_hors_idf": dict(tranches_ailleurs), "siege_introuvable": len(sans_siege),
        "note": "les tailles du profil ne sont pas appliquées ici : on mesure le maximum perdu"}
    print(f"  siège ailleurs : {res['siege_uniquement']['siege_hors_idf_entreprises_jamais_trouvees']}")

    # 3. Sièges fermés malgré l'unité légale active
    res["sieges_fermes"] = {"sieges_ul_active": s.total(sieges),
                            "dont_etablissement_non_actif": s.total(
                                f"{sieges} AND -periode(etatAdministratifEtablissement:A)")}

    # 4. Effectif
    par_tranche = {t: s.total(f"{sieges} AND {P.VARIABLE_TRANCHE}:{t}")
                   for t in ["NN", *[t for v in TRANCHES_PAR_TAILLE.values() for t in v if t != "NN"]]}
    par_tranche["absente"] = s.total(f"{sieges} AND {P.ABSENTS_PAR}")
    total_sieges = res["sieges_fermes"]["sieges_ul_active"] or 0
    nombre = lambda v: v if isinstance(v, int) else 0  # noqa: E731
    par_taille = {cle: sum(nombre(par_tranche.get(t)) for t in tr) for cle, tr in TRANCHES_PAR_TAILLE.items()}
    corps = s.get(sieges, nombre=1000, champs="siren,trancheEffectifsUniteLegale,anneeEffectifsUniteLegale")
    annees = Counter(str((e.get("uniteLegale") or {}).get("anneeEffectifsUniteLegale")) for e in
                     corps.get("etablissements") or [])
    res["effectif"] = {"sieges": total_sieges, "par_tranche": par_tranche, "par_taille": par_taille,
                       "ecartes_par_defaut_NN": pourcentage(nombre(par_tranche["NN"]), total_sieges),
                       "somme_tranches_et_absente": sum(nombre(v) for v in par_tranche.values()),
                       "annee_effectif_sur_1000_sieges": dict(sorted(annees.items()))}
    print(f"  NN écartés par défaut : {res['effectif']['ecartes_par_defaut_NN']}")

    # 5. Pagination jusqu'au bout : la plus grosse requête du plan
    candidates = [p for p in res["plan"] if isinstance(p["total"], int)]
    if candidates:
        cible = max(candidates, key=lambda p: p["total"])
        if cible["total"] > args.max_pagination:
            cible = min((p for p in candidates if p["total"]), key=lambda p: abs(p["total"] - args.max_pagination))
        collecte, entreprises = R.Collecte(cle, print), {}
        n = collecte.recuperer(cible["q"], entreprises)
        vus, curseur, pages, fin = Counter(), "*", 0, ""
        while True:
            corps = s.get(cible["q"], nombre=1000, curseur=curseur, champs="siret")
            etabs = corps.get("etablissements") or []
            pages += 1
            for e in etabs:
                vus[e.get("siret")] += 1
            suivant = (corps.get("header") or {}).get("curseurSuivant")
            if not etabs:
                fin = "page vide"
                break
            if not suivant or suivant == curseur:
                fin = "curseurSuivant égal au curseur" if suivant else "pas de curseurSuivant"
                break
            curseur = suivant
        res["pagination"] = {"q": cible["q"], "total_annonce": cible["total"], "app_nouvelles": n,
                             "app_requetes": collecte.requetes, "independant_lus": sum(vus.values()),
                             "independant_distincts": len(vus), "doublons": sum(v - 1 for v in vus.values() if v > 1),
                             "pages": pages, "arret": fin}
        print(f"  pagination : annoncé {cible['total']}, application {n}, indépendant {len(vus)} ({fin})")
    res["requetes"], res["duree_s"] = s.requetes, chrono.s
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--user", type=int, required=True)
    ap.add_argument("--mode", default="alternance")
    ap.add_argument("--base", help="URL SQLite de la base (défaut : DATABASE_URL)")
    ap.add_argument("--max-sirens", type=int, default=3000, help="SIREN de non-sièges dont chercher le siège")
    ap.add_argument("--max-pagination", type=int, default=20000, help="taille max de la requête lue jusqu'au bout")
    args = ap.parse_args(argv)
    res = auditer(args)
    print("  ->", ecrire_json(f"audit_sirene_{args.mode}", res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
