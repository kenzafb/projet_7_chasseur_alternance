"""
scripts/verifier_lba.py
=======================
Vérifie sur la vraie API de La Bonne Alternance les points encore ouverts
(SPEC_SOURCES.md, section 7), à lancer par l'humain avec sa clé
(LBA_API_KEY du .env) :

    venv/bin/python scripts/verifier_lba.py

1. Requête de référence (10 codes M18, Paris, 30 km) : code de réponse,
   nombre d'offres par partenaire, nombre d'entreprises à fort potentiel,
   clés de la réponse.
2. Codes métiers : nombre maximal de codes par requête (20, 21, 30, 50,
   100 codes tirés de metiers.json) et recherche sans aucun code.
3. Rayon : 10, 30, 60, 100, 150, 200 et 201 km ; plus grand rayon accepté.
4. Coordonnées : sans coordonnées, et Cergy comparée à Paris sur 10 km
   (des résultats identiques signaleraient des coordonnées ignorées).
5. Niveau de diplôme : plusieurs noms et formats de paramètre, comparés à
   la référence (filtre, ignoré ou refusé, avec le message de l'API) ; pour
   le paramètre qui filtre, chaque niveau de 3 à 7 et le niveau lu dans
   les offres renvoyées. Information seulement : le niveau n'est jamais
   envoyé (décision D38), il est filtré après récupération.
6. Plafond par source : nombre maximal de résultats observé par source sur
   des recherches larges (si plusieurs sources butent sur la même valeur,
   c'est le plafond).
7. Entreprises à fort potentiel : tous les champs présents (chemins
   pointés), leur fréquence, des exemples (emails et téléphones masqués),
   et le chemin trouvé pour SIRET, nom, adresse, effectif, email,
   téléphone, identifiant de candidature.
8. Offres relayées depuis France Travail : offres par partenaire avec et
   sans les paramètres d'exclusion de parametres_lba.py.

Résultat détaillé dans docs/referentiels/lba/verification_api.json
(--sortie pour un autre dossier), sans clé ni email ni téléphone. À la fin,
les valeurs à reporter dans france_travail/parametres_lba.py, seul endroit
du code qui dépend de ces réponses. Une quarantaine de requêtes, moins
d'une minute. Code de sortie 1 si la clé manque ou est refusée, 0 sinon.
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import config  # noqa: E402  (charge le .env)
from france_travail import parametres_lba as P  # noqa: E402
from shared import referentiels  # noqa: E402

DOSSIER_SORTIE = config.BASE_DIR / "docs" / "referentiels" / "lba"
PAUSE_S = 0.5
DELAI_S = 30

PARIS = (48.8566, 2.3522)
CERGY = (49.0364, 2.0761)
CODES_REFERENCE = ["M1801", "M1802", "M1803", "M1804", "M1805",
                   "M1806", "M1807", "M1808", "M1809", "M1810"]
NOMBRES_DE_CODES = [20, 21, 30, 50, 100]
RAYONS = [10, 30, 60, 100, 150, 200, 201]
# (paramètre, valeur pour le niveau 6 = bac+3) ; une valeur inconnue en dernier
ESSAIS_NIVEAU = [
    ("target_diploma_level", "6"),
    ("diploma", "6"),
    ("diploma", "6 (Licence, BUT...)"),
    ("diplomaLevel", "6"),
    ("niveau", "6"),
    ("target_diploma_level", "99"),
]
# Niveau lu dans une offre, pour vérifier le sens du filtre
CHAMPS_NIVEAU_OFFRE = [P.CHAMP_NIVEAU_OFFRE, "offer.target_diploma_level", "diplomaLevel"]
# Champs recherchés dans les entreprises : nom -> mots du dernier élément du chemin
MOTS_CHAMPS = {
    "siret": ("siret",), "nom": ("name", "brand", "nom"), "adresse": ("address", "adresse"),
    "effectif": ("size", "effectif", "headcount"), "email": ("email", "mail"),
    "telephone": ("phone", "telephone", "tel"), "candidature": ("recipient", "apply", "url"),
}
MOTS_SENSIBLES = ("mail", "phone", "tel")
RE_EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.[\w.-]+)")


class ErreurCle(Exception):
    pass


def _chemins(valeur, prefixe=""):
    """(chemin pointé, valeur) de chaque champ feuille d'un dict, sous-dicts compris."""
    if isinstance(valeur, dict):
        for cle, v in valeur.items():
            chemin = f"{prefixe}.{cle}" if prefixe else cle
            if isinstance(v, dict):
                yield from _chemins(v, chemin)
            else:
                yield chemin, v


