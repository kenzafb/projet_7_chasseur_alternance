"""
scripts/verifier_france_travail.py
==================================
Vérifie sur la vraie API Offres d'emploi v2 les points de France Travail
encore ouverts (SPEC_SOURCES.md, section 7), à lancer par l'humain avec
ses identifiants (FT_CLIENT_ID, FT_CLIENT_SECRET du .env) :

    venv/bin/python scripts/verifier_france_travail.py

1. Paramètre de domaine : nombre d'offres en Île-de-France avec domaine=M18,
   grandDomaine=M18, grandDomaine=M, domaine=M, codeROME=M1805 et avec des
   valeurs inexistantes, comparé au total sans filtre. Un paramètre qui
   filtre réduit le total ; un paramètre ignoré le laisse identique.
   Couverture : somme des 14 grands domaines et des 8 départements.
2. Valeurs multiples séparées par des virgules (natureContrat, typeContrat,
   grandDomaine, domaine, secteurActivite, theme) : total de chaque valeur
   seule, puis de la liste. Liste acceptée (OU) : total entre le plus grand
   total seul et leur somme, au-dessus du plus grand. Liste refusée (400) :
   nouvel essai avec deux valeurs.
3. Tranche d'effectif : sur 300 offres réelles (150 sans filtre, 150 en
   apprentissage), chaque champ dont le nom contient « effectif » ou
   « tranche », sa présence, ses valeurs les plus fréquentes et la part
   reconnue par shared.tailles.taille_depuis_tranche.
4. Découpage par date (décision D31) : fenêtre depuis DATE_PLUS_ANCIENNE
   jusqu'à maintenant, maintenant plus 3 h, maintenant plus la marge de
   parametres_api.py, comparées au total sans dates ; deux moitiés
   jointives comparées à la fenêtre complète (bornes incluses ou non).
5. Stages (phase 6b) : France Travail n'a ni type ni nature de contrat
   « stage ». Essai motsCles=stage en Île-de-France : nombre d'offres,
   répartition exacte par type et par nature de contrat (un comptage par
   code des référentiels), et sur les 150 plus récentes : types, natures,
   part des intitulés qui contiennent « stage » ou « stagiaire », 20
   intitulés d'exemple. Résultat dans verification_stage.json, à lire par
   l'humain avant de brancher France Travail dans le mode stage.
   --stage : cette étape seulement (une quarantaine de requêtes).

Résultat détaillé dans docs/referentiels/france_travail/verification_api.json
(--sortie pour un autre dossier), sans identifiant ni token. À la fin, les
valeurs à reporter dans france_travail/parametres_api.py, seul endroit du
code qui dépend de ces réponses. Une centaine de requêtes, une à deux
minutes. Code de sortie 1 si le token ne peut pas être obtenu, 0 sinon.
"""

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from france_travail import parametres_api  # noqa: E402
from scripts.explorer_france_travail import (  # noqa: E402
    DOSSIER_SORTIE, PAUSE_S, ROUTE_RECHERCHE, ErreurToken, Explorateur, _message, _total)
from shared import referentiels  # noqa: E402
from shared.config import DEPTS_IDF, FT_REGION  # noqa: E402
from shared.tailles import taille_depuis_tranche  # noqa: E402

BASE = {"region": FT_REGION}
# Plage demandée pour un simple comptage (le total est dans Content-Range) ;
# si l'API la refuse, 0-149 est utilisée pour la suite
PLAGE_COMPTAGE = "0-0"
PLAGE_PAGE = "0-149"

