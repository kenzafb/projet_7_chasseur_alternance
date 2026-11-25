"""D211 : plafonds du mode job, niveau maximal demandé par l'offre et
expérience par domaine, en Python, avant l'IA."""

import pytest

from database.candidatures_db import ajouter_candidature, lire_candidature
from database.profil_db import lire_profil, sauvegarder_profil
from offres.analyse import analyser_offre, marquer_non_analysee
from offres.analyse_differee import analyser_en_attente
from offres.analyse_v2 import lignes_extraites
from shared import domaines_experience as D
from shared import eligibilite as el
from shared import exigences as X
from shared.criteres import normaliser_recherche
from tests.test_analyse_v2 import _extraction, _jugement

RELATION_CLIENT = [{"domaine": "relation_client", "mois": 3}]


def profil(**recherche):
    return {"prenom": "Ada", "niveau_etudes": "Bac", "types_jobs_ok": "vente", "competences": ["Accueil"],
            "recherche": recherche}


def offre(description, titre="Employé polyvalent", **k):
    return {"id": "J1", "titre": titre, "description": description, **k}


def experience(ligne, titre="Employé polyvalent", domaines=RELATION_CLIENT):
    return el.raisons_sans_ia(offre(f"Missions.\nExpérience : {ligne}", titre),
                              profil(experience_domaines=domaines), "job")


# ─── Niveau maximal demandé par l'offre ───────────────────────────────────────
@pytest.mark.parametrize("texte, maximum, raison", [
    ("Bac+2 souhaité.", "bac", "Niveau demandé trop élevé (Bac+2 demandé, Bac au plus)"),
    ("Bac+3 exigé.", "bac+2", "Niveau demandé trop élevé (Bac+3 demandé, Bac+2 au plus)"),
    ("Bac +4-5.", "bac+3", "Niveau demandé trop élevé (Bac+4 demandé, Bac+3 au plus)"),
    ("Formation : Vente - Bac+2 ou équivalents (souhaitée)", "bac",
     "Niveau demandé trop élevé (Bac+2 demandé, Bac au plus)"),
    ("CAP cuisine souhaité.", "aucun", "Niveau demandé trop élevé (CAP/BEP demandé, aucun diplôme au plus)"),
    ("Bac souhaité.", "cap", "Niveau demandé trop élevé (Bac demandé, CAP/BEP au plus)"),
    ("Accueil des clients, vente.", "bac", ""),               # sans niveau : gardée
    ("Accueil des clients, vente.", "aucun", ""),
    ("Niveau bac.", "bac", ""),
    ("Bac à Bac+2.", "bac", ""),                              # borne basse d'une fourchette
    ("CAP ou BTS.", "bac", ""),
    ("Sans diplôme ou Bac+2.", "bac", ""),
    ("Master 2 exigé.", "bac+5", ""),
    ("Bac+5 souhaité.", "", ""),                              # sans limite (défaut)
    ("Magasin de 500 m2.", "bac", ""),                        # une surface, pas un M2
    ("Licence IV appréciée.", "bac", ""),
    ("Cap emploi : garder le cap.", "aucun", ""),
])
def test_niveau_maximal(texte, maximum, raison):
    recherche = {"niveau_max_offre": maximum} if maximum else {}
    raisons = el.raisons_sans_ia(offre(texte), profil(**recherche), "job")
    assert [r for r in raisons if r.startswith("Niveau demandé")] == ([raison] if raison else [])


def test_niveau_maximal_une_seule_raison_de_niveau_et_job_seulement():
    p = profil(niveau_max_offre="bac")
    assert el.raisons_sans_ia(offre("Bac+5 exigé."), p, "job") == [
        "Niveau demandé trop élevé (Bac+5 demandé, Bac au plus)"]
    assert el.raisons_sans_ia(offre("Bac+2 souhaité."), p, "stage") == []
    assert el.raisons_sans_ia(offre("Bac+2 souhaité."), p, "alternance") == []


# ─── Expérience par domaine ───────────────────────────────────────────────────
@pytest.mark.parametrize("ligne, raison", [
    # Les trois exemples de la demande
    ("6 Mois - en manutention (exigée)", "Expérience exigée dans un autre domaine (6 mois, en manutention)"),
    ("1 Mois - en manutention (exigée)", "Expérience exigée dans un autre domaine (1 mois, en manutention)"),
    ("3 Mois - en relation client (exigée)", ""),
    # Même domaine, trop longue
    ("6 Mois - Hôte / Hôtesse d'accueil (exigée)", "Expérience exigée trop longue (6 mois, 3 mois au plus)"),
    # Domaine absent du référentiel : un autre domaine
    ("1 An(s) - radiologie (exigée)", "Expérience exigée dans un autre domaine (1 an, radiologie)"),
    # Domaine non précisé : durée seule, sans les 12 mois de D174
    ("6 Mois (exigée)", "Expérience exigée trop longue (6 mois, 3 mois au plus)"),
    ("3 Mois (exigée)", ""),
    ("Expérience exigée", ""),
    ("Expérience exigée de 1 An(s)", "Expérience exigée trop longue (1 an, 3 mois au plus)"),
    # Sans exigence
    ("Débutant accepté", ""), ("2 An(s) - manutention (débutant accepté)", ""),
    ("2 An(s) - manutention (souhaitée)", ""), ("2 An(s)", ""),
])
def test_experience_par_domaine(ligne, raison):
    assert experience(ligne) == ([raison] if raison else [])