def masquer(chemin: str, valeur) -> str:
    """Exemple affichable : emails réduits au domaine, téléphones masqués."""
    texte = str(valeur)[:120]
    if any(m in chemin.rsplit(".", 1)[-1].lower() for m in MOTS_SENSIBLES):
        return RE_EMAIL.sub(r"***@\1", texte) if "@" in texte else "***"
    return RE_EMAIL.sub(r"***@\1", texte)


def _normaliser(texte) -> str:
    texte = str(texte or "").lower()
    for a, b in (("ô", "o"), ("é", "e"), ("è", "e")):
        texte = texte.replace(a, b)
    return texte


class Verificateur:
    def __init__(self, session=None, pause=PAUSE_S, afficher=print):
        self.session = session or requests.Session()
        self.pause = pause
        self.afficher = afficher
        self.cle = os.getenv("LBA_API_KEY", "")
        self.requetes = 0
        self.max_par_source = Counter()   # plus grand nombre de résultats vu par source
        self.max_offres = 0               # plus grand nombre d'offres vu dans une réponse
        self.entreprises_vues = []
        self.offres_vues = []

    def _purger(self, texte) -> str:
        texte = str(texte)
        return texte.replace(self.cle, "***") if self.cle else texte

    def _message(self, r) -> str:
        try:
            corps = r.json()
            texte = json.dumps(corps, ensure_ascii=False) if not isinstance(corps, dict) else (
                corps.get("message") or corps.get("error") or json.dumps(corps, ensure_ascii=False))
            if isinstance(corps, dict) and corps.get("data"):
                texte = f"{texte} {json.dumps(corps['data'], ensure_ascii=False)}"
        except (ValueError, AttributeError):
            texte = getattr(r, "text", "") or ""
        return self._purger(" ".join(str(texte).split())[:600])

    def rechercher(self, params: dict) -> dict:
        """{params, statut, offres, entreprises, par_source, message?} d'une recherche."""
        if self.requetes:
            time.sleep(self.pause)
        self.requetes += 1
        essai = {"params": {k: (v if len(str(v)) < 80 else f"{str(v)[:60]}... ({len(str(v).split(','))} valeurs)")
                            for k, v in params.items()},
                 "statut": None, "offres": None, "entreprises": None, "par_source": {}}
        try:
            r = self.session.get(P.URL_RECHERCHE, params=params, timeout=DELAI_S,
                                 headers={"Authorization": f"Bearer {self.cle}", "Accept": "application/json"})
        except requests.RequestException as e:
            essai["message"] = f"injoignable ({type(e).__name__})"
            return essai
        essai["statut"] = r.status_code
        if r.status_code in (401, 403):
            raise ErreurCle(f"clé LBA refusée ({r.status_code}) : {self._message(r)}")
        if r.status_code != 200:
            essai["message"] = self._message(r)
            return essai
        try:
            corps = r.json()
        except ValueError:
            essai["message"] = "réponse illisible"
            return essai
        offres = corps.get(P.CLE_OFFRES) or []
        entreprises = corps.get(P.CLE_ENTREPRISES) or []
        essai.update(offres=len(offres), entreprises=len(entreprises), cles_reponse=sorted(corps),
                     par_source=dict(Counter(str(P.lire(o, P.CHAMP_PARTENAIRE)) for o in offres)))
        if corps.get("warnings"):
            essai["avertissements"] = self._purger(json.dumps(corps["warnings"], ensure_ascii=False))[:600]
        essai["par_source"]["<entreprises>"] = len(entreprises)
        self.max_offres = max(self.max_offres, len(offres))
        for source, n in essai["par_source"].items():
            self.max_par_source[source] = max(self.max_par_source[source], n)
        self.entreprises_vues += entreprises[:200]
        self.offres_vues += offres[:200]
        essai["_corps"] = corps
        return essai

    def base(self, **autres) -> dict:
        lat, lon = autres.pop("centre", PARIS)
        params = {P.PARAM_CODES: ",".join(autres.pop("codes", CODES_REFERENCE)),
                  P.PARAM_LATITUDE: lat, P.PARAM_LONGITUDE: lon, P.PARAM_RAYON: autres.pop("rayon", 30)}
        params.update(P.PARAMS_EXCLUSION)
        params.update(autres)
        return {k: v for k, v in params.items() if v is not None}

    def _court(self, e) -> str:
        if e["statut"] != 200:
            return f"refusé ({e['statut']}) {e.get('message', '')[:150]}"
        return f"{e['offres']} offres, {e['entreprises']} entreprises"

    @staticmethod
    def _sans_corps(e):
        return {k: v for k, v in e.items() if k != "_corps"}

    # ── 1. Référence ──
    def reference(self) -> dict:
        e = self.rechercher(self.base())
        self.afficher(f"  {self._court(e)} ; par source : {e['par_source']}")
        return self._sans_corps(e)

    # ── 2. Codes métiers ──
    def codes(self) -> dict:
        metiers = [m["code"] for m in referentiels.france_travail("metiers")]
        metiers = sorted(metiers, key=lambda c: (not c.startswith("M18"), c))
        essais = {}
        for n in NOMBRES_DE_CODES:
            e = self.rechercher(self.base(codes=metiers[:n]))
            essais[n] = self._sans_corps(e)
            self.afficher(f"  {n} codes : {self._court(e)}")
        acceptes = [n for n, e in essais.items() if e["statut"] == 200]
        refuses = [n for n, e in essais.items() if e["statut"] != 200]
        maximum = max((n for n in acceptes if not refuses or n < min(refuses)), default=None)
        params = self.base()
        params.pop(P.PARAM_CODES)
        sans = self.rechercher(params)
        self.afficher(f"  sans code métier : {self._court(sans)}")
        return {"essais": essais, "max_par_requete": maximum, "sans_codes": self._sans_corps(sans),
                "accepte_sans_codes": sans["statut"] == 200 and (sans["offres"] or sans["entreprises"] or 0) > 0}

    # ── 3. Rayon ──
    def rayon(self) -> dict:
        essais = {}
        for km in RAYONS:
            e = self.rechercher(self.base(rayon=km))
            essais[km] = self._sans_corps(e)
            self.afficher(f"  {km} km : {self._court(e)}")
        acceptes = [km for km, e in essais.items() if e["statut"] == 200]
        return {"essais": essais, "rayon_max": max(acceptes, default=None)}

    # ── 4. Coordonnées ──
    def coordonnees(self) -> dict:
        params = self.base()
        for p in (P.PARAM_LATITUDE, P.PARAM_LONGITUDE, P.PARAM_RAYON):
            params.pop(p)
        sans = self.rechercher(params)
        paris = self.rechercher(self.base(rayon=10))
        cergy = self.rechercher(self.base(rayon=10, centre=CERGY))
        ids = [sorted(str(P.lire(o, "identifier.id")) for o in (e.get("_corps") or {}).get(P.CLE_OFFRES) or [])
               for e in (paris, cergy)]
        ignorees = paris["statut"] == cergy["statut"] == 200 and ids[0] == ids[1] and bool(ids[0])
        self.afficher(f"  sans coordonnées : {self._court(sans)}")
        self.afficher(f"  Paris 10 km : {self._court(paris)} ; Cergy 10 km : {self._court(cergy)}"
                      + (" ; résultats identiques : coordonnées ignorées ?" if ignorees else ""))
        return {"sans_coordonnees": self._sans_corps(sans), "paris_10km": self._sans_corps(paris),
                "cergy_10km": self._sans_corps(cergy), "coordonnees_ignorees": ignorees}

    # ── 5. Niveau de diplôme ──
    def niveau(self, reference: dict) -> dict:
        essais = []
        for param, valeur in ESSAIS_NIVEAU:
            e = self.rechercher(self.base(**{param: valeur}))
            if e["statut"] != 200:
                effet = "refusé"
            elif (e["offres"], e["entreprises"]) == (reference["offres"], reference["entreprises"]):
                effet = "ignoré (résultats inchangés)"
            else:
                effet = "filtre"
            essais.append({**self._sans_corps(e), "param": param, "valeur": valeur, "effet": effet})
            self.afficher(f"  {param}={valeur} : {self._court(e)} : {effet}")
        filtrant = next((e for e in essais if e["effet"] == "filtre" and e["valeur"] != "99"), None)
        par_niveau = {}
        if filtrant:
            p, v = filtrant["param"], filtrant["valeur"]
            for niv in range(3, 8):
                valeur = v.replace("6", str(niv), 1) if v.startswith("6") else str(niv)
                e = self.rechercher(self.base(rayon=60, **{p: valeur}))
                lus = Counter(str(next((P.lire(o, c) for c in CHAMPS_NIVEAU_OFFRE
                                        if P.lire(o, c) not in (None, "")), None))
                              for o in (e.get("_corps") or {}).get(P.CLE_OFFRES) or [])
                par_niveau[niv] = {**self._sans_corps(e), "valeur": valeur, "niveaux_lus_dans_les_offres": dict(lus)}
                self.afficher(f"  {p}={valeur} : {self._court(e)} ; niveaux lus : {dict(lus)}")
        return {"essais": essais, "param": filtrant["param"] if filtrant else None,
                "format_valeur": filtrant["valeur"] if filtrant else None, "par_niveau": par_niveau}

    # ── 6. Plafond ──
    def plafond(self, max_codes) -> dict:
        larges = sorted(m["code"] for m in referentiels.france_travail("metiers")
                        if m["code"][0] in "DMK")[: max_codes or P.CODES_PAR_REQUETE]
        essais = {}
        for km in (30, 60):
            e = self.rechercher(self.base(codes=larges, rayon=km))
            essais[f"{len(larges)} codes D, K, M, {km} km"] = self._sans_corps(e)
            self.afficher(f"  {len(larges)} codes larges, {km} km : {self._court(e)} ; {e['par_source']}")
        valeurs = Counter(n for n in self.max_par_source.values() if n >= 50)
        repete = [n for n, fois in valeurs.items() if fois >= 2]
        plafond = max(repete) if repete else None
        self.afficher(f"  plus grand nombre vu par source : {dict(self.max_par_source)}"
                      + (f" ; plusieurs sources butent sur {plafond}" if plafond else ""))
        return {"essais": essais, "max_par_source": dict(self.max_par_source), "plafond_observe": plafond,
                "max_offres": self.max_offres}

    # ── 7. Entreprises à fort potentiel ──
    def entreprises(self) -> dict:
        lues = self.entreprises_vues
        presence, exemples = Counter(), {}
        for ent in lues:
            for chemin, v in _chemins(ent):
                if v not in (None, "", [], {}):
                    presence[chemin] += 1
                    exemples.setdefault(chemin, [])
                    if len(exemples[chemin]) < 3:
                        exemples[chemin].append(masquer(chemin, v))
        champs = {c: {"presence": n, "sur": len(lues), "exemples": exemples[c]} for c, n in presence.most_common()}
        trouves = {}
        for nom, mots in MOTS_CHAMPS.items():
            trouves[nom] = [c for c in presence if any(m in c.rsplit(".", 1)[-1].lower() for m in mots)]
        self.afficher(f"  {len(lues)} entreprises lues, {len(champs)} champs")
        for nom, chemins in trouves.items():
            self.afficher(f"  {nom} : " + (", ".join(f"{c} ({presence[c]}/{len(lues)})" for c in chemins)
                                           or "absent"))
        actuels = {nom: {"chemins": chemins, "presence": {c: presence.get(c, 0) for c in chemins}}
                   for nom, chemins in P.CHAMPS_ENTREPRISE.items()}
        return {"lues": len(lues), "champs": champs, "champs_par_nom": trouves,
                "chemins_de_parametres_lba": actuels}

    # ── 8. Offres relayées depuis France Travail ──
    def france_travail(self) -> dict:
        avec = self.rechercher(self.base(rayon=60))
        params = self.base(rayon=60)
        for p in P.PARAMS_EXCLUSION:
            params.pop(p, None)
        sans = self.rechercher(params)
        labels = sorted(set(avec["par_source"]) | set(sans["par_source"]))
        relayees = [s for s in labels if any(m in _normaliser(s) for m in ("france travail", "pole emploi",
                                                                             "francetravail"))]
        restantes = {s: avec["par_source"].get(s, 0) for s in relayees if avec["par_source"].get(s)}
        self.afficher(f"  sans exclusion : {sans['par_source']}")
        self.afficher(f"  avec {P.PARAMS_EXCLUSION} : {avec['par_source']}")
        if restantes:
            self.afficher(f"  ⚠️  offres France Travail encore présentes malgré l'exclusion : {restantes} "
                          "(écartées par le code d'après leur partenaire)")
        return {"avec_exclusion": self._sans_corps(avec), "sans_exclusion": self._sans_corps(sans),
                "partenaires_france_travail": relayees, "restantes_malgre_exclusion": restantes,
                "exclusion_efficace": bool(relayees) and not restantes}


