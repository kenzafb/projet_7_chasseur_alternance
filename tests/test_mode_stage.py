"""Mode stage (phase 6b) : page /stage, profil propre (dates, durée,
établissement, formation, missions, portfolio), balises du mail de
candidature spontanée, objet et trame par défaut, offres pas encore
disponibles, candidatures spontanées par Sirene seulement."""

import sqlite3
from datetime import date

import pytest
from alembic import command

import spontanees.envoyeur as envoyeur
import spontanees.fetch_entreprises as fetch
from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
from database.profil_db import lire_profil, sauvegarder_profil
from database.schema import config_alembic
from shared import balises_mail, modes
from shared.erreurs import ErreurUtilisateur
from shared.stage import date_en_lettres, duree_semaines
from tests.conftest import compte_verifie
from tests.faux_sirene import FausseSirene, etablissement, siret_sirene

PROFIL_STAGE = {"prenom": "Alice", "nom": "Martin", "email": "alice@exemple.fr", "telephone": "0600000000",
                "date_debut": "2027-01-04", "date_fin": "2027-06-25", "etablissement": "Université Paris Cité",
                "formation": "Licence 3 informatique", "missions": "Développement web",
                "portfolio": "https://alice.exemple.fr"}


@pytest.fixture(autouse=True)
def sans_pause(monkeypatch):
    monkeypatch.setattr(envoyeur, "PAUSE_ENTRE_MAILS", (0, 0))


@pytest.fixture
def stagiaire(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    client.mode = "stage"
    return client, uid


def _corps(message) -> str:
    return message.get_body(("plain",)).get_content()


# ─── Durée et dates ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("debut,fin,semaines", [
    (date(2027, 1, 4), date(2027, 6, 25), 25),    # 173 jours
    (date(2027, 1, 4), date(2027, 1, 8), 1),      # une semaine de 5 jours
    (date(2027, 1, 4), date(2027, 1, 4), 1),      # au moins 1
    (date(2027, 1, 4), date(2027, 1, 31), 4),     # 28 jours
    (date(2027, 1, 4), date(2027, 2, 7), 5),      # 35 jours
    (date(2027, 1, 4), date(2027, 1, 27), 3),     # 24 jours : 3,4 semaines
    (date(2027, 1, 4), date(2027, 1, 28), 4),     # 25 jours : 3,6 semaines
])
def test_duree_en_semaines(debut, fin, semaines):
    assert duree_semaines(debut, fin) == semaines


def test_duree_sans_dates_ou_a_l_envers():
    assert duree_semaines(None, date(2027, 1, 4)) is None
    assert duree_semaines(date(2027, 1, 4), date(2027, 1, 3)) is None


def test_dates_en_lettres():
    assert date_en_lettres(date(2027, 1, 4)) == "4 janvier 2027"
    assert date_en_lettres(date(2027, 2, 1)) == "1er février 2027"
    assert date_en_lettres(None) == ""


# ─── Page, mode et offres ─────────────────────────────────────────────────────
def test_page_stage(stagiaire):
    client, _ = stagiaire
    page = client.get("/stage").text
    assert 'data-mode="stage"' in page and "<title>Chasseur de Stage" in page
    assert 'data-limite="analyses"' in page                              # offres disponibles (D74)
    assert 'data-mode-section="stage"' in page and 'type="date" data-profil="date_debut"' in page
    assert "{date_debut}" in page and "{duree_semaines}" in page       # aide des balises du stage
    assert "La Bonne Alternance (fort potentiel" not in page            # pas de LBA en stage
    assert client.get("/api/mode").json() == {"mode": "stage", "label": "Chasseur de Stage", "couleur": "vert"}


