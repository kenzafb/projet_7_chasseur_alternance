"""Candidature sur La Bonne Alternance (phase 11, D126 à D131) : pages de
candidature fournies par l'API, jamais de lien construit au hasard."""

import pytest

import france_travail.scraper_lba as lba
from database.candidatures_db import ajouter_candidature, lire_candidatures
from shared import lba as pages
from tests.faux_lba import offre

SITE = "https://labonnealternance.apprentissage.beta.gouv.fr"
PAGE_ENTREPRISE = f"{SITE}/emploi/recruteurs_lba/84845778400025/lehibou-cybersecurity"


# ─── Point 5 : aucun lien construit au hasard (D128) ─────────────────────────
def test_offre_sans_apply_url_sans_lien():
    o = offre(1)
    del o["apply"]
    assert lba._normaliser_offre_lba(o)["lien"] == ""
    o = offre(2)
    o["apply"]["url"] = f"{SITE}/emploi/offres_emploi_lba/6a0/developpeur"
    assert lba._normaliser_offre_lba(o)["lien"] == f"{SITE}/emploi/offres_emploi_lba/6a0/developpeur"


def test_ancien_lien_invente_masque(utilisateur):
    _, uid = utilisateur("ada@test.fr")
    base = {"titre": "Dev", "entreprise": "ACME", "lieu": "Paris", "description": "x", "source": "La Bonne Alternance"}
    ajouter_candidature(uid, {**base, "id": "R1", "lien": f"{SITE}/emploi/6a003c399a6be614e48abba9"})
    ajouter_candidature(uid, {**base, "id": "R2", "lien": f"{SITE}/emploi/offres_emploi_lba/6a0/dev"})
    liens = {o["id"]: o["lien"] for o in lire_candidatures(uid)}
    assert liens == {"R1": "", "R2": f"{SITE}/emploi/offres_emploi_lba/6a0/dev"}


@pytest.mark.parametrize("lien,source,attendu", [
    (f"{SITE}/emploi/offres_emploi_lba/6a0/developpeur", "La Bonne Alternance", True),
    (f"{SITE}/emploi/partenaires/abc123", "La Bonne Alternance", True),
    (f"{SITE}/emploi/6a003c399a6be614e48abba9", "La Bonne Alternance", False),    # ancien repli inventé
    ("https://partenaire.example/offre/12", "La Bonne Alternance", False),        # hors du site LBA
    ("http://labonnealternance.apprentissage.beta.gouv.fr/emploi/x/y", "La Bonne Alternance", False),
    (f"{SITE}/emploi/offres_emploi_lba/6a0/dev", "France Travail", False),
    ("", "La Bonne Alternance", False),
    (f"{SITE}.attaquant.example/emploi/x/y", "La Bonne Alternance", False),
])
def test_page_offre(lien, source, attendu):
    assert bool(pages.page_offre({"lien": lien, "source": source})) is attendu


def test_page_entreprise():
    assert pages.page_entreprise("84845778400025", "LEHIBOU CYBERSECURITY", PAGE_ENTREPRISE) == PAGE_ENTREPRISE
    # Sans URL de l'API : format observé, à partir du SIRET (le slug ne compte pas pour le site)
    assert pages.page_entreprise("84845778400025", "Lehibou Cybersécurité") == (
        f"{SITE}/emploi/recruteurs_lba/84845778400025/lehibou-cybersecurite")
    # URL d'un autre SIRET ou d'un autre format : remplacée par le format observé
    assert pages.page_entreprise("97885742300013", "GRANITE", PAGE_ENTREPRISE) == (
        f"{SITE}/emploi/recruteurs_lba/97885742300013/granite")
    assert pages.page_entreprise("97885742300013", "GRANITE", "https://ailleurs.example/x") == (
        f"{SITE}/emploi/recruteurs_lba/97885742300013/granite")
    # Sans SIRET valide : rien
    for siret in ("", "123", "8484577840002X"):
        assert pages.page_entreprise(siret, "X") == ""
    assert pages.page_entreprise("", "X", PAGE_ENTREPRISE) == PAGE_ENTREPRISE
