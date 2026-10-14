"""Profil : compétences, projets et expérience dans les trois modes (stage et
job compris), utilisés par les prompts d'analyse et de lettre du stage, et
avertissement quand ils sont vides (D96)."""

import re

import pytest

from france_travail import analyseur, generateur
from shared import config

STAGE = {"prenom": "Alice", "nom": "Martin", "email": "a@test.fr", "formation": "BUT 2e année informatique",
         "missions": "MISSIONS-VISEES", "competences": ["COMPETENCE-A", "COMPETENCE-B"],
         "experience": "EXPERIENCE-DU-PROFIL", "projets": [{"nom": "PROJET-X", "description": "appli web"}],
         "date_debut": "2027-02-01", "date_fin": "2027-04-09", "duree_semaines": 10}
OFFRE = {"id": "R1", "titre": "Stagiaire développeur", "entreprise": "ACME", "lieu": "Paris", "description": "..."}
REPONSE = ('{"score": 7, "eligible": true, "points_forts": [], "points_faibles": [], "domaine": "Dev", '
           '"resume": "ok", "niveau_requis": "non_precise", "duree_mois": null, "date_debut_offre": null, '
           '"alternance_seulement": false, "niveau_exigence": "non_precise"}')


def _sections(page, titre):
    """Modes de la carte du profil qui porte ce titre."""
    i = page.index(f'<h3 class="profil-card__title">{titre}</h3>')
    return re.findall(r'data-mode-section="([^"]+)"', page[:i])[-1].split()


@pytest.mark.parametrize("mode", ["alternance", "stage", "job"])
def test_sections_dans_les_trois_modes(utilisateur, mode):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = client.get(f"/{mode}").text
    assert mode in _sections(page, "Compétences techniques") and mode in _sections(page, "Projets")
    # Une zone « Expérience » dans une section du mode
    sections = re.findall(r'data-mode-section="([^"]+)"(.*?)(?=data-mode-section=|\Z)', page, flags=re.S)
    assert any(mode in m.split() and 'data-profil="experience"' in bloc for m, bloc in sections)
    js = (config.STATIC_DIR / "js" / "profil.js").read_text(encoding="utf-8")
    assert 'dataset.modeSection.split(" ")' in js


def test_profil_stage_enregistre_et_relu(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    client.mode = "stage"
    client.post("/api/profil", json={k: v for k, v in STAGE.items() if k != "duree_semaines"})
    p = client.get("/api/profil").json()
    assert p["competences"] == STAGE["competences"] and p["projets"][0]["nom"] == "PROJET-X"
    assert p["experience"] == "EXPERIENCE-DU-PROFIL" and p["manques_ia"] == []


@pytest.mark.parametrize("mode", ["stage", "job", "alternance"])
def test_avertissement_si_vides(utilisateur, mode):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    client.mode = mode
    client.post("/api/profil", json={"prenom": "Alice", "competences": ["Excel"]})
    assert client.get("/api/profil").json()["manques_ia"] == ["projets", "expérience"]
    assert "data-ia-avert" in client.get(f"/{mode}").text
    js = (config.STATIC_DIR / "js" / "profil.js").read_text(encoding="utf-8")
    assert "l'IA juge " in js and "à l'aveugle" in js


def test_prompt_d_analyse_du_stage_utilise_ces_champs(ia):
    ia.reponse = REPONSE
    analyseur.analyser_offre(OFFRE, STAGE, mode="stage")
    texte = ia.textes(0)
    for attendu in ("MISSIONS-VISEES", "COMPETENCE-A, COMPETENCE-B", "EXPERIENCE-DU-PROFIL", "PROJET-X : appli web",
                    "- Niveau d'études : Bac+2"):
        assert attendu in texte, attendu


def test_prompt_de_lettre_du_stage_utilise_ces_champs(ia):
    generateur.rediger_paragraphe(OFFRE, STAGE, "stage", lettre_type="{paragraphe}")
    texte = ia.textes(0)
    for attendu in ("MISSIONS-VISEES", "COMPETENCE-A, COMPETENCE-B", "EXPERIENCE-DU-PROFIL", "PROJET-X : appli web"):
        assert attendu in texte, attendu


def test_prompt_d_analyse_du_job_cite_les_projets(ia):
    ia.reponse = REPONSE
    analyseur.analyser_offre(OFFRE, STAGE, mode="job")
    assert "PROJET-X" in ia.textes(0) and "COMPETENCE-A" in ia.textes(0) and "EXPERIENCE-DU-PROFIL" in ia.textes(0)
