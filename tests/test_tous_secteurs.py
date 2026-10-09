"""Case « tous les secteurs » des candidatures spontanées et message avant
lancement (phase 6b) : sans domaine, secteur ni cette case, « Récupérer »
ne cherche rien sur Sirene et le dit avant tout lancement, dans tous les
modes."""

import pytest

import main
import spontanees.fetch_entreprises as fetch
from database.entreprises_db import lire_entreprises
from database.profil_db import lire_profil, sauvegarder_profil
from shared import naf
from shared.criteres import normaliser_recherche, options_du_profil
from tests.faux_sirene import FausseSirene, etablissement

EXCLUSION = "-activitePrincipaleUniteLegale:(41.10D OR 66.19A OR 68.32B)"


class Journal(list):
    def __call__(self, msg):
        self.append(msg)

    def texte(self):
        return "\n".join(self)


@pytest.fixture
def sirene(monkeypatch):
    monkeypatch.setenv("INSEE_API_KEY", "cle-insee")
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAFRev2")
    monkeypatch.setattr(fetch.P, "PAUSE_S", 0)

    def brancher(fausse):
        monkeypatch.setattr(fetch.requests, "get", fausse.get)
        return fausse
    return brancher


def _jeu():
    return [etablissement(1, naf="62.01Z"),                   # informatique (cœur M18)
            etablissement(2, naf="47.11B"),                   # commerce
            etablissement(3, naf="86.10Z", tranche="NN"),     # sans salarié : jamais par défaut
            etablissement(4, naf="68.32B"),                   # support juridique : exclu partout
            etablissement(5, naf="10.71C", cp="92100")]       # hors département


def _sirets(uid, mode):
    return sorted(int(e["_extra"]["siret"][:9]) for e in lire_entreprises(uid, mode))


def test_case_non_cochee_par_defaut_et_normalisee():
    assert normaliser_recherche({"tous_secteurs": "oui"})["tous_secteurs"] is False
    assert normaliser_recherche({"tous_secteurs": True})["tous_secteurs"] is True
    assert "tous_secteurs" not in normaliser_recherche({})
    o = options_du_profil()
    assert o["domaines_naf"] == ["C15", "M18"] and "382 663" in o["volume_tous_secteurs"] and "67 755" in o["volume_tous_secteurs"]
    assert o["message_rien_a_chercher"] == naf.MESSAGE_RIEN_A_CHERCHER


def test_avertissements():
    assert naf.avertissement_sirene([]) == naf.MESSAGE_RIEN_A_CHERCHER
    assert naf.avertissement_sirene([], tous_secteurs=True) == ""
    assert naf.avertissement_sirene(["J11"], tous_secteurs=True) == ""
    assert "ou coche « tous les secteurs »" in naf.avertissement_sirene(["J11"])
    rien = naf.sirene_pour_profil({"recherche": {"domaines": []}})
    assert rien["rien_a_chercher"] and rien["avertissement"] == naf.MESSAGE_RIEN_A_CHERCHER
    assert not naf.sirene_pour_profil({"recherche": {"tous_secteurs": True}})["rien_a_chercher"]
    assert naf.sirene_pour_profil({"recherche": {"domaines": ["J11"]}})["rien_a_chercher"]
    assert not naf.sirene_pour_profil({"recherche": {"domaines": ["J11"], "secteurs": ["86"]}})["rien_a_chercher"]


def test_plan_tous_secteurs_en_dernier():
    p = {"recherche": {"domaines": ["M18"], "tous_secteurs": True, "departements": ["75"],
                       "tailles_spontanees": ["10_49"], "taille_inconnue_spontanees": False}}
    plan = fetch.plan_sirene(p, Journal())
    groupes = [g for g, _ in plan]
    assert groupes[0] == "cœurs" and groupes[-1] == "tous secteurs" and groupes.count("tous secteurs") == 1
    q = plan[-1][1]
    assert EXCLUSION in q and "activitePrincipaleUniteLegale:(" not in q.replace(EXCLUSION, "")
    assert "trancheEffectifsUniteLegale:(11 OR 12)" in q and "codePostalEtablissement:75*" in q
    # Effectifs inconnus cochés : une requête de plus, à part
    p["recherche"]["taille_inconnue_spontanees"] = True
    assert [g for g, _ in fetch.plan_sirene(p, Journal())].count("tous secteurs") == 2


