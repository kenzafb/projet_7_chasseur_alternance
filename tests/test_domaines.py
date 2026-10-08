"""Modèle des domaines (SPEC_SOURCES section 1) : codes France Travail,
indifférent, anciennes clés, migration 0007, enregistrement du profil,
LBA et Sirene inchangés pour les profils existants."""

import sqlite3

import pytest
from alembic import command

import main
from database.profil_db import lire_profil, sauvegarder_profil
from database.schema import config_alembic
from france_travail.analyseur import construire_contexte_profil_job
from shared import domaines as d


def test_arbre_des_domaines():
    arbre = d.grands_domaines()
    assert [g["code"] for g in arbre] == list("ABCDEFGHIJKLMN")
    m = next(g for g in arbre if g["code"] == "M")
    assert m["libelle"] == "Support à l'entreprise"
    assert {"code": "M18", "libelle": "Systèmes d'information et de télécommunication"} in m["domaines"]
    assert sum(len(g["domaines"]) for g in arbre) == 110
    assert all(x["code"].startswith(g["code"]) for g in arbre for x in g["domaines"])


@pytest.mark.parametrize("entree, sortie", [
    (["informatique"], ["M18"]),
    (["immobilier", "informatique"], ["C15", "M18"]),
    (["M18", "m18", " M18 "], ["M18"]),
    (["C15", "C"], ["C"]),                       # C15 couvert par son grand domaine
    (["C", "C15", "M18"], ["C", "M18"]),
    (["Z99", "inconnu", 3, ""], []),
    ([], []),
    (None, []), ("M18", []), ({"M18": 1}, []),
])
def test_normalisation(entree, sortie):
    assert d.normaliser_domaines(entree) == sortie


def test_libelles():
    assert d.libelles_domaines(["informatique", "C"]) == [
        "Systèmes d'information et de télécommunication", "Banque, assurance, immobilier"]
    contexte = construire_contexte_profil_job({"recherche": {"domaines": ["C15"]}})
    assert "DOMAINES PRÉFÉRÉS (optionnel) : Immobilier" in contexte


def test_lba_et_sirene_inchanges_pour_les_profils_existants():
    """Correspondances d'avant la phase 5b, rangées sous les nouveaux codes."""
    romes_info = [f"M18{i:02d}" for i in range(1, 11)]
    assert d.lba_romes(["M18"]) == d.lba_romes(["informatique"]) == romes_info
    assert d.lba_romes([]) == romes_info                          # ancien défaut
    assert d.lba_romes(["C15"]) == ["C1501", "C1502", "C1503", "C1504"]
    assert "68.32B" in d.naf_codes(["C15"]) and len(d.naf_codes(["C15"])) == 7
    assert len(d.naf_codes([])) == 16 and d.naf_codes([]) == d.naf_codes(["M18"])
    # Domaine sans correspondance : rien de cherché, signalé
    assert d.lba_romes(["J"]) == [] and d.naf_codes(["J11"]) == []
    assert d.lba_romes(["J", "M18"]) == romes_info
    assert d.domaines_sans_correspondance(["J", "M18"], "lba") == ["J"]


