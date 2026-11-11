"""Balise {portfolio} dans les emails et les lettres des trois modes
(phase 10, D125) : le portfolio est dans la carte Identité (D120)."""

import pytest

from france_travail import generateur
from shared import balises_mail
from shared.erreurs import ErreurUtilisateur

PROFIL = {"prenom": "Ada", "nom": "Lovelace", "email": "ada@exemple.fr", "telephone": "0600000000",
          "portfolio": "https://ada.exemple.fr",
          "lettre_type": "{contact_entreprise}\nObjet : {poste}\n{paragraphe}\nMon portfolio : {portfolio}"}
OFFRE = {"titre": "Développeuse", "entreprise": "ACME", "lieu": "Lyon"}


@pytest.mark.parametrize("mode", ["alternance", "job", "stage"])
def test_email_portfolio_dans_tous_les_modes(mode):
    assert "portfolio" in balises_mail.balises_du_mode(mode)
    assert balises_mail.verifier_balises("Voir {portfolio}", mode) == ["portfolio"]
    assert balises_mail.remplir("{prenom}, voir { portfolio }", PROFIL, mode) == "Ada, voir https://ada.exemple.fr"
    with pytest.raises(ErreurUtilisateur, match=r"\{portfolio\}.*le lien de ton portfolio"):
        balises_mail.remplir("Voir {portfolio}", {**PROFIL, "portfolio": ""}, mode)


def test_les_balises_du_stage_restent_au_stage():
    with pytest.raises(ErreurUtilisateur, match=r"\{missions\}"):
        balises_mail.verifier_balises("{missions}", "job")


def test_lettre_avec_portfolio():
    lettre = generateur.assembler_lettre(OFFRE, PROFIL, "Paragraphe.")
    assert lettre.endswith("Mon portfolio : https://ada.exemple.fr")
    assert generateur.marqueurs_a_completer(lettre) == []
    assert generateur.preparer_lettre_type("Voir { portfolio } {paragraphe}") == "Voir {portfolio} {paragraphe}"


def test_lettre_portfolio_vide_balise_laissee_a_completer():
    lettre = generateur.assembler_lettre(OFFRE, {**PROFIL, "portfolio": "  "}, "Paragraphe.")
    assert lettre.endswith("Mon portfolio : {portfolio}")
    assert generateur.marqueurs_a_completer(lettre) == ["portfolio"]
    assert "Portfolio vide" in generateur.A_COMPLETER["portfolio"]


def test_message_d_erreur_cite_le_portfolio():
    with pytest.raises(generateur.LettreTypeInvalide, match=r"\{portfolio\}"):
        generateur.preparer_lettre_type("{inconnue} {paragraphe}")


def test_route_lettre_signale_le_portfolio_vide(utilisateur, ia):
    from database.candidatures_db import ajouter_candidature
    from database.profil_db import sauvegarder_profil
    client, uid = utilisateur("ada@test.fr", prenom="Ada", nom="Lovelace")
    sauvegarder_profil(uid, {"lettre_type": PROFIL["lettre_type"], "portfolio": "", "email": "ada@exemple.fr"})
    ajouter_candidature(uid, {"id": "R1", "titre": "Dev", "entreprise": "ACME", "lieu": "Lyon",
                              "description": "x", "lien": "", "source": "ft"})
    cid = client.get("/api/candidatures").json()[0]["id"]
    r = client.post("/api/lettre/assembler", json={"id": cid, "paragraphe": "P."})
    assert r.status_code == 200, r.text
    assert "{portfolio}" in r.json()["lettre"] and "Portfolio vide" in r.json()["message"]
