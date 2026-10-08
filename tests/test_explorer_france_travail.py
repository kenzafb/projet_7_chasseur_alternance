"""scripts/explorer_france_travail.py, réponses HTTP simulées : référentiels
(404 compris), répartition Île-de-France, test de pagination, et jamais
d'identifiant ni de token dans les fichiers produits."""

import json

import pytest
import requests

from scripts import explorer_france_travail as ex

ID, SECRET, TOKEN = "id-client-tres-secret", "secret-client-tres-secret", "token-tres-secret"


class Reponse:
    def __init__(self, statut=200, corps=None, entetes=None, texte=None):
        self.status_code = statut
        self._corps = corps
        self.headers = entetes or {}
        self.text = texte if texte is not None else (json.dumps(corps) if corps is not None else "")
        self.content = self.text.encode()

    def json(self):
        if self._corps is None:
            raise ValueError("pas de JSON")
        return self._corps


class FausseSession:
    """Routes simulées : chemin (après URL_API) -> fonction(params) -> Reponse."""

    def __init__(self):
        self.token = Reponse(200, {"access_token": TOKEN, "expires_in": 1499})
        self.routes = {}
        self.appels = []

    def post(self, url, data=None, timeout=None):
        self.appels.append(("POST", url, data))
        if isinstance(self.token, Exception):
            raise self.token
        return self.token

    def get(self, url, params=None, headers=None, timeout=None):
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        route = url.removeprefix(ex.URL_API)
        self.appels.append(("GET", route, params))
        if route not in self.routes:
            return Reponse(404, {"message": "Not Found"})
        return self.routes[route](params or {})


FILTRES = [
    {"filtre": "typeContrat", "agregation": [{"valeurPossible": "CDI", "nbResultats": 60000},
                                             {"valeurPossible": "CDD", "nbResultats": 25000}]},
    {"filtre": "natureContrat", "agregation": [{"valeurPossible": "E1", "nbResultats": 80000},
                                               {"valeurPossible": "E2", "nbResultats": 4000}]},
    {"filtre": "experience", "agregation": [{"valeurPossible": "1", "nbResultats": 50000}]},
]


def recherche(params):
    debut, fin = (int(x) for x in params["range"].split("-"))
    if fin - debut + 1 > 150:
        return Reponse(400, {"message": "La valeur du paramètre range est incorrecte. Taille max : 150."})
    if debut > 1000 or fin > 1149:
        return Reponse(400, {"message": "La position de départ doit être inférieure ou égale à 1000 et la "
                                        f"position finale à 1149. client={ID}"})
    return Reponse(206, {"resultats": [{"id": str(i)} for i in range(debut, fin + 1)],
                         "filtresPossibles": FILTRES},
                   {"Content-Range": f"offres {debut}-{fin}/91234", "Accept-Range": "offres 150"})


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("FT_CLIENT_ID", ID)
    monkeypatch.setenv("FT_CLIENT_SECRET", SECRET)
    monkeypatch.setattr(ex.time, "sleep", lambda s: None)
    s = FausseSession()
    s.routes["/referentiel/metiers"] = lambda p: Reponse(200, [{"code": "M18", "libelle": "Informatique"}])
    s.routes["/referentiel/typesContrats"] = lambda p: Reponse(200, [{"code": "CDI", "libelle": "Contrat à durée indéterminée"},
                                                                     {"code": "CDD", "libelle": "Contrat à durée déterminée"}])
    s.routes["/referentiel/naturesContrats"] = lambda p: Reponse(200, [{"code": "E2", "libelle": "Contrat apprentissage"}])
    s.routes["/referentiel/communes"] = lambda p: Reponse(200, [{"code": f"{i:05d}", "libelle": "x" * 40}
                                                                for i in range(30000)])
    s.routes["/referentiel/langues"] = lambda p: Reponse(500, {"message": f"panne, jeton {TOKEN}"})
    s.routes[ex.ROUTE_RECHERCHE] = recherche
    return s


def lancer(session, tmp_path):
    sorties = []
    code = ex.main(session=session, sortie=tmp_path, pause=0, afficher=sorties.append)
    return code, "\n".join(sorties)


def lire(tmp_path, nom):
    return json.loads((tmp_path / f"{nom}.json").read_text(encoding="utf-8"))


