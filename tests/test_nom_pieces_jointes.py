"""Nom des pièces jointes (D198) : fichier sans nom répété ni suffixes
empilés ; le nom reçu par l'entreprise est le nom affiché de la pièce."""

import pytest

from routes.profil import _base_nom_fichier, nom_sans_repetition
from scripts.renommer_pieces_jointes import nom_propre
from spontanees.envoi import charger_pieces_jointes


@pytest.mark.parametrize("base, propre", [
    ("Programme_BTS_SIO_Programme_BTS_SIO", "Programme_BTS_SIO"),
    ("Lettre_Recommandation_Camille_Martin_Lettre_Recommandation_Camille_M",
     "Lettre_Recommandation_Camille_Martin"),
    ("CV_Alice_1a2b3c4d", "CV_Alice"), ("CV_Alice_1a2b3c4d_9f8e7d6c", "CV_Alice"),
    ("CV_Alice", "CV_Alice"), ("Rapport_de_stage", "Rapport_de_stage"), ("Note_No", "Note_No"),
])
def test_nom_sans_repetition(base, propre):
    assert nom_sans_repetition(base) == propre


def test_televersement_d_un_fichier_au_nom_double():
    assert _base_nom_fichier("Programme_BTS_SIO_Programme_BTS_SIO.pdf") == "Programme_BTS_SIO"
    assert _base_nom_fichier("../CV Alice_1a2b3c4d.pdf") == "CV_Alice"


def test_nom_propre_des_fichiers_herites():
    assert nom_propre("user_1/Programme_BTS_SIO_Programme_BTS_SIO.pdf") == "user_1/Programme_BTS_SIO.pdf"
    assert nom_propre("user_1/Lettre_X_Y_Lettre_X_Y") == "user_1/Lettre_X_Y.pdf"     # extension ajoutée


def test_televerse_puis_envoye_sans_repetition(utilisateur, tmp_path):
    client, uid = utilisateur("a@test.fr")
    r = client.post("/api/profil/upload?mode=alternance", data={"nom": "Programme BTS"},
                    files={"fichier": ("Programme_BTS_SIO_Programme_BTS_SIO.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.json()["ok"] is True
    assert r.json()["fichier"].startswith("Programme_BTS_SIO_") and "SIO_Programme" not in r.json()["fichier"]
    pj = client.get("/api/profil?mode=alternance").json()["pieces_jointes"]
    assert [n for n, _ in charger_pieces_jointes(pj)] == ["Programme_BTS.pdf"]      # nom reçu par l'entreprise
