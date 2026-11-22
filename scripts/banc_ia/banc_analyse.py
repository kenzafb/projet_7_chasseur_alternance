"""
scripts/banc_ia/banc_analyse.py
===============================
B3 (phase 15) : lance un modèle et un prompt sur le jeu de référence
annoté, plusieurs fois, et mesure l'analyse des offres telle que
l'application la produit (réponse du modèle, puis règles Python de
shared/eligibilite.py et offres.analyse.appliquer_eligibilite). Rien n'est
écrit en base. Ollama (ou le serveur de IA_BASE_URL) démarré :

    venv/bin/python scripts/banc_ia/banc_analyse.py audit_exports/banc_reference.json
    venv/bin/python scripts/banc_ia/banc_analyse.py ref.json --modele ministral-3:8b --essais 3 --temperatures 0,0.1
    venv/bin/python scripts/banc_ia/banc_analyse.py ref.json --prompt mes_prompts/v2.py --mode stage

--prompt : fichier Python qui définit construire_messages(offre, profil,
mode) -> messages (même signature que offres.analyse) ; sans lui, le prompt
de l'application. --temperatures : liste (défaut 0) ; --essais par
température (défaut 3). Les offres sans « attendu » rempli comptent dans les
temps et la variance, pas dans l'exactitude.

Mesures, par température :
  - exactitude de l'éligibilité (attendu.eligible), faux éligibles et faux
    inéligibles ;
  - niveau : niveau_requis final (après contrôle Python) contre
    attendu.niveau_vise ;
  - faux positifs de niveau : offre dont le niveau attendu est Bac+4 ou
    plus, notée Bien ou mieux (7 et plus, éligible) pour un profil de Bac+2
    ou moins ;
  - catégorie : écart de rang moyen avec attendu.categorie (Très bien,
    Bien, Moyen, Faible, Hors sujet), part exacte, matrice de confusion ;
  - variance sur les essais : écart type de la note par offre, offres dont
    la catégorie change d'un essai à l'autre ;
  - temps par offre (moyen, médian, max), réponses invalides.

Sortie : audit_exports/banc_analyse_<modele>_<horodatage>.json (chaque
réponse brute du modèle et le résultat final, par offre et par essai).
"""

import argparse
import statistics
import time
from collections import Counter

from commun import (RANG, activer_ia, categorie_du_resultat, charger_prompt, charger_reference,
                    ecart_type, moyenne, profil_de)  # noqa: E402

from audit_commun import ecrire_json, maintenant  # noqa: E402

CRANS = {"bac": 0, "bac+2": 2, "bac+3": 3, "bac+4": 4, "bac+5": 5}


def analyser(offre, profil, mode, modele, temperature, construire):
    """(résultat final comme l'application, réponse brute du modèle, secondes)."""
    from offres.analyse import _valider_analyse, appliquer_eligibilite, construire_messages
    from shared.ia import appeler_structure
    from shared.schemas_ia import AnalyseOffre
    messages = (construire or construire_messages)(offre, profil, mode)
    debut = time.monotonic()
    brut = appeler_structure(messages, AnalyseOffre, usage="analyse", modele=modele, essais=1,
                             temperature=temperature)
    duree = time.monotonic() - debut
    res = _valider_analyse(brut)
    score_modele = res["score"]
    appliquer_eligibilite(res, offre, profil, mode)
    res["score_modele"] = score_modele
    return res, brut.model_dump(), duree


