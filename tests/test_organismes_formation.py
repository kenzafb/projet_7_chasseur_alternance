"""Organismes de formation (D156) : noms vérifiés qui écartent une offre
d'alternance, mots génériques seulement affichés comme indices."""
import pytest

from offres.analyse import archivage_mots_cles, est_ecole_cfa
from shared.marques import etiquettes, indices_ecole, liste, organismes_verifies


def _o(titre="Alternance développeur", entreprise="ACME", description=""):
    return {"titre": titre, "entreprise": entreprise, "description": description}


@pytest.mark.parametrize("offre", [
    _o(entreprise="ISCOD"),
    _o(entreprise="SCHOLIA"),
    _o(description="Formation assurée par My Digital School, rythme 3 jours / 2 jours."),
    _o(titre="Alternance - Sup de Vinci - Développeur"),
    _o(entreprise="AUREIS FORMATION"),
    _o(entreprise="Groupe IGF"),          # jamais trouvé avant (majuscules dans la liste)
    _o(description="Inscription chez Studi pour le diplôme."),
])
def test_organisme_verifie_ecarte(offre):
    assert est_ecole_cfa(offre) and archivage_mots_cles(offre, "alternance") == "ecole_cfa"


@pytest.mark.parametrize("offre", [
    _o(description="Formation au CFA de votre choix, rythme école-entreprise."),
    _o(description="Vous travaillerez sur la plateforme de données du groupe."),
    _o(description="Notre studio de création recherche un alternant."),          # « studi »
    _o(description="Horaires : 9h30 - 17h30. Titre H3 du site."),                  # « h3 »
    _o(description="Centre de formation interne, organisme de formation agréé."),
    _o(entreprise="NEXANS FRANCE"),                                               # « nexa »
    _o(description="Designs graphiques et maquettes."),                           # « igs »
    _o(entreprise="Ecole Polytechnique"),                                         # indice seulement
])
def test_mot_generique_n_ecarte_plus(offre):
    assert not est_ecole_cfa(offre) and archivage_mots_cles(offre, "alternance") is None


def test_indices_affiches_titre_et_entreprise_seulement():
    o = _o(titre="Alternance CFA - assistant", entreprise="THE BRIDGE ECOLE ENTREPRISES",
           description="Organisme de formation")
    assert indices_ecole(o) == ["cfa", "ecole"]
    assert etiquettes(o) == ["Indice d'école ou de CFA : « cfa », « ecole »"]
    assert etiquettes(_o(description="CFA de votre choix")) == []


def test_marques_affichees():
    o = {**_o(entreprise="CFA X"), "marques": ["organisme_formation", "niveau_different"]}
    # L'organisme est déjà dit : pas d'indice en plus
    assert etiquettes(o) == ["Offre déposée par un organisme de formation", "Niveau différent du tien"]


def test_fichier_lisible():
    verifies, indices, a_marquer = liste()
    assert [n for n, _ in a_marquer] == ["capivision"]
    assert len(verifies) >= 20 and {"cfa", "ecole"} <= {n for n, _ in indices}
    assert organismes_verifies(_o(entreprise="Simplon.co")) == ["simplon"]


def test_capivision_marquee_jamais_archivee():
    """D156 : les offres CAPIVISION « IGF ... - ALT » recrutent pour l'école IGF :
    marquées comme les offres déléguées, ni archivées ni mêlées aux autres."""
    from offres.analyse import marquer_non_analysee
    o = marquer_non_analysee(_o(titre="IGF Assistant(e) comptable - BTS CG - 75 - GROUPE LAVIALE - ALT F/H",
                                entreprise="CAPIVISION", description="Formation au CFA IGF."), verbeux=False)
    assert o["marques"] == ["organisme_formation"] and o.get("statut") != "archive" and o["raison_archivage"] == ""
    assert etiquettes(o) == ["Offre déposée par un organisme de formation"]
    assert marquer_non_analysee(_o(), verbeux=False).get("marques", []) == []
