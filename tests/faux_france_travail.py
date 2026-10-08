"""API Offres d'emploi v2 de France Travail simulée, sans réseau : un jeu
d'offres filtré selon les paramètres de recherche, avec les limites de
pagination mesurées le 8 octobre 2026 (150 par page, début au plus 3000).

Le comportement des points encore à vérifier (SPEC_SOURCES section 7) est
réglable : paramètres reconnus (un paramètre inconnu est ignoré, comme
le ferait l'API au pire), valeurs multiples acceptées ou non.
"""

import json
from datetime import datetime, timedelta, timezone

URL_TOKEN = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
URL_RECHERCHE = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
DEPTS = ["75", "77", "78", "91", "92", "93", "94", "95"]
MAINTENANT = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class Reponse:
    def __init__(self, statut=200, corps=None, entetes=None):
        self.status_code = statut
        self._corps = corps
        self.headers = entetes or {}
        self.text = json.dumps(corps) if corps is not None else ""
        self.content = self.text.encode()

    def json(self):
        if self._corps is None:
            raise ValueError("pas de JSON")
        return self._corps


def offre(n, dept="75", domaine="M18", nature="E2", type_contrat="CDD", secteur="62", themes=(),
          jours=0, tranche="20 à 49 salariés", alternance=None, titre=None):
    """Offre au format de l'API ; les champs « _ » servent au filtrage simulé."""
    o = {
        "id": f"FT{n}",
        "intitule": titre or f"Offre {n}",
        "lieuTravail": {"libelle": f"{dept} - Ville"},
        "entreprise": {"nom": f"Entreprise {n}"},
        "romeCode": f"{domaine}05",
        "typeContrat": type_contrat,
        "natureContrat": nature,
        "secteurActivite": secteur,
        "alternance": nature in ("E2", "FS") if alternance is None else alternance,
        "dateCreation": (MAINTENANT - timedelta(days=jours, minutes=n % 1000)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "_dept": dept, "_domaine": domaine, "_themes": list(themes),
    }
    if tranche is not None:
        o["trancheEffectifEtab"] = tranche
    return o


def _date(texte):
    return datetime.strptime(texte, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class FausseAPI:
    """Remplace requests.get / requests.post (ou une session) pour France Travail."""

    def __init__(self, offres=(), params_reconnus=None, multiples=None, multiples_refuses=False,
                 max_valeurs=None, decalage_heures=0):
        self.offres = list(offres)
        # Paramètres de filtre compris par l'API simulée ; les autres sont ignorés
        self.params_reconnus = set(params_reconnus if params_reconnus is not None else (
            "region", "departement", "natureContrat", "typeContrat", "grandDomaine", "domaine",
            "secteurActivite", "theme", "codeROME", "minCreationDate", "maxCreationDate", "qualification"))
        # Paramètres acceptant plusieurs valeurs (OU) ; les autres : première valeur seulement,
        # ou 400 si multiples_refuses
        self.multiples = set(multiples if multiples is not None else self.params_reconnus)
        self.multiples_refuses = multiples_refuses
        # Nombre maximal de valeurs par paramètre (400 au-delà), ex. {"secteurActivite": 2}
        self.max_valeurs = dict(max_valeurs or {})
        # Dates reçues lues en heure locale (Paris en été : 2) malgré le « Z »
        self.decalage_heures = decalage_heures
        self.recherches = []
        self.token = Reponse(200, {"access_token": "token-de-test", "expires_in": 1499})

    # ── requests ──
    def post(self, url, data=None, timeout=None, **_):
        return self.token

    def get(self, url, params=None, headers=None, timeout=None, **_):
        assert url.endswith("/offres/search"), url
        params = dict(params or {})
        self.recherches.append(params)
        return self.rechercher(params)

    # ── Simulation ──
    def _garde(self, o, param, valeurs):
        if param == "region":
            return "11" in valeurs
        if param == "departement":
            return o["_dept"] in valeurs
        if param == "natureContrat":
            return o["natureContrat"] in valeurs
        if param == "typeContrat":
            return o["typeContrat"] in valeurs
        if param == "grandDomaine":
            return any(o["_domaine"].startswith(v) for v in valeurs)
        if param == "domaine":
            return o["_domaine"] in valeurs
        if param == "secteurActivite":
            return o["secteurActivite"] in valeurs
        if param == "theme":
            return any(t in valeurs for t in o["_themes"])
        if param == "codeROME":
            return o["romeCode"] in valeurs
        if param == "qualification":
            return o.get("qualificationCode", "X") in valeurs
        return True

    def filtrer(self, params):
        offres = self.offres
        dates = {"minCreationDate", "maxCreationDate"} & self.params_reconnus
        if dates & set(params):
            if not ("minCreationDate" in params and "maxCreationDate" in params):
                raise ValueError("les deux dates sont exigées")
            decalage = timedelta(hours=self.decalage_heures)
            debut = _date(params["minCreationDate"]) - decalage
            fin = _date(params["maxCreationDate"]) - decalage
            offres = [o for o in offres if debut <= _date(o["dateCreation"][:19] + "Z") <= fin]
        for param, brut in params.items():
            if param in ("range", "sort", "minCreationDate", "maxCreationDate") or param not in self.params_reconnus:
                continue
            valeurs = str(brut).split(",")
            if len(valeurs) > self.max_valeurs.get(param, len(valeurs)):
                raise ValueError(f"Format du paramètre « {param} » incorrect.")
            if len(valeurs) > 1 and param not in self.multiples:
                if self.multiples_refuses:
                    raise ValueError(f"{param} : une seule valeur")
                valeurs = valeurs[:1]
            offres = [o for o in offres if self._garde(o, param, valeurs)]
        return offres

    def rechercher(self, params):
        debut, fin = (int(x) for x in params.get("range", "0-149").split("-"))
        if fin - debut + 1 > 150:
            return Reponse(400, {"message": "La plage de résultats demandée est trop importante."})
        if debut > 3000:
            return Reponse(400, {"message": "La position de début doit être inférieure ou égale à 3000."})
        try:
            trouvees = self.filtrer(params)
        except ValueError as e:
            return Reponse(400, {"message": str(e)})
        if not trouvees:
            return Reponse(204)
        if params.get("sort") == "1":   # date de création décroissante, comme l'API
            trouvees = sorted(trouvees, key=lambda o: o["dateCreation"], reverse=True)
        page = trouvees[debut:fin + 1]
        statut = 200 if len(trouvees) <= fin + 1 and debut == 0 else 206
        return Reponse(statut, {"resultats": page},
                       {"Content-Range": f"offres {debut}-{debut + len(page) - 1}/{len(trouvees)}",
                        "Accept-Range": "150"})
