"""Référentiels versionnés : lecture, nettoyage des libellés, tailles d'entreprise."""

import pytest

from shared import referentiels
from shared.tailles import CLES_TAILLES, garder_selon_taille, taille_depuis_tranche


@pytest.mark.parametrize("brut, propre", [
    ("'Fabrication industrielle de pain et de pâtisserie fraîche');",
     "Fabrication industrielle de pain et de pâtisserie fraîche"),
    ("'Fabrication d'articles en fils métalliques", "Fabrication d'articles en fils métalliques"),
    ("Travail du bois et fabrication d'articles en bois et en liège,à l'exception des meubles",
     "Travail du bois et fabrication d'articles en bois et en liège, à l'exception des meubles"),
    ("  Systèmes d'information   et de télécommunication ", "Systèmes d'information et de télécommunication"),
    ("Quincaillerie (moins de 400 m²)", "Quincaillerie (moins de 400 m²)"),
    ("Taux 1,5", "Taux 1,5"),
    (None, ""),
])
def test_nettoyage_des_libelles(brut, propre):
    assert referentiels.nettoyer_libelle(brut) == propre


def test_referentiels_france_travail_lus_et_nettoyes():
    domaines = referentiels.libelles(referentiels.france_travail("domaines"))
    assert len(domaines) == 110
    assert domaines["M18"] == "Systèmes d'information et de télécommunication"
    assert domaines["C15"] == "Immobilier"
    assert len(referentiels.france_travail("secteurs_activites")) == 88
    for nom in ("nafs", "secteurs_activites", "metiers", "domaines", "themes"):
        for e in referentiels.france_travail(nom):
            assert not e["libelle"].startswith("'") and not e["libelle"].endswith(");"), (nom, e)


def test_grands_domaines_couvrent_les_domaines():
    lettres = [g["code"] for g in referentiels.local("grands_domaines")]
    assert lettres == list("ABCDEFGHIJKLMN")
    assert {d["code"][0] for d in referentiels.france_travail("domaines")} == set(lettres)


@pytest.mark.parametrize("tranche, taille", [
    ("0 salarié", "moins_10"), ("1 ou 2 salariés", "moins_10"), ("6 à 9 salariés", "moins_10"),
    ("10 à 19 salariés", "10_49"), ("20 à 49 salariés", "10_49"),
    ("50 à 99 salariés", "50_249"), ("200 à 249 salariés", "50_249"),
    ("250 à 499 salariés", "250_4999"), ("2 000 à 4 999 salariés", "250_4999"),
    ("5 000 à 9 999 salariés", "5000_plus"), ("10 000 salariés et plus", "5000_plus"),
    ("Moins de 10 salariés", "moins_10"),
    ("03", "moins_10"), ("11", "10_49"), ("31", "50_249"), ("32", "250_4999"), ("53", "5000_plus"),
    ({"code": "21", "libelle": "?"}, "50_249"), ({"libelle": "100 à 199 salariés"}, "50_249"),
    (42, "10_49"),
    ("NN", None), ("Non renseigné", None), ("", None), (None, None), ({}, None),
])
def test_taille_depuis_tranche(tranche, taille):
    assert taille_depuis_tranche(tranche) == taille


def test_filtre_de_taille():
    assert garder_selon_taille("moins_10", [], False)          # aucune taille choisie : tout passe
    assert garder_selon_taille(None, [], False)
    assert garder_selon_taille("10_49", ["10_49", "50_249"], False)
    assert not garder_selon_taille("moins_10", ["10_49"], True)
    assert garder_selon_taille(None, ["10_49"], True)
    assert not garder_selon_taille(None, ["10_49"], False)
    assert len(CLES_TAILLES) == 5
