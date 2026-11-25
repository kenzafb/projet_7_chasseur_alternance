"""
scripts/audit_france_travail.py
===============================
Audit A1 (phase 15) : ce que l'application récupère de France Travail,
comparé à ce que l'API contient vraiment. Lecture seule : rien n'est écrit
en base, aucune offre n'est marquée vue. À lancer par l'humain (FT_CLIENT_ID
et FT_CLIENT_SECRET du .env) :

    venv/bin/python scripts/audit_france_travail.py                 # trois modes, profils vides
    venv/bin/python scripts/audit_france_travail.py --mode stage
    venv/bin/python scripts/audit_france_travail.py --user 1        # critères des profils de l'utilisateur 1
    venv/bin/python scripts/audit_france_travail.py --hors-ligne    # seulement les paramètres envoyés (sans réseau)

Pour chaque mode :
  1. paramètres : les requêtes exactes que l'application envoie
     (offres.france_travail.requetes_initiales) et les filtres appliqués
     après récupération, dans l'ordre du code ;
  2. couverture : la collecte de l'application (même classe Collecte, sans
     objectif de lot) est rejouée en notant chaque page ; comparée au total
     annoncé par l'API (Content-Range) : offres distinctes, doublons reçus,
     tranches restées au plafond, puis un contrôle indépendant : les 150
     offres les plus récentes de chaque département (et des offres sans
     département) doivent toutes être dans la collecte ;
  3. écartées après récupération : « hors IDF » (detecter_zone sur le
     libellé du lieu) avec les libellés en cause, « Sans titre »,
     alternance, intitulé de stage, taille (répartition des tranches) ;
  4. domaines et secteurs : offres qu'aucun grand domaine ne trouve, et
     offres sans secteur d'activité (perdues dès qu'un domaine ou un secteur
     est choisi dans le profil) ;
  5. stage seulement : mots-clés « stage », « stagiaire », « internship »,
     « intern », « stage de fin d'études », « fin d'études », « convention
     de stage », et la liste « stage,stagiaire » (OU ou ET ?) ; offres
     trouvées par les autres mots-clés et pas par « stage », offres de
     « stage » écartées par l'intitulé (intitules_stage.txt) ou parce
     qu'elles sont aussi proposées en alternance.

Sortie : audit_exports/audit_france_travail_<mode>.json (titres, libellés,
identifiants d'offres, aucun jeton). Durée : quelques minutes par mode
(alternance ~ 30 requêtes, job ~ 200, stage ~ 30), 0,4 s entre deux.

Documentation : l'API Offres d'emploi v2 n'a pas de spécification OpenAPI
publique (data.gouv.fr, fiche « API Offres d'emploi » : « Documentation
machine (OpenAPI) manquante ») ; sa documentation est sur
https://francetravail.io/data/api/offres-emploi (compte requis). Les
comportements mesurés le 8 et le 9 octobre 2026 sont dans
scripts/verifications/france_travail/verification_api.json et
verification_stage.json ; ce script enregistre les réponses réelles
(messages d'erreur de l'API compris) pour chaque point.
"""

import argparse
from collections import Counter

from audit_commun import (Chrono, ecrire_json, maintenant, mots_ecole_trouves, organismes_trouves,  # noqa: E402
                          pourcentage, session_lecture)

from offres import france_travail as ft  # noqa: E402
from offres import parametres_france_travail as P  # noqa: E402
from shared.config import DEPTS_IDF, FT_REGION  # noqa: E402
from shared.criteres import criteres_france_travail  # noqa: E402
from shared.intitules_stage import designe_un_stage  # noqa: E402
from shared.modes import MODES  # noqa: E402
from shared.tailles import TAILLES, garder_selon_taille, taille_depuis_tranche  # noqa: E402

MOTS_STAGE = ["stage", "stagiaire", "internship", "intern", "stage de fin d'études", "fin d'études",
              "convention de stage", "stage,stagiaire"]
GRANDS_DOMAINES = list("ABCDEFGHIJKLMN")
EXEMPLES = 40