def mesurer(lignes: list[dict], ref) -> dict:
    """Métriques d'une température (lignes : un essai d'une offre chacune)."""
    ok = [x for x in lignes if x.get("final")]
    annotees = [x for x in ok if x["attendu"].get("eligible") is not None]
    vrais = sum(1 for x in annotees if x["final"]["eligible"] == x["attendu"]["eligible"])
    faux_elig = [x["ref"] for x in annotees if x["final"]["eligible"] and not x["attendu"]["eligible"]]
    faux_inel = [x["ref"] for x in annotees if not x["final"]["eligible"] and x["attendu"]["eligible"]]
    avec_niveau = [x for x in ok if x["attendu"].get("niveau_vise")]
    niveau_ok = sum(1 for x in avec_niveau if x["final"].get("niveau_requis") == x["attendu"]["niveau_vise"])
    fp_niveau = [x["ref"] for x in ok
                 if CRANS.get(x["attendu"].get("niveau_vise") or "", -1) >= 4
                 and (x["profil_crans"] is not None and x["profil_crans"] <= 2)
                 and x["final"]["eligible"] and x["final"]["score"] >= 7]
    cat = [x for x in ok if x["attendu"].get("categorie") in RANG]
    ecarts = [abs(RANG[categorie_du_resultat(x["final"])] - RANG[x["attendu"]["categorie"]]) for x in cat]
    confusion = Counter((x["attendu"]["categorie"], categorie_du_resultat(x["final"])) for x in cat)
    par_offre = {}
    for x in ok:
        par_offre.setdefault(x["ref"], []).append(x)
    instables = [r for r, xs in par_offre.items() if len({categorie_du_resultat(x["final"]) for x in xs}) > 1]
    temps = [x["secondes"] for x in ok]
    return {
        "reponses": len(lignes), "invalides": len(lignes) - len(ok),
        "eligibilite": {"annotees": len(annotees), "exactitude": round(vrais / len(annotees), 3) if annotees else None,
                        "faux_eligibles": faux_elig, "faux_ineligibles": faux_inel},
        "niveau_extrait": {"annotees": len(avec_niveau),
                           "exactitude": round(niveau_ok / len(avec_niveau), 3) if avec_niveau else None},
        "faux_positifs_niveau": {"nombre": len(fp_niveau), "refs": sorted(set(fp_niveau)),
                                 "regle": "attendu Bac+4 ou plus, profil Bac+2 ou moins, éligible et note >= 7"},
        "categorie": {"annotees": len(cat), "ecart_moyen_rangs": moyenne(ecarts),
                      "exacte": round(sum(1 for e in ecarts if e == 0) / len(ecarts), 3) if ecarts else None,
                      "a_deux_rangs_ou_plus": sum(1 for e in ecarts if e >= 2),
                      "confusion_attendu_obtenu": {f"{a} -> {b}": n for (a, b), n in sorted(confusion.items())}},
        "variance": {"ecart_type_note_moyen": moyenne([ecart_type([x["final"]["score"] for x in xs])
                                                       for xs in par_offre.values()]),
                     "offres_a_categorie_instable": instables},
        "temps_s": {"moyen": moyenne(temps), "median": round(statistics.median(temps), 2) if temps else None,
                    "max": round(max(temps), 2) if temps else None},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("reference", help="jeu de référence annoté (format README.md)")
    ap.add_argument("--modele", help="modèle (défaut : IA_MODELE_ANALYSE)")
    ap.add_argument("--prompt", help="fichier Python définissant construire_messages(offre, profil, mode)")
    ap.add_argument("--temperatures", default="0", help="liste séparée par des virgules (défaut 0)")
    ap.add_argument("--essais", type=int, default=3)
    ap.add_argument("--mode", help="seulement les offres de ce mode")
    ap.add_argument("--max", type=int, help="offres au plus")
    ap.add_argument("--annotees", action="store_true", help="seulement les offres annotées")
    args = ap.parse_args(argv)

    activer_ia()
    from shared.config import modele_ia
    from shared.eligibilite import niveau_du_profil
    from shared.ia import ErreurIABloquante, ErreurIAPassagere, verifier_demarrage
    modele = args.modele or modele_ia("analyse")
    construire = charger_prompt(args.prompt, "construire_messages")
    ref = charger_reference(args.reference)
    offres = [o for o in ref["offres"] if (not args.mode or o["mode"] == args.mode)
              and (not args.annotees or any(v not in (None, "") for v in (o.get("attendu") or {}).values()))]
    offres = offres[:args.max] if args.max else offres
    print(f"Modèle {modele}, prompt {args.prompt or 'de l application'}, {len(offres)} offres")
    print(f"Test de démarrage : {verifier_demarrage(modele):.1f} s")

    resultats = {"le": maintenant(), "modele": modele, "prompt": args.prompt or "offres.analyse.construire_messages",
                 "reference": args.reference, "essais": args.essais, "par_temperature": {}}
    for t in [float(x) for x in args.temperatures.split(",")]:
        lignes = []
        for essai in range(1, args.essais + 1):
            for i, o in enumerate(offres, 1):
                profil = profil_de(ref, o)
                ligne = {"ref": o["ref"], "mode": o["mode"], "essai": essai, "attendu": o.get("attendu") or {},
                         "profil_crans": niveau_du_profil(profil)["crans"]}
                try:
                    final, brut, s = analyser(o, profil, o["mode"], modele, t, construire)
                except ErreurIABloquante as e:
                    raise SystemExit(f"IA bloquée : {e}") from e
                except ErreurIAPassagere as e:
                    ligne.update(erreur=str(e), secondes=None)
                else:
                    ligne.update(final=final, brut=brut, secondes=round(s, 2))
                    print(f"  T={t} essai {essai} [{i}/{len(offres)}] {o['titre'][:50]} : modèle {brut['score']}, "
                          f"final {final['score']} {categorie_du_resultat(final)}"
                          f" (attendu {ligne['attendu'].get('categorie') or '?'}) {s:.1f} s")
                lignes.append(ligne)
        resultats["par_temperature"][str(t)] = {"mesures": mesurer(lignes, ref), "lignes": lignes}
        m = resultats["par_temperature"][str(t)]["mesures"]
        print(f"\nT={t} : éligibilité {m['eligibilite']['exactitude']}, faux positifs de niveau "
              f"{m['faux_positifs_niveau']['nombre']}, écart de catégorie {m['categorie']['ecart_moyen_rangs']}, "
              f"σ note {m['variance']['ecart_type_note_moyen']}, {m['temps_s']['moyen']} s/offre")
    nom = f"banc_analyse_{modele.replace(':', '_').replace('/', '_')}_{time.strftime('%Y%m%d_%H%M%S')}"
    print("->", ecrire_json(nom, resultats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
