"""
scripts/verifier_sirene.py
==========================
Vérifie sur la vraie API Sirene de l'INSEE (version 3.11) les points
encore ouverts (SPEC_SOURCES.md, section 7), à lancer par l'humain avec sa
clé (INSEE_API_KEY du .env) :

    venv/bin/python scripts/verifier_sirene.py

Requête de référence : sièges actifs à Paris (codes postaux 75), NAF 62.01Z.

1. Tranche d'effectif : filtre sur l'unité légale et sur l'établissement,
   liste de tranches par OU comparée à la somme des tranches seules ;
   « NN » ; unités sans tranche du tout (plusieurs syntaxes) ; part des
   effectifs non renseignés, comptée aussi sur 1000 établissements lus.
2. Catégorie d'entreprise : PME, ETI, GE seules et en liste, sur l'unité
   légale et (essai) sur l'établissement.
3. Plusieurs codes NAF en une requête : 2 et 10 codes comparés à la somme
   des codes seuls, puis 30, 60, 120 et 250 codes (limite de longueur).
4. Plusieurs départements en une requête : (75* OR 92*) comparé à la somme.
5. Code NAF 2025 : noms de variable candidats dans une requête, et champs
   des réponses dont le nom évoque une nomenclature ou la NAF 2025, avec
   leur présence réelle.
6. Pagination : nombre=1000 et 1001, début 1000 et 20000, trois pages par
   curseur.

Résultat détaillé dans docs/referentiels/insee/verification_api.json
(--sortie pour un autre dossier), sans clé. À la fin, les valeurs à
reporter dans spontanees/parametres_sirene.py, seul endroit du code qui
dépend de ces réponses. Une soixantaine de requêtes espacées de 2 s (quota
de 30 par minute), environ deux minutes. Code de sortie 1 si la clé manque
ou est refusée, 0 sinon.
"""

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import config  # noqa: E402  (charge le .env)
from spontanees import parametres_sirene as P  # noqa: E402

DOSSIER_SORTIE = config.BASE_DIR / "docs" / "referentiels" / "insee"
CORRESPONDANCE = config.BASE_DIR / "docs" / "referentiels" / "insee" / "correspondance_naf_rev2_naf2025.csv"
PAUSE_S = 2.1          # quota de l'API : 30 requêtes par minute
DELAI_S = 30

BASE = ["etablissementSiege:true", "etatAdministratifUniteLegale:A"]
DEPT, NAF = "75", "62.01Z"
TRANCHES = ["00", "01", "02", "03", "11", "12", "21", "22", "31", "32", "41", "42", "51", "52", "53"]
CATEGORIES = ["PME", "ETI", "GE"]
NOMBRES_DE_NAF = [30, 60, 120, 250]
CANDIDATS_NAF2025 = [
    "activitePrincipaleNAF25UniteLegale", "activitePrincipaleUniteLegaleNAF25",
    "activitePrincipaleNaf25UniteLegale", "activitePrincipaleNAF2025UniteLegale",
    "activitePrincipale2025UniteLegale",
]
SYNTAXES_ABSENTS = [
    "-{v}:*", "NOT {v}:*", "-{v}:[* TO *]",
]
MOTS_NOMENCLATURE = ("naf", "nomenclature", "2025", "25")


class ErreurCle(Exception):
    pass


def requete(*clauses) -> str:
    return " AND ".join(BASE + [c for c in clauses if c])


def ou(variable: str, valeurs) -> str:
    valeurs = list(valeurs)
    return f"{variable}:{valeurs[0]}" if len(valeurs) == 1 else f"{variable}:({' OR '.join(valeurs)})"


def _cles(valeur, prefixe=""):
    """Chemins pointés de toutes les clés d'un objet (listes parcourues)."""
    if isinstance(valeur, dict):
        for k, v in valeur.items():
            chemin = f"{prefixe}.{k}" if prefixe else k
            yield chemin, v
            yield from _cles(v, chemin)
    elif isinstance(valeur, list):
        for v in valeur[:1]:
            yield from _cles(v, prefixe + "[]")