@pytest.mark.parametrize("ligne", ["3 Mois (exigée)", "3 Mois - sur un poste similaire (exigée)"])
def test_sans_domaine_ecrit_celui_de_l_intitule(ligne):
    assert experience(ligne, "Vendeur en boutique") == []
    assert experience(ligne, "Manutentionnaire (h/f)") == [
        "Expérience exigée dans un autre domaine (3 mois, intitulé Manutentionnaire (h/f))"]      # banc n° 62
    assert experience(ligne, "Employé polyvalent") == []                      # intitulé inconnu : durée seule
    # Le domaine écrit passe avant l'intitulé
    assert experience("3 Mois - relation client (exigée)", "Manutentionnaire") == []


# Banc n° 99 : des diplômes cités comme objets de missions
SCOLARITE = """Mission principale : Gestion de la scolarité de 4 masters
- Gérer administrativement et pédagogiquement les étudiants (du dépôt de dossier au retrait de diplôme),
- Mettre en place les auditions ou examens d'entrée en Master 1 et Master 2,
- Communication des résultats au service des diplômes,
- Réalisation et mise à jour de brochures sur les Masters.
PROFIL RECHERCHÉ :
Niveau et nature des responsabilités essentielles : être opérationnel, polyvalent.
Expérience : Débutant accepté"""


def test_diplome_objet_d_une_mission_ignore():
    assert el.niveau_detecte(SCOLARITE) is None and el.niveaux_dans_texte(SCOLARITE) == (set(), [])
    assert el.raisons_sans_ia(offre(SCOLARITE, "Adjoint en scolarité"), profil(niveau_max_offre="bac"), "job") == []
    # Un vrai niveau dans la même offre reste lu
    assert el.niveau_detecte(SCOLARITE + "\nVous êtes titulaire d'un Bac+2.") == ("bac+2", "souhaite")


@pytest.mark.parametrize("texte, niveau", [
    ("Vous préparez un Master 2 en ressources humaines.", "bac+5"), ("- BTS SIO option SLAM (2e année)", "bac+2"),
    ("BAC + 5, Master informatique ou école d'ingénieur.", "bac+5"), ("Titulaire d'une licence.", "bac+3"),
    ("Vous gérez les dossiers ; Bac+2 exigé.", "bac+2"),
    ("Organiser les jurys de licence et de master.", None), ("Réaliser des plaquettes sur le BTS.", None),
    ("Vente de jeux, rayon master collection.", None)])
def test_niveau_seulement_dans_un_contexte_de_recrutement(texte, niveau):
    assert (el.niveau_detecte(texte) or (None,))[0] == niveau


def test_plusieurs_domaines_et_maximum():
    deux = RELATION_CLIENT + [{"domaine": "manutention", "mois": 12}]
    assert experience("6 Mois - manutention (exigée)", domaines=deux) == []
    assert experience("6 Mois - accueil (exigée)", domaines=deux) == [
        "Expérience exigée trop longue (6 mois, 3 mois au plus)"]
    assert experience("12 Mois (exigée)", domaines=deux) == []       # non précisé : le plus long des miens


def test_liste_vide_regle_d174_et_autres_modes():
    o = offre("Expérience : 2 An(s) - manutention (exigée)")
    assert X.raisons(o, profil(experience_mois=3), "job", 0) == ["2 ans d'expérience exigés, profil 3 mois"]
    assert X.reserves(o, profil(experience_mois=18), "job") == ["Expérience demandée : 2 ans"]
    assert X.reserves(o, profil(experience_mois=18, experience_domaines=RELATION_CLIENT), "job") == []
    assert el.raisons_sans_ia(o, profil(experience_domaines=RELATION_CLIENT), "stage") == []


@pytest.mark.parametrize("texte", ["Accueil", "vente en boulangerie", "Hôtesse de caisse", "service clients",
                                   "conseillère", "télé-enquête", "téléenquêteurs", "relation clientèle"])
def test_synonymes_de_la_relation_client(texte):
    assert "relation_client" in D.classer(texte)[0]


def test_synonymes_mots_entiers():
    assert D.classer("manutentionnaires")[0] == {"manutention"}
    assert D.classer("inventeur") == (set(), True)                   # pas « vente »
    assert D.classer("expérience professionnelle de 2 ans minimum") == (set(), False)
    cles = list(D.referentiel())
    assert len(cles) == len(set(cles)) and all(o["libelle"] for o in D.options())


