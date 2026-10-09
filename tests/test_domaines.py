"""Modèle des domaines (SPEC_SOURCES section 1) : codes France Travail,
indifférent, anciennes clés, migration 0007, enregistrement du profil,
codes métiers de LBA tirés du référentiel (phase 5c). Sirene : tests/test_sirene.py."""

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


def test_codes_metiers_lba_tires_du_referentiel():
    """Phase 5c : tous les métiers du référentiel dont le code commence par
    un domaine ou un grand domaine choisi ; indifférent : aucun code."""
    m18 = d.codes_metiers(["M18"])
    assert len(m18) == 96 and all(c.startswith("M18") and len(c) == 5 for c in m18)
    assert d.codes_metiers(["informatique"]) == m18                # ancienne clé comprise
    assert len(d.codes_metiers(["C"])) == 64
    assert d.codes_metiers(["C", "C15"]) == d.codes_metiers(["C"])   # C15 déjà dans C
    assert d.codes_metiers([]) == []                               # indifférent : sans code
    assert d.codes_metiers(["J", "M18"]) == sorted(d.codes_metiers(["J"]) + m18)


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


def test_lba_cherche_tout_domaine_et_l_indifferent(utilisateur, monkeypatch):
    """Décision D37 : plus de domaine « non couvert » sur LBA ; un profil
    indifférent cherche sans code métier."""
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    from tests.test_pipelines import attendre
    monkeypatch.setattr(main, "lancer_recherche", lambda *a, **k: [])
    profils = []
    monkeypatch.setattr(main, "rechercher_lba", lambda profil, log=print: profils.append(profil) or
                        {"offres": [], "entreprises": [], "requetes": 0})
    for domaines in (["J"], []):
        sauvegarder_profil(uid, {"recherche": {"domaines": domaines}})
        r = client.post("/api/recherche").json()
        attendre(lambda: not main.pipelines.etat("recherche", uid)["en_cours"])
        assert "avertissement" not in r
    assert [p["recherche"]["domaines"] for p in profils] == [["J"], []]


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
def test_avertissement_au_lancement(utilisateur, monkeypatch):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    sauvegarder_profil(uid, {"recherche": {"domaines": ["J", "M18"]}})
    import spontanees.fetch_entreprises as fetch
    monkeypatch.setattr(fetch, "main", lambda **kw: None)
    from tests.test_pipelines import attendre
    r = client.post("/api/spontanees/fetch").json()
    assert "Sirene" in r["avertissement"] and "Santé (J)" in r["avertissement"]
    assert "choisis des secteurs" in r["avertissement"]
    assert "La Bonne Alternance" not in r["avertissement"]      # LBA couvre tout (D37)
    # Tout couvert : pas d'avertissement
    sauvegarder_profil(uid, {"recherche": {"domaines": ["M18"]}})
    attendre(lambda: not main.pipelines.etat("spontanees", uid)["en_cours"])
    assert "avertissement" not in client.post("/api/spontanees/fetch").json()


def test_bandeau_domaines_vides_dans_le_profil(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = client.get("/alternance").text
    assert "data-domaines-vide hidden" in page and "Aucun domaine choisi" in page
