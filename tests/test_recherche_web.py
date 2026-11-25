"""Recherche web du site (D187) : moteurs de ddgs dans l'ordre de
RECHERCHE_BACKENDS avec repli, arrêt pour le lancement après
ECHECS_AVANT_ARRET requêtes d'affilée sans réponse."""

import pytest

import spontanees.recherche_emails as se


class FauxDDGS:
    """Remplace ddgs.DDGS : reponses[moteur] = liste d'URLs, ou exception."""
    reponses: dict = {}
    appels: list = []

    def __init__(self, **_):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def text(self, requete, region=None, backend=None, max_results=10):
        FauxDDGS.appels.append((backend, region))
        r = FauxDDGS.reponses.get(backend, Exception("No results found."))
        if isinstance(r, Exception):
            raise r
        return [{"href": u, "title": "", "body": ""} for u in r]


@pytest.fixture
def moteurs(monkeypatch):
    FauxDDGS.reponses, FauxDDGS.appels = {}, []
    monkeypatch.setattr(se, "DDGS", FauxDDGS)
    monkeypatch.setattr(se, "pause_ddg", lambda: None)
    monkeypatch.delenv("RECHERCHE_BACKENDS", raising=False)
    journal = []
    monkeypatch.setattr(se, "journaliser", journal.append)
    se.reinitialiser_recherche()
    yield journal
    se.reinitialiser_recherche()


def test_ordre_par_defaut_et_depuis_env(moteurs, monkeypatch):
    assert se.backends_recherche() == ["brave", "mojeek", "duckduckgo", "yahoo", "yandex"]
    monkeypatch.setenv("RECHERCHE_BACKENDS", " Yandex, mojeek ,inconnu, mojeek")
    assert se.backends_recherche() == ["yandex", "mojeek"]
    assert any("inconnu" in ligne for ligne in moteurs)
    monkeypatch.setenv("RECHERCHE_BACKENDS", "inconnu")
    assert se.backends_recherche() == ["brave", "mojeek", "duckduckgo", "yahoo", "yandex"]


def test_repli_sur_le_moteur_suivant(moteurs):
    FauxDDGS.reponses = {"brave": Exception("429 Ratelimit"), "mojeek": ["https://acme.fr"],
                         "duckduckgo": ["https://autre.fr"]}
    assert [r["href"] for r in se._resultats_ddg("acme")] == ["https://acme.fr"]
    assert FauxDDGS.appels == [("brave", "fr-fr"), ("mojeek", "fr-fr")]   # duckduckgo pas sollicité


def test_arret_apres_echecs_d_affilee(moteurs):
    erreurs = se.erreurs_ddg
    for _ in range(se.ECHECS_AVANT_ARRET):
        assert se._resultats_ddg("x") == []
    assert se.recherche_arretee
    assert any("Recherche web arrêtée pour ce lancement" in ligne for ligne in moteurs)
    appels = len(FauxDDGS.appels)
    FauxDDGS.reponses = {"brave": ["https://acme.fr"]}
    assert se._resultats_ddg("y") == [] and len(FauxDDGS.appels) == appels   # plus aucune requête
    assert se.erreurs_ddg == erreurs + se.ECHECS_AVANT_ARRET
    se.reinitialiser_recherche()                                            # lancement suivant
    assert se._resultats_ddg("y")[0]["href"] == "https://acme.fr"


def test_un_succes_remet_le_compte_a_zero(moteurs):
    for _ in range(se.ECHECS_AVANT_ARRET - 1):
        se._resultats_ddg("x")
    FauxDDGS.reponses = {"duckduckgo": ["https://acme.fr"]}
    assert se._resultats_ddg("acme")
    FauxDDGS.reponses = {}
    for _ in range(se.ECHECS_AVANT_ARRET - 1):
        se._resultats_ddg("x")
    assert not se.recherche_arretee


def test_plus_d_attente_de_90_secondes(moteurs, monkeypatch):
    attentes = []
    monkeypatch.setattr(se.time, "sleep", attentes.append)
    se._resultats_ddg("x")
    assert attentes == []
