"""
scripts/audit_lba_export.py
===========================
Phase 15, étape 2 (point 3) : mesures sur l'export complet de La Bonne
Alternance déjà téléchargé par scripts/audit_lba.py
(audit_exports/lba_export_brut.json), lu en flux (pas de chargement entier
en mémoire), sans réseau ni clé, base en lecture seule :

  1. niveau (D154) : offres d'IDF des codes métiers du profil gardées avec
     l'ancien filtre (niveau visé ou sans niveau) et le nouveau (visé ± 1),
     ajoutées, 10 exemples (complétés par des offres d'autres codes s'il en
     manque) ;
  2. offres déléguées (D155) : nombre, archivées « École ou CFA » avant
     (ancienne liste de mots) et maintenant ;
  3. mots-clés école/CFA (D156) : offres d'IDF non déléguées archivées par
     l'ancienne liste et par les organismes vérifiés, exemples libérés ;
  4. entreprises à fort potentiel (recruteurs_lba) : ce que l'export
     donnerait à l'étape « Trouver des entreprises » (IDF, codes du profil,
     filtre de taille et de départements du profil), comparé aux entreprises
     LBA déjà en base ; avec --recherche (clé LBA_API_KEY, réseau) aussi
     comparé à la recherche de l'application (cercles, plafond de 150).

    CHASSEUR_ENV_FILE=/dev/null venv/bin/python scripts/audit_lba_export.py --user 1 --base sqlite:///data/chasseur_v2.db
    venv/bin/python scripts/audit_lba_export.py --user 1 --recherche

Sortie : audit_exports/audit_lba_export.json.
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_commun import (SORTIE, Chrono, ecrire_json, maintenant, mots_ecole_trouves,  # noqa: E402
                          organismes_trouves, pourcentage, session_lecture)

from offres import la_bonne_alternance as lba  # noqa: E402
from offres import parametres_lba as P  # noqa: E402
from shared.domaines import codes_metiers, domaines_du_profil  # noqa: E402

EXEMPLES = 10
RECRUTEURS = "recruteurs_lba"


def lire_en_flux(chemin: Path, bloc: int = 1 << 22):
    """Objets d'une liste JSON « [{...},{...}] », un à un."""
    dec = json.JSONDecoder()
    tampon, i, fin = "", 0, False
    with open(chemin, encoding="utf-8") as f:
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
                lu = f.read(bloc)       # objet coupé : le tampon garde la fin non lue
                fin = not lu
                tampon, i = tampon[i:] + lu, 0
                continue
            yield objet


def profil_alternance(user, base) -> dict:
    if not user:
        return {}
    from database.models import Profil
    from database.profil_db import profil_vers_dict
    with session_lecture(base) as db:
        p = db.query(Profil).filter_by(user_id=user, mode="alternance").first()
        return profil_vers_dict(p) if p else {}


def entreprises_en_base(user, base) -> dict:
    """SIRET des entreprises LBA déjà en base pour cet utilisateur."""
    if not user:
        return {}
    from database.models import Entreprise
    with session_lecture(base) as db:
        lignes = db.query(Entreprise).filter_by(user_id=user).all()
        siret = {}
        for e in lignes:
            s = str((e.extra or {}).get("siret") or "")
            if s and "lba" in " ".join(e.sources or []).lower():
                siret[s] = e.nom_commercial
        return {"lba": siret, "toutes": len(lignes)}