ESSAIS_DOMAINE = [
    ("domaine", "M18"), ("grandDomaine", "M18"), ("grandDomaine", "M"), ("domaine", "M"),
    ("codeROME", "M1805"), ("domaine", "Z99"), ("grandDomaine", "Z"),
]
# Valeurs multiples : (paramètre ou rôle, valeurs). « domaine » et « grand
# domaine » utilisent le paramètre trouvé à l'étape 1.
ESSAIS_MULTIPLES = [
    ("natureContrat", ["E2", "FS"]),
    ("typeContrat", ["CDD", "MIS", "SAI"]),
    ("theme", ["13", "17"]),
    ("<grand domaine>", ["M", "C", "J", "D", "H"]),
    ("<domaine>", ["M18", "C15", "M13", "J11", "D12"]),
    ("secteurActivite", ["62", "68", "86", "47", "41"]),
    # Message de l'API sur la liste de cinq : « 2 chaînes de caractères
    # séparées par des virgules » ; exactement deux valeurs
    ("secteurActivite", ["62", "68"]),
]
MOTS_TAILLE = ("effectif", "tranche")
# Stages : mot-clé essayé, intitulés montrés, mots qui signalent un vrai stage
MOTS_CLES_STAGE = "stage"
EXEMPLES_STAGE = 20
MOTS_INTITULE_STAGE = ("stage", "stagiaire")
FORMAT_DATE = "%Y-%m-%dT%H:%M:%SZ"
# Écart toléré entre la fenêtre complète et le total sans dates : offres
# publiées ou retirées entre les deux requêtes
ECART_TOLERE = 5


def _chemins(valeur, prefixe=""):
    """(chemin pointé, valeur) de chaque champ d'un dict, sous-dicts compris."""
    if isinstance(valeur, dict):
        for cle, v in valeur.items():
            chemin = f"{prefixe}.{cle}" if prefixe else cle
            yield chemin, v
            yield from _chemins(v, chemin)


