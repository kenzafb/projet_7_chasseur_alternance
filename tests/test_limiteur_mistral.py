"""Limitation commune des appels Mistral : plusieurs threads, appels espacés.

Temps simulé : l'horloge du limiteur est figée et ses attentes sont notées
sans dormir. Les créneaux attribués sont donc exacts, quelle que soit la
charge de la machine (l'ancienne version mesurait des instants réels et
échouait parfois sous charge)."""

import threading

import pytest

import shared.ia
from france_travail.analyseur import analyser_offre
from shared.ia import Limiteur, appeler_mistral
from tests.conftest import en_parallele

INTERVALLE = 0.15


class TempsSimule:
    """Horloge figée à `t` ; dormir(d) note la durée sans attendre."""

    def __init__(self):
        self.t = 100.0
        self.attentes = []
        self._verrou = threading.Lock()

    def horloge(self):
        return self.t

    def dormir(self, duree):
        with self._verrou:
            self.attentes.append(duree)


class Creneaux(list):
    temps = None


@pytest.fixture
def creneaux(mistral, monkeypatch):
    """Limiteur à 0,15 s en temps simulé ; liste des créneaux attribués."""
    temps = TempsSimule()
    limiteur = Limiteur(INTERVALLE, horloge=temps.horloge, dormir=temps.dormir)
    vus = Creneaux()
    verrou = threading.Lock()
    attendre = limiteur.attendre

    def noter():
        c = attendre()
        with verrou:
            vus.append(c)
        return c

    limiteur.attendre = noter
    monkeypatch.setattr(shared.ia, "limiteur", limiteur)
    vus.temps = temps
    return vus


def test_appels_de_plusieurs_threads_espaces(creneaux):
    def pipeline():
        for _ in range(3):
            appeler_mistral([{"role": "user", "content": "x"}])

    assert en_parallele(pipeline, 4) == []
    assert len(creneaux) == 12
    # Douze créneaux distincts, exactement un intervalle entre deux voisins,
    # le premier tout de suite : ni chevauchement ni sérialisation excessive
    assert sorted(creneaux) == pytest.approx([100.0 + i * INTERVALLE for i in range(12)])
    assert sorted(creneaux.temps.attentes) == pytest.approx([i * INTERVALLE for i in range(1, 12)])


def test_les_retries_passent_aussi_par_le_limiteur(creneaux, mistral, monkeypatch):
    echecs = iter([Exception("429 rate limit"), None])
    complete = mistral.chat.complete

    def parfois_429(**kwargs):
        err = next(echecs)
        if err:
            raise err
        return complete(**kwargs)

    monkeypatch.setattr(mistral.chat, "complete", parfois_429)
    appeler_mistral([{"role": "user", "content": "x"}], attente=lambda n: 0)
    assert creneaux == pytest.approx([100.0, 100.0 + INTERVALLE])


def test_limiteur_en_temps_reel_attend():
    """Contrôle du vrai sommeil, sans mesure fine : le second appel est repoussé."""
    limiteur = Limiteur(0.05)
    premier = limiteur.attendre()
    assert limiteur.attendre() == pytest.approx(premier + 0.05)


def test_analyse_lba_passe_par_le_limiteur(monkeypatch, mistral):
    """La boucle LBA de main.py appelle analyser_offre sans pause propre :
    c'est le limiteur qui l'espace."""
    mistral.reponse = '{"score": 6, "eligible": true}'
    appels = []
    monkeypatch.setattr(shared.ia, "limiteur", type("L", (), {"attendre": lambda self: appels.append(1)})())
    analyser_offre({"titre": "Dev", "description": "..."}, {"prenom": "A"})
    assert appels == [1]