def propositions(res: dict) -> dict:
    """Valeurs proposées pour france_travail/parametres_lba.py (valeur actuelle si non tranché)."""
    prop = {}
    prop["CODES_PAR_REQUETE"] = res["codes"]["max_par_requete"] or P.CODES_PAR_REQUETE
    prop["ACCEPTE_SANS_CODES"] = res["codes"]["accepte_sans_codes"]
    prop["RAYON_MAX_KM"] = res["rayon"]["rayon_max"] or P.RAYON_MAX_KM
    prop["PLAFOND_PAR_SOURCE"] = res["plafond"]["plafond_observe"] or P.PLAFOND_PAR_SOURCE
    # Un total observé au-dessus du plafond actuel montre que le plafond est plus haut
    prop["PLAFOND_TOTAL_OFFRES"] = max(P.PLAFOND_TOTAL_OFFRES, res["plafond"]["max_offres"])
    noms = [_normaliser(s) for s in res["france_travail"]["partenaires_france_travail"]]
    prop["PARTENAIRES_FRANCE_TRAVAIL"] = tuple(sorted(set(P.PARTENAIRES_FRANCE_TRAVAIL) | set(noms)))
    return prop


def resume(res: dict, afficher=print):
    afficher("")
    afficher("══ À reporter dans france_travail/parametres_lba.py ══")
    for nom, valeur in res["propositions"].items():
        actuel = getattr(P, nom)
        note = "inchangé" if actuel == valeur else f"actuel : {actuel!r}"
        afficher(f"{nom} = {valeur!r}   # {note}")
    niv = res["niveau"]
    if niv["param"]:
        afficher(f"ℹ️  Niveau de diplôme : {niv['param']} filtre (format {niv['format_valeur']!r}), mais il "
                 "n'est pas envoyé (décision D38) : filtre après récupération sur "
                 f"{P.CHAMP_NIVEAU_OFFRE}, voir « par_niveau » dans le fichier.")
    else:
        afficher("ℹ️  Aucun paramètre de niveau ne filtre : voir « niveau » dans le fichier.")
    if not res["plafond"]["plafond_observe"]:
        afficher(f"ℹ️  Plafond par source non atteint : {P.PLAFOND_PAR_SOURCE} gardé (voir « plafond »).")
    if res["coordonnees"]["coordonnees_ignorees"]:
        afficher("⚠️  Paris et Cergy donnent les mêmes offres : coordonnées ignorées ?")
    ent = res["entreprises"]
    for nom in ("siret", "email", "candidature"):
        if not ent["champs_par_nom"].get(nom):
            afficher(f"ℹ️  Entreprises à fort potentiel : aucun champ « {nom} » trouvé.")
    afficher("Chemins des champs d'entreprise (CHAMPS_ENTREPRISE) : voir « entreprises » dans le fichier.")