def test_recuperer_tous_secteurs_en_job(utilisateur, sirene):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    sirene(FausseSirene(_jeu()))
    sauvegarder_profil(uid, {"recherche": {"domaines": [], "tous_secteurs": True}}, mode="job")
    logs = Journal()
    fetch.main(uid, log_fn=logs, mode="job")
    assert _sirets(uid, "job") == [1, 2, 5]                    # ni NN, ni support juridique
    assert "3 tous secteurs" in logs.texte()


def test_domaines_d_abord_puis_tous_secteurs(utilisateur, sirene):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    sirene(FausseSirene(list(reversed(_jeu()))))               # l'API rend le commerce avant l'informatique
    sauvegarder_profil(uid, {"recherche": {"domaines": ["M18"], "tous_secteurs": True, "departements": ["75"]}},
                       mode="stage")
    logs = Journal()
    fetch.main(uid, max_entreprises=1, log_fn=logs, mode="stage")
    assert _sirets(uid, "stage") == [1]                        # le cœur remplit la limite
    fetch.main(uid, max_entreprises=5, log_fn=Journal(), mode="stage")
    assert _sirets(uid, "stage") == [1, 2]


@pytest.mark.parametrize("mode", ["job", "stage"])
def test_recuperer_refuse_sans_rien_a_chercher(utilisateur, mode, pipelines_neufs):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    client.mode = mode
    client.post("/api/profil", json={"recherche": {"domaines": []}})
    stats = client.get("/api/spontanees/stats").json()
    assert stats["avertissement_recuperer"] == naf.MESSAGE_RIEN_A_CHERCHER     # dit avant tout lancement
    r = client.post("/api/spontanees/fetch", json={"max_entreprises": 5})
    assert r.status_code == 400 and r.json()["erreur"] == naf.MESSAGE_RIEN_A_CHERCHER
    assert not pipelines_neufs.etat("spontanees", uid)["en_cours"]
    client.post("/api/profil", json={"recherche": {"domaines": [], "tous_secteurs": True}})
    assert lire_profil(uid, mode)["recherche"]["tous_secteurs"] is True
    assert client.get("/api/spontanees/stats").json()["avertissement_recuperer"] == ""


def test_alternance_lance_quand_meme_pour_lba(utilisateur, pipelines_neufs, monkeypatch):
    monkeypatch.setattr(fetch, "main", lambda **kwargs: None)
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    client.post("/api/profil", json={"recherche": {"domaines": []}})
    r = client.post("/api/spontanees/fetch", json={"max_entreprises": 5})
    assert r.status_code == 200 and naf.MESSAGE_RIEN_A_CHERCHER in r.json()["avertissement"]


def test_departements_et_tailles_des_spontanees_en_job(utilisateur, sirene):
    """D75 : le profil job a les départements et tailles des spontanées,
    mêmes défauts que le stage (rien de coché : toute l'IDF, toutes tailles
    sauf « sans salarié », effectifs inconnus gardés)."""
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    client.mode = "job"
    client.post("/api/profil", json={"recherche": {"domaines": ["M18"], "departements": ["92"],
                                                   "tailles_spontanees": ["10_49"],
                                                   "taille_inconnue_spontanees": False}})
    rech = lire_profil(uid, "job")["recherche"]
    assert (rech["departements"], rech["tailles_spontanees"], rech["taille_inconnue_spontanees"]) == (
        ["92"], ["10_49"], False)
    plan = fetch.plan_sirene(lire_profil(uid, "job"), Journal())
    assert all("codePostalEtablissement:92*" in q and "trancheEffectifsUniteLegale:(11 OR 12)" in q for _, q in plan)
    assert len(plan) == 1                                          # effectifs inconnus non cherchés
    defauts = fetch.plan_sirene({"recherche": {"domaines": ["M18"]}}, Journal())
    assert "(75* OR 77* OR 78* OR 91* OR 92* OR 93* OR 94* OR 95*)" in defauts[0][1]
    assert [g for g, _ in defauts][:2] == ["cœurs", "cœurs"]       # tranches, puis effectifs inconnus
