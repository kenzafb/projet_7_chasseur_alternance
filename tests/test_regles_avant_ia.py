"""D202 à D206 : niveau maximal en stage, code métier ROME, règles Python
avant l'IA, champs gardés de l'IA à la base, description LBA."""

import json
from datetime import datetime, timezone

import pytest

from database.candidatures_db import ajouter_candidature, lire_candidature
from offres import france_travail
from offres import la_bonne_alternance as lba
from offres.analyse import analyser_offre, marquer_non_analysee
from offres.analyse_differee import analyser_en_attente
from shared import eligibilite as el
from shared.metiers_informatique import hors_informatique, titre_informatique
from tests.faux_france_travail import offre as offre_ft
from tests.test_analyse_v2 import _extraction, _jugement

BUT2 = {"prenom": "Ada", "niveau_etudes": "Bac+2", "missions": "développement", "competences": ["Python"],
        "date_debut": "2027-02-08", "date_fin": "2027-04-18", "duree_semaines": 10, "recherche": {}}


def stage(description, titre="Stage dev", **k):
    return {"id": "S1", "titre": titre, "description": description, **k}


# ─── D202 : niveau maximal en stage ───────────────────────────────────────────
@pytest.mark.parametrize("texte, raison", [
    ("Étudiant en Bac+5.", "Bac+5 souhaité, Bac+3 au plus en stage"),
    ("Formation Bac+4/5.", "Bac+4 souhaité, Bac+3 au plus en stage"),
    ("De Bac+4 à Bac+5.", "Bac+4 souhaité, Bac+3 au plus en stage"),
    ("De Bac+3 à Bac+5.", ""),                 # fourchette : la borne basse
    ("BTS, licence ou Master.", ""),
    ("Licence exigée.", ""),
    ("Aucun prérequis.", ""),                  # rien d'écrit : jamais bloquant
])
def test_niveau_maximal_en_stage(texte, raison):
    raisons = el.raisons_sans_ia(stage(texte), BUT2, "stage")
    assert raisons == ([raison] if raison else [])
    # Autres modes : la règle ne s'applique pas
    assert el.raisons_sans_ia(stage(texte), BUT2, "job") == []


def test_niveau_exige_une_seule_raison():
    assert el.raisons_sans_ia(stage("Bac+5 exigé."), BUT2, "stage") == ["Bac+5 exigé, profil Bac+2"]


def test_profil_master_pas_bloque_en_stage():
    assert el.niveau_trop_haut_stage(stage("Étudiant en Bac+5."), {"niveau_etudes": "Bac+5"}) == ""


def test_niveau_verifie_aussi_apres_l_ia(ia):
    """Sans les règles d'abord (bancs), le niveau reste décidé en Python."""
    ia.file = [_extraction(), _jugement("Très bien")]
    from offres.analyse_v2 import analyser_offre_v2
    r = analyser_offre_v2(stage("Étudiant en Bac+5."), BUT2, "stage")
    assert r["eligible"] is False and "Bac+3 au plus" in r["raison_ineligibilite"]


# ─── D203 : code métier ROME ──────────────────────────────────────────────────
def test_code_rome_enregistre(utilisateur):
    _, uid = utilisateur("a@test.fr")
    brut = {**offre_ft(1), "romeCode": "m1805"}
    o = france_travail._normaliser_une(brut)
    assert o["code_rome"] == "M1805"
    ajouter_candidature(uid, marquer_non_analysee(o, mode="job"), mode="job")
    assert lire_candidature(uid, o["id"], mode="job")["code_rome"] == "M1805"
    assert france_travail.code_rome({}) == "" and france_travail.code_rome({"romeCode": "??"}) == ""


@pytest.mark.parametrize("code, titre, hors", [
    ("M1501", "Assistant RH", True), ("E1206", "Stage Expérience Utilisateur", True),
    ("M1808", "Cartographe", True), ("M1809", "Météorologue", True), ("M1893", "Technicien météo", True),
    ("M1855", "Assistant", False), ("M1828", "PMO", False), ("M1895", "Géomaticien", False),
    ("", "Assistant RH", False), ("X", "Assistant RH", False),                # code inconnu : l'offre passe
    ("F1112", "Stage - Développement Contrôle-Commande", False),               # mot informatique du titre
    ("M1211", "Chargé de base de données en stage", False), ("K1", "Data analyst", False),
    ("M1501", "Chargé.e des RÉSEAUX sociaux", False), ("D1401", "Cyber-sécurité", False),
])
def test_hors_informatique(code, titre, hors):
    assert hors_informatique({"code_rome": code, "titre": titre}) is hors


