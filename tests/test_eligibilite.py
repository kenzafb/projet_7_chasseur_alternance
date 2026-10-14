"""Éligibilité décidée en Python (D94) : niveau, durée, début, alternance,
à partir des champs extraits par le modèle ; non précisé = jamais bloquant.
Cas de départ : comparaison humaine sur trois offres de stage (octobre 2026)."""

import json

import pytest

from france_travail.analyseur import analyser_offre, appliquer_archivage_auto, appliquer_analyse
from shared import eligibilite as el

# BUT2, 10 semaines de février à avril (le profil de la comparaison humaine)
BUT2 = {"prenom": "Alice", "formation": "BUT 2e année informatique", "date_debut": "2027-02-01",
        "date_fin": "2027-04-09", "duree_semaines": 10, "recherche": {"domaines": ["M18"]}}


O1_TEXTE = ("Stage de 6 mois à partir de janvier 2027. Profil : étudiant en dernière année d'école "
            "d'ingénieurs (Bac+5), réseaux et télécoms.")


def extraits(niveau="non_precise", duree=None, debut=None, alternance=False, exigence="exige"):
    return {"niveau_requis": niveau, "duree_mois": duree, "date_debut_offre": debut, "alternance_seulement": alternance,
            "niveau_exigence": exigence}


def test_o1_orange_inéligible_pour_trois_raisons():
    raisons = el.raisons_ineligibilite(extraits("bac+5", 6, "janvier 2027"), BUT2, "stage")
    assert raisons == ["Bac+5 exigé, profil Bac+2", "6 mois demandés, 10 semaines disponibles",
                       "début en janvier 2027, stage possible du 1er février 2027 au 9 avril 2027"]


@pytest.mark.parametrize("valeurs, bloque", [
    (extraits("bac+5"), True),                    # O2 : Bac+5 exigé
    (extraits("bac+4"), True),                    # deux crans
    (extraits("bac+3"), False),                   # un cran : pas bloquant
    (extraits("non_precise"), False),
    (extraits(duree=3), False),                   # 13 semaines : moins de 10 + 4
    (extraits(duree=3.5), True),                  # 15,2 semaines
    (extraits(duree=None), False),
    (extraits(debut="mars 2027"), False),
    (extraits(debut="mai 2027"), True),
    (extraits(debut="01/2027"), True),
    (extraits(debut="28/01/2027"), False),        # quelques jours avant : toléré
    (extraits(debut="2027-01-15"), True),
    (extraits(debut="dès que possible"), False),
    (extraits(debut="janvier"), False),           # sans année : non précisé
    (extraits(alternance=True), True),
])
def test_regles_du_stage(valeurs, bloque):
    assert bool(el.raisons_ineligibilite(valeurs, BUT2, "stage")) is bloque


def test_durees_et_dates_seulement_en_stage():
    assert el.raisons_ineligibilite(extraits(duree=12, debut="janvier 2027"), BUT2, "job") == []
    assert el.raisons_ineligibilite(extraits(alternance=True), BUT2, "alternance") == []
    assert el.raisons_ineligibilite(extraits(alternance=True), BUT2, "job") == ["offre en alternance seulement"]


def test_profil_sans_dates_ni_niveau_rien_ne_bloque():
    assert el.raisons_ineligibilite(extraits("bac+5", 12, "janvier 2027"), {"prenom": "A"}, "stage") == []


@pytest.mark.parametrize("profil, crans, source", [
    ({"niveau_etudes": "Bac+2"}, 2, "niveau d'études"),
    ({"niveau_etudes": "Bac+3 en cours, Bac+2 obtenu"}, 3, "niveau d'études"),
    ({"niveau_etudes": "bac"}, 0, "niveau d'études"),
    ({"formation": "BUT1 GEA"}, 0, "formation"),
    ({"formation": "BUT 2e année"}, 2, "formation"),
    ({"formation": "2e année de BUT informatique"}, 2, "formation"),
    ({"formation": "BUT3"}, 3, "formation"),
    ({"formation": "Licence 3 économie"}, 3, "formation"),
    ({"formation": "Master 1"}, 4, "formation"),
    ({"formation": "M2 MIAGE"}, 5, "formation"),
    ({"niveau_vise": "Bac+3", "formation": "BUT2"}, 3, "niveau visé"),
    ({"niveau_etudes": "Bac+2", "formation": "Master 2"}, 2, "niveau d'études"),   # le champ prime
])
def test_niveau_du_profil(profil, crans, source):
    n = el.niveau_du_profil(profil)
    assert (n["crans"], n["source"], n["avertissement"]) == (crans, source, "")


