"""
scripts/revalider_emails_en_base.py
===================================
Phase 15, étape 2 (point 7, D162) : repasse toutes les adresses déjà en base
aux règles de shared/validation_emails.py (site vérifié exigé, domaine du
site vérifié, adresses factices et mal formées écartées). Rien n'est
envoyé, l'IA n'est pas appelée : une adresse douteuse reste à valider.

Par défaut, lecture seule : la base est ouverte en mode ro, le rapport va
dans audit_exports/revalidation_emails.json. --appliquer écrit le résultat
(base de DATABASE_URL) : adresses écartées retirées de emails_trouves et
notées dans extra["emails_ecartes_revalidation"], site vérifié enregistré.

Le site de chaque entreprise est celui déjà vérifié par le scraper (D160) ;
avec --verifier-sites, il est cherché et vérifié maintenant (site LBA,
offres, recherche web avec --recherche) : réseau.

Une adresse fournie par La Bonne Alternance (extra.emails_lba) est gardée :
elle ne vient pas d'un site. Une entreprise déjà contactée n'est pas touchée.

    CHASSEUR_ENV_FILE=/dev/null venv/bin/python scripts/revalider_emails_en_base.py --base sqlite:///data/chasseur_v2.db --verifier-sites --recherche
    venv/bin/python scripts/revalider_emails_en_base.py --verifier-sites --recherche --appliquer
"""

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_commun import ecrire_json, maintenant, session_lecture  # noqa: E402

from shared.validation_emails import DOUTEUX, ECARTE, VALIDE, classer  # noqa: E402


@contextmanager
def session_ecriture():
    from database.connexion import SessionLocal
    db = SessionLocal()
    try:
        yield db
        db.commit()
    finally:
        db.close()


def en_dict(e) -> dict:
    extra = e.extra or {}
    return {"nom": extra.get("nom") or e.nom_commercial, "nom_commercial": e.nom_commercial, "siren": e.siren,
            "_extra": extra, "site_web": e.site_web}


def revalider_une(e, verification) -> dict:
    """Décision des règles pour chaque adresse d'une entreprise."""
    extra = e.extra or {}
    domaine = (verification or {}).get("domaine")
    lba = set(extra.get("emails_lba") or [])
    garde, douteuses, ecartees = [], [], []
    for a in e.emails_trouves or []:
        if a in lba:
            garde.append(a)
            continue
        decision, raison = classer(a, domaine, verifie=bool(domaine))
        if decision == VALIDE:
            garde.append(a)
        elif decision == DOUTEUX:
            garde.append(a)
            douteuses.append(a)
        else:
            assert decision == ECARTE
            ecartees.append((a, raison))
    return {"id": e.id, "nom": e.nom_commercial, "site_en_base": e.site_web, "site_verifie": verification,
            "avant": list(e.emails_trouves or []), "apres": garde, "douteuses": douteuses,
            "ecartees": [{"adresse": a, "raison": r} for a, r in ecartees], "emails_lba_gardes": sorted(lba & set(garde)),
            "etait_envoyable": bool(e.emails_trouves) and not extra.get("emails_non_valides")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", help="URL SQLite (lecture seule ; défaut : DATABASE_URL)")
    ap.add_argument("--user", type=int, help="un seul utilisateur")
    ap.add_argument("--verifier-sites", action="store_true", help="chercher et vérifier le site maintenant (réseau)")
    ap.add_argument("--recherche", action="store_true", help="avec --verifier-sites : recherche web aussi")
    ap.add_argument("--appliquer", action="store_true", help="écrire le résultat en base (sans rien envoyer)")
    args = ap.parse_args(argv)
    from database.candidatures_db import sites_des_offres
    from database.models import Entreprise
    from spontanees.site_officiel import identifier

    ouvrir = session_ecriture() if args.appliquer else session_lecture(args.base)
    rapport = {"le": maintenant(), "applique": args.appliquer, "entreprises": []}
    with ouvrir as db:
        q = db.query(Entreprise).filter(Entreprise.emails_trouves.isnot(None))
        if args.user:
            q = q.filter(Entreprise.user_id == args.user)
        sites = {}
        for e in q.order_by(Entreprise.id):
            if not e.emails_trouves or any(m.mail_envoye for m in e.modes):
                continue
            verification = (e.extra or {}).get("site_verifie")
            if not (verification or {}).get("domaine"):
                verification = None              # {"verifie": False} : le scraper n'a rien vérifié
            if not verification and args.verifier_sites:
                if e.user_id not in sites:
                    sites[e.user_id] = sites_des_offres(e.user_id, db)
                recherche = None
                if args.recherche:
                    from spontanees.recherche_emails import urls_recherche
                    recherche = urls_recherche
                v, essais = identifier(en_dict(e), sites[e.user_id], recherche, log=print)
                verification = {**v.resume(), "le": maintenant()} if v else None
            r = revalider_une(e, verification)
            rapport["entreprises"].append(r)
            print(f"{e.nom_commercial} : {len(r['avant'])} -> {len(r['apres'])} adresse(s)"
                  + (f", site vérifié {verification['domaine']}" if verification else ", site non vérifié")
                  + "".join(f"\n    écartée {x['adresse']} ({x['raison']})" for x in r["ecartees"]))
            if args.appliquer:
                extra = dict(e.extra or {})
                extra["site_verifie"] = verification
                extra["emails_douteux"] = r["douteuses"]
                extra["emails_non_valides"] = bool(r["douteuses"])
                extra["emails_ecartes_revalidation"] = r["ecartees"]
                e.emails_trouves, e.extra = r["apres"], extra
    ents = rapport["entreprises"]
    rapport["bilan"] = {
        "entreprises_avec_adresses": len(ents),
        "adresses_avant": sum(len(x["avant"]) for x in ents), "adresses_apres": sum(len(x["apres"]) for x in ents),
        "envoyables_avant": sum(x["etait_envoyable"] for x in ents),
        "envoyables_apres": sum(1 for x in ents if set(x["apres"]) - set(x["douteuses"])),
        "sites_verifies": sum(1 for x in ents if x["site_verifie"])}
    print(rapport["bilan"])
    print("->", ecrire_json("revalidation_emails" + ("_appliquee" if args.appliquer else ""), rapport))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
