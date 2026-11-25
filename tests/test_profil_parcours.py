"""Partie « Ton parcours » du profil (phase 16) : permis, expérience en mois
et certifications enregistrés puis relus tels quels, et le formulaire qui
ne perd pas une certification choisie dans la liste suggérée."""

import re
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "static" / "js" / "profil.js"


@pytest.mark.parametrize("mode", ["job", "alternance", "stage"])
def test_certification_enregistree_puis_relue(utilisateur, mode):
    client, _ = utilisateur("a@test.fr")
    # Ce que collecter() envoie : tout recherche, champs vides compris
    corps = {"prenom": "Ada", "recherche": {"domaines": [], "domaines_indifferent": False, "experience_mois": "3",
                                            "permis": ["aucun"], "certifications": ["CACES R489"]}}
    assert client.post(f"/api/profil?mode={mode}", json=corps).json() == {"ok": True}
    relu = client.get(f"/api/profil?mode={mode}").json()
    assert relu["recherche"]["certifications"] == ["CACES R489"]
    assert relu["certifications"] == ["CACES R489"]
    assert (relu["recherche"]["permis"], relu["recherche"]["experience_mois"]) == (["aucun"], 3)
    # Un nouvel enregistrement sans certification les retire
    corps["recherche"]["certifications"] = []
    client.post(f"/api/profil?mode={mode}", json=corps)
    assert client.get(f"/api/profil?mode={mode}").json()["recherche"]["certifications"] == []


def test_formulaire_garde_la_suggestion_choisie():
    """Choisir « CACES R489 » dans la liste suggérée ne déclenche pas la
    touche Entrée : l'étiquette se crée à l'événement input (valeur égale
    à une suggestion), au change, et collecter() compte la saisie en cours."""
    js = JS.read_text()
    branche = js[js.index("function brancherTags"):js.index("/* ── Projets")]
    assert 'addEventListener("input"' in branche and "input.list" in branche
    assert 'addEventListener("change"' in branche
    assert re.search(r'rech\.certifications = avecSaisieEnCours\("certifications"\)', js)
