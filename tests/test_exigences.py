"""B (phase 15, étape 3, D169) : éligibilité décidée par Python à partir des
champs structurés des offres : permis, formation, expérience,
certifications exigés."""
import pytest

import offres.france_travail as ft
from offres.analyse import appliquer_eligibilite
from offres.la_bonne_alternance import lignes_experience
from shared import exigences as X
from tests.faux_france_travail import offre as brute


def _ft(**champs):
    o = brute(1, nature="E1", type_contrat="CDD")
    o.update(champs)
    return ft._normaliser_une(o)


def _profil(niveau="Bac", **rech):
    return {"niveau_etudes": niveau, "recherche": rech}


def _analyse(score=8):
    return {"score": score, "eligible": True, "verdict": "bon", "points_faibles": [], "niveau_requis": "non_precise",
            "niveau_exigence": "non_precise", "duree_mois": None, "date_debut_offre": None,
            "alternance_seulement": False}


def test_lignes_structurees_de_france_travail():
    o = _ft(permis=[{"libelle": "B - Véhicule léger", "exigence": "E"}, {"libelle": "C - Poids lourd", "exigence": "S"}],
            experienceExige="E", experienceLibelle="2 An(s)",
            formations=[{"domaineLibelle": "Cuisine", "niveauLibelle": "CAP, BEP et équivalents", "exigence": "E"}],
            competences=[{"libelle": "CACES R489 cat 1 3 5", "exigence": "E"}], description="x" * 20000)
    d = o["description"]
    assert len(d) <= ft.LONGUEUR_DESCRIPTION and d.endswith("Compétence : CACES R489 cat 1 3 5 (indispensable)")
    assert "Permis : B - Véhicule léger (exigé)" in d and "Permis : C - Poids lourd (souhaité)" in d
    assert "Expérience : 2 An(s) (exigée)" in d
    assert X.permis_exiges(d) == ["B"] and X.experience_exigee(d) == 24
    assert X.formations_exigees(d) == [(-1, "Cuisine - CAP, BEP et équivalents")]
    assert X.certifications_exigees(d) == ["CACES"]
    assert "(débutant accepté)" not in _ft(experienceExige="D", experienceLibelle="Débutant accepté")["description"]


@pytest.mark.parametrize("ligne, mois", [
    ("Expérience : 2 An(s) (exigée)", 24), ("Expérience : 6 Mois (exigée)", 6),
    ("Expérience : Expérience exigée", 0), ("Expérience : 1 An(s) (souhaitée)", None),
    ("Expérience : 1 An(s)", None),                    # offres d'avant D169 : exigence inconnue
    ("Expérience : Débutant accepté", None),
])
def test_experience_exigee(ligne, mois):
    assert X.experience_exigee(ligne) == mois


def test_permis_exige_et_profil():
    d = _ft(permis=[{"libelle": "B - Véhicule léger", "exigence": "E"}])
    assert X.raisons(d, _profil(permis=["aucun"]), "job", 0) == ["permis B exigé, tu n'as pas de permis"]
    assert X.raisons(d, _profil(permis=["A"]), "job", 0) == ["permis B exigé, ton permis : A"]
    assert X.raisons(d, _profil(permis=["B"]), "job", 0) == []
    assert X.raisons(d, _profil(), "job", 0) == []              # non renseigné : ne bloque pas


def test_formation_exigee_au_dessus_du_profil():
    d = _ft(formations=[{"niveauLibelle": "Bac+3, Bac+4 ou équivalents", "exigence": "E"}])
    assert X.raisons(d, _profil(), "job", 0) == ["formation exigée : Bac+3, Bac+4 ou équivalents, profil Bac"]
    assert X.raisons(d, _profil(), "job", 3) == []
    souhaitee = _ft(formations=[{"niveauLibelle": "Bac+5 et plus ou équivalents", "exigence": "S"}])
    assert X.raisons(souhaitee, _profil(), "job", 0) == []