# ─── Collecte instrumentée ────────────────────────────────────────────────────
class CollecteNotee(ft.Collecte):
    """La Collecte de l'application, chaque page notée (paramètres, début,
    total annoncé, offres reçues)."""

    def __init__(self, token, log=print):
        super().__init__(token, log=log)
        self.pages = []
        self.recus = Counter()        # identifiant -> nombre de fois reçu

    def _page(self, params, debut):
        total, resultats = super()._page(params, debut)
        self.pages.append({"params": {k: v for k, v in params.items() if k != "sort"}, "debut": debut,
                           "total": total, "recus": len(resultats)})
        for o in resultats:
            self.recus[o.get("id") or "(sans id)"] += 1
        return total, resultats


def compter(token, params: dict) -> dict:
    """Total annoncé d'une requête (une page de 1 offre), ou l'erreur de l'API."""
    import requests
    r = requests.get(ft.URL_RECHERCHE, params={**params, "range": "0-0"},
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    ft.time.sleep(ft.PAUSE_S)
    if r.status_code == 204:
        return {"statut": 204, "total": 0}
    if r.status_code not in (200, 206):
        return {"statut": r.status_code, "total": None, "message": r.text[:300]}
    try:
        total = int(r.headers.get("Content-Range", "").rsplit("/", 1)[1])
    except (IndexError, ValueError):
        total = None
    return {"statut": r.status_code, "total": total}


def premiere_page(token, params: dict) -> list:
    try:
        return ft._page({**params, "sort": "1"}, 0, token)[1]
    except ft.ErreurFT:
        return []
    finally:
        ft.time.sleep(ft.PAUSE_S)


def collecter(token, requetes: list[dict]) -> CollecteNotee:
    c = CollecteNotee(token, log=lambda m: print(m))
    for params in requetes:
        c.recuperer(params)
    return c


# ─── Mesures ──────────────────────────────────────────────────────────────────
def filtres_apres_recuperation(criteres: dict) -> list[str]:
    """Filtres de chercher_offres, dans l'ordre du code."""
    f = ["lieu : detecter_zone(lieuTravail.libelle) doit lire un département d'IDF avant « - » (sinon « hors IDF »)",
         "intitulé : « Sans titre » écarté",
         "déjà vues : offres_vues (user, mode)",
         f"taille : garder_selon_taille({P.CHAMP_TRANCHE_EFFECTIF}, tailles={criteres['tailles']}, "
         f"taille_inconnue={criteres['taille_inconnue']})"]
    if criteres.get("exclure_alternance"):
        f.append("alternance : champ « alternance » de l'offre vrai -> écartée")
    if criteres.get("intitules_stage"):
        f.append("intitulé de stage : designe_un_stage(intitulé), règles shared/referentiels/intitules_stage.txt")
    return f


def couverture(token, requetes, collecte: CollecteNotee) -> dict:
    totaux = [compter(token, {k: v for k, v in q.items() if k != "sort"}) for q in requetes]
    annonce = sum(t["total"] or 0 for t in totaux)
    distinctes = len(collecte.offres)
    doublons = sum(n - 1 for n in collecte.recus.values() if n > 1)
    feuilles = [p for p in collecte.pages if p["debut"] == 0 and p["total"] <= ft.PLAFOND_REQUETE]
    res = {
        "requetes": [{"params": {k: v for k, v in q.items() if k != "sort"}, **t} for q, t in zip(requetes, totaux, strict=True)],
        "total_annonce": annonce,
        "note_total": "somme des totaux des requêtes initiales : une offre trouvée par deux requêtes (deux paquets "
                      "de valeurs) y compte deux fois",
        "distinctes_recuperees": distinctes,
        "ecart": annonce - distinctes,
        "pages_demandees": len(collecte.pages),
        "receptions_en_double": doublons,
        "sans_identifiant": collecte.recus.get("(sans id)", 0),
        "non_recuperees_plafond": collecte.non_recuperees,
        "erreurs": collecte.erreurs,
        "tranches_feuilles": len(feuilles),
        "somme_totaux_feuilles": sum(p["total"] for p in feuilles),
    }
    # Contrôle indépendant : les plus récentes de chaque département
    # (et de la région hors départements) sont-elles toutes dans la collecte ?
    manquantes, verifiees = [], 0
    for q in requetes:
        base = {k: v for k, v in q.items() if k not in ("sort", "region")}
        for dept in sorted(DEPTS_IDF):
            for o in premiere_page(token, {**base, "departement": dept}):
                verifiees += 1
                if o.get("id") not in collecte.offres:
                    manquantes.append({"id": o.get("id"), "departement": dept, "dateCreation": o.get("dateCreation"),
                                       "intitule": o.get("intitule")})
    res["controle_par_departement"] = {"offres_verifiees": verifiees, "absentes_de_la_collecte": len(manquantes),
                                       "exemples": manquantes[:EXEMPLES]}
    return res


def ecartees(collecte: CollecteNotee, criteres: dict) -> dict:
    bruts = list(collecte.offres.values())
    hors_idf = [o for o in bruts if ft._normaliser_une(o) is None]
    libelles = Counter((o.get("lieuTravail") or {}).get("libelle") or "(vide)" for o in hors_idf)
    communes = Counter(str((o.get("lieuTravail") or {}).get("commune") or "")[:2] for o in hors_idf)
    normalisees = [o for o in map(ft._normaliser_une, bruts) if o]
    tranches = Counter(str(P.tranche_effectif(o)) for o in bruts)
    tailles = Counter(taille_depuis_tranche(P.tranche_effectif(o)) or "inconnue" for o in bruts)
    res = {
        "recues": len(bruts),
        "hors_idf": {"nombre": len(hors_idf), "part": pourcentage(len(hors_idf), len(bruts)),
                     "libelles": libelles.most_common(30),
                     "prefixe_code_commune": communes.most_common(15),
                     "note": "region=11 est envoyé : une offre « hors IDF » ici est une offre d'IDF dont le libellé "
                             "ne commence pas par « NN - »"},
        "sans_titre": sum(1 for o in normalisees if o["titre"] == "Sans titre"),
        "alternance": sum(1 for o in normalisees if o["_alternance"]),
        "tranche_effectif_brute": tranches.most_common(25),
        "taille": dict(tailles),
        "ecartees_par_taille_selon_le_choix": {
            t["cle"]: sum(1 for o in normalisees if not garder_selon_taille(o["_taille"], [t["cle"]], True))
            for t in TAILLES},
        "ecartees_par_taille_profil": sum(1 for o in normalisees if not garder_selon_taille(
            o["_taille"], criteres["tailles"], criteres["taille_inconnue"])),
    }
    # Alternance : archivage « école/CFA » par mots-clés (offres.analyse.est_ecole_cfa)
    touchees = [(o, mots_ecole_trouves(o)) for o in normalisees]
    touchees = [(o, m) for o, m in touchees if m]
    res["archivage_ecole_cfa"] = {
        "nombre": pourcentage(len(touchees), len(normalisees)),
        "par_mot": Counter(m for _, ms in touchees for m in ms).most_common(30),
        "exemples": [{"titre": o["titre"], "entreprise": o["entreprise"], "mots": m} for o, m in touchees[:EXEMPLES]],
        "note": "liste d'avant D156, appliquée en mode alternance seulement (archivage_mots_cles)"}
    apres = [(o, organismes_trouves(o)) for o in normalisees]
    apres = [(o, m) for o, m in apres if m]
    res["archivage_ecole_cfa_apres_D156"] = {
        "nombre": pourcentage(len(apres), len(normalisees)),
        "par_organisme": Counter(m for _, ms in apres for m in ms).most_common(30),
        "plus_archivees": [{"titre": o["titre"], "entreprise": o["entreprise"], "mots_d_avant": m}
                           for o, m in touchees if not organismes_trouves(o)][:EXEMPLES]}
    if criteres.get("intitules_stage"):
        rejet = [o for o in normalisees if not designe_un_stage(o["titre"])]
        res["intitule_stage_rejete"] = {"nombre": len(rejet), "titres": [o["titre"] for o in rejet][:200]}
    return res


def domaines_et_secteurs(token, requetes, collecte: CollecteNotee) -> dict:
    """Offres qu'aucun grand domaine ne trouve (perdues dès qu'un domaine est
    choisi) et offres sans secteur d'activité (perdues dès qu'un secteur est choisi)."""
    res = {}
    for q in requetes[:1]:
        base = {k: v for k, v in q.items() if k != "sort"}
        sans = compter(token, base)["total"] or 0
        paquets = [GRANDS_DOMAINES[i:i + 5] for i in range(0, len(GRANDS_DOMAINES), 5)]
        par_lettre = {g: compter(token, {**base, P.PARAM_GRAND_DOMAINE: g})["total"] for g in GRANDS_DOMAINES}
        union = sum(compter(token, {**base, P.PARAM_GRAND_DOMAINE: ",".join(p)})["total"] or 0 for p in paquets)
        res["domaines"] = {"requete": base, "total_sans_domaine": sans, "union_des_14_grands_domaines": union,
                           "par_grand_domaine": par_lettre, "hors_de_tout_grand_domaine": sans - union}
    bruts = list(collecte.offres.values())
    sans_secteur = [o for o in bruts if not o.get("secteurActivite")]
    sans_rome = [o for o in bruts if not o.get("romeCode")]
    res["secteurs"] = {"sans_secteurActivite": pourcentage(len(sans_secteur), len(bruts)),
                       "exemples": [o.get("intitule") for o in sans_secteur[:15]]}
    res["rome"] = {"sans_romeCode": pourcentage(len(sans_rome), len(bruts)),
                   "exemples": [o.get("intitule") for o in sans_rome[:15]]}
    return res


def stage(token) -> dict:
    """Mots-clés du stage : ce que « stage » rate, ce que le filtre d'intitulé rejette."""
    base = {"region": FT_REGION, "sort": "1"}
    ensembles, res = {}, {"mots_cles": {}}
    for mot in MOTS_STAGE:
        c = collecter(token, [{**base, "motsCles": mot}])
        ensembles[mot] = c.offres
        res["mots_cles"][mot] = {"total": compter(token, {"region": FT_REGION, "motsCles": mot}),
                                 "recuperees": len(c.offres)}
    ids_stage = set(ensembles["stage"])
    union = set(ensembles["stage"]) | set(ensembles["stagiaire"])
    res["liste_stage_stagiaire"] = {"union_des_deux": len(union), "liste": len(ensembles["stage,stagiaire"]),
                                    "lecture": "OU si la liste vaut l'union, ET si elle vaut l'intersection"}
    hors_stage = {}
    for mot, offres in ensembles.items():
        if mot in ("stage", "stage,stagiaire"):
            continue
        extra = [o for i, o in offres.items() if i not in ids_stage]
        hors_stage[mot] = {"nombre": len(extra), "offres": [{
            "id": o.get("id"), "intitule": o.get("intitule"), "garde_par_intitule": designe_un_stage(o.get("intitule") or ""),
            "alternance": bool(o.get("alternance")), "natureContrat": o.get("natureContrat"),
            "typeContrat": o.get("typeContrat")} for o in extra[:EXEMPLES]]}
    res["trouvees_sans_le_mot_stage"] = hors_stage
    offres = list(ensembles["stage"].values())
    norm = [n for n in map(ft._normaliser_une, offres) if n]
    res["mot_stage"] = {
        "recues": len(offres),
        "intitule_sans_stage_ni_stagiaire": [o.get("intitule") for o in offres
                                             if not any(m in (o.get("intitule") or "").lower()
                                                        for m in ("stage", "stagiaire"))][:EXEMPLES],
        "rejetees_par_intitule": [n["titre"] for n in norm if not designe_un_stage(n["titre"])],
        "ecartees_car_alternance": [{"titre": n["titre"], "garde_par_intitule": designe_un_stage(n["titre"])}
                                    for n in norm if n["_alternance"]],
        "gardees_au_final": sum(1 for n in norm if not n["_alternance"] and designe_un_stage(n["titre"])),
    }
    return res


def gardees(token, criteres: dict) -> dict:
    """Offres que chercher_offres garderait pour ces critères (sans le filtre
    « déjà vues ») : lieu, intitulé, taille, alternance, intitulé de stage."""
    c = collecter(token, ft.requetes_initiales(criteres["filtres"], criteres["domaines"]))
    norm = [n for n in map(ft._normaliser_une, c.offres.values()) if n]
    res = [n for n in norm if n["titre"] != "Sans titre"
           and garder_selon_taille(n["_taille"], criteres["tailles"], criteres["taille_inconnue"])
           and not (criteres.get("exclure_alternance") and n["_alternance"])
           and (not criteres.get("intitules_stage") or designe_un_stage(n["titre"]))]
    return {"requetes": c.requetes, "recues": len(c.offres), "en_idf": len(norm), "gardees": len(res),
            "ids": {n["id"]: n["titre"] for n in res}}


def avant_apres_stage(token, criteres: dict, profil: dict) -> dict:
    """D152 : avant, motsCles=stage et domaines du profil ; après, les critères
    actuels (stage et stagiaire, sans domaine)."""
    avant_c = {**criteres, "filtres": {**criteres["filtres"], "motsCles": ["stage"]},
               "domaines": ((profil.get("recherche") or {}).get("domaines") or [])}
    avant, apres = gardees(token, avant_c), gardees(token, criteres)
    nouvelles = {i: t for i, t in apres["ids"].items() if i not in avant["ids"]}
    perdues = {i: t for i, t in avant["ids"].items() if i not in apres["ids"]}
    return {"avant": {k: v for k, v in avant.items() if k != "ids"} | {"domaines": avant_c["domaines"]},
            "apres": {k: v for k, v in apres.items() if k != "ids"},
            "ajoutees": len(nouvelles), "perdues": len(perdues),
            "exemples_ajoutees": list(nouvelles.values())[:EXEMPLES], "exemples_perdues": list(perdues.values())}


# ─── Main ─────────────────────────────────────────────────────────────────────
def profil_du_mode(mode: str, user: int | None, base: str | None) -> dict:
    if not user:
        return {}
    from database.models import Profil
    from database.profil_db import profil_vers_dict
    with session_lecture(base) as db:
        p = db.query(Profil).filter_by(user_id=user, mode=mode).first()
        return profil_vers_dict(p) if p else {}


def criteres_du_mode(mode: str, user: int | None, base: str | None) -> dict:
    return criteres_france_travail(profil_du_mode(mode, user, base), mode)


def auditer(mode: str, user, base, hors_ligne: bool) -> dict:
    criteres = criteres_du_mode(mode, user, base)
    requetes = ft.requetes_initiales(criteres["filtres"], criteres["domaines"])
    res = {"mode": mode, "le": maintenant(), "user": user, "criteres": criteres,
           "parametres_envoyes": requetes, "pagination": f"range=0-149 ... jusqu'à début {ft.DEBUT_MAX}, "
                                                         f"sort=1, découpage par minCreationDate/maxCreationDate",
           "filtres_apres_recuperation": filtres_apres_recuperation(criteres)}
    print(f"\n=== {mode} : {len(requetes)} requête(s) initiale(s)")
    for q in requetes:
        print("   ", q)
    if hors_ligne:
        return res
    token = ft.get_token(print)
    if not token:
        raise SystemExit("Jeton France Travail refusé : vérifier FT_CLIENT_ID et FT_CLIENT_SECRET.")
    chrono = Chrono()
    collecte = collecter(token, requetes)
    res["couverture"] = couverture(token, requetes, collecte)
    res["ecartees_apres_recuperation"] = ecartees(collecte, criteres)
    res["domaines_et_secteurs"] = domaines_et_secteurs(token, requetes, collecte)
    if mode == "stage":
        res["stage"] = stage(token)
        res["avant_apres_D152"] = a = avant_apres_stage(token, criteres, profil_du_mode(mode, user, base))
        print(f"  stage, offres gardées : avant {a['avant']['gardees']}, après {a['apres']['gardees']} "
              f"(+{a['ajoutees']}, -{a['perdues']})")
    res["duree_s"] = chrono.s
    c, e = res["couverture"], res["ecartees_apres_recuperation"]
    print(f"  annoncées {c['total_annonce']}, distinctes {c['distinctes_recuperees']}, écart {c['ecart']}, "
          f"plafond {c['non_recuperees_plafond']}, contrôle départements : "
          f"{c['controle_par_departement']['absentes_de_la_collecte']} absentes sur "
          f"{c['controle_par_departement']['offres_verifiees']}")
    print(f"  hors IDF {e['hors_idf']['part']}, libellés : {e['hors_idf']['libelles'][:5]}")
    print(f"  domaines : {res['domaines_et_secteurs'].get('domaines', {}).get('hors_de_tout_grand_domaine')} offres "
          "hors de tout grand domaine")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mode", choices=[*MODES, "tous"], default="tous")
    ap.add_argument("--user", type=int, help="critères des profils de cet utilisateur (base en lecture seule)")
    ap.add_argument("--base", help="URL SQLite de la base (défaut : DATABASE_URL)")
    ap.add_argument("--hors-ligne", action="store_true", help="paramètres seulement, sans réseau")
    args = ap.parse_args(argv)
    for mode in (MODES if args.mode == "tous" else [args.mode]):
        res = auditer(mode, args.user, args.base, args.hors_ligne)
        print("  ->", ecrire_json(f"audit_france_travail_{mode}{'_parametres' if args.hors_ligne else ''}", res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