@pytest.mark.parametrize("profil", [{}, {"formation": "École d'ingénieurs"}, {"formation": "BUT2 puis Master 1"},
                                    {"formation": "BTS"}])
def test_niveau_inconnu_ou_ambigu_avertissement(profil):
    n = el.niveau_du_profil(profil)
    assert n["crans"] is None and "niveau d'études actuel" in n["avertissement"]


# ─── Dans l'analyse ──────────────────────────────────────────────────────────
def reponse(score, **champs):
    base = {"score": score, "eligible": True, "points_forts": ["a"], "points_faibles": ["b"], "domaine": "Dev",
            "resume": "ok", "niveau_requis": "non_precise", "duree_mois": None, "date_debut_offre": None,
            "alternance_seulement": False, "niveau_exigence": "non_precise"}
    return json.dumps({**base, **champs})


def test_analyse_plafonnee_avec_la_raison(ia):
    ia.reponse = reponse(9, niveau_requis="bac+5", duree_mois=6, date_debut_offre="janvier 2027",
                         niveau_exigence="exige")
    a = analyser_offre({"titre": "Stage ingénieur", "description": O1_TEXTE}, BUT2, mode="stage")
    assert (a["score"], a["eligible"], a["verdict"]) == (3, False, "ineligible")
    assert a["raison_ineligibilite"].startswith("Bac+5 exigé, profil Bac+2 ; 6 mois demandés")
    assert a["points_faibles"][0] == "Inéligible : Bac+5 exigé, profil Bac+2" and a["points_faibles"][-1] == "b"
    offre = {"titre": "Stage ingénieur", "description": O1_TEXTE}
    appliquer_analyse(offre, a, mode="stage", verbeux=False)
    assert (offre["statut"], offre["raison_archivage"]) == ("archive", "ineligible")


def test_information_non_precisee_jamais_bloquante(ia):
    ia.reponse = reponse(9)
    a = analyser_offre({"titre": "Stage", "description": "..."}, BUT2, mode="stage")
    assert (a["score"], a["eligible"], a["raison_ineligibilite"]) == (9, True, "")


def test_score_bas_mais_eligible_pas_archive():
    offre = {"titre": "Dev", "description": "...", "eligible": True, "score": 2}
    appliquer_archivage_auto(offre, {}, mode="job", verbeux=False)
    assert "statut" not in offre