def test_profil_enregistre_en_codes(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    r = client.post("/api/profil", json={"recherche": {"domaines": ["informatique", "Z99", "C", "C15"],
                                                       "disponibilite": "septembre"}})
    assert r.json() == {"ok": True}
    assert lire_profil(uid)["recherche"] == {"domaines": ["M18", "C"], "disponibilite": "septembre"}
    sauvegarder_profil(uid, {"recherche": "pas un dict"})
    assert lire_profil(uid)["recherche"] == {}


def test_route_des_domaines(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    arbre = client.get("/api/domaines").json()
    assert len(arbre) == 14 and arbre[0]["domaines"][0]["code"] == "A11"


def test_lba_ignoree_si_aucun_domaine_pris_en_charge(utilisateur, monkeypatch):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    sauvegarder_profil(uid, {"recherche": {"domaines": ["J"]}})
    appels = []
    monkeypatch.setattr(main, "lancer_recherche", lambda *a, **k: [])
    monkeypatch.setattr(main, "chercher_offres_lba", lambda romes: appels.append(romes) or [])
    from tests.test_pipelines import attendre
    assert client.post("/api/recherche").status_code == 200
    attendre(lambda: not main.pipelines.etat("recherche", uid)["en_cours"])
    logs = "\n".join(str(l) for l in main.pipelines.logs(uid))
    assert appels == []
    assert "LBA ignorée : aucun domaine du profil" in logs and "ignorés : J" in logs


def test_migration_0007(tmp_path):
    chemin = tmp_path / "v6.db"
    cfg = config_alembic(f"sqlite:///{chemin}")
    command.upgrade(cfg, "0006")
    cx = sqlite3.connect(chemin)
    cx.execute("INSERT INTO users (id, email, mot_de_passe_hash) VALUES (1, 'a@test.fr', 'x')")
    for id_, mode, recherche in [
        (1, "alternance", '{"domaines": ["informatique", "immobilier"], "disponibilite": "sept"}'),
        (2, "job", '{"domaines": ["immobilier", "informatique", "immobilier"]}'),
        (3, "stage", '{"disponibilite": "x"}'),
    ]:
        cx.execute("INSERT INTO profils (id, user_id, mode, recherche) VALUES (?, 1, ?, ?)", (id_, mode, recherche))
    cx.execute("INSERT INTO users (id, email, mot_de_passe_hash) VALUES (2, 'b@test.fr', 'x')")
    cx.execute("INSERT INTO profils (id, user_id, mode, recherche) VALUES (4, 2, 'alternance', NULL)")
    cx.commit()
    cx.close()

    command.upgrade(cfg, "0007")
    cx = sqlite3.connect(chemin)
    lignes = dict(cx.execute("SELECT id, recherche FROM profils").fetchall())
    cx.close()
    import json
    assert json.loads(lignes[1]) == {"domaines": ["M18", "C15"], "disponibilite": "sept"}
    assert json.loads(lignes[2]) == {"domaines": ["C15", "M18"]}
    assert json.loads(lignes[3]) == {"disponibilite": "x"}
    assert lignes[4] is None

    # Retour arrière : anciennes clés, codes nouveaux retirés
    cx = sqlite3.connect(chemin)
    cx.execute("""UPDATE profils SET recherche = '{"domaines": ["M18", "J", "C15"]}' WHERE id = 2""")
    cx.commit()
    cx.close()
    command.downgrade(cfg, "0006")
    cx = sqlite3.connect(chemin)
    lignes = dict(cx.execute("SELECT id, recherche FROM profils").fetchall())
    cx.close()
    assert json.loads(lignes[1])["domaines"] == ["informatique", "immobilier"]
    assert json.loads(lignes[2]) == {"domaines": ["informatique", "immobilier"]}


# ─── Décisions D27 et D28 ─────────────────────────────────────────────────────
def test_avertissement_domaines_non_couverts():
    assert d.avertissement_non_couverts([], "lba") == ""            # indifférent : ancien défaut
    assert d.avertissement_non_couverts(["M18", "C15"], "sirene") == ""
    m = d.avertissement_non_couverts(["J", "M18"], "lba")
    assert m.startswith("Domaines pas encore couverts par La Bonne Alternance : Santé (J)")
    assert "pas cherchés pour l'instant" in m
    m = d.avertissement_non_couverts(["J11"], "sirene")
    assert "Sirene" in m and "(J11)" in m and "cette source est ignorée" in m


def test_avertissement_au_lancement(utilisateur, monkeypatch):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    sauvegarder_profil(uid, {"recherche": {"domaines": ["J", "M18"]}})
    monkeypatch.setattr(main, "lancer_recherche", lambda *a, **k: [])
    monkeypatch.setattr(main, "chercher_offres_lba", lambda romes: [])
    from tests.test_pipelines import attendre
    r = client.post("/api/recherche").json()
    attendre(lambda: not main.pipelines.etat("recherche", uid)["en_cours"])
    assert "La Bonne Alternance : Santé (J)" in r["avertissement"]
    import spontanees.fetch_entreprises as fetch
    monkeypatch.setattr(fetch, "main", lambda **kw: None)
    r = client.post("/api/spontanees/fetch").json()
    assert "Sirene" in r["avertissement"] and "Santé (J)" in r["avertissement"]
    # Tout couvert : pas d'avertissement
    sauvegarder_profil(uid, {"recherche": {"domaines": ["M18"]}})
    attendre(lambda: not main.pipelines.etat("spontanees", uid)["en_cours"])
    assert "avertissement" not in client.post("/api/spontanees/fetch").json()


def test_bandeau_domaines_vides_dans_le_profil(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = client.get("/").text
    assert "data-domaines-vide hidden" in page and "Aucun domaine choisi" in page