def main(session=None, sortie=DOSSIER_SORTIE, pause=PAUSE_S, afficher=print) -> int:
    v = Verificateur(session=session, pause=pause, afficher=afficher)
    if not v.cle:
        afficher("❌ LBA_API_KEY absente du .env")
        return 1
    try:
        afficher("1. Requête de référence :")
        reference = v.reference()
        if reference["statut"] != 200:
            afficher(f"❌ La requête de référence échoue ({reference['statut']}) : {reference.get('message', '')}")
        afficher("2. Codes métiers :")
        codes = v.codes()
        afficher("3. Rayon :")
        rayon = v.rayon()
        afficher("4. Coordonnées :")
        coordonnees = v.coordonnees()
        afficher("5. Niveau de diplôme :")
        niveau = v.niveau(reference)
        afficher("6. Plafond par source :")
        plafond = v.plafond(codes["max_par_requete"])
        afficher("7. Entreprises à fort potentiel :")
        entreprises = v.entreprises()
        afficher("8. Offres relayées depuis France Travail :")
        ft = v.france_travail()
    except ErreurCle as e:
        afficher(f"❌ {e}")
        return 1
    res = {"verifie_le": datetime.now(timezone.utc).isoformat(timespec="seconds"), "requetes": v.requetes,
           "reference": reference, "codes": codes, "rayon": rayon, "coordonnees": coordonnees,
           "niveau": niveau, "plafond": plafond, "entreprises": entreprises, "france_travail": ft}
    res["propositions"] = propositions(res)
    sortie = Path(sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    chemin = sortie / "verification_api.json"
    texte = v._purger(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    chemin.write_text(texte + "\n", encoding="utf-8")
    afficher(f"Détail écrit dans {chemin} ({v.requetes} requêtes)")
    resume(res, afficher)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vérification des points ouverts de l'API La Bonne Alternance.")
    parser.add_argument("--sortie", type=Path, default=DOSSIER_SORTIE, help="dossier du fichier produit")
    sys.exit(main(sortie=parser.parse_args().sortie))