def test_avertissement_dans_le_profil(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    client.mode = "stage"
    client.post("/api/profil", json={"prenom": "Alice", "formation": "École d'ingénieurs"})
    assert "niveau d'études actuel" in client.get("/api/profil").json()["niveau_profil"]["avertissement"]
    client.post("/api/profil", json={"niveau_etudes": "Bac+2 en cours"})
    assert client.get("/api/profil").json()["niveau_profil"] == {
        "crans": 2, "libelle": "Bac+2", "source": "niveau d'études", "avertissement": ""}
    page = client.get("/stage").text
    assert page.count('data-profil="niveau_etudes"') == 3 and page.count("data-niveau-avert") == 3


def test_archive_ineligible_motif_filtre_et_retour(utilisateur, ia):
    from database.candidatures_db import ajouter_candidature, lire_candidature
    from france_travail.analyseur import marquer_non_analysee
    from shared import config
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    client.mode = "stage"
    client.post("/api/profil", json={**{k: v for k, v in BUT2.items() if k != "duree_semaines"}})
    ajouter_candidature(uid, marquer_non_analysee({"id": "O1", "titre": "Stage ingénieur", "description": O1_TEXTE},
                                                  mode="stage"), mode="stage")
    ia.reponse = reponse(8, niveau_requis="bac+5", niveau_exigence="exige")
    assert client.post("/api/analyser", json={"id": "O1"}).status_code == 200
    o = lire_candidature(uid, "O1", mode="stage")
    assert (o["statut"], o["raison_archivage"], o["score"]) == ("archive", "ineligible", 3)
    assert o["points_faibles"][0] == "Inéligible : Bac+5 exigé, profil Bac+2"
    # Remise dans les offres actives
    assert client.post("/api/offre/archivage", json={"id": "O1", "desarchiver": True}).json()["ok"]
    assert lire_candidature(uid, "O1", mode="stage")["statut"] == "nouveau"
    assert client.post("/api/offre/archivage", json={"id": "O1", "raison": "ineligible"}).status_code == 200
    page = client.get("/stage").text
    assert 'data-filter="ineligible">Inéligible<' in page
    js = (config.STATIC_DIR / "js" / "offres.js").read_text(encoding="utf-8")
    assert "Remettre dans les offres actives" in js and "motifIneligible" in js


# ─── D98 : valeurs extraites contrôlées contre le texte de l'offre ───────────
OHANA = ("Au sein de notre équipe infrastructure, tu participeras à l'automatisation des déploiements. "
         "Profil recherché : Étudiant(e) en informatique (école d'ingénieur, master ou équivalent), "
         "curieux(se) et autonome.")
MOSS = ("Missions : supervision réseau, scripts d'exploitation. Profil : vous êtes en dernière année d'école "
        "d'ingénieurs ou en Master 2 (Bac+5) dans le domaine des réseaux.")


def test_ohana_niveau_souhaite_eligible(ia):
    ia.reponse = reponse(8, niveau_requis="bac+5", niveau_exigence="exige")    # le modèle se trompe d'exigence
    a = analyser_offre({"titre": "Stage DevOps", "description": OHANA}, BUT2, mode="stage")
    assert (a["eligible"], a["niveau_exigence"], a["raison_ineligibilite"]) == (True, "souhaite", "")
    assert a["score"] == 6 and a["points_faibles"][0] == "Bac+5 souhaité, profil Bac+2"   # 3 crans : -2


def test_moss_niveau_exige_ineligible(ia):
    ia.reponse = reponse(8, niveau_requis="bac+5", niveau_exigence="exige")
    a = analyser_offre({"titre": "Stage réseau", "description": MOSS}, BUT2, mode="stage")
    assert (a["eligible"], a["niveau_exigence"], a["score"]) == (False, "exige", 3)
    assert a["raison_ineligibilite"] == "Bac+5 exigé, profil Bac+2"


@pytest.mark.parametrize("titre", ["Stage : Ingénieur/e Système", "Ingénieur/e Réseau H/F",
                                   "Stage Ingénieur/e DevOps", "Ingénieur(e) sécurité - stage"])
def test_intitule_ingenieur_n_est_pas_un_niveau(ia, titre):
    """Cas réel : qwen3.5:9b a lu « Bac+5 exigé » dans quatre intitulés « Ingénieur/e ... »
    dont le texte ne dit rien du niveau."""
    ia.reponse = reponse(8, niveau_requis="bac+5", niveau_exigence="exige")
    texte = "Vous participerez à l'administration des serveurs Linux et à la supervision, avec l'équipe ingénieur."
    a = analyser_offre({"titre": titre, "description": texte}, BUT2, mode="stage")
    assert (a["niveau_requis"], a["niveau_exigence"], a["eligible"], a["score"]) == ("non_precise", "non_precise", True, 8)
    assert a["extraits_ecartes"] == ["niveau_requis bac+5 absent de l'offre"]


def test_duree_du_profil_recopiee_ecartee(ia):
    """Constat : duree_mois = 2,5 (les 10 semaines du profil) pour presque toutes les offres."""
    ia.reponse = reponse(8, duree_mois=2.5)
    a = analyser_offre({"titre": "Stage", "description": "Stage de développement web, dès que possible."}, BUT2,
                       mode="stage")
    assert a["duree_mois"] is None and a["extraits_ecartes"] == ["duree_mois 2.5 absente de l'offre"]
    ia.reponse = reponse(8, duree_mois=6)
    a = analyser_offre({"titre": "Stage", "description": "Stage de 6 mois."}, BUT2, mode="stage")
    assert a["duree_mois"] == 6 and not a["eligible"]


@pytest.mark.parametrize("texte, valeur, gardee", [
    ("Stage de 24 semaines.", 5.5, True),
    ("Stage de 6 mois.", 6, True),
    ("Stage de 6 mois.", 2.5, False),
    ("Expérience : 6 mois exigé(e)\nStage en équipe.", 6, False),     # ligne d'expérience de France Travail
])
def test_controle_de_la_duree(texte, valeur, gardee):
    e = extraits(duree=valeur)
    el.controler_extraits(e, {"description": texte})
    assert (e["duree_mois"] == valeur) is gardee


@pytest.mark.parametrize("texte, valeur, gardee", [
    ("Début en janvier 2027.", "janvier 2027", True),
    ("Début : 01/2027.", "janvier 2027", True),
    ("Démarrage le 15/01/2027.", "15/01/2027", True),
    ("Début en janvier.", "janvier 2027", False),          # année inventée
    ("Stage dès que possible.", "février 2027", False),
    ("Stage dès que possible.", "dès que possible", True),  # non lisible : gardé, jamais bloquant
])
def test_controle_de_la_date(texte, valeur, gardee):
    e = extraits(debut=valeur)
    el.controler_extraits(e, {"description": texte})
    assert (e["date_debut_offre"] == valeur) is gardee


@pytest.mark.parametrize("texte, niveau, garde, exigence", [
    ("Formation Bac+5 en informatique.", "bac+5", True, "exige"),
    ("Étudiant en Master.", "bac+5", True, "exige"),
    ("Étudiant en Master.", "bac+4", True, "exige"),
    ("Titulaire d'un BTS SIO.", "bac+2", True, "exige"),
    ("Étudiant en BUT informatique.", "bac+3", True, "exige"),
    ("Licence ou équivalent.", "bac+3", True, "souhaite"),
    ("Idéalement en école d'ingénieurs.", "bac+5", True, "souhaite"),
    ("Formation : Bac+5 informatique (souhaitée)", "bac+5", True, "souhaite"),   # libellé de France Travail
    ("Vous rejoindrez une équipe d'ingénieurs.", "bac+5", False, "non_precise"),
    ("Le but du stage est d'apprendre.", "bac+3", False, "non_precise"),          # « but » n'est pas le BUT
])
def test_controle_du_niveau_et_de_l_exigence(texte, niveau, garde, exigence):
    e = extraits(niveau=niveau)
    el.controler_extraits(e, {"description": texte})
    assert (e["niveau_requis"] == niveau) is garde and e["niveau_exigence"] == exigence


def test_souhait_a_deux_crans_un_point():
    e = extraits(niveau="bac+4", exigence="souhaite")
    assert el.penalite_souhait(e, BUT2) == (1, "Bac+4 souhaité, profil Bac+2")
    assert el.raisons_ineligibilite(e, BUT2, "stage") == []
    assert el.penalite_souhait(extraits(niveau="bac+3", exigence="souhaite"), BUT2) == (0, "")


# ─── D100 : niveau de secours lu par Python ──────────────────────────────────
def test_ohana_non_precise_par_le_modele_bac5_souhaite(ia):
    """Cas réel : OHana ressort non_precise chez les deux modèles."""
    ia.reponse = reponse(8)                                   # niveau_requis non_precise
    a = analyser_offre({"titre": "Stage DevOps", "description": OHANA}, BUT2, mode="stage")
    assert (a["niveau_requis"], a["niveau_exigence"], a["eligible"]) == ("bac+5", "souhaite", True)
    assert a["score"] == 6 and a["points_faibles"][0] == "Bac+5 souhaité, profil Bac+2"
    assert "remplacé par bac+5 (souhaite)" in a["extraits_ecartes"][0]


def test_moss_non_precise_par_le_modele_bac5_exige(ia):
    ia.reponse = reponse(8)
    a = analyser_offre({"titre": "Stage réseau", "description": MOSS}, BUT2, mode="stage")
    assert (a["niveau_requis"], a["niveau_exigence"], a["eligible"]) == ("bac+5", "exige", False)


@pytest.mark.parametrize("texte, attendu", [
    (OHANA, ("bac+5", "souhaite")),
    (MOSS, ("bac+5", "exige")),
    ("Titulaire d'un BTS ou d'une licence.", ("bac+2", "exige")),
    ("Étudiant en Master.", ("bac+5", "exige")),
    ("Étudiant(e) en BUT ou équivalent.", ("bac+3", "souhaite")),
    ("Vous rejoindrez nos ingénieurs.", None),
    ("Aucun prérequis.", None),
])
def test_niveau_detecte(texte, attendu):
    assert el.niveau_detecte(texte) == attendu


def test_pas_de_secours_sans_indice(ia):
    ia.reponse = reponse(8)
    a = analyser_offre({"titre": "Stage : Ingénieur/e Système", "description": "Administration Linux."}, BUT2,
                       mode="stage")
    assert (a["niveau_requis"], a["niveau_exigence"], a["extraits_ecartes"]) == ("non_precise", "non_precise", [])