class Verificateur:
    def __init__(self, explorateur: Explorateur):
        self.ex = explorateur
        self.afficher = explorateur.afficher
        self.plage = PLAGE_COMPTAGE

    # ── Comptage ──
    def compter(self, params: dict) -> dict:
        """{params, statut, total, message?} d'une recherche."""
        r = self.ex.get(ROUTE_RECHERCHE, params={**params, "range": self.plage})
        if r is not None and r.status_code == 400 and self.plage == PLAGE_COMPTAGE:
            r2 = self.ex.get(ROUTE_RECHERCHE, params={**params, "range": PLAGE_PAGE})
            if r2 is not None and r2.status_code in (200, 204, 206):
                self.plage, r = PLAGE_PAGE, r2
        if r is None:
            return {"params": params, "statut": None, "total": None, "message": "injoignable"}
        essai = {"params": params, "statut": r.status_code, "total": None}
        if r.status_code == 204:
            essai["total"] = 0
        elif r.status_code in (200, 206):
            essai["total"] = _total(r.headers.get("Content-Range", ""))
            if essai["total"] is None:
                try:
                    essai["total"] = len(r.json().get("resultats") or [])
                except ValueError:
                    essai["message"] = "réponse illisible"
        else:
            essai["message"] = _message(r, self.ex.secrets)
        return essai

    @staticmethod
    def _effet(essai: dict, total_base) -> str:
        if essai["total"] is None:
            return f"refusé ({essai['statut']})" if essai["statut"] else "injoignable"
        if total_base is not None and essai["total"] == total_base:
            return "ignoré (total inchangé)"
        if essai["total"] == 0:
            return "aucune offre"
        return "filtre"

    # ── 1. Paramètre de domaine ──
    def domaine(self) -> dict:
        base = self.compter(BASE)
        t0 = base["total"]
        self.afficher(f"  Île-de-France sans filtre : {t0}")
        essais = []
        for param, valeur in ESSAIS_DOMAINE:
            e = self.compter({**BASE, param: valeur})
            e["effet"] = self._effet(e, t0)
            essais.append(e)
            self.afficher(f"  {param + '=' + valeur:<18} {e['total']}  {e['effet']}")

        def filtre(param, valeur):
            return next((e for e in essais if e["params"].get(param) == valeur and e["effet"] == "filtre"
                         and e["total"]), None)

        param_domaine = next((p for p in ("domaine", "grandDomaine") if filtre(p, "M18")), None)
        param_grand = next((p for p in ("grandDomaine", "domaine") if filtre(p, "M")), None)
        coherent = None
        if param_domaine and param_grand:
            coherent = filtre(param_grand, "M")["total"] >= filtre(param_domaine, "M18")["total"]

        couverture = {}
        if param_grand:
            lettres = [g["code"] for g in referentiels.local("grands_domaines")]
            totaux = {lettre: self.compter({**BASE, param_grand: lettre})["total"] for lettre in lettres}
            couverture["grands_domaines"] = {"totaux": totaux, "somme": sum(t or 0 for t in totaux.values()),
                                             "total_sans_filtre": t0}
            self.afficher(f"  Somme des 14 grands domaines ({param_grand}) : "
                          f"{couverture['grands_domaines']['somme']} pour {t0}")
        totaux = {d: self.compter({"departement": d})["total"] for d in sorted(DEPTS_IDF)}
        couverture["departements"] = {"totaux": totaux, "somme": sum(t or 0 for t in totaux.values()),
                                      "total_sans_filtre": t0}
        self.afficher(f"  Somme des 8 départements : {couverture['departements']['somme']} pour {t0}")
        return {"base": base, "essais": essais, "param_domaine": param_domaine,
                "param_grand_domaine": param_grand, "grand_domaine_contient_domaine": coherent,
                "couverture": couverture}

    # ── 2. Valeurs multiples ──
    def multiples(self, param_domaine, param_grand) -> dict:
        resultats = {}
        roles = {"<domaine>": param_domaine, "<grand domaine>": param_grand}
        for nom, valeurs in ESSAIS_MULTIPLES:
            param = roles.get(nom, nom)
            if not param:
                resultats[nom] = {"param": None, "verdict": "non testé : paramètre de domaine introuvable"}
                self.afficher(f"  {nom} : non testé (paramètre introuvable)")
                continue
            seules = {v: self.compter({**BASE, param: v})["total"] for v in valeurs}
            essai = self._liste(param, valeurs, seules)
            if essai["max"] is None and len(valeurs) > 2 and essai["refuse"]:
                essai2 = self._liste(param, valeurs[:2], seules)
                essai.update(max=essai2["max"], essai_deux_valeurs=essai2)
                if essai2["max"]:
                    essai["verdict"] += " ; deux valeurs acceptées"
            essai.update(param=param, seules=seules)
            resultats[f"{param}={','.join(valeurs)}"] = essai
            self.afficher(f"  {param}={','.join(valeurs)} : {essai['verdict']}")
        return resultats

    def _liste(self, param, valeurs, seules) -> dict:
        e = self.compter({**BASE, param: ",".join(valeurs)})
        seules = {v: seules.get(v) for v in valeurs}   # seulement les valeurs de la liste
        connus = [t for t in seules.values() if t is not None]
        plus_grand, somme = max(connus, default=0), sum(connus)
        if e["total"] is None:
            return {"liste": e, "refuse": True, "max": None,
                    "verdict": f"liste refusée ({e['statut']}) : {e.get('message', '')[:100]}"}
        if plus_grand < e["total"] <= somme:
            return {"liste": e, "refuse": False, "max": len(valeurs),
                    "verdict": f"acceptée, OU des valeurs ({e['total']}, somme des valeurs seules {somme})"}
        premiere = seules.get(valeurs[0])
        if e["total"] == premiere and somme > premiere:
            return {"liste": e, "refuse": False, "max": 1,
                    "verdict": f"seule la première valeur est prise en compte ({e['total']})"}
        if e["total"] == plus_grand and somme == plus_grand:
            return {"liste": e, "refuse": False, "max": None,
                    "verdict": f"indécidable : une seule valeur a des offres ({e['total']})"}
        return {"liste": e, "refuse": False, "max": None,
                "verdict": f"incohérent ({e['total']} ; valeurs seules {seules})"}

    # ── 3. Tranche d'effectif ──
    def tranche_effectif(self) -> dict:
        offres = []
        for params in (BASE, {**BASE, "natureContrat": "E2"}):
            r = self.ex.get(ROUTE_RECHERCHE, params={**params, "range": PLAGE_PAGE})
            if r is not None and r.status_code in (200, 206):
                try:
                    offres += r.json().get("resultats") or []
                except ValueError:
                    pass
        champs = Counter()
        valeurs = {}
        for o in offres:
            for chemin, v in _chemins(o):
                if any(m in chemin.rsplit(".", 1)[-1].lower() for m in MOTS_TAILLE) and v not in (None, "", {}):
                    champs[chemin] += 1
                    valeurs.setdefault(chemin, Counter())[str(v)] += 1
        details = {}
        for chemin, n in champs.most_common():
            reconnues = sum(c for v, c in valeurs[chemin].items() if taille_depuis_tranche(v))
            details[chemin] = {"presence": n, "sur": len(offres),
                               "valeurs_frequentes": valeurs[chemin].most_common(15),
                               "reconnues": reconnues,
                               "non_reconnues": [v for v in valeurs[chemin] if not taille_depuis_tranche(v)][:15]}
            self.afficher(f"  {chemin} : présent dans {n}/{len(offres)} offres, {reconnues} reconnues ; "
                          f"ex. {', '.join(v for v, _ in valeurs[chemin].most_common(4))}")
        if not champs:
            self.afficher(f"  aucun champ « effectif » ou « tranche » dans {len(offres)} offres")
        cles = Counter(k for o in offres for k in o)
        return {"offres_lues": len(offres), "champs": details,
                "champ_propose": champs.most_common(1)[0][0] if champs else None,
                "cles_des_offres": dict(cles.most_common()),
                "cles_entreprise": dict(Counter(k for o in offres for k in (o.get("entreprise") or {}))
                                        .most_common())}

    # ── 4. Paramètres du découpage ──
    def decoupage(self, total_base) -> dict:
        """Fenêtres de dates du découpage (décision D31) : avec quelle fin
        l'union retrouve le total, et ce que donnent deux moitiés."""
        maintenant = datetime.now(timezone.utc).replace(microsecond=0)
        avec_marge = maintenant + timedelta(hours=parametres_api.MARGE_FIN_FENETRE_HEURES)
        milieu = maintenant - timedelta(days=3)

        def fenetre(debut, fin):
            return self.compter({**BASE, "minCreationDate": debut if isinstance(debut, str) else
                                 debut.strftime(FORMAT_DATE), "maxCreationDate": fin.strftime(FORMAT_DATE)})

        debut = parametres_api.DATE_PLUS_ANCIENNE
        essais = {
            "departement=75": self.compter({"departement": "75"}),
            "fenetre_7_jours": fenetre(maintenant - timedelta(days=7), maintenant),
            "fenetre_fin_maintenant": fenetre(debut, maintenant),
            "fenetre_fin_plus_3h": fenetre(debut, maintenant + timedelta(hours=3)),
            "fenetre_complete": fenetre(debut, avec_marge),
            "moitie_avant": fenetre(debut, milieu),
            "moitie_apres": fenetre(milieu, avec_marge),
        }
        # Total sans dates mesuré juste après, la base du début ayant pu bouger
        essais["total_sans_dates"] = self.compter(BASE)
        reference = essais["total_sans_dates"]["total"] or total_base
        for nom, e in essais.items():
            e["effet"] = self._effet(e, reference)
            self.afficher(f"  {nom} : {e['total']} ({e['statut']})"
                          + (f" {e.get('message', '')[:100]}" if e["total"] is None else ""))
        complete = essais["fenetre_complete"]["total"]
        essais["fenetre_complete_couvre_tout"] = (complete is not None and reference is not None
                                                  and abs(complete - reference) <= ECART_TOLERE)
        moities = [essais[k]["total"] for k in ("moitie_avant", "moitie_apres")]
        if None not in moities and complete is not None:
            essais["moities_moins_complete"] = sum(moities) - complete
            self.afficher(f"  deux moitiés : {sum(moities)} pour {complete} "
                          f"({sum(moities) - complete:+d} : offres à la borne commune, comptées deux fois "
                          "si les bornes sont incluses)")
        self.afficher(f"  fenêtre complète (fin + {parametres_api.MARGE_FIN_FENETRE_HEURES} h) : "
                      f"{complete} pour {reference} sans dates")
        return essais


    # ── 5. Stages ──
    def stage(self) -> dict:
        """Offres trouvées par motsCles=stage en Île-de-France : nombre,
        répartition par type et nature de contrat, intitulés d'exemple."""
        recherche = {**BASE, "motsCles": MOTS_CLES_STAGE}
        total = self.compter(recherche)
        self.afficher(f"  motsCles={MOTS_CLES_STAGE} : {total['total']} offres en Île-de-France"
                      + (f" ({total['statut']} {total.get('message', '')[:100]})" if total["total"] is None else ""))
        repartition = {}
        for param, referentiel in (("typeContrat", "types_contrats"), ("natureContrat", "natures_contrats")):
            libelles = referentiels.libelles(referentiels.france_travail(referentiel))
            totaux = {code: self.compter({**recherche, param: code})["total"] for code in libelles}
            non_nuls = {c: n for c, n in sorted(totaux.items(), key=lambda x: -(x[1] or 0)) if n}
            repartition[param] = {"totaux": totaux, "somme": sum(n or 0 for n in totaux.values()),
                                  "libelles": libelles}
            self.afficher(f"  par {param} (somme {repartition[param]['somme']}) : "
                          + (", ".join(f"{c} {libelles[c]} {n}" for c, n in non_nuls.items()) or "aucune"))
        # Échantillon : les plus récentes
        offres = []
        r = self.ex.get(ROUTE_RECHERCHE, params={**recherche, "range": PLAGE_PAGE, "sort": "1"})
        if r is not None and r.status_code in (200, 206):
            try:
                offres = r.json().get("resultats") or []
            except ValueError:
                pass
        intitules = [o.get("intitule") or "" for o in offres]
        avec_mot = sum(1 for t in intitules if any(m in t.lower() for m in MOTS_INTITULE_STAGE))
        echantillon = {
            "offres_lues": len(offres),
            "typeContrat": dict(Counter(o.get("typeContrat") or "?" for o in offres).most_common()),
            "natureContrat": dict(Counter(o.get("natureContrat") or "?" for o in offres).most_common()),
            "alternance": sum(1 for o in offres if o.get("alternance")),
            "intitule_avec_stage": avec_mot,
            "exemples": intitules[:EXEMPLES_STAGE],
        }
        self.afficher(f"  {len(offres)} plus récentes : types {echantillon['typeContrat']}, "
                      f"natures {echantillon['natureContrat']}, {echantillon['alternance']} en alternance, "
                      f"{avec_mot} avec « stage » ou « stagiaire » dans l'intitulé")
        self.afficher(f"  {min(EXEMPLES_STAGE, len(intitules))} intitulés d'exemple :")
        for t in echantillon["exemples"]:
            self.afficher(f"    - {t}")
        return {"recherche": recherche, "total": total, "repartition": repartition, "echantillon": echantillon}


