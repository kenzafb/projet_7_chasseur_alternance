"""
scripts/audit_lba.py
====================
Audit A2 (phase 15) : La Bonne Alternance. Ce que l'application récupère
(recherche plafonnée, cercles redécoupés), comparé à l'export complet de
l'API, et ce que vaut le champ is_delegated face aux mots-clés « école/CFA ».
Lecture seule. À lancer par l'humain (LBA_API_KEY du .env) :

    venv/bin/python scripts/audit_lba.py --user 1          # domaines et niveau du profil alternance
    venv/bin/python scripts/audit_lba.py --user 1 --sans-export
    venv/bin/python scripts/audit_lba.py --export-local audit_exports/lba_export_brut.json

Documentation (OpenAPI de l'API, https://api.apprentissage.beta.gouv.fr/api/documentation/json,
version 62a4dd4, lue le 22 novembre 2026) :
  - GET /job/v1/search : « The results are limited to 150 for each of the
    three sources i.e. 450 maximum results, and currently, it is not
    possible to retrieve all the offers matching the search criteria » ;
    recruiters « limited to 150 » ; paramètres latitude, longitude, radius
    (0 à 200, défaut 30), romes, rncp, target_diploma_level, opco,
    departements (tableau), partners_to_exclude ; 60 appels par minute ;
  - GET /job/v1/export : « Lists all job opportunities (job postings and
    companies to which you can send unsolicited applications).
    Opportunities are updated once a day at 3:00 AM Paris time. Rate
    limit: 2 calls per minute » ; réponse {url, lastUpdate}, « URL valid
    for 2 minutes », « The data structure of the offers is identical to the
    response of the search route » ;
  - is_delegated (JobOfferRead, obligatoire) : « true if offer management
    is delegated to a partner school » ; workplace.name, legal_name, siret,
    location.address et apply.phone sont alors ceux de l'école (« or school
    legal name if is_delegated = true »...).

Mesures :
  1. collecte de l'application (offres.la_bonne_alternance.CollecteLBA,
     mêmes centres, mêmes redécoupages, offres et entreprises) : requêtes,
     cercles au plafond, offres et entreprises distinctes ;
  2. export : téléchargé (gros fichier, gardé dans audit_exports/), offres
     d'IDF (code postal) ; parmi celles qui ont un code ROME du profil,
     combien la collecte n'a pas, par partenaire ; entreprises (recruiters)
     de l'export en IDF contre celles de la collecte ;
  3. paramètre departements (75 à 95) à la place des cercles : totaux ;
  4. is_delegated : part des offres déléguées ; parmi elles, celles que
     est_ecole_cfa archive (le nom de l'entreprise y est celui de l'école) ;
     parmi les non déléguées, celles que les mots-clés archivent quand
     même, avec le mot en cause (à lire : vraies offres d'école ou faux
     positifs ?) ;
  5. niveau : répartition de offer.target_diploma.european, et offres
     écartées par filtrer_niveau (égalité stricte avec le niveau du profil).

Sortie : audit_exports/audit_lba.json, et audit_exports/lba_export_brut.json
(l'export tel que téléchargé).
"""

import argparse
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import requests

from audit_commun import SORTIE, Chrono, ecrire_json, maintenant, mots_ecole_trouves, pourcentage, session_lecture  # noqa: E402

from offres import la_bonne_alternance as lba  # noqa: E402
from offres import parametres_lba as P  # noqa: E402
from shared.config import DEPTS_IDF  # noqa: E402
from shared.domaines import codes_metiers, domaines_du_profil  # noqa: E402

URL_EXPORT = "https://api.apprentissage.beta.gouv.fr/api/job/v1/export"
EXEMPLES = 40
RE_CP = re.compile(r"\b(\d{5})\b")