def codes_naf_rev2() -> list[str]:
    with open(CORRESPONDANCE, encoding="utf-8") as f:
        return sorted({ligne["naf_rev2"] for ligne in csv.DictReader(f)})


class Verificateur:
    def __init__(self, session=None, pause=PAUSE_S, afficher=print):
        self.session = session or requests.Session()
        self.pause = pause
        self.afficher = afficher
        self.cle = os.getenv("INSEE_API_KEY", "")
        self.requetes = 0

    def _purger(self, texte) -> str:
        texte = str(texte)
        return texte.replace(self.cle, "***") if self.cle else texte

    def appeler(self, q: str, **params) -> dict:
        """{q, statut, total, message?, _corps?} d'une recherche."""
        if self.requetes:
            time.sleep(self.pause)
        self.requetes += 1
        essai = {"q": q if len(q) < 300 else f"{q[:200]}... ({len(q)} caractères)", "statut": None, "total": None}
        params = {"q": q, "nombre": 1, **params}
        try:
            r = self.session.get(P.URL_RECHERCHE, params=params, timeout=DELAI_S,
                                 headers={P.ENTETE_CLE: self.cle, "Accept": "application/json"})
        except requests.RequestException as e:
            essai["message"] = f"injoignable ({type(e).__name__})"
            return essai
        essai["statut"] = r.status_code
        if r.status_code in (401, 403):
            raise ErreurCle(f"clé INSEE refusée ({r.status_code})")
        if r.status_code == 404:
            essai["total"] = 0
            return essai
        try:
            corps = r.json()
        except ValueError:
            corps = None
        if r.status_code != 200 or not isinstance(corps, dict):
            texte = (corps or {}).get("header", {}).get("message") if isinstance(corps, dict) else None
            essai["message"] = self._purger(" ".join(str(texte or getattr(r, "text", ""))[:400].split()))
            return essai
        entete = corps.get("header") or {}
        essai["total"] = entete.get("total")
        essai["curseur_suivant"] = entete.get("curseurSuivant")
        essai["_corps"] = corps
        return essai

    def compter(self, *clauses) -> dict:
        return self.appeler(requete(*clauses))

    @staticmethod
    def sans_corps(e: dict) -> dict:
        return {k: v for k, v in e.items() if k != "_corps"}

    def _court(self, e) -> str:
        if e["total"] is None:
            return f"refusé ({e['statut']}) {e.get('message', '')[:150]}"
        return str(e["total"])

    def comparer_liste(self, variable, valeurs, *clauses) -> dict:
        """Liste par OU comparée à la somme des valeurs seules."""
        seules = {v: self.compter(f"{variable}:{v}", *clauses)["total"] for v in valeurs}
        liste = self.compter(ou(variable, valeurs), *clauses)
        somme = sum(t or 0 for t in seules.values())
        accepte = liste["total"] is not None and liste["total"] == somme
        return {"seules": seules, "somme": somme, "liste": self.sans_corps(liste), "ou_exact": accepte}

    # ── Référence ──
    def reference(self) -> dict:
        e = self.compter(f"{P.VARIABLE_CODE_POSTAL}:{DEPT}*", f"activitePrincipaleUniteLegale:{NAF}")
        self.afficher(f"  sièges actifs, {DEPT}, {NAF} : {self._court(e)}")
        return self.sans_corps(e)

    # ── 1. Tranche d'effectif ──
    def tranches(self, total) -> dict:
        base = (f"{P.VARIABLE_CODE_POSTAL}:{DEPT}*", f"activitePrincipaleUniteLegale:{NAF}")
        res = {}
        for variable in ("trancheEffectifsUniteLegale", "trancheEffectifsEtablissement"):
            c = self.comparer_liste(variable, ["11", "12"], *base)
            nn = self.compter(f"{variable}:NN", *base)
            c["NN"] = nn["total"]
            absents = {}
            for syntaxe in SYNTAXES_ABSENTS:
                e = self.compter(syntaxe.format(v=variable), *base)
                absents[syntaxe] = self.sans_corps(e)
            c["absents"] = absents
            res[variable] = c
            self.afficher(f"  {variable} : (11 OR 12) {c['liste']['total']} pour {c['somme']} "
                          f"({'OU exact' if c['ou_exact'] else 'différent'}) ; NN {nn['total']} ; absents : "
                          + ", ".join(f"{s.format(v='…')} {self._court(e)}" for s, e in absents.items()))
        # Répartition lue dans 1000 établissements (absents compris)
        e = self.appeler(requete(*base), nombre=P.PAR_PAGE)
        etabs = (e.get("_corps") or {}).get("etablissements") or []
        ul = Counter(str((x.get("uniteLegale") or {}).get("trancheEffectifsUniteLegale")) for x in etabs)
        et = Counter(str(x.get("trancheEffectifsEtablissement")) for x in etabs)
        inconnus = ul.get("NN", 0) + ul.get("None", 0)
        res["lus"] = {"etablissements": len(etabs), "unite_legale": dict(ul.most_common()),
                      "etablissement": dict(et.most_common()),
                      "part_non_renseignes_unite_legale": round(inconnus / len(etabs), 3) if etabs else None}
        self.afficher(f"  sur {len(etabs)} établissements lus : tranche de l'unité légale NN ou absente "
                      f"{inconnus} ({res['lus']['part_non_renseignes_unite_legale']}) ; détail {dict(ul.most_common(6))}")
        # Part des non renseignés sur toute la requête : total moins les tranches connues
        connues = self.compter(ou("trancheEffectifsUniteLegale", TRANCHES), *base)["total"]
        res["toutes_tranches_connues"] = connues
        res["total"] = total
        res["part_non_renseignes_requete"] = (round(1 - connues / total, 3)
                                              if connues is not None and total else None)
        self.afficher(f"  tranches connues {connues} sur {total} : non renseignés "
                      f"{res['part_non_renseignes_requete']}")
        return res

    # ── 2. Catégorie ──
    def categories(self) -> dict:
        base = (f"{P.VARIABLE_CODE_POSTAL}:{DEPT}*", f"activitePrincipaleUniteLegale:{NAF}")
        c = self.comparer_liste("categorieEntreprise", CATEGORIES, *base)
        self.afficher(f"  categorieEntreprise : {c['seules']} ; liste {c['liste']['total']} "
                      f"({'OU exact' if c['ou_exact'] else 'différent'})")
        etab = self.compter("categorieEntrepriseEtablissement:GE", *base)
        self.afficher(f"  categorieEntrepriseEtablissement:GE : {self._court(etab)}")
        grandes = self.compter(f"({ou('trancheEffectifsUniteLegale', ['32', '41', '42', '51', '52', '53'])} "
                               f"OR {ou('categorieEntreprise', ['ETI', 'GE'])})", *base)
        self.afficher(f"  250 salariés et plus OU catégorie ETI ou GE : {self._court(grandes)}")
        return {"unite_legale": c, "etablissement_GE": self.sans_corps(etab),
                "transverses_tranche_ou_categorie": self.sans_corps(grandes)}

    # ── 3. Plusieurs codes NAF ──
    def naf_multiples(self) -> dict:
        dept = f"{P.VARIABLE_CODE_POSTAL}:{DEPT}*"
        res = {"deux": self.comparer_liste("activitePrincipaleUniteLegale", ["62.01Z", "62.02A"], dept),
               "dix": self.comparer_liste("activitePrincipaleUniteLegale",
                                          ["62.01Z", "62.02A", "62.02B", "62.03Z", "62.09Z", "63.11Z", "63.12Z",
                                           "58.21Z", "58.29A", "58.29C"], dept)}
        for nom in ("deux", "dix"):
            self.afficher(f"  {nom} codes : {res[nom]['liste']['total']} pour {res[nom]['somme']} "
                          f"({'OU exact' if res[nom]['ou_exact'] else 'différent'})")
        codes = codes_naf_rev2()
        longs = {}
        for n in NOMBRES_DE_NAF:
            e = self.compter(ou("activitePrincipaleUniteLegale", codes[:n]), dept)
            longs[n] = self.sans_corps(e)
            self.afficher(f"  {n} codes : {self._court(e)}")
        res["longs"] = longs
        # Plus grand nombre de codes accepté (10 au moins si la liste de dix est exacte)
        acceptes = [n for n, e in longs.items() if e["total"] is not None]
        res["max_accepte"] = max(acceptes, default=10 if res["dix"]["ou_exact"] else None)
        return res

    # ── 4. Plusieurs départements ──
    def departements(self) -> dict:
        naf = f"activitePrincipaleUniteLegale:{NAF}"
        seules = {d: self.compter(f"{P.VARIABLE_CODE_POSTAL}:{d}*", naf)["total"] for d in ("75", "92")}
        liste = self.compter(f"{P.VARIABLE_CODE_POSTAL}:(75* OR 92*)", naf)
        somme = sum(t or 0 for t in seules.values())
        self.afficher(f"  (75* OR 92*) : {self._court(liste)} pour {somme}")
        return {"seules": seules, "somme": somme, "liste": self.sans_corps(liste),
                "ou_exact": liste["total"] == somme}

    # ── 5. NAF 2025 ──
    def naf2025(self) -> dict:
        base = (f"{P.VARIABLE_CODE_POSTAL}:{DEPT}*",)
        e = self.appeler(requete(*base, f"activitePrincipaleUniteLegale:{NAF}"), nombre=100)
        etabs = (e.get("_corps") or {}).get("etablissements") or []
        presence, exemples = Counter(), {}
        for x in etabs:
            for chemin, v in _cles(x):
                nom = chemin.rsplit(".", 1)[-1].lower()
                if any(m in nom for m in MOTS_NOMENCLATURE) and not isinstance(v, (dict, list)):
                    if v not in (None, ""):
                        presence[chemin] += 1
                    exemples.setdefault(chemin, Counter())[str(v)] += 1
        champs = {c: {"presence": presence.get(c, 0), "sur": len(etabs),
                      "valeurs": dict(exemples[c].most_common(5))} for c in exemples}
        for c, d in champs.items():
            self.afficher(f"  champ {c} : non vide dans {d['presence']}/{d['sur']}, ex. {d['valeurs']}")
        essais = {}
        for variable in CANDIDATS_NAF2025:
            r = self.compter(*base, f"{variable}:62.10Y")
            essais[variable] = self.sans_corps(r)
            self.afficher(f"  {variable}:62.10Y : {self._court(r)}")
        trouve = next((v for v, r in essais.items() if r["total"]), None)
        # Variable vue dans les réponses, même si le nom essayé n'y était pas
        vue = next((c.rsplit(".", 1)[-1] for c in champs
                    if ("naf25" in c.lower() or "2025" in c) and champs[c]["presence"]), None)
        return {"champs": champs, "essais": essais, "variable_qui_filtre": trouve,
                "variable_vue_dans_les_reponses": vue}

    # ── 6. Pagination ──
    def pagination(self) -> dict:
        q = requete(f"{P.VARIABLE_CODE_POSTAL}:{DEPT}*", f"activitePrincipaleUniteLegale:{NAF}")
        res = {}
        for nom, params in (("nombre_1000", {"nombre": 1000}), ("nombre_1001", {"nombre": 1001}),
                            ("debut_1000", {"debut": 1000}), ("debut_20000", {"debut": 20000})):
            e = self.appeler(q, **params)
            res[nom] = self.sans_corps(e)
            self.afficher(f"  {nom} : {self._court(e)}")
        curseur, pages, lus = "*", 0, 0
        for _ in range(3):
            e = self.appeler(q, nombre=P.PAR_PAGE, curseur=curseur)
            if e["total"] is None:
                break
            pages += 1
            lus += len((e.get("_corps") or {}).get("etablissements") or [])
            suivant = e.get("curseur_suivant")
            if not suivant or suivant == curseur:
                break
            curseur = suivant
        res["curseur"] = {"pages": pages, "lus": lus}
        self.afficher(f"  curseur : {pages} pages, {lus} établissements lus")
        return res