def test_diplome_d_etat():
    d = {"description": "Travailleur social. Diplôme d'État d'éducateur spécialisé exigé."}
    assert X.raisons(d, _profil(), "job", 2) == ["diplôme d'État exigé"]
    assert X.raisons(d, {"formation": "DEES obtenu en 2024", "recherche": {}}, "job", 2) == []
    assert X.raisons(d, _profil(), "alternance", 2) == []        # souvent le diplôme préparé
    assert X.raisons({"description": "Le diplôme d'État est un plus."}, _profil(), "job", 2) == []


def test_experience_job_et_alternance():
    deux_ans = _ft(experienceExige="E", experienceLibelle="2 An(s)")
    assert X.raisons(deux_ans, _profil(experience_mois=6), "job", 0) == ["2 ans d'expérience exigés, profil 6 mois"]
    # 12 mois d'écart ou moins : éligible, plafond Moyen (D174)
    assert X.raisons(deux_ans, _profil(experience_mois=12), "job", 0) == []
    assert X.reserves(deux_ans, _profil(experience_mois=12), "job") == ["Expérience demandée : 2 ans"]
    assert X.raisons(deux_ans, _profil(experience_mois=30), "job", 0) == []
    assert X.raisons(deux_ans, _profil(), "job", 0) == []        # non renseignée : ne bloque pas
    assert X.raisons(deux_ans, _profil(), "alternance", 0) == ["2 ans d'expérience exigés : ce n'est pas une alternance"]
    un_an = _ft(experienceExige="E", experienceLibelle="1 An(s)")
    assert X.raisons(un_an, _profil(), "alternance", 0) == []


def test_certification_exigee():
    d = _ft(competences=[{"libelle": "CASES 1-3-5", "exigence": "E"}])       # coquille vue en base
    assert X.raisons(d, _profil(), "job", 0) == ["CACES exigé, absent du profil"]
    assert X.raisons(d, _profil(certifications=["CACES R489"]), "job", 0) == []
    ssiap = _ft(competences=[{"libelle": "SSIAP 1", "exigence": "S"}])
    assert X.raisons(ssiap, _profil(), "job", 0) == []           # souhaitée seulement


def test_lba_fourchette_d_experience():
    assert lignes_experience(["3-5 ans"]) == ["Expérience : 3 An(s) (exigée)"]
    assert lignes_experience(["débutant à 1 an", "Cet emploi est accessible avec un CAP"]) == []
    lba = {"description": "Offre\n" + lignes_experience(["3-5 ans"])[0]}
    assert X.raisons(lba, _profil(), "alternance", 2) == ["3 ans d'expérience exigés : ce n'est pas une alternance"]


def test_eligibilite_decidee_par_python():
    """Les raisons tirées des exigences rendent l'offre inéligible comme les autres règles."""
    o = _ft(competences=[{"libelle": "CACES R489", "exigence": "E"}])
    r = appliquer_eligibilite(_analyse(9), o, _profil(), "job")
    assert r["eligible"] is False and r["score"] == 3 and r["raison_ineligibilite"] == "CACES exigé, absent du profil"


def test_experience_un_peu_au_dessus_plafond_moyen():
    """D174 : 1 an exigé, profil 3 mois : éligible, Moyen au plus, raison dans Ce qui coince."""
    o = _ft(experienceExige="E", experienceLibelle="1 An(s)")
    r = appliquer_eligibilite(_analyse(9), o, _profil(experience_mois=3), "job")
    assert r["eligible"] is True and r["score"] == 5 and r["verdict"] == "moyen"
    assert r["points_faibles"][0] == "Expérience demandée : 1 an"
    r = appliquer_eligibilite(_analyse(9), _ft(experienceExige="E", experienceLibelle="3 An(s)"),
                              _profil(experience_mois=3), "job")
    assert r["eligible"] is False


