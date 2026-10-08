"""Archivage « public spécifique » : seulement les offres réellement
réservées (BOETH, RQTH), jamais la mention standard d'égalité des chances."""

import pytest

from france_travail.analyseur import appliquer_archivage_auto, reserve_public_specifique

# Les trois offres archivées à tort pendant la recette (data/chasseur_v2.db)
MENTIONS_DE_LA_RECETTE = [
    "s'engage en faveur de la diversité et de l'égalité des chances. À ce titre, ce poste est ouvert "
    "aux personnes en situation de handicap.",
    "engagé en faveur de l'égalité des chances, Le poste proposé est ouvert, à compétences égales, aux "
    "candidatures de personnes en situation de handicap.",
    "engagé en faveur de l'égalité des chances. Le poste proposé est ouvert, à compétences égales, aux "
    "personnes en situation de handicap.",
]

MENTIONS_OUVERTES = MENTIONS_DE_LA_RECETTE + [
    "Nous recrutons uniquement sur la base des compétences ; tous nos postes sont ouverts aux personnes "
    "en situation de handicap.",
    "Tous nos postes sont accessibles aux travailleurs handicapés.",
    "Engagés pour l'emploi des personnes en situation de handicap, nous étudions toutes les candidatures.",
    "Notre mission handicap accompagne les collaborateurs en situation de handicap.",
    "Entreprise handi-accueillante, signataire de la charte BOETH.",
    "",
]

RESERVEES = [
    "Offre réservée aux bénéficiaires de l'obligation d'emploi (BOETH).",
    "Ce poste est exclusivement ouvert aux personnes bénéficiant d'une RQTH.",
    "Poste BOETH",
    "RQTH obligatoire.",
    "Vous devez être titulaire d'une RQTH.",
    "Recrutement réservé aux travailleurs handicapés.",
    "Offre uniquement accessible aux personnes en situation de handicap",
    "Ce poste est réservé aux personnes reconnues travailleurs handicapés (RQTH).",
    "Offre destinée aux travailleurs handicapés.",
    "Reconnaissance de la qualité de travailleur handicapé exigée.",
]


@pytest.mark.parametrize("texte", MENTIONS_OUVERTES)
def test_mention_d_ouverture_ne_reserve_rien(texte):
    assert reserve_public_specifique(texte) is False


@pytest.mark.parametrize("texte", RESERVEES)
def test_offre_reservee_detectee(texte):
    assert reserve_public_specifique(texte) is True


def _offre(description, titre="Développeur en alternance"):
    return {"titre": titre, "description": description, "score": 8, "eligible": True, "domaine": "Dev"}


@pytest.mark.parametrize("texte", MENTIONS_DE_LA_RECETTE)
def test_offres_de_la_recette_restent_actives(texte):
    offre = _offre(texte)
    appliquer_archivage_auto(offre, {}, verbeux=False)
    assert offre.get("statut") != "archive" and offre["raison_archivage"] == ""


def test_offre_reservee_archivee_avec_sa_raison():
    offre = _offre("Description. Poste réservé aux bénéficiaires de l'obligation d'emploi.")
    appliquer_archivage_auto(offre, {}, verbeux=False)
    assert (offre["statut"], offre["raison_archivage"]) == ("archive", "public_specifique")


def test_reservation_dans_le_titre():
    offre = _offre("...", titre="Alternance développeur - poste réservé RQTH")
    appliquer_archivage_auto(offre, {}, verbeux=False)
    assert offre["raison_archivage"] == "public_specifique"


def test_mode_job_non_concerne():
    offre = _offre("Poste réservé aux bénéficiaires de l'obligation d'emploi.")
    appliquer_archivage_auto(offre, {}, mode="job", verbeux=False)
    assert offre["raison_archivage"] == ""