def test_referentiels(session, tmp_path):
    code, sortie = lancer(session, tmp_path)
    assert code == 0
    metiers = lire(tmp_path, "metiers")
    assert metiers["route"] == "/referentiel/metiers" and metiers["nombre"] == 1
    assert metiers["donnees"] == [{"code": "M18", "libelle": "Informatique"}]
    # Routes absentes : notées, pas de fichier, l'exploration continue
    assert not (tmp_path / "domaines.json").exists()
    assert "domaines" in sortie and "absent (404)" in sortie
    assert not (tmp_path / "langues.json").exists() and "erreur 500" in sortie
    # Chaque route configurée a été demandée
    demandees = {a[1] for a in session.appels if a[0] == "GET"}
    assert set(ex.ROUTES_REFERENTIELS.values()) <= demandees


def test_communes_trop_volumineuses_en_resume(session, tmp_path):
    lancer(session, tmp_path)
    communes = lire(tmp_path, "communes")
    assert communes["resume_seulement"] is True and communes["nombre"] == 30000
    assert len(communes["donnees"]) == ex.ELEMENTS_DANS_RESUME


def test_repartition_idf(session, tmp_path):
    lancer(session, tmp_path)
    appel = next(a for a in session.appels if a[1] == ex.ROUTE_RECHERCHE)
    assert appel[2] == {"region": "11", "range": "0-149"}   # aucun autre filtre
    rep = lire(tmp_path, "repartition_idf")
    assert rep["total"] == 91234 and rep["parametres"] == {"region": "11"}
    assert rep["filtres"]["typeContrat"][0] == {"valeur": "CDI", "nombre": 60000,
                                                "libelle": "Contrat à durée indéterminée"}
    assert rep["filtres"]["natureContrat"][1] == {"valeur": "E2", "nombre": 4000, "libelle": "Contrat apprentissage"}
    assert rep["filtres"]["experience"] == [{"valeur": "1", "nombre": 50000}]
    assert rep["filtres_possibles_bruts"] == FILTRES


def test_pagination(session, tmp_path):
    code, sortie = lancer(session, tmp_path)
    pag = lire(tmp_path, "test_pagination")
    par_plage = {e["range"]: e for e in pag["essais"]}
    assert set(par_plage) == set(ex.PLAGES_PAGINATION)
    assert par_plage["1000-1149"]["statut"] == 206 and par_plage["1000-1149"]["nombre_resultats"] == 150
    assert par_plage["1150-1299"]["statut"] == 400
    assert "1149" in par_plage["1150-1299"]["message"]
    assert "Taille max" in par_plage["0-199"]["message"]
    assert pag["dernier_index_obtenu"] == 1149
    assert "Résumé" in sortie and "91234" in sortie and "dernier index obtenu 1149" in sortie


def test_aucun_secret_dans_les_fichiers(session, tmp_path):
    lancer(session, tmp_path)
    fichiers = list(tmp_path.glob("*.json"))
    assert fichiers
    for f in fichiers:
        texte = f.read_text(encoding="utf-8")
        for secret in (ID, SECRET, TOKEN):
            assert secret not in texte, (f.name, secret)
    # Le message d'erreur qui contenait l'identifiant est bien gardé, purgé
    pag = lire(tmp_path, "test_pagination")
    assert "client=***" in {e["range"]: e for e in pag["essais"]}["1150-1299"]["message"]


def test_429_une_nouvelle_tentative(session, tmp_path):
    reponses = iter([Reponse(429, {}, {"Retry-After": "1"}), Reponse(200, [{"code": "A", "libelle": "a"}])])
    session.routes["/referentiel/domaines"] = lambda p: next(reponses)
    lancer(session, tmp_path)
    assert lire(tmp_path, "domaines")["nombre"] == 1


def test_404_sur_la_recherche(session, tmp_path):
    del session.routes[ex.ROUTE_RECHERCHE]
    code, sortie = lancer(session, tmp_path)
    assert code == 0
    assert lire(tmp_path, "repartition_idf")["statut"] == 404
    assert lire(tmp_path, "test_pagination")["plages_acceptees"] == []


@pytest.mark.parametrize("token", [Reponse(401, {"error": "invalid_client", "error_description": f"client {ID} inconnu"}),
                                   requests.ConnectionError("x")])
def test_token_refuse(session, tmp_path, token):
    session.token = token
    code, sortie = lancer(session, tmp_path)
    assert code == 1 and "❌" in sortie and ID not in sortie and SECRET not in sortie
    assert list(tmp_path.iterdir()) == []


def test_identifiants_absents(session, tmp_path, monkeypatch):
    monkeypatch.delenv("FT_CLIENT_SECRET")
    code, sortie = lancer(session, tmp_path)
    assert code == 1 and "FT_CLIENT_SECRET" in sortie and session.appels == []
