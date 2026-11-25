"""Prompt d'analyse v2 (D170) : extraction sans le profil sur la description
entière, jugement en un mot converti par Python, plafonds et exigences
extraites contrôlées contre le texte."""
import json
import sys
from pathlib import Path

from offres.analyse_v2 import NOTES, NUM_CTX_ANALYSE, analyser_offre_v2, lignes_extraites

PROFIL = {"prenom": "Alice", "niveau_etudes": "Bac+2", "missions": "développement web", "competences": ["Python"],
          "recherche": {"domaines": ["M18"]}}


def _extraction(**k):
    base = {"niveau_requis": "non_precise", "niveau_exigence": "non_precise", "duree_mois": None,
            "date_debut_offre": None, "alternance_seulement": False, "experience_exigee_annees": None,
            "permis_exige": None, "certifications_exigees": [], "diplome_etat_exige": False}
    return json.dumps({**base, **k})


def _jugement(categorie="Bien", car="aucune"):
    return json.dumps({"categorie": categorie, "hors_sujet_car": car, "points_forts": ["Python"], "points_faibles": [],
                       "domaine": "Web", "resume": "Stage web"})


def test_deux_appels_l_extraction_ne_voit_pas_le_profil(ia):
    ia.file = [_extraction(), _jugement("Très bien")]
    offre = {"titre": "Stage dev", "description": "a" * 6000 + " FIN-DU-TEXTE"}
    r = analyser_offre_v2(offre, PROFIL, "stage")
    assert len(ia.appels) == 2
    extraction, jugement = ia.textes(0), ia.textes(1)
    assert "FIN-DU-TEXTE" in extraction and "Alice" not in extraction and "développement web" not in extraction
    assert "développement web" in jugement and "FIN-DU-TEXTE" in jugement         # description entière (D193)
    assert (r["categorie"], r["score"], r["verdict"], r["eligible"]) == ("Très bien", 9, "excellent", True)
    assert r["description_coupee"] is None
    # Même num_ctx pour les deux appels : pas de rechargement du modèle entre eux
    assert ia.appels[0]["options"]["num_ctx"] == ia.appels[1]["options"]["num_ctx"] == NUM_CTX_ANALYSE == 4096


def test_mot_converti_en_note():
    assert NOTES == {"Très bien": 9, "Bien": 7, "Moyen": 5, "Faible": 3, "Hors sujet": 1}


def test_plafond_niveau_souhaite(ia):
    ia.file = [_extraction(niveau_requis="bac+5", niveau_exigence="souhaite"), _jugement("Très bien")]
    offre = {"titre": "Stage", "description": "Idéalement en école d'ingénieurs (Bac+5)."}
    r = analyser_offre_v2(offre, PROFIL, "job")        # en stage : inéligible (D202)
    assert (r["score"], r["eligible"]) == (5, True) and r["points_faibles"][0] == "Bac+5 souhaité, profil Bac+2"


def test_niveau_exige_ineligible(ia):
    ia.file = [_extraction(niveau_requis="bac+5", niveau_exigence="exige"), _jugement("Bien")]
    r = analyser_offre_v2({"titre": "Stage", "description": "Bac+5 exigé."}, PROFIL, "stage")
    assert r["eligible"] is False and r["score"] <= 3


def test_exigences_extraites_controlees_contre_le_texte():
    offre = {"description": "CACES R489 catégorie 3 obligatoire. 3 ans d'expérience exigés. Permis B indispensable."}
    lignes = lignes_extraites({"experience_exigee_annees": 3, "permis_exige": "B", "certifications_exigees": ["CACES 3"],
                               "diplome_etat_exige": True}, offre)
    assert lignes == ["Expérience : 3 An(s) (exigée)", "Permis : B (exigé)", "Compétence : CACES (indispensable)"]
    # Inventé par le modèle : absent du texte, rien n'est gardé
    assert lignes_extraites({"experience_exigee_annees": 5, "permis_exige": "C", "certifications_exigees": ["SSIAP"],
                             "diplome_etat_exige": False}, {"description": "Débutant accepté."}) == []


def test_certification_extraite_rend_ineligible(ia):
    ia.file = [_extraction(certifications_exigees=["CACES R489"]), _jugement("Bien")]
    r = analyser_offre_v2({"titre": "Cariste", "description": "CACES R489 obligatoire."}, PROFIL, "job")
    assert r["eligible"] is False and "CACES exigé" in r["raison_ineligibilite"]