# ─── Extraction v2 : domaine recopié, contrôlé contre le texte ────────────────
@pytest.mark.parametrize("extrait, texte, lignes", [
    ({"experience_exigee_annees": 2, "experience_exigee_domaine": "manutention"},
     "Expérience de 2 ans en manutention exigée.", ["Expérience : 2 An(s) - manutention (exigée)"]),
    ({"experience_exigee_domaine": "manutention"}, "6 mois d'expérience en manutention exigés.",
     ["Expérience : 6 Mois - manutention (exigée)"]),
    ({"experience_exigee_domaine": "manutention"}, "Expérience en manutention appréciée.", []),
    ({"experience_exigee_domaine": "cuisine"}, "Expérience exigée en manutention.", []),            # absent du texte
    ({"experience_exigee_domaine": "manutention"}, "Missions : manutention.", []),                  # sans « expérience »
    ({"experience_exigee_domaine": "null"}, "Expérience null exigée.", []),                         # « null » écrit
    ({"experience_exigee_domaine": "port"}, "Expérience exigée en transport.", []),                 # pas un mot entier
    ({"experience_exigee_domaine": "manutention"},
     "Une expérience en manutention.\nExpérience : 3 Mois (exigée)",
     ["Expérience : Expérience exigée - manutention (exigée)"]),
])
def test_domaine_extrait_controle(extrait, texte, lignes):
    assert lignes_extraites(extrait, {"description": texte}) == lignes


def test_domaine_extrait_complete_la_ligne_france_travail():
    description = ("Une expérience en manutention est demandée.\nExpérience : 3 Mois (exigée)\n"
                   "Expérience : Expérience exigée - manutention (exigée)")
    assert X.experience_demandee(description) == (3, "manutention")
    # « Débutant accepté » l'emporte sur l'extraction
    assert X.experience_demandee("Expérience : Débutant accepté\nExpérience : 2 An(s) - manutention (exigée)") is None


# ─── Avant l'IA, raison en base ; après l'IA, par l'extraction ────────────────
def test_avant_l_ia_raison_enregistree(utilisateur, ia):
    _, uid = utilisateur("a@test.fr", prenom="Ada")
    ajouter_candidature(uid, marquer_non_analysee(offre("Bac+2 souhaité.\nExpérience : 6 Mois - manutention (exigée)"),
                                                  mode="job"), mode="job")
    analyser_en_attente(uid, "job", profil(niveau_max_offre="bac", experience_domaines=RELATION_CLIENT), 1,
                        log=lambda m: None)
    o = lire_candidature(uid, "J1", mode="job")
    assert ia.appels == [] and o["verdict"] == "ineligible" and o["score"] is None
    assert o["points_faibles"] == [
        "Inéligible : Expérience exigée dans un autre domaine (6 mois, manutention)",
        "Inéligible : Niveau demandé trop élevé (Bac+2 demandé, Bac au plus)"]


def test_apres_l_ia_domaine_extrait(ia, monkeypatch):
    monkeypatch.setenv("IA_VERSION_ANALYSE", "v2")
    ia.file = [_extraction(experience_exigee_domaine="manutention"), _jugement("Bien")]
    r = analyser_offre(offre("6 mois d'expérience en manutention exigés."),
                       profil(experience_domaines=RELATION_CLIENT), "job")
    assert not r["eligible"] and r["raison_ineligibilite"] == (
        "Expérience exigée dans un autre domaine (6 mois, manutention)")


# ─── Profil ───────────────────────────────────────────────────────────────────
def test_reglages_normalises():
    r = normaliser_recherche({"niveau_max_offre": "bac", "experience_domaines": [
        {"domaine": "relation_client", "mois": "3"}, {"domaine": "relation_client", "mois": 2},
        {"domaine": "inconnu", "mois": 5}, {"domaine": "manutention", "mois": ""}, "x"]})
    assert r == {"niveau_max_offre": "bac", "experience_domaines": RELATION_CLIENT}
    assert normaliser_recherche({"niveau_max_offre": "", "experience_domaines": None}) == {"experience_domaines": []}


def test_profil_job_enregistre_et_formulaire(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    sauvegarder_profil(uid, {"recherche": {"niveau_max_offre": "bac", "experience_domaines": RELATION_CLIENT,
                                           "experience_mois": "4"}}, mode="job")
    r = lire_profil(uid, mode="job")["recherche"]
    assert (r["niveau_max_offre"], r["experience_domaines"], r["experience_mois"]) == ("bac", RELATION_CLIENT, 4)
    page = client.get("/job").text
    assert 'data-rech="niveau_max_offre"' in page and "data-experiences" in page
    # Total en mois : visible en alternance et en stage, gardé sans être affiché en job
    assert page.count('type="number" min="0" max="600" step="1" inputmode="numeric"\n'
                      '                   data-rech="experience_mois"') == 2
    assert '<input type="hidden" data-rech="experience_mois">' in page
    cles = [o["cle"] for o in client.get("/api/criteres_options").json()["experience_domaines"]]
    assert "relation_client" in cles and "manutention" in cles