def auditer(args) -> dict:
    chrono = Chrono()
    profil = profil_alternance(args.user, args.base)
    codes = set(codes_metiers(domaines_du_profil(profil)))
    niveau = lba.niveau_du_profil(profil, log=lambda *_: None)
    garder_ent = lba.filtre_entreprise(profil)
    res = {"le": maintenant(), "user": args.user, "export": str(args.export), "codes_du_profil": len(codes),
           "niveau_profil": niveau}

    vus = Counter()
    niveau_avant, niveau_apres, ajoutees, autres_codes = 0, 0, [], []
    deleguees, deleg_avant, deleg_exemples = 0, 0, []
    cfa_avant, cfa_apres, liberees, par_organisme = 0, 0, [], Counter()
    recruteurs, recruteurs_filtres, recruteurs_hors_idf = {}, {}, 0
    for brut in lire_en_flux(args.export):
        vus["objets"] += 1
        partenaire = str(P.lire(brut, P.CHAMP_PARTENAIRE) or "")
        romes = set(P.lire(brut, "offer.rome_codes") or [])
        du_profil = not codes or bool(romes & codes)
        if partenaire == RECRUTEURS:
            vus["recruteurs"] += 1
            ent = lba.normaliser_entreprise(brut)
            if ent is None:
                recruteurs_hors_idf += 1
                continue
            if du_profil:
                cle = lba._cle_entreprise(ent)
                recruteurs[cle] = ent
                if garder_ent(ent):
                    recruteurs_filtres[cle] = ent
            continue
        if lba.relayee_de_france_travail(brut):
            vus["relayees_ft"] += 1
            continue
        o = lba._normaliser_offre_lba(brut)
        if o is None:
            continue
        vus["offres_idf"] += 1
        # 2. et 3. : offres d'IDF, tous codes (l'archivage ne dépend pas du profil)
        anciens = mots_ecole_trouves(o)
        if o["marques"]:
            deleguees += 1
            deleg_avant += bool(anciens)
            if len(deleg_exemples) < EXEMPLES:
                deleg_exemples.append({"titre": o["titre"], "entreprise": o["entreprise"], "mots_d_avant": anciens})
        else:
            nouveaux = organismes_trouves(o)
            cfa_avant += bool(anciens)
            cfa_apres += bool(nouveaux)
            par_organisme.update(m.split("@")[0] for m in nouveaux)
            if anciens and not nouveaux and len(liberees) < 3 * EXEMPLES:
                liberees.append({"titre": o["titre"], "entreprise": o["entreprise"], "mots_d_avant": anciens})
        # 1. niveau, codes du profil
        n = o["_niveau"]
        if niveau is None:
            continue
        exact = n is None or n == niveau
        adjacent = n is not None and abs(n - niveau) == 1
        if du_profil:
            vus["offres_idf_du_profil"] += 1
            niveau_avant += exact
            niveau_apres += exact or adjacent
            if adjacent:
                ajoutees.append({"titre": o["titre"], "entreprise": o["entreprise"], "niveau": n, "lieu": o["lieu"]})
        elif adjacent and len(autres_codes) < EXEMPLES:
            autres_codes.append({"titre": o["titre"], "entreprise": o["entreprise"], "niveau": n, "lieu": o["lieu"],
                                 "note": "hors des codes du profil"})
    res["lus"] = dict(vus)
    res["niveau_D154"] = {
        "profil": niveau, "offres_idf_des_codes_du_profil": vus["offres_idf_du_profil"],
        "gardees_avant": niveau_avant, "gardees_apres": niveau_apres, "ajoutees": len(ajoutees),
        "exemples": (ajoutees + autres_codes)[:EXEMPLES]}
    res["deleguees_D155"] = {
        "offres_idf": vus["offres_idf"], "deleguees": deleguees,
        "archivees_avant": pourcentage(deleg_avant, deleguees), "archivees_apres": 0, "exemples": deleg_exemples}
    non_deleg = vus["offres_idf"] - deleguees
    res["mots_cles_D156"] = {
        "offres_idf_non_deleguees": non_deleg, "archivees_avant": pourcentage(cfa_avant, non_deleg),
        "archivees_apres": pourcentage(cfa_apres, non_deleg), "par_organisme": par_organisme.most_common(),
        "exemples_plus_archivees": liberees}
    base = entreprises_en_base(args.user, args.base)
    deja = set(base.get("lba", {}))
    sirets = {e["siret"] for e in recruteurs_filtres.values() if e["siret"]}
    res["recruteurs_export"] = {
        "recruteurs_lus": vus["recruteurs"], "hors_idf": recruteurs_hors_idf,
        "idf_codes_du_profil": len(recruteurs), "apres_filtre_taille_departements": len(recruteurs_filtres),
        "par_departement": Counter(e["departement"] for e in recruteurs_filtres.values()).most_common(),
        "avec_site_web": sum(1 for e in recruteurs_filtres.values() if e["site_web"]),
        "avec_email": sum(1 for e in recruteurs_filtres.values() if e["email"]),
        "entreprises_lba_en_base": len(deja), "dont_dans_l_export": len(deja & sirets),
        "nouvelles_par_rapport_a_la_base": len(sirets - deja)}
    if args.recherche:
        res["recherche_application"] = comparer_recherche(profil, recruteurs_filtres)
    res["duree_s"] = chrono.s
    return res


def comparer_recherche(profil: dict, export: dict) -> dict:
    """Entreprises de la recherche de l'application (étape « Trouver des
    entreprises » : cercles redécoupés, LBA_REQUETES_MAX) contre l'export."""
    debut = time.monotonic()
    r = lba.rechercher_pour_profil(profil, log=print, redecouper_entreprises=True) or {}
    duree = round(time.monotonic() - debut, 1)
    app = {lba._cle_entreprise(e) for e in r.get("entreprises", [])}
    exp = set(export)
    return {"requetes": r.get("requetes"), "duree_s": duree, "entreprises_recherche": len(app),
            "entreprises_export": len(exp), "communes": len(app & exp), "seulement_recherche": len(app - exp),
            "seulement_export": len(exp - app),
            "exemples_seulement_recherche": sorted(app - exp)[:EXEMPLES]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--user", type=int)
    ap.add_argument("--base", help="URL SQLite de la base (défaut : DATABASE_URL)")
    ap.add_argument("--export", type=Path, default=SORTIE / "lba_export_brut.json")
    ap.add_argument("--recherche", action="store_true", help="comparer à la recherche de l'application (réseau, clé)")
    args = ap.parse_args(argv)
    res = auditer(args)
    n, d, m, r = res["niveau_D154"], res["deleguees_D155"], res["mots_cles_D156"], res["recruteurs_export"]
    print(f"niveau : {n['gardees_avant']} -> {n['gardees_apres']} offres gardées (+{n['ajoutees']})")
    print(f"déléguées : {d['deleguees']}, archivées avant {d['archivees_avant']}, maintenant 0")
    print(f"mots-clés : archivées avant {m['archivees_avant']}, après {m['archivees_apres']}")
    print(f"recruteurs : {r['idf_codes_du_profil']} en IDF pour les codes du profil, "
          f"{r['apres_filtre_taille_departements']} après filtres ; en base {r['entreprises_lba_en_base']}")
    if "recherche_application" in res:
        print("recherche :", {k: v for k, v in res["recherche_application"].items() if not k.startswith("exemples")})
    print("->", ecrire_json("audit_lba_export", res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