def propositions(resultat: dict) -> dict:
    """Valeurs proposées pour france_travail/parametres_api.py (None : non tranché)."""
    dom = resultat["domaine"]
    valeurs = {"PARAM_GRAND_DOMAINE": dom["param_grand_domaine"], "PARAM_DOMAINE": dom["param_domaine"]}
    par_requete = dict(parametres_api.VALEURS_PAR_REQUETE)
    acceptes, refuses = {}, set()
    for essai in resultat["multiples"].values():
        param = essai.get("param")
        if essai.get("max"):
            acceptes[param] = max(acceptes.get(param, 0), essai["max"])
        elif essai.get("refuse"):
            refuses.add(param)
    for param in par_requete:
        if param in acceptes:
            par_requete[param] = acceptes[param]
        elif param in refuses:
            par_requete[param] = 1
    valeurs["VALEURS_PAR_REQUETE"] = par_requete
    valeurs["CHAMP_TRANCHE_EFFECTIF"] = resultat["tranche_effectif"]["champ_propose"]
    return valeurs


def resume(resultat: dict, afficher=print):
    afficher("")
    afficher("══ À reporter dans france_travail/parametres_api.py ══")
    for nom, valeur in resultat["propositions"].items():
        actuel = getattr(parametres_api, nom)
        if nom == "VALEURS_PAR_REQUETE":
            afficher("VALEURS_PAR_REQUETE = {")
            for param, n in valeur.items():
                note = "" if actuel.get(param) == n else f"   # actuel : {actuel.get(param)}"
                afficher(f"    {param!r}: {n},{note}")
            afficher("}")
        else:
            note = "inchangé" if actuel == valeur else f"actuel : {actuel!r}"
            afficher(f"{nom} = {valeur!r}   # {note}")
    if not resultat["propositions"]["PARAM_DOMAINE"]:
        afficher("⚠️  Aucun paramètre ne filtre M18 : voir les essais de domaine dans le fichier.")
    if resultat["domaine"].get("grand_domaine_contient_domaine") is False:
        afficher("⚠️  Le grand domaine M compte moins d'offres que M18 : paramètres à revoir.")
    if not resultat["decoupage"]["fenetre_complete_couvre_tout"]:
        afficher("⚠️  La fenêtre complète (avec la marge de fin) ne retrouve pas le total sans dates : "
                 "voir « decoupage » dans le fichier.")