class CollecteNotee(lba.CollecteLBA):
    """CollecteLBA de l'application, réponses brutes gardées."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.bruts, self.recruteurs_bruts = {}, {}

    def _ajouter(self, corps):
        for b in corps.get(P.CLE_OFFRES) or []:
            self.bruts.setdefault(str(P.lire(b, "identifier.id")), b)
        for b in corps.get(P.CLE_ENTREPRISES) or []:
            self.recruteurs_bruts.setdefault(str(P.lire(b, "workplace.siret") or P.lire(b, "identifier.id")), b)
        return super()._ajouter(corps)


def dept(objet) -> str:
    m = RE_CP.search(str(P.lire(objet, "workplace.location.address") or ""))
    return m.group(1)[:2] if m else ""


def romes(objet) -> set[str]:
    valeur = P.lire(objet, "offer.rome_codes") or []
    return set(valeur if isinstance(valeur, list) else [valeur])


def profil(user, base) -> dict:
    if not user:
        return {}
    from database.models import Profil
    from database.profil_db import profil_vers_dict
    with session_lecture(base) as db:
        p = db.query(Profil).filter_by(user_id=user, mode="alternance").first()
        return profil_vers_dict(p) if p else {}


def telecharger_export(cle: str) -> tuple[list, list, str]:
    r = requests.get(URL_EXPORT, headers={"Authorization": f"Bearer {cle}", "Accept": "application/json"}, timeout=60)
    if r.status_code != 200:
        raise SystemExit(f"Export refusé ({r.status_code}) : {r.text[:300]}")
    info = r.json()
    print(f"  export du {info.get('lastUpdate')}, téléchargement...")
    chemin = SORTIE / "lba_export_brut.json"
    SORTIE.mkdir(parents=True, exist_ok=True)
    with requests.get(info["url"], stream=True, timeout=600) as f, open(chemin, "wb") as sortie:
        f.raise_for_status()
        for bloc in f.iter_content(1 << 20):
            sortie.write(bloc)
    print(f"  {chemin} ({chemin.stat().st_size / 1e6:.0f} Mo)")
    return *lire_export(chemin), info.get("lastUpdate")


def lire_export(chemin) -> tuple[list, list]:
    donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    if isinstance(donnees, dict):
        return donnees.get(P.CLE_OFFRES) or donnees.get("jobs") or [], donnees.get(P.CLE_ENTREPRISES) or []
    # Liste à plat : offres et entreprises mêlées (entreprises sans « offer »)
    return [d for d in donnees if d.get("offer")], [d for d in donnees if not d.get("offer")]


def ecole(brut) -> list[str]:
    o = lba._normaliser_offre_lba(brut)
    return mots_ecole_trouves(o) if o else []


def auditer(args) -> dict:
    cle = os.getenv("LBA_API_KEY")
    if not cle:
        raise SystemExit("LBA_API_KEY absente du .env.")
    prof = profil(args.user, args.base)
    codes = codes_metiers(domaines_du_profil(prof))
    niveau = lba.niveau_du_profil(prof, print)
    res = {"le": maintenant(), "user": args.user, "codes_rome": len(codes), "niveau_profil": niveau,
           "parametres_envoyes": {"url": P.URL_RECHERCHE, "centres": lba.centres(), "codes_par_requete":
                                  P.CODES_PAR_REQUETE, "exclusion": P.PARAMS_EXCLUSION,
                                  "target_diploma_level": "jamais envoyé (D38)"}}

    # 1. Collecte de l'application
    chrono = Chrono()
    c = CollecteNotee(cle, print, avec_entreprises=True, redecouper_entreprises=True)
    c.parcourir(lba._lots(codes))
    res["collecte"] = {"requetes": c.requetes, "duree_s": chrono.s, "offres": len(c.offres),
                       "offres_brutes": len(c.bruts), "entreprises": len(c.entreprises),
                       "relayees_ft": len(c.relayees_ft), "hors_idf": len(c.hors_idf),
                       "au_plafond_rayon_min": [(lba.decrire_cercle(x), len(k), q) for x, k, q in c.au_plafond],
                       "limite_requetes_atteinte": c.requetes >= lba.LBA_REQUETES_MAX}
    print(f"  collecte : {len(c.offres)} offres, {len(c.entreprises)} entreprises, {c.requetes} requêtes")

    # 3. Paramètre departements
    par_dept = {}
    for d in sorted(DEPTS_IDF):
        params = {"departements": d, **P.PARAMS_EXCLUSION}
        if codes:
            params[P.PARAM_CODES] = ",".join(codes[:P.CODES_PAR_REQUETE])
        corps = c._get(params)
        par_dept[d] = {"offres": len(corps.get(P.CLE_OFFRES) or []),
                       "entreprises": len(corps.get(P.CLE_ENTREPRISES) or []),
                       "par_source": Counter(str(P.lire(b, P.CHAMP_PARTENAIRE)) for b in corps.get(P.CLE_OFFRES) or [])}
    res["parametre_departements"] = {"note": "un seul lot de codes ; 150 par source au plus, comme les cercles",
                                     "par_departement": par_dept}

    # 2. Export complet
    if not args.sans_export:
        if args.export_local:
            offres_exp, recr_exp = lire_export(args.export_local)
            date = "fichier local"
        else:
            time.sleep(1)
            offres_exp, recr_exp, date = telecharger_export(cle)
        idf = [o for o in offres_exp if dept(o) in DEPTS_IDF]
        ciblees = [o for o in idf if not codes or romes(o) & set(codes)]
        ciblees = [o for o in ciblees if not lba.relayee_de_france_travail(o)]
        ids_app = set(c.bruts)
        manquees = [o for o in ciblees if str(P.lire(o, "identifier.id")) not in ids_app]
        recr_idf = [r for r in recr_exp if dept(r) in DEPTS_IDF]
        sirets_app = set(c.recruteurs_bruts)
        res["export"] = {
            "date": date, "offres_france": len(offres_exp), "offres_idf": len(idf),
            "offres_idf_codes_du_profil_hors_ft": len(ciblees),
            "dans_la_collecte": len(ciblees) - len(manquees),
            "manquees_par_la_collecte": pourcentage(len(manquees), len(ciblees)),
            "manquees_par_partenaire": Counter(str(P.lire(o, P.CHAMP_PARTENAIRE)) for o in manquees).most_common(),
            "exemples_manquees": [{"id": P.lire(o, "identifier.id"), "titre": P.lire(o, "offer.title"),
                                   "partenaire": P.lire(o, P.CHAMP_PARTENAIRE), "dept": dept(o)}
                                  for o in manquees[:EXEMPLES]],
            "recruteurs_france": len(recr_exp), "recruteurs_idf": len(recr_idf),
            "recruteurs_collecte": len(sirets_app),
            "recruteurs_idf_absents_de_la_collecte": sum(1 for r in recr_idf
                                                         if str(P.lire(r, "workplace.siret")) not in sirets_app),
            "champ_rome_lu": "offer.rome_codes (JobOfferRead)",
        }
        source_delegation = idf
    else:
        source_delegation = list(c.bruts.values())

    # 4. is_delegated contre les mots-clés école/CFA
    deleg = [o for o in source_delegation if o.get("is_delegated") is True]
    non_deleg = [o for o in source_delegation if o.get("is_delegated") is False]
    res["is_delegated"] = {
        "source": "export IDF" if not args.sans_export else "collecte",
        "offres": len(source_delegation), "deleguees": pourcentage(len(deleg), len(source_delegation)),
        "champ_absent": sum(1 for o in source_delegation if "is_delegated" not in o),
        "deleguees_archivees_par_mots_cles": pourcentage(sum(1 for o in deleg if ecole(o)), len(deleg)),
        "exemples_deleguees": [{"titre": P.lire(o, "offer.title"), "nom_affiche": P.lire(o, "workplace.name"),
                                "mots": ecole(o)} for o in deleg[:EXEMPLES]],
        "non_deleguees_archivees_par_mots_cles": pourcentage(sum(1 for o in non_deleg if ecole(o)), len(non_deleg)),
        "mots_en_cause_non_deleguees": Counter(m for o in non_deleg for m in ecole(o)).most_common(30),
        "exemples_non_deleguees_archivees": [{"titre": P.lire(o, "offer.title"), "entreprise": P.lire(o, "workplace.name"),
                                              "mots": ecole(o)} for o in non_deleg if ecole(o)][:EXEMPLES],
    }

    # 5. Niveau
    niveaux = Counter(str(P.lire(o, P.CHAMP_NIVEAU_OFFRE)) for o in c.bruts.values())
    norm = list(c.offres.values())
    res["niveau"] = {"repartition_offer.target_diploma.european": dict(niveaux),
                     "ecartees_par_filtrer_niveau": {str(n): lba.filtrer_niveau(norm, n)[1] for n in (3, 4, 5, 6, 7)},
                     "note": "filtrer_niveau garde le niveau égal à celui du profil ou sans niveau : une offre "
                             "« BTS à Master » codée à un seul niveau est écartée pour les autres"}
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--user", type=int, help="profil alternance de cet utilisateur (base en lecture seule)")
    ap.add_argument("--base", help="URL SQLite de la base (défaut : DATABASE_URL)")
    ap.add_argument("--sans-export", action="store_true", help="ne télécharge pas l'export complet")
    ap.add_argument("--export-local", help="export déjà téléchargé (JSON)")
    args = ap.parse_args(argv)
    res = auditer(args)
    print("  ->", ecrire_json("audit_lba", res))
    if "export" in res:
        e = res["export"]
        print(f"  export : {e['offres_idf_codes_du_profil_hors_ft']} offres IDF du profil (hors FT), "
              f"manquées par la collecte {e['manquees_par_la_collecte']}")
    d = res["is_delegated"]
    print(f"  is_delegated : {d['deleguees']} ; déléguées archivées par mots-clés {d['deleguees_archivees_par_mots_cles']} ; "
          f"non déléguées archivées {d['non_deleguees_archivees_par_mots_cles']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
