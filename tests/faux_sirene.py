"""API Sirene de l'INSEE (3.11) simulée, sans réseau : un jeu d'établissements
filtré par une requête dans le sous-ensemble de la syntaxe Lucene qu'emploie
le code (ET, OU, valeurs entre parenthèses, préfixe « 75* », existence
« -variable:* »), pagination par curseur.

Réglable : nom de la variable NAF 2025, nombre maximal de valeurs par OU
(au-delà : 414), syntaxe d'absence acceptée ou non.
"""

import json


class Reponse:
    def __init__(self, statut=200, corps=None):
        self.status_code = statut
        self._corps = corps
        self.headers = {}
        self.text = json.dumps(corps) if corps is not None else ""

    def json(self):
        if self._corps is None:
            raise ValueError("pas de JSON")
        return self._corps


def siret_sirene(n):
    """SIRET du siège simulé : SIREN n sur 9 chiffres, établissement 00012."""
    return f"{n:09d}00012"


def etablissement(n, naf="62.01Z", cp="75011", tranche="12", categorie="PME", naf25="62.10Y",
                  tranche_etab=None, siege=True, actif=True, nom=None):
    """Établissement simulé ; tranche None : unité légale sans tranche."""
    return {"siret": siret_sirene(n), "cp": cp, "naf": naf, "naf25": naf25, "tranche": tranche,
            "tranche_etab": tranche_etab if tranche_etab is not None else tranche,
            "categorie": categorie, "siege": siege, "actif": actif, "nom": nom or f"Société {n}"}


def _decouper(texte: str, separateur: str) -> list[str]:
    """Découpe au niveau 0 des parenthèses."""
    parties, profondeur, debut, i = [], 0, 0, 0
    while i < len(texte):
        c = texte[i]
        if c == "(":
            profondeur += 1
        elif c == ")":
            profondeur -= 1
        elif profondeur == 0 and texte.startswith(separateur, i):
            parties.append(texte[debut:i])
            i += len(separateur)
            debut = i
            continue
        i += 1
    parties.append(texte[debut:])
    return [p.strip() for p in parties]


class ErreurRequete(Exception):
    pass


class FausseSirene:
    def __init__(self, etablissements=(), variable_naf25="activitePrincipaleNAF25UniteLegale", max_ou=None,
                 absents_ok=True):
        self.etablissements = list(etablissements)
        self.variable_naf25 = variable_naf25
        self.max_ou = max_ou
        self.absents_ok = absents_ok
        self.recherches = []

    # ── Champs ──
    def _valeur(self, e, variable):
        table = {
            "etablissementSiege": "true" if e["siege"] else "false",
            "etatAdministratifUniteLegale": "A" if e["actif"] else "C",
            "activitePrincipaleUniteLegale": e["naf"],
            "codePostalEtablissement": e["cp"],
            "trancheEffectifsUniteLegale": e["tranche"],
            "trancheEffectifsEtablissement": e["tranche_etab"],
            "categorieEntreprise": e["categorie"],
        }
        if self.variable_naf25:
            table[self.variable_naf25] = e["naf25"]
        if variable not in table:
            raise ErreurRequete(f"Variable inconnue : {variable}")
        return table[variable]

    def _clause(self, texte):
        texte = texte.strip()
        if texte.startswith("(") and texte.endswith(")") and len(_decouper(texte[1:-1], " OR ")) > 1:
            sous = [self._clause(p) for p in _decouper(texte[1:-1], " OR ")]
            return lambda e: any(f(e) for f in sous)
        negation = texte.startswith("-") or texte.startswith("NOT ")
        if negation:
            texte = texte[1:] if texte.startswith("-") else texte[4:]
        variable, _, valeurs = texte.partition(":")
        if valeurs in ("*", "[* TO *]"):
            if not self.absents_ok:
                raise ErreurRequete("syntaxe non prise en charge")
            existe = lambda e: self._valeur(e, variable) not in (None, "")   # noqa: E731
            return (lambda e: not existe(e)) if negation else existe
        if valeurs.startswith("(") and valeurs.endswith(")"):
            liste = [v.strip() for v in valeurs[1:-1].split(" OR ")]
        else:
            liste = [valeurs]
        if self.max_ou and len(liste) > self.max_ou:
            raise ErreurRequete("trop de valeurs")

        def garde(e):
            v = self._valeur(e, variable)
            if v is None:
                return False
            return any(v.startswith(x[:-1]) if x.endswith("*") else v == x for x in liste)
        return (lambda e: not garde(e)) if negation else garde

    def filtrer(self, q):
        clauses = [self._clause(c) for c in _decouper(q, " AND ")]
        return [e for e in self.etablissements if all(f(e) for f in clauses)]

    # ── Format de l'API ──
    def _json(self, e):
        ul = {"siren": e["siret"][:9], "denominationUniteLegale": e["nom"], "categorieEntreprise": e["categorie"],
              "trancheEffectifsUniteLegale": e["tranche"], "activitePrincipaleUniteLegale": e["naf"],
              "nomenclatureActivitePrincipaleUniteLegale": "NAFRev2"}
        if self.variable_naf25:
            ul[self.variable_naf25] = e["naf25"]
        return {"siret": e["siret"], "trancheEffectifsEtablissement": e["tranche_etab"], "uniteLegale": ul,
                "adresseEtablissement": {"codePostalEtablissement": e["cp"], "libelleCommuneEtablissement": "PARIS",
                                         "numeroVoieEtablissement": "1", "typeVoieEtablissement": "RUE",
                                         "libelleVoieEtablissement": "TEST"},
                "periodesEtablissement": [{"dateFin": None, "activitePrincipaleEtablissement": e["naf"]}]}

    def get(self, url, params=None, headers=None, timeout=None, **_):
        params = dict(params or {})
        self.recherches.append(params)
        if not (headers or {}).get("X-INSEE-Api-Key-Integration"):
            return Reponse(401, {"header": {"statut": 401, "message": "clé absente"}})
        nombre = int(params.get("nombre", 20))
        if nombre > 1000:
            return Reponse(400, {"header": {"statut": 400, "message": "nombre doit être au plus 1000"}})
        q = params.get("q", "")
        if len(q) > 8000:
            return Reponse(414, None)
        try:
            trouves = self.filtrer(q)
        except ErreurRequete as e:
            statut = 414 if "trop" in str(e) else 400
            return Reponse(statut, {"header": {"statut": statut, "message": str(e)}})
        if not trouves:
            return Reponse(404, {"header": {"statut": 404, "message": "Aucun élément trouvé"}})
        curseur = params.get("curseur")
        debut = int(params.get("debut", 0)) if curseur is None else (0 if curseur == "*" else int(curseur[1:]))
        page = trouves[debut:debut + nombre]
        suivant = f"c{debut + nombre}" if debut + nombre < len(trouves) else (curseur or "*")
        return Reponse(200, {"header": {"statut": 200, "total": len(trouves), "debut": debut, "nombre": len(page),
                                        "curseur": curseur, "curseurSuivant": suivant},
                             "etablissements": [self._json(e) for e in page]})