def verifier_stage(v: Verificateur, afficher=print):
    """Étape 5, écrite à part : verification_stage.json."""
    resultat = {"verifie_le": datetime.now(timezone.utc).isoformat(timespec="seconds"), **v.stage()}
    chemin = v.ex.ecrire("verification_stage", resultat)
    afficher(f"Détail des stages écrit dans {chemin} : à lire avant de brancher France Travail "
             "dans le mode stage.")


def main(session=None, sortie=DOSSIER_SORTIE, pause=PAUSE_S, afficher=print, seulement_stage=False) -> int:
    ex = Explorateur(session=session, sortie=sortie, pause=pause, afficher=afficher)
    try:
        ex.obtenir_token()
    except ErreurToken as e:
        afficher(f"❌ {e}")
        return 1
    v = Verificateur(ex)
    if seulement_stage:
        afficher("5. Stages (motsCles) :")
        verifier_stage(v, afficher)
        return 0
    afficher("1. Paramètre de domaine :")
    domaine = v.domaine()
    afficher("2. Valeurs multiples :")
    multiples = v.multiples(domaine["param_domaine"], domaine["param_grand_domaine"])
    afficher("3. Tranche d'effectif dans les offres :")
    tranche = v.tranche_effectif()
    afficher("4. Paramètres du découpage :")
    decoupage = v.decoupage(domaine["base"]["total"])
    resultat = {"verifie_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "plage_de_comptage": v.plage, "domaine": domaine, "multiples": multiples,
                "tranche_effectif": tranche, "decoupage": decoupage}
    resultat["propositions"] = propositions(resultat)
    chemin = ex.ecrire("verification_api", resultat)
    afficher(f"Détail écrit dans {chemin}")
    afficher("5. Stages (motsCles) :")
    verifier_stage(v, afficher)
    resume(resultat, afficher)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vérification des points ouverts de l'API France Travail.")
    parser.add_argument("--sortie", type=Path, default=DOSSIER_SORTIE, help="dossier du fichier produit")
    parser.add_argument("--stage", action="store_true", help="seulement l'essai motsCles=stage (étape 5)")
    args = parser.parse_args()
    sys.exit(main(sortie=args.sortie, seulement_stage=args.stage))