def propositions(res: dict) -> dict:
    """Valeurs proposées pour spontanees/parametres_sirene.py (valeur actuelle si non tranché)."""
    prop = {}
    nafs = res["naf_multiples"]
    prop["NAF_PAR_REQUETE"] = nafs["max_accepte"] if nafs["dix"]["ou_exact"] else P.NAF_PAR_REQUETE
    prop["DEPARTEMENTS_PAR_REQUETE"] = 8 if res["departements"]["ou_exact"] else P.DEPARTEMENTS_PAR_REQUETE
    variable = res["naf2025"]["variable_qui_filtre"]
    prop["VARIABLE_NAF"] = {**P.VARIABLE_NAF, "NAF2025": variable or P.VARIABLE_NAF["NAF2025"]}
    absents = res["tranches"]["trancheEffectifsUniteLegale"]["absents"]
    syntaxe = next((s for s, e in absents.items() if e["total"]), None)
    prop["ABSENTS_PAR"] = syntaxe.format(v=P.VARIABLE_TRANCHE) if syntaxe else P.ABSENTS_PAR
    prop["PAR_PAGE"] = 1000 if res["pagination"]["nombre_1000"]["total"] is not None else P.PAR_PAGE
    return prop


def resume(res: dict, afficher=print):
    afficher("")
    afficher("══ À reporter dans spontanees/parametres_sirene.py ══")
    for nom, valeur in res["propositions"].items():
        actuel = getattr(P, nom)
        note = "inchangé" if actuel == valeur else f"actuel : {actuel!r}"
        afficher(f"{nom} = {valeur!r}   # {note}")
    n25 = res["naf2025"]
    if not n25["variable_qui_filtre"]:
        afficher("⚠️  Aucune variable NAF 2025 essayée ne filtre"
                 + (f" ; vue dans les réponses : {n25['variable_vue_dans_les_reponses']}"
                    if n25["variable_vue_dans_les_reponses"] else "")
                 + ". Voir « naf2025 » dans le fichier.")
    if not res["tranches"]["trancheEffectifsUniteLegale"]["ou_exact"]:
        afficher("⚠️  La liste de tranches par OU ne donne pas la somme des tranches seules.")