def test_aucun_permis_et_permis_exige_toute_categorie():
    """D175 : permis exigé lu dans le texte sans catégorie sûre."""
    from offres.analyse_v2 import lignes_extraites
    offre = {"description": "Conducteur de bus. Permis D obligatoire, FIMO voyageurs."}
    lignes = lignes_extraites({"permis_exige": "C"}, offre)            # le modèle se trompe de catégorie
    assert lignes == ["Permis : * - catégorie non lue (exigé)"]
    vue = {"description": offre["description"] + "\n" + lignes[0]}
    assert X.raisons(vue, _profil(permis=["aucun"]), "job", 0) == ["permis exigé, tu n'as pas de permis"]
    assert X.raisons(vue, _profil(permis=["B"]), "job", 0) == []     # catégorie inconnue : ne bloque pas un titulaire
    assert X.raisons(vue, _profil(), "job", 0) == []                 # non renseigné
    assert lignes_extraites({"permis_exige": "C"}, {"description": "Poste sédentaire."}) == []


@pytest.mark.parametrize("texte, annees", [
    ("3 ans d'expérience exigés", {3}), ("trois ans d'expérience", {3}), ("de 3 à 5 ans en gestion de patrimoine", {3}),
    ("3-5 ans", {3}), ("2 ans minimum", {2}), ("minimum 2 ans", {2}), ("au moins deux années", {2}),
    ("une expérience de un an", {1}), ("Débutant accepté", set()), ("75012 Paris", set()),
])
def test_annees_dans_le_texte(texte, annees):
    """D176 : années en chiffres, en lettres, en fourchettes (borne basse)."""
    assert X.annees_dans_texte(texte) == annees


def test_experience_extraite_en_lettres_retenue():
    from offres.analyse_v2 import lignes_extraites
    assert lignes_extraites({"experience_exigee_annees": 3},
                            {"description": "Vous justifiez de trois ans d'expérience minimum."}) == [
        "Expérience : 3 An(s) (exigée)"]
    assert lignes_extraites({"experience_exigee_annees": 3}, {"description": "De 3 à 5 ans."}) == [
        "Expérience : 3 An(s) (exigée)"]


@pytest.mark.parametrize("texte, exigence", [
    ("Stage de fin d'études (6 mois), au sein de l'équipe R&D.", "exige"),
    ("Vous êtes en dernière année d'école d'ingénieurs.", "exige"),
    ("Étudiant en dernière année de master informatique.", "exige"),
    ("Vous préparez un M2 en data science.", "exige"),
    ("Idéalement en école d'ingénieurs (Bac+5).", "souhaite"),            # pas de tournure de D177
])
def test_bac5_exige_sans_mot_d_exigence(texte, exigence):
    """D177 : stage de fin d'études, dernière année d'école d'ingénieurs ou de master, M2."""
    from shared.eligibilite import niveau_detecte
    assert niveau_detecte(texte) == ("bac+5", exigence)


def test_stage_de_fin_d_etudes_ineligible_pour_un_bac2():
    from shared.eligibilite import controler_extraits, raisons_ineligibilite
    ext = {"niveau_requis": "bac+5", "niveau_exigence": "souhaite", "duree_mois": None, "date_debut_offre": None,
           "alternance_seulement": False}
    offre = {"description": "Stage de fin d'études : développement d'un code de calcul."}
    controler_extraits(ext, offre)
    assert ext["niveau_exigence"] == "exige"
    assert raisons_ineligibilite(ext, _profil("Bac+2"), "stage") == ["Bac+5 exigé, profil Bac+2"]


@pytest.mark.parametrize("vise, requis, raison", [
    ("Bac+2 (DEUST)", "bac+5", ["diplôme préparé Bac+5, niveau visé Bac+2"]),
    ("Bac+2", "bac+4", ["diplôme préparé Bac+4, niveau visé Bac+2"]),
    ("Bac+2", "bac+3", []),                                 # un niveau au-dessus : toléré
    ("Bac+3", "bac+3", []),
    ("", "bac+5", []),                                      # niveau visé non renseigné : ne bloque pas
])
def test_alternance_diplome_prepare_trop_haut(vise, requis, raison):
    """D178 : diplôme préparé à plus d'un niveau au-dessus du niveau visé."""
    from shared.eligibilite import raisons_ineligibilite
    ext = {"niveau_requis": requis, "niveau_exigence": "souhaite"}
    assert raisons_ineligibilite(ext, {"niveau_vise": vise}, "alternance") == raison
