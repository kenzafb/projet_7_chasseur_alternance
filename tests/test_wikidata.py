"""Site officiel d'après Wikidata (D188) : SIREN (P1616) -> site (P856),
avant toute recherche web ; un site trouvé ainsi compte comme vérifié dès
que son accueil se lit."""

import spontanees.site_officiel as S
import spontanees.wikidata as W
from tests.faux_web import FauxWeb, brancher, site


class Rep:
    def __init__(self, statut, donnees):
        self.status_code, self._d = statut, donnees

    def json(self):
        return self._d


def _reponse(paires):
    return {"results": {"bindings": [{"siren": {"value": s}, "site": {"value": u}} for s, u in paires]}}


def test_interroger_lit_les_sites_par_siren(monkeypatch):
    envoye = {}

    def get(url, params=None, headers=None, timeout=None):
        envoye.update(params=params, headers=headers)
        return Rep(200, _reponse([("123456789", "https://acme.fr/"), ("123456789", "https://acme.com"),
                                  ("987654321", "ftp://x")]))
    monkeypatch.setattr(W.requests, "get", get)     # requests hors ligne de conftest, get remplacé
    assert W._interroger(["123456789", "987654321"]) == {"123456789": ["https://acme.fr/", "https://acme.com"]}
    assert '"123456789"' in envoye["params"]["query"] and "wdt:P1616" in envoye["params"]["query"]
    assert "wdt:P856" in envoye["params"]["query"]
    assert "Chasseur" in envoye["headers"]["User-Agent"] and "@" not in envoye["headers"]["User-Agent"]


def test_panne_de_wikidata(monkeypatch):
    assert W._interroger(["123456789"]) is None      # hors ligne (conftest)
    monkeypatch.setattr(W.requests, "get", lambda *a, **k: Rep(503, {}))
    assert W._interroger(["123456789"]) is None

    def coupe(*a, **k):
        raise W.requests.ConnectionError("hors ligne")
    monkeypatch.setattr(W.requests, "get", coupe)
    assert W._interroger(["123456789"]) is None


def test_lots_et_cache(monkeypatch):
    lots = []

    def interroger(sirens):
        lots.append(list(sirens))
        return {"000000001": ["https://un.fr"]} if len(lots) == 1 else None
    monkeypatch.setattr(W, "_interroger", interroger)
    monkeypatch.setattr(W, "TAILLE_LOT", 2)
    sirens = ["000000001", "000000002", "000000003", "pas un siren", "000000001"]
    assert W.precharger(sirens) == 1
    assert lots == [["000000001", "000000002"], ["000000003"]]
    assert W._cache == {"000000001": ["https://un.fr"], "000000002": []}   # lot sans réponse : pas en cache
    W.precharger(["000000001", "000000002"])
    assert len(lots) == 2                                                  # déjà connus : pas redemandés
    assert W.sites_wikidata({"_extra": {"siret": "00000000100012"}}) == ["https://un.fr"]


def test_site_wikidata_verifie_sans_autre_preuve(monkeypatch):
    # Ni SIREN ni nom sur le site : retenu quand même, déclaré dans Wikidata
    brancher(monkeypatch, FauxWeb(site(nom="Autre chose", siren="000000000")))
    monkeypatch.setattr(W, "_cache", {"123456789": ["https://acme.fr/"]})
    e = {"nom": "PLATEFORME DES DONNEES DE SANTE", "siren": "123456789"}
    v, essais = S.identifier(e, {}, recherche=lambda e: iter(["https://autre.fr"]), sites_export={})
    assert (v.source, v.preuve, v.domaine) == (S.WIKIDATA, "wikidata", "acme.fr")
    assert len(essais) == 1                                                # pas de recherche web


def test_avant_lba_et_illisible_passe_a_la_suite(monkeypatch):
    web = brancher(monkeypatch, FauxWeb(site(), erreurs=["https://mort.fr"]))
    monkeypatch.setattr(W, "_cache", {"123456789": ["https://mort.fr"]})
    e = {"nom": "ACME", "siren": "123456789"}
    v, essais = S.identifier(e, {}, None, sites_export={"123456789": "https://acme.fr"})
    assert v.source == S.LBA and v.url == "https://acme.fr"
    assert web.demandes.index("https://mort.fr") < web.demandes.index("https://acme.fr")