def main(session=None, sortie=DOSSIER_SORTIE, pause=PAUSE_S, afficher=print) -> int:
    v = Verificateur(session=session, pause=pause, afficher=afficher)
    if not v.cle:
        afficher("❌ INSEE_API_KEY absente du .env")
        return 1
    try:
        afficher("Référence :")
        reference = v.reference()
        afficher("1. Tranche d'effectif :")
        tranches = v.tranches(reference["total"])
        afficher("2. Catégorie d'entreprise :")
        categories = v.categories()
        afficher("3. Plusieurs codes NAF :")
        naf_multiples = v.naf_multiples()
        afficher("4. Plusieurs départements :")
        departements = v.departements()
        afficher("5. Code NAF 2025 :")
        naf2025 = v.naf2025()
        afficher("6. Pagination :")
        pagination = v.pagination()
    except ErreurCle as e:
        afficher(f"❌ {e}")
        return 1
    res = {"verifie_le": datetime.now(timezone.utc).isoformat(timespec="seconds"), "requetes": v.requetes,
           "reference": reference, "tranches": tranches, "categories": categories,
           "naf_multiples": naf_multiples, "departements": departements, "naf2025": naf2025,
           "pagination": pagination}
    res["propositions"] = propositions(res)
    sortie = Path(sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    chemin = sortie / "verification_api.json"
    chemin.write_text(v._purger(json.dumps(res, ensure_ascii=False, indent=2, default=str)) + "\n",
                      encoding="utf-8")
    afficher(f"Détail écrit dans {chemin} ({v.requetes} requêtes)")
    resume(res, afficher)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vérification des points ouverts de l'API Sirene.")
    parser.add_argument("--sortie", type=Path, default=DOSSIER_SORTIE, help="dossier du fichier produit")
    sys.exit(main(sortie=parser.parse_args().sortie))
