"""Règle des intitulés du mode stage (shared/referentiels/intitules_stage.txt),
sur les 20 intitulés d'exemple de l'essai motsCles=stage du 9 octobre 2026
(docs/referentiels/france_travail/verification_stage.json)."""

import json

import pytest

from shared.config import BASE_DIR
from shared.intitules_stage import designe_un_stage

ESSAI = BASE_DIR / "docs" / "referentiels" / "france_travail" / "verification_stage.json"

# Les 20 intitulés de l'essai : gardé (le stage est le poste) ou écarté (il en est l'objet)
EXEMPLES = {
    "STAGE - Assistant(e) Projet Retail H/F": True,
    "Stage - Coordinateur(rice) référencement de marque H/F": True,
    "Candidature spontanée ALTERNANCE/STAGE (H/F)": True,
    "Stage en Cuisine F/H - Terlia": True,
    "STAGE STANDARDISTE/ASSISTANT ANTENNE H/F/NB": True,
    "Stage - Assistant(e) Développement RH (H/F)": True,
    "Stage - Gestion et modernisation des Cartes SIM et eSIM F/H": True,
    "COORDINATEUR (H/F) EN CHARGE DES ATELIERS, STAGES & RESTITUTION": False,
    "Stage - Ingénieur(e) Données - R&D H/F": True,
    "STAGE - Chargé(e) de missions RSE - Structuration de la Démarche et Bilan Carbone H/F": True,
    "Stage - Ingénieur Développement Contrôle-Commande Simulateur F/H": True,
    "Stage Développement international des territoires H/F": True,
    "Coordinateur / Coordinatrice de stages de formation professionnel (H/F)": False,
    "STAGE - ASSISTANT(E) CHEF DE PRODUITS (MARKETING & ÉVÉNEMENTIEL) - CATÉGORIE JARDIN - H/F": True,
    "Stagiaire en assistanat relations entreprises - Stage de 6 mois (H/F)": True,
    "Gestionnaire du service des stages F/H - ESCP Business School": False,
    "Stage Développeur Logiciel (H/F)": True,
    "Stage assistant ingénieur performance thermique/énergétique H/F": True,
}


def test_les_20_intitules_de_l_essai_sont_tous_classes():
    exemples = json.loads(ESSAI.read_text(encoding="utf-8"))["echantillon"]["exemples"]
    assert len(exemples) == 20 and set(exemples) == set(EXEMPLES)   # deux doublons dans l'essai


@pytest.mark.parametrize("intitule,garde", EXEMPLES.items())
def test_intitule(intitule, garde):
    assert designe_un_stage(intitule) is garde


@pytest.mark.parametrize("intitule,garde", [
    ("Stagiaire juriste", True),
    ("Assistant marketing (stage)", True),
    ("Assistant RH en stage 6 mois", True),
    ("Assistant RH - Stage", True),
    ("Assistant RH : stage 6 mois", True),
    ("Responsable des stages", False),
    ("Chargée des stages et de l'alternance", False),
    ("Technicien support", False),
    ("Moniteur de stages sportifs", False),
    ("", False),
])
def test_autres_intitules(intitule, garde):
    assert designe_un_stage(intitule) is garde
