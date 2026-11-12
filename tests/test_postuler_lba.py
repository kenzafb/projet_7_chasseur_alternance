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


# ─── Point 2 : boutons « Postuler sur La Bonne Alternance » (D129) ───────────
def test_offres_page_lba_dans_l_api(utilisateur):
    client, uid = utilisateur("ada@test.fr")
    base = {"titre": "Dev", "entreprise": "ACME", "lieu": "Paris", "description": "x"}
    ajouter_candidature(uid, {**base, "id": "L1", "source": "La Bonne Alternance",
                              "lien": f"{SITE}/emploi/offres_emploi_lba/6a0/dev"})
    ajouter_candidature(uid, {**base, "id": "L2", "source": "La Bonne Alternance", "lien": "https://partenaire.example/o"})
    ajouter_candidature(uid, {**base, "id": "F1", "source": "France Travail", "lien": "https://francetravail.fr/o/1"})
    pages_lba = {o["id"]: o["page_lba"] for o in client.get("/api/candidatures").json()}
    assert pages_lba == {"L1": f"{SITE}/emploi/offres_emploi_lba/6a0/dev", "L2": "", "F1": ""}


def _entreprise_lba(n, recipient=True, url=True, siret=None):
    from tests.faux_lba import entreprise, siret_lba
    e = entreprise(n, siret=siret or siret_lba(n))
    e["apply"]["url"] = f"{SITE}/emploi/recruteurs_lba/{e['workplace']['siret']}/societe-{n}" if url else None
    if not recipient:
        del e["apply"]["recipient_id"]
    return lba.normaliser_entreprise(e)


def test_entreprises_formulaire_seulement_avec_contact(utilisateur):
    from database.entreprises_db import ajouter_entreprises, ajouter_entreprises_lba, calculer_stats
    from tests.faux_lba import siret_lba
    client, uid = utilisateur("ada@test.fr")
    ajouter_entreprises_lba(uid, [_entreprise_lba(1), _entreprise_lba(2, recipient=False),
                                  _entreprise_lba(3, url=False)])
    ajouter_entreprises(uid, [{"siret": "12345678900011", "siren": "123456789", "nom": "Sirene seule"}])
    par_nom = {e["nom"]: e["lba"] for e in calculer_stats(uid)["prochaines"]}
    assert par_nom["Société 1"] == {"url": f"{SITE}/emploi/recruteurs_lba/{siret_lba(1)}/societe-1", "formulaire": True}
    assert par_nom["Société 2"] == {"url": f"{SITE}/emploi/recruteurs_lba/{siret_lba(2)}/societe-2", "formulaire": False}
    assert par_nom["Société 3"] == {"url": f"{SITE}/emploi/recruteurs_lba/{siret_lba(3)}/societe-3", "formulaire": True}
    assert par_nom["Sirene seule"] is None                                 # pas trouvée par LBA : rien
    stats = client.get("/api/spontanees/stats").json()
    assert any(e.get("lba") and e["lba"]["formulaire"] for e in stats["prochaines"])
