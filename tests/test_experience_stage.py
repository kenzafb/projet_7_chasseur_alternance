"""D212 : stage seulement, expérience exigée au-delà de « Expérience
professionnelle, en mois »."""

import pytest

from database.candidatures_db import ajouter_candidature, lire_candidature
from offres.analyse import analyser_offre, marquer_non_analysee
from offres.analyse_differee import analyser_en_attente
from offres.analyse_v2 import lignes_extraites
from shared import eligibilite as el
from tests.test_analyse_v2 import _extraction, _jugement

TROP_LONGUE = "Expérience exigée trop longue (1 an, 3 mois au plus)"


def profil(mois=3):
    return {"prenom": "Ada", "niveau_etudes": "Bac+2", "missions": "développement", "competences": ["Python"],
            "recherche": {} if mois is None else {"experience_mois": mois}}


def offre(ligne):
    return {"id": "S1", "titre": "Développeur web", "description": f"Missions.\nExpérience : {ligne}"}


@pytest.mark.parametrize("ligne, raison", [
    ("1 An(s) (exigée)", TROP_LONGUE),
    ("6 Mois (exigée)", "Expérience exigée trop longue (6 mois, 3 mois au plus)"),
    ("3 Mois (exigée)", ""), ("0 An(s) (exigée)", ""), ("0 An(s)", ""), ("Expérience exigée", ""),
    ("1 An(s) (souhaitée)", ""), ("Débutant accepté", ""), ("1 An(s) (débutant accepté)", ""),
])
def test_experience_exigee(ligne, raison):
    assert el.raisons_sans_ia(offre(ligne), profil(), "stage") == ([raison] if raison else [])


def test_champ_vide_aucune_regle_et_zero_mois():
    assert el.raisons_sans_ia(offre("1 An(s) (exigée)"), profil(None), "stage") == []
    assert el.raisons_sans_ia(offre("3 Mois (exigée)"), profil(0), "stage") == [
        "Expérience exigée trop longue (3 mois, aucune au plus)"]


def test_alternance_seulement_la_regle_des_deux_ans():
    """D169, comme avant, quels que soient les mois du profil (banc n° 8 : 1 an exigé, gardée)."""
    for mois in (None, 0, 3, 30):
        assert el.raisons_sans_ia(offre("1 An(s) (exigée)"), profil(mois), "alternance") == []
        assert el.raisons_sans_ia(offre("6 Mois (exigée)"), profil(mois), "alternance") == []
        assert el.raisons_sans_ia(offre("2 An(s) (exigée)"), profil(mois), "alternance") == [
            "2 ans d'expérience exigés : ce n'est pas une alternance"]


def test_job_inchange():
    assert el.raisons_sans_ia(offre("1 An(s) (exigée)"), profil(), "job") == []        # D174 : 9 mois d'écart


def test_avant_l_ia_raison_enregistree(utilisateur, ia):
    _, uid = utilisateur("a@test.fr", prenom="Ada")
    ajouter_candidature(uid, marquer_non_analysee(offre("1 An(s) (exigée)"), mode="stage"), mode="stage")
    analyser_en_attente(uid, "stage", profil(), 1, log=lambda m: None)
    o = lire_candidature(uid, "S1", mode="stage")
    assert ia.appels == [] and (o["verdict"], o["score"]) == ("ineligible", None)
    assert o["points_faibles"] == [f"Inéligible : {TROP_LONGUE}"]


@pytest.mark.parametrize("texte, eligible", [
    ("Vous avez 2 ans d'expérience minimum.", False),
    ("2 ans d'expérience souhaités.", True), ("Idéalement 2 ans d'expérience.", True),
    ("2 ans d'expérience.\nExpérience : Débutant accepté", True),
    ("2 ans d'expérience.\nExpérience : 0 An(s) (exigée)", True)])
def test_apres_l_ia(ia, monkeypatch, texte, eligible):
    monkeypatch.setenv("IA_VERSION_ANALYSE", "v2")
    ia.file = [_extraction(experience_exigee_annees=2), _jugement("Bien")]
    r = analyser_offre({"id": "S1", "titre": "Stage dev", "description": texte}, profil(), "stage")
    assert r["eligible"] is eligible


def test_souhait_et_exigence_dans_des_phrases_differentes():
    texte = "2 ans d'expérience exigés.\nIdéalement 5 ans."
    assert lignes_extraites({"experience_exigee_annees": 2}, {"description": texte}) == [
        "Expérience : 2 An(s) (exigée)"]
    assert lignes_extraites({"experience_exigee_annees": 5}, {"description": texte}) == []
    assert lignes_extraites({"experience_exigee_annees": 5}, {"description": texte}, "alternance") == [
        "Expérience : 5 An(s) (exigée)"]                                            # inchangée en alternance


def test_texte_d_aide(utilisateur):
    """Les deux textes sont dans la page, chacun dans la section de son mode."""
    client, _ = utilisateur("a@test.fr", prenom="Ada")
    page = client.get("/stage").text
    stage = "Une offre qui exige davantage d'expérience est écartée ; vide : jamais écartée pour ça."
    alternance = "Une offre qui exige 2 ans d'expérience ou plus est écartée : ce n'est pas une alternance."
    for texte, mode in ((stage, "stage"), (alternance, "alternance")):
        assert page.count(texte) == 1
        assert page[:page.index(texte)].rsplit('data-mode-section="', 1)[1].startswith(f'{mode}"')