def test_balises_du_stage_absentes_ailleurs(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = client.get("/alternance").text
    assert "{prenom}" in page and "{duree_semaines}" not in page


def test_mode_a_venir_refuse(monkeypatch):
    monkeypatch.setitem(modes.MODES_A_VENIR, "autre", {"label": "Chasseur d'autre chose"})
    with pytest.raises(ErreurUtilisateur, match="pas encore disponible"):
        modes.verifier_mode("autre")
    assert modes.verifier_mode("stage") == "stage"


# ─── Profil ───────────────────────────────────────────────────────────────────
def test_profil_de_stage(stagiaire):
    client, uid = stagiaire
    r = client.post("/api/profil", json={**PROFIL_STAGE, "recherche": {"domaines": ["M18"], "departements": ["75"],
                                                                      "tailles_spontanees": ["10_49"]}})
    assert r.json() == {"ok": True}
    p = client.get("/api/profil").json()
    assert (p["date_debut"], p["date_fin"], p["duree_semaines"]) == ("2027-01-04", "2027-06-25", 25)
    assert (p["etablissement"], p["formation"], p["missions"], p["portfolio"]) == (
        "Université Paris Cité", "Licence 3 informatique", "Développement web", "https://alice.exemple.fr")
    assert p["recherche"]["departements"] == ["75"]
    # Profil propre au mode : l'alternance n'a rien reçu
    assert lire_profil(uid, "alternance")["formation"] == "" and lire_profil(uid, "alternance")["date_debut"] == ""
    # Dates effacées
    client.post("/api/profil", json={"date_debut": "", "date_fin": ""})
    p = client.get("/api/profil").json()
    assert (p["date_debut"], p["date_fin"], p["duree_semaines"]) == ("", "", None)


@pytest.mark.parametrize("donnees,message", [
    ({"date_debut": "04/01/2027"}, "Date de début du stage invalide"),
    ({"date_debut": "2027-06-25", "date_fin": "2027-01-04"}, "antérieure à sa date de début"),
    ({"email_type": "Bonjour {entreprise}"}, "Balise inconnue"),
    ({"email_objet": "Stage { date_debut"}, "accolade { ou } isolée"),
])
def test_profil_de_stage_refuse(stagiaire, donnees, message):
    client, uid = stagiaire
    client.post("/api/profil", json={"date_debut": "2027-01-04", "etablissement": "Avant"})
    r = client.post("/api/profil", json={"etablissement": "Après", **donnees})
    assert r.status_code == 400 and message in r.json()["erreur"]
    p = lire_profil(uid, "stage")
    assert (p["etablissement"], p["date_debut"]) == ("Avant", "2027-01-04")   # rien d'écrit


def test_fin_seule_avant_le_debut_enregistre(stagiaire):
    client, _ = stagiaire
    client.post("/api/profil", json={"date_debut": "2027-03-01"})
    r = client.post("/api/profil", json={"date_fin": "2027-02-01"})
    assert r.status_code == 400 and "antérieure" in r.json()["erreur"]


# ─── Balises ──────────────────────────────────────────────────────────────────
def test_balises_par_mode():
    assert balises_mail.verifier_balises("Stage du { date_debut } au {date_fin}", "stage") == ["date_debut", "date_fin"]
    assert balises_mail.verifier_balises("Bonjour, {prenom} {nom}", "alternance") == ["prenom", "nom"]
    with pytest.raises(ErreurUtilisateur, match="Balise inconnue.*{date_debut}"):
        balises_mail.verifier_balises("du {date_debut}", "job")       # balise du stage, hors stage
    for texte in ("{}", "{ prenom", "prenom }", "{date.__class__}", "{prenom!r}"):
        with pytest.raises(ErreurUtilisateur):
            balises_mail.verifier_balises(texte, "stage")


def test_remplir_et_balise_vide():
    profil = {**PROFIL_STAGE, "portfolio": ""}
    texte = balises_mail.remplir("{prenom} : {duree_semaines} semaines du {date_debut} au {date_fin}, "
                                 "{formation} à {etablissement}", profil, "stage")
    assert texte == ("Alice : 25 semaines du 4 janvier 2027 au 25 juin 2027, "
                     "Licence 3 informatique à Université Paris Cité")
    with pytest.raises(ErreurUtilisateur, match=r"\{portfolio\}.*le lien de ton portfolio"):
        balises_mail.remplir("Voir {portfolio}", profil, "stage")


def test_objet_et_trame_par_defaut_du_stage():
    objet, corps = envoyeur.objet_et_corps(PROFIL_STAGE, "stage")
    assert objet == "Candidature spontanée : stage du 4 janvier 2027 au 25 juin 2027"
    assert "stage conventionné de 25 semaines, du 4 janvier 2027 au 25 juin 2027" in corps
    assert corps.rstrip().endswith("Alice Martin\n0600000000\nalice@exemple.fr")
    assert "{" not in objet + corps
    # Générique : ni établissement, ni formation, ni accord de genre
    assert "Université" not in corps and "Licence" not in corps
    with pytest.raises(ErreurUtilisateur, match="date de début du stage"):
        envoyeur.objet_et_corps({**PROFIL_STAGE, "date_debut": ""}, "stage")


def test_objets_des_autres_modes_inchanges():
    profil = {"prenom": "Alice", "nom": "Martin"}
    assert envoyeur.objet_et_corps(profil, "alternance")[0] == "Candidature spontanée en alternance"
    assert envoyeur.objet_et_corps(profil, "job")[0] == "Candidature spontanée"
    assert envoyeur.objet_et_corps({**profil, "email_objet": "Candidature de {prenom}"}, "job")[0] == \
        "Candidature de Alice"


# ─── Envoi ────────────────────────────────────────────────────────────────────
def _entreprise_avec_email(uid, mode="stage"):
    ajouter_entreprises(uid, [{"siret": "S1", "nom": "ACME"}], mode=mode)
    liste = lire_entreprises(uid, mode)
    liste[0]["emails_trouves"] = ["rh@acme.fr"]
    sauvegarder_enrichissement(uid, liste)


def test_envoi_du_stage_avec_les_balises(stagiaire, smtp_simule):
    client, uid = stagiaire
    compte_verifie(smtp_simule, uid, "alice@gmail.com")
    sauvegarder_profil(uid, {**PROFIL_STAGE, "email_type": "Bonjour,\n{formation} à {etablissement}, "
                                                           "{duree_semaines} semaines.\n{portfolio}"}, mode="stage")
    _entreprise_avec_email(uid)
    assert envoyeur.main(uid, limite=5, mode="stage")["envoyes"] == 1
    (_, _, to, message), = smtp_simule.messages
    assert to == ["rh@acme.fr"]
    assert message["Subject"] == "Candidature spontanée : stage du 4 janvier 2027 au 25 juin 2027"
    assert _corps(message).startswith("Bonjour,\nLicence 3 informatique à Université Paris Cité, 25 semaines.\n"
                                      "https://alice.exemple.fr")
    assert len(lire_entreprises(uid, "stage")) == 1 and lire_entreprises(uid, "stage")[0]["mail_envoye"]
    assert lire_entreprises(uid, "alternance") == []


def test_envoi_refuse_avant_lancement_sans_les_dates(stagiaire, smtp_simule, pipelines_neufs):
    client, uid = stagiaire
    compte_verifie(smtp_simule, uid, "alice@gmail.com")
    sauvegarder_profil(uid, {**PROFIL_STAGE, "date_fin": ""}, mode="stage")
    _entreprise_avec_email(uid)
    r = client.post("/api/spontanees/envoyer", json={"limite": 1})
    assert r.status_code == 400 and "date de fin du stage" in r.json()["erreur"]
    assert smtp_simule.messages == [] and not pipelines_neufs.etat("spontanees", uid)["en_cours"]


# ─── Candidatures spontanées : Sirene, pas LBA ────────────────────────────────
def test_recuperer_en_stage_par_sirene_seulement(stagiaire, monkeypatch):
    monkeypatch.setenv("INSEE_API_KEY", "cle-insee")
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAFRev2")
    monkeypatch.setattr(fetch.P, "PAUSE_S", 0)
    api = FausseSirene([etablissement(1), etablissement(2, cp="92100"), etablissement(3, tranche="NN")])
    monkeypatch.setattr(fetch.requests, "get", api.get)

    def lba_interdite(*args, **kwargs):
        raise AssertionError("LBA ne doit pas être interrogée en stage")
    monkeypatch.setattr(fetch, "entreprises_lba", lba_interdite)
    _, uid = stagiaire
    sauvegarder_profil(uid, {"recherche": {"domaines": ["M18"], "departements": ["75"]}}, mode="stage")
    logs = []
    fetch.main(uid, max_entreprises=5, log_fn=logs.append, mode="stage")
    assert [e["_extra"]["siret"] for e in lire_entreprises(uid, "stage")] == [siret_sirene(1)]
    assert lire_entreprises(uid, "alternance") == []
    assert any("départements 75" in m for m in logs)


# ─── Migration 0012 ───────────────────────────────────────────────────────────
def test_migration_0012(tmp_path):
    chemin = tmp_path / "v11.db"
    cfg = config_alembic(f"sqlite:///{chemin}")
    command.upgrade(cfg, "0011")
    cx = sqlite3.connect(chemin)
    cx.execute("INSERT INTO users (id, email, mot_de_passe_hash) VALUES (1, 'a@test.fr', 'x')")
    cx.execute("INSERT INTO profils (user_id, mode, prenom, formation) VALUES (1, 'alternance', 'Alice', 'BTS')")
    cx.commit()
    cx.close()
    command.upgrade(cfg, "0012")
    cx = sqlite3.connect(chemin)
    assert cx.execute("SELECT prenom, formation, date_debut, date_fin, etablissement, missions, portfolio "
                      "FROM profils").fetchall() == [("Alice", "BTS", None, None, None, None, None)]
    cx.close()
    command.downgrade(cfg, "0011")
    cx = sqlite3.connect(chemin)
    assert "date_debut" not in {r[1] for r in cx.execute("PRAGMA table_info(profils)")}
    assert cx.execute("SELECT prenom FROM profils").fetchall() == [("Alice",)]
    cx.close()


# ─── Offres France Travail du mode stage (D74) ────────────────────────────────
from tests.test_france_travail import api  # noqa: E402,F401  (fixture)


def test_criteres_france_travail_du_stage():
    from shared.criteres import criteres_france_travail
    c = criteres_france_travail({"recherche": {"domaines": ["M18"], "secteurs": ["62"], "themes": ["13"]}}, "stage")
    assert c["filtres"] == {"motsCles": ["stage"], "secteurActivite": ["62"]}     # pas de thème hors job
    assert c["domaines"] == ["M18"] and c["exclure_alternance"] and c["intitules_stage"]


def test_recherche_d_offres_de_stage(api, stagiaire):
    from france_travail.main import lancer_recherche
    from tests.faux_france_travail import offre
    _, uid = stagiaire
    api.offres = [offre(1, nature="E1", type_contrat="CDD", titre="Stage - Assistant(e) RH H/F"),
                  offre(2, nature="E2", type_contrat="CDD", titre="Stage - Apprenti logistique"),   # alternance
                  offre(3, nature="FS", type_contrat="CDD", titre="STAGE comptable"),               # alternance
                  offre(4, nature="E1", type_contrat="CDI", titre="Gestionnaire du service des stages"),
                  offre(5, nature="E1", type_contrat="CDI", titre="Technicien support"),            # pas « stage »
                  offre(6, nature="E1", type_contrat="CDI", titre="Stagiaire juriste", domaine="K19")]
    api.offres[4]["description"] = "Stage de fin d'études possible."
    profil = {"recherche": {"domaines": ["M18"]}}
    ecrites, logs = [], []
    lancer_recherche(uid, profil, analyser=False, max_analyse=10, on_offre=ecrites.append, mode="stage",
                     log_fn=logs.append)
    assert all(r.get("motsCles") == "stage" and r.get("domaine") == "M18" for r in api.recherches)
    assert [o["titre"] for o in ecrites] == ["Stage - Assistant(e) RH H/F"]
    o, = ecrites
    assert (o["verdict"], o["score"], o["statut"], o["raison_archivage"]) == ("non_analysee", None, "nouveau", "")
    texte = "\n".join(logs)
    assert "2 offres d'alternance écartées (mode stage)" in texte
    assert "2 offres écartées par l'intitulé" in texte


def test_recherche_par_la_route_en_stage(stagiaire, monkeypatch, pipelines_neufs):
    """La page Offres du mode stage se remplit comme les autres : offres « non analysées »."""
    import main
    from database.candidatures_db import lire_candidatures
    monkeypatch.setenv("ANALYSE_IA", "false")
    client, uid = stagiaire
    client.post("/api/profil", json=PROFIL_STAGE)

    def recherche(user_id, profil, analyser, max_analyse, on_offre, mode, log_fn):
        o = {"id": "s1", "titre": "Stage - Assistant RH", "entreprise": "ACME", "lieu": "75 - Paris",
             "zone": "Paris", "lien": "", "source": "France Travail", "description": "", "statut": "nouveau"}
        from france_travail.analyseur import marquer_non_analysee
        marquer_non_analysee(o, mode=mode)
        on_offre(o)
        return [o]
    monkeypatch.setattr(main, "lancer_recherche", recherche)
    r = client.post("/api/recherche", json={"max_analyses": 5})
    assert r.status_code == 200 and "avertissement" not in r.json()
    import time
    for _ in range(200):
        if not pipelines_neufs.etat("recherche", uid)["en_cours"]:
            break
        time.sleep(0.01)
    c, = lire_candidatures(uid, mode="stage")
    assert (c["titre"], c["statut"], c["verdict"]) == ("Stage - Assistant RH", "nouveau", "non_analysee")
    assert "LBA ignorée" in client.get("/api/logs").text
    assert lire_candidatures(uid, mode="alternance") == []


def test_archivage_par_mots_cles_en_stage():
    from france_travail.analyseur import marquer_non_analysee
    def offre(**k):
        return {"titre": "Stage - Assistant", "description": "", "entreprise": "ACME", **k}
    assert marquer_non_analysee(offre(), mode="stage").get("statut") != "archive"
    assert marquer_non_analysee(offre(entreprise="ESCP Business School"), mode="stage").get("statut") != "archive"
    assert marquer_non_analysee(offre(), mode="alternance")["raison_archivage"] == "stage"
    reserve = offre(description="Poste réservé aux bénéficiaires de l'obligation d'emploi")
    assert marquer_non_analysee(reserve, mode="stage")["raison_archivage"] == "public_specifique"
