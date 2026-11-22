"""
scripts/banc_ia/banc_emails.py
==============================
B4 (phase 15), emails des candidatures spontanées : rejoue la validation
(shared/validation_emails.py : règles, puis un appel à l'IA par entreprise
pour les adresses douteuses) sur un jeu étiqueté à la main, et compte
faux positifs (adresse retenue alors qu'elle ne sert pas à candidater) et
faux négatifs (adresse utile écartée ou laissée douteuse). Rien n'est
écrit en base.

    venv/bin/python scripts/banc_ia/banc_emails.py audit_exports/banc_emails_reference.json
    venv/bin/python scripts/banc_ia/banc_emails.py ref.json --modele qwen3.5:4b --essais 3 --sans-ia

Jeu : banc_emails_a_annoter.json (exporter.py) ou emails_candidats.json
(audit_scraper.py), avec « attendu_valide » rempli (true / false) ; les
lignes sans étiquette sont ignorées. Une entreprise = les lignes de même
entreprise_id (ou même entreprise + site_web).

Pour chaque essai : décision des règles seules (valide / écartée /
douteuse), puis finale après l'IA. Une adresse douteuse restante compte
comme non envoyée (D15). Résultat : matrice par étape, liste des erreurs,
variance d'un essai à l'autre, temps par entreprise.
"""

import argparse
import time
from collections import defaultdict

from commun import activer_ia, lire_json  # noqa: E402

from audit_commun import ecrire_json, maintenant  # noqa: E402


def domaine(url: str) -> str | None:
    from spontanees.recherche_emails import extraire_domaine
    if not url:
        return None
    return extraire_domaine(url if "://" in url else "https://" + url) or None


def matrice(decisions: dict, attendu: dict) -> dict:
    vp = [a for a, v in decisions.items() if v and attendu[a]]
    fp = [a for a, v in decisions.items() if v and not attendu[a]]
    fn = [a for a, v in decisions.items() if not v and attendu[a]]
    vn = [a for a, v in decisions.items() if not v and not attendu[a]]
    return {"vrais_positifs": len(vp), "faux_positifs": fp, "faux_negatifs": fn, "vrais_negatifs": len(vn),
            "precision": round(len(vp) / (len(vp) + len(fp)), 3) if vp or fp else None,
            "rappel": round(len(vp) / (len(vp) + len(fn)), 3) if vp or fn else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("reference")
    ap.add_argument("--modele", help="modèle (défaut : IA_MODELE_EXTRACTION)")
    ap.add_argument("--essais", type=int, default=3)
    ap.add_argument("--sans-ia", action="store_true", help="règles seules")
    args = ap.parse_args(argv)
    from shared.validation_emails import ECARTE, VALIDE, classer, site_fiable
    ref = lire_json(args.reference)
    lignes = [x for x in ref.get("emails", []) if x.get("attendu_valide") is not None]
    if not lignes:
        raise SystemExit("Aucune adresse étiquetée (attendu_valide true ou false).")
    groupes = defaultdict(list)
    for x in lignes:
        groupes[x.get("entreprise_id") or f"{x['entreprise']}|{x.get('site_web')}"].append(x)
    attendu = {x["email"].lower(): bool(x["attendu_valide"]) for x in lignes}

    regles, a_juger = {}, []
    for g in groupes.values():
        site = domaine(g[0].get("url_scrapee") or g[0].get("site_web"))
        nom = g[0]["entreprise"]
        fiable = site_fiable(site, nom)
        douteuses = []
        for x in g:
            decision, raison = classer(x["email"], site, fiable)
            regles[x["email"].lower()] = {"decision": decision, "raison": raison}
            if decision not in (VALIDE, ECARTE):
                douteuses.append(x)
        if douteuses:
            a_juger.append((nom, site, douteuses, [x["email"] for x in g if regles[x["email"].lower()]["decision"] == VALIDE]))
    sortie = {"le": maintenant(), "adresses": len(lignes), "entreprises": len(groupes),
              "regles": {"detail": regles,
                         "matrice_regles_seules": matrice({a: r["decision"] == VALIDE for a, r in regles.items()}, attendu)},
              "essais": []}
    print(f"{len(lignes)} adresses étiquetées, {len(groupes)} entreprises, {sum(len(d) for _, _, d, _ in a_juger)} "
          "douteuses pour l'IA")
    print("Règles seules :", {k: v for k, v in sortie["regles"]["matrice_regles_seules"].items()})
    if not args.sans_ia and a_juger:
        activer_ia()
        from shared.config import modele_ia
        from shared.ia import ErreurIAPassagere
        from shared.validation_emails import avis_ia
        modele = args.modele or modele_ia("extraction")
        sortie["modele"] = modele
        for essai in range(1, args.essais + 1):
            finale = {a: r["decision"] == VALIDE for a, r in regles.items()}
            temps, erreurs = [], 0
            for nom, site, douteuses, valides in a_juger:
                debut = time.monotonic()
                try:
                    retenues, _ = avis_ia(nom, site, [x["email"].lower() for x in douteuses], valides,
                                          {x["email"].lower(): x.get("contexte") or "" for x in douteuses},
                                          modele=modele, essais=1)
                except ErreurIAPassagere:
                    erreurs += 1
                    retenues = []
                temps.append(time.monotonic() - debut)
                for x in douteuses:
                    finale[x["email"].lower()] = x["email"].lower() in retenues
            m = matrice(finale, attendu)
            sortie["essais"].append({"essai": essai, "matrice_finale": m, "erreurs_ia": erreurs,
                                     "secondes_par_entreprise": round(sum(temps) / len(temps), 2),
                                     "decisions": finale})
            print(f"Essai {essai} (règles + IA {modele}) :", {k: v for k, v in m.items()})
        decisions = [e["decisions"] for e in sortie["essais"]]
        sortie["instables"] = sorted(a for a in attendu if len({d.get(a) for d in decisions}) > 1)
    print("->", ecrire_json(f"banc_emails_{time.strftime('%Y%m%d_%H%M%S')}", sortie))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