@pytest.mark.parametrize("titre, attendu", [
    ("Développeuse web", True), ("Stage IA", True), ("DevOps", True), ("Systèmes", True), ("Logiciels", True),
    ("Commercial", False), ("Stagiaire Webanalytics", False), ("Médiation", False), ("Database", False)])
def test_mots_entiers_du_titre(titre, attendu):
    assert titre_informatique(titre) is attendu


def test_domaines_du_profil_respectes():
    o = {"code_rome": "C1503", "titre": "Gestion immobilière"}
    assert hors_informatique(o, {"recherche": {"domaines": ["M18"]}})
    assert not hors_informatique(o, {"recherche": {"domaines": ["C15"]}})
    assert not hors_informatique(o, {"recherche": {"domaines": ["M18", "C15"]}})
    assert not hors_informatique({"code_rome": "M1501", "titre": "RH"}, {"recherche": {"domaines": ["M"]}})


def test_archivee_a_la_recuperation_en_stage_seulement(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    for mode in ("stage", "job"):
        o = marquer_non_analysee({"id": mode, "titre": "Assistant RH", "description": "...", "code_rome": "M1501"},
                                 mode=mode, verbeux=False)
        ajouter_candidature(uid, o, mode=mode)
    s, j = (lire_candidature(uid, m, mode=m) for m in ("stage", "job"))
    assert (s["statut"], s["raison_archivage"]) == ("archive", "hors_informatique")
    assert "Hors informatique (code métier)" in s["etiquettes"]
    assert j["statut"] == "nouveau" and j["marques"] == []
    page = client.get("/stage").text
    assert '<option value="hors_informatique">Hors informatique (code métier)</option>' in page


# ─── D204 : règles Python avant l'IA ──────────────────────────────────────────
@pytest.mark.parametrize("texte, duree", [
    ("Stage de 6 mois.", 6), ("Durée : 4 à 6 mois", 4), ("Stage conventionné de 4 à 6 mois", 4),
    ("Durée du stage : 2 mois", 2), ("Stage de 6 mois. Délai de réponse : 4 semaines.", 4 / el.SEMAINES_PAR_MOIS),
    ("Première expérience (stage de 6 mois) appréciée.", None), ("Nous recrutons 6 mois par an.", None),
    ("Expérience : 6 Mois (exigée)", None)])
def test_duree_sure(texte, duree):
    assert el.duree_sure(stage(texte)) == (pytest.approx(duree) if duree else None)


@pytest.mark.parametrize("texte, debut", [
    ("À pourvoir à partir de janvier 2027.", "janvier 2027"), ("Début : 1er décembre 2026", "1er décembre 2026"),
    ("À partir de janvier 2027, dates flexibles.", None), ("À partir de janvier ou février 2027.", None),
    ("Candidature à partir de janvier 2027.", None), ("Date limite de candidature, dès le 1/12/2026", None),
    ("En janvier 2027 nous avons déménagé.", None), ("Dès que possible.", None)])
def test_debut_sur(texte, debut):
    assert el.debut_sur(stage(texte)) == debut


def test_mois_du_profil_cite_laisse_a_l_ia():
    assert el.raisons_sans_ia(stage("À partir de janvier 2027."), BUT2, "stage") != []
    assert el.raisons_sans_ia(stage("À partir de janvier 2027 (ou entre mars et juin)."), BUT2, "stage") == []


def test_offre_ineligible_jamais_lue_par_l_ia(utilisateur, ia, monkeypatch):
    monkeypatch.setenv("IA_VERSION_ANALYSE", "v2")
    _, uid = utilisateur("a@test.fr", prenom="Ada")
    jour = datetime(2026, 11, 1, tzinfo=timezone.utc)
    for ref, texte in (("A", "Stage de 6 mois."), ("B", "Étudiant en Bac+5."), ("C", "Développement web."),
                       ("D", "À partir de janvier 2027.")):
        ajouter_candidature(uid, marquer_non_analysee({"id": ref, "titre": f"Stage {ref}", "description": texte,
                                                       "date_trouvee": jour}, mode="stage"), mode="stage")
    ajouter_candidature(uid, {"id": "E", "titre": "RH", "description": "...", "verdict": "non_analysee",
                              "score": None, "code_rome": "M1501", "date_trouvee": jour}, mode="stage")
    ia.file = [_extraction(), _jugement("Bien")]
    journal = []
    bilan = analyser_en_attente(uid, "stage", BUT2, 10, log=journal.append)
    assert len(ia.appels) == 2                                        # C seulement, deux appels
    assert (bilan["analysees"], bilan["sans_ia"], bilan["mots_cles"], bilan["archivees"]) == (4, 3, 1, 3)
    attendus = {"A": "6 mois demandés", "B": "Bac+5 souhaité", "D": "début en janvier 2027"}
    for ref, raison in attendus.items():
        o = lire_candidature(uid, ref, mode="stage")
        assert (o["statut"], o["raison_archivage"], o["verdict"], o["score"], o["eligible"]) == \
            ("archive", "ineligible", "ineligible", None, False)
        assert o["points_faibles"][0].startswith(f"Inéligible : {raison}")
    assert lire_candidature(uid, "C", mode="stage")["score"] == 7
    e = lire_candidature(uid, "E", mode="stage")
    assert (e["statut"], e["raison_archivage"], e["marques"]) == ("archive", "hors_informatique", ["hors_informatique"])
    assert any("inéligible sans IA (6 mois demandés" in x for x in journal)


def test_regles_d_abord_desactivable(ia):
    ia.reponse = json.dumps({"score": 9, "points_forts": [], "points_faibles": [], "domaine": "Dev", "resume": "x",
                             "niveau_requis": "non_precise", "duree_mois": None, "date_debut_offre": None,
                             "alternance_seulement": False, "niveau_exigence": "non_precise"})
    assert analyser_offre(stage("Bac+5 exigé."), BUT2, "stage")["sans_ia"] and ia.appels == []
    analyser_offre(stage("Bac+5 exigé."), BUT2, "stage", regles_d_abord=False)
    assert len(ia.appels) == 1


# ─── D205 : de la réponse de l'IA à la base ───────────────────────────────────
@pytest.mark.parametrize("car, garde, note", [
    ("domaines recherchés : Systèmes d'information", "domaines recherchés : Systèmes d'information", 1),
    ("une phrase inventée", "une phrase inventée", 3),       # rétrogradée en Faible, mais gardée
    ("aucune", "", 3)])
def test_points_forts_et_hors_sujet_car_arrivent_en_base(utilisateur, ia, monkeypatch, car, garde, note):
    monkeypatch.setenv("IA_VERSION_ANALYSE", "v2")
    _, uid = utilisateur("a@test.fr", prenom="Ada")
    ajouter_candidature(uid, marquer_non_analysee(stage("Missions."), mode="stage"), mode="stage")
    ia.file = [_extraction(), _jugement("Hors sujet", car)]
    profil = {**BUT2, "recherche": {"domaines": ["M18"]}}
    analyser_en_attente(uid, "stage", profil, 1, log=lambda m: None)
    o = lire_candidature(uid, "S1", mode="stage")
    assert (o["points_forts"], o["hors_sujet_car"], o["score"]) == (["Python"], garde, note)


# ─── D206 : description LBA ───────────────────────────────────────────────────
def test_description_lba_entiere_ou_coupure_journalisee(monkeypatch):
    lignes = []
    monkeypatch.setattr(lba, "journaliser", lignes.append)
    assert len(lba._description({"description": "a" * 12000}, "Dev")) == 12000 and lignes == []
    monkeypatch.setenv("IA_LONGUEUR_DESCRIPTION", "300")
    assert len(lba._description({"description": "a" * 12000}, "Dev")) == 300
    assert "12000 caractères, gardés : 300" in lignes[0]