def test_decoupage_fixe_et_reparti_par_mode():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "banc_ia"))
    from decouper import decouper
    ref = {"version": 1, "profils": {}, "offres": [{"ref": f"r{i}", "mode": m} for i, m in
                                                    enumerate(["job"] * 10 + ["stage"] * 5 + ["alternance"] * 3)]}
    a, b = decouper(ref)
    assert decouper(ref) == (a, b)                                    # même graine, mêmes moitiés
    assert {o["ref"] for o in a["offres"]} | {o["ref"] for o in b["offres"]} == {f"r{i}" for i in range(18)}
    assert not {o["ref"] for o in a["offres"]} & {o["ref"] for o in b["offres"]}
    assert [sum(o["mode"] == m for o in a["offres"]) for m in ("job", "stage", "alternance")] == [5, 3, 2]


def test_seules_les_variables_ia_du_env_sont_lues(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "banc_ia"))
    from commun import charger_ia_env
    env = tmp_path / ".env"
    env.write_text("SECRET_KEY=x\nFT_CLIENT_SECRET=y\nIA_NUM_CTX=4096\nIA_MODELE_ANALYSE=\"ministral-3:3b\" # commentaire\n")
    for v in ("IA_NUM_CTX", "IA_MODELE_ANALYSE"):     # suivies par monkeypatch, remises après le test
        monkeypatch.setenv(v, "provisoire")
        monkeypatch.delenv(v)
    assert charger_ia_env(env) == {"IA_NUM_CTX": "4096", "IA_MODELE_ANALYSE": "ministral-3:3b"}
    import os
    assert os.environ["IA_NUM_CTX"] == "4096" and "SECRET_KEY" not in charger_ia_env(env)


def test_hors_sujet_exige_une_phrase_du_profil(ia):
    profil = {**PROFIL, "types_jobs_eviter": "Postes très physiques ou pénibles (déménagement, BTP)"}
    ia.file = [_extraction(), _jugement("Hors sujet", "aucune")]
    assert analyser_offre_v2({"titre": "Caissier", "description": "x"}, profil, "job")["categorie"] == "Faible"
    ia.file = [_extraction(), _jugement("Hors sujet", "Postes très physiques ou pénibles")]
    assert analyser_offre_v2({"titre": "Déménageur", "description": "x"}, profil, "job")["categorie"] == "Hors sujet"
    ia.file = [_extraction(), _jugement("Hors sujet", "Idéalement des postes calmes")]   # pas un champ d'exclusion
    assert analyser_offre_v2({"titre": "Caissier", "description": "x"}, profil, "job")["categorie"] == "Faible"


def test_v2_par_defaut_dans_l_application(ia, monkeypatch):
    """analyser_offre (analyse différée, bouton « Noter ») passe par v2 par défaut."""
    from offres.analyse import analyser_offre
    from shared.config import ia_version_analyse
    monkeypatch.delenv("IA_VERSION_ANALYSE")
    assert ia_version_analyse() == "v2"
    ia.file = [_extraction(), _jugement("Bien")]
    r = analyser_offre({"titre": "Stage dev", "description": "Développement web en Python."}, PROFIL, "stage")
    assert (r["categorie"], r["score"], len(ia.appels)) == ("Bien", 7, 2)
    monkeypatch.setenv("IA_VERSION_ANALYSE", "v1")
    assert ia_version_analyse() == "v1"


def test_stage_ce_qu_il_prefere_eviter(ia):
    """D201 : le champ « à éviter » du stage est envoyé au jugement et peut
    rendre une offre hors sujet ; vide, le prompt est inchangé."""
    from offres.analyse_v2 import EVITER_STAGE, hors_sujet_justifie, messages_jugement
    offre = {"titre": "Stage RH", "description": "Recrutement."}
    vide = messages_jugement(offre, {**PROFIL, "criteres_eviter": ""}, "stage", 2000)[1]["content"]
    assert vide == messages_jugement(offre, PROFIL, "stage", 2000)[1]["content"]
    assert "Préfère éviter" not in vide and EVITER_STAGE not in vide
    profil = {**PROFIL, "criteres_eviter": "ressources humaines, marketing, commerce"}
    rempli = messages_jugement(offre, profil, "stage", 2000)[1]["content"]
    assert "- Préfère éviter : ressources humaines, marketing, commerce" in rempli and EVITER_STAGE in rempli
    assert hors_sujet_justifie("Préfère éviter : ressources humaines", profil, "stage")
    # Les autres modes gardent leur règle
    job = messages_jugement(offre, profil, "job", 2000)[1]["content"]
    assert EVITER_STAGE not in job and "Préfère éviter" not in job


def test_stage_champ_eviter_enregistre(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Ada")
    client.post("/api/profil?mode=stage", json={"criteres_eviter": "marketing"})
    assert client.get("/api/profil?mode=stage").json()["criteres_eviter"] == "marketing"
    assert client.get("/api/profil?mode=alternance").json()["criteres_eviter"] == ""
