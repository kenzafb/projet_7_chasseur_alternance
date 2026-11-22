"""
scripts/banc_ia/exporter.py
===========================
B1 et B4 (phase 15) : exporte de la base, en LECTURE SEULE, les jeux à
annoter à la main :

  - audit_exports/banc_offres_a_annoter.json : les offres des trois modes
    (titre, entreprise, lieu, description complète, niveau détecté par
    Python, note, verdict, éligibilité, raison, points forts et faibles,
    archivage) avec le profil de leur mode (identité retirée), et un bloc
    « attendu » vide à remplir : c'est le jeu de référence du banc
    (format : README.md) ;
  - audit_exports/banc_emails_a_annoter.json : chaque adresse trouvée,
    douteuse ou écartée par l'IA, avec l'entreprise, le domaine du site, le
    texte autour et « attendu_valide » vide ;
  - audit_exports/banc_lettres.json : les lettres types des profils et les
    paragraphes déjà rédigés (lettres enregistrées), pour comparaison.

    CHASSEUR_ENV_FILE=/dev/null venv/bin/python scripts/banc_ia/exporter.py --base sqlite:///data/chasseur_v2.db
    venv/bin/python scripts/banc_ia/exporter.py --user 1 --mode stage --toutes   # archivées comprises

Par défaut : toutes les offres analysées et non analysées, archivées
comprises (une offre archivée à tort compte aussi). --max N par mode.
"""

import argparse

from commun import CHAMPS_IDENTITE  # noqa: E402

from audit_commun import ecrire_json, maintenant, session_lecture  # noqa: E402


def exporter(base=None, user=None, mode=None, maximum=None) -> dict:
    from database.candidatures_db import candidature_vers_dict
    from database.models import Candidature, Entreprise, EntrepriseMode, Profil
    from database.profil_db import profil_vers_dict
    from shared.eligibilite import niveau_detecte, niveaux_dans_texte

    offres, profils, emails, lettres = [], {}, [], []
    with session_lecture(base) as db:
        q = db.query(Profil)
        if user:
            q = q.filter(Profil.user_id == user)
        for p in q:
            d = profil_vers_dict(p)
            cle = f"{p.user_id}:{p.mode}"
            lettres.append({"profil": cle, "lettre_type": d.get("lettre_type") or ""})
            profils[cle] = {k: v for k, v in d.items() if k not in CHAMPS_IDENTITE} | {"mode": p.mode}
        par_mode = {}
        q = db.query(Candidature)
        if user:
            q = q.filter(Candidature.user_id == user)
        if mode:
            q = q.filter(Candidature.mode == mode)
        for c in q.order_by(Candidature.mode, Candidature.id):
            par_mode[c.mode] = par_mode.get(c.mode, 0) + 1
            if maximum and par_mode[c.mode] > maximum:
                continue
            o = candidature_vers_dict(c)
            detecte = niveau_detecte(c.description or "")
            offres.append({
                "ref": c.ref_offre, "id_base": c.id, "mode": c.mode, "profil": f"{c.user_id}:{c.mode}",
                "source": c.source, "titre": c.titre, "entreprise": c.entreprise, "lieu": c.lieu,
                "description": c.description or "",
                "niveau_detecte": {"niveau": detecte[0], "exigence": detecte[1]} if detecte else None,
                "niveaux_possibles_dans_le_texte": sorted(niveaux_dans_texte(c.description or "")[0]),
                "app": {"score": c.score, "verdict": c.verdict, "eligible": c.eligible, "statut": c.statut,
                        "raison_archivage": c.raison_archivage, "points_forts": c.points_forts or [],
                        "points_faibles": c.points_faibles or [], "domaine": c.domaine,
                        "resume": c.resume_analyse, "date_trouvee": o.get("date_trouvee")},
                "attendu": {"eligible": None, "niveau_vise": None, "categorie": None, "commentaire": ""},
            })
            if (c.lettre or "").strip():
                lettres.append({"profil": f"{c.user_id}:{c.mode}", "ref": c.ref_offre, "titre": c.titre,
                                "lettre_enregistree": c.lettre})
        q = db.query(Entreprise)
        if user:
            q = q.filter(Entreprise.user_id == user)
        for e in q:
            extra = e.extra or {}
            modes = [m.mode for m in db.query(EntrepriseMode).filter_by(entreprise_id=e.id)]
            douteux = set(extra.get("emails_douteux") or [])
            provenance = extra.get("validation_emails") or {}
            contextes = extra.get("contextes_emails") or {}
            adresses = list(dict.fromkeys([*(e.emails_trouves or []), *(extra.get("emails_ecartes_ia") or [])]))
            for a in adresses:
                etat = ("ecartee_ia" if a in (extra.get("emails_ecartes_ia") or []) else
                        "douteuse" if a in douteux else f"validee_{provenance.get(a, 'avant_phase_7')}")
                emails.append({"entreprise_id": e.id, "entreprise": e.nom_commercial or extra.get("nom") or "",
                               "modes": modes, "site_web": e.site_web or "", "url_scrapee": extra.get("url_scrapee", ""),
                               "email": a, "etat_app": etat, "contexte": contextes.get(a, ""),
                               "attendu_valide": None, "commentaire": ""})
    return {"version": 1, "exporte_le": maintenant(), "profils": profils, "offres": offres}, \
        {"version": 1, "exporte_le": maintenant(), "emails": emails}, \
        {"version": 1, "exporte_le": maintenant(), "lettres": lettres}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", help="URL SQLite de la base (défaut : DATABASE_URL)")
    ap.add_argument("--user", type=int)
    ap.add_argument("--mode")
    ap.add_argument("--max", type=int, help="offres au plus par mode")
    args = ap.parse_args(argv)
    offres, emails, lettres = exporter(args.base, args.user, args.mode, args.max)
    par_mode = {}
    for o in offres["offres"]:
        par_mode[o["mode"]] = par_mode.get(o["mode"], 0) + 1
    print("offres :", par_mode, "->", ecrire_json("banc_offres_a_annoter", offres))
    print("emails :", len(emails["emails"]), "->", ecrire_json("banc_emails_a_annoter", emails))
    print("lettres :", len(lettres["lettres"]), "->", ecrire_json("banc_lettres", lettres))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
