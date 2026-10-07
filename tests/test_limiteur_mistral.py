"""Limitation commune des appels Mistral : plusieurs threads, appels espacés."""

import time

import pytest

import shared.ia
from france_travail.analyseur import analyser_offre
from shared.ia import Limiteur, appeler_mistral
from tests.conftest import en_parallele

INTERVALLE = 0.15


@pytest.fixture
def instants(mistral, monkeypatch):
    """Le faux Mistral note l'instant de chaque appel ; limiteur à 0,15 s."""
    vus = []
    complete = mistral.chat.complete

    def horodate(**kwargs):
        vus.append(time.monotonic())
        return complete(**kwargs)

    monkeypatch.setattr(mistral.chat, "complete", horodate)
    monkeypatch.setattr(shared.ia, "limiteur", Limiteur(INTERVALLE))
    return vus


def test_appels_de_plusieurs_threads_espaces(instants):
    def pipeline():
        for _ in range(3):
            appeler_mistral([{"role": "user", "content": "x"}])

    assert en_parallele(pipeline, 4) == []
    assert len(instants) == 12
    ecarts = [b - a for a, b in zip(sorted(instants), sorted(instants)[1:])]
    assert min(ecarts) >= INTERVALLE - 0.01
    # Pas de sérialisation excessive non plus : environ 11 intervalles au total
    assert sorted(instants)[-1] - sorted(instants)[0] < 11 * INTERVALLE + 1.0


def test_les_retries_passent_aussi_par_le_limiteur(instants, mistral, monkeypatch):
    echecs = iter([Exception("429 rate limit"), None])
    complete = mistral.chat.complete

    def parfois_429(**kwargs):
        err = next(echecs)
        if err:
            instants.append(time.monotonic())
            raise err
        return complete(**kwargs)

    monkeypatch.setattr(mistral.chat, "complete", parfois_429)
    appeler_mistral([{"role": "user", "content": "x"}], attente=lambda n: 0)
    assert len(instants) == 2
    assert instants[1] - instants[0] >= INTERVALLE - 0.01


def test_analyse_lba_passe_par_le_limiteur(monkeypatch):
    """La boucle LBA de main.py appelle analyser_offre sans pause propre :
    c'est le limiteur qui l'espace."""
    appels = []
    monkeypatch.setattr(shared.ia, "limiteur", type("L", (), {"attendre": lambda self: appels.append(1)})())
    analyser_offre({"titre": "Dev", "description": "..."}, {"prenom": "A"})
    assert appels == [1]
