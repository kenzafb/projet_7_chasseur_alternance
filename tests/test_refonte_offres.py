"""Page Offres de la refonte (D145) : offre vue à l'ouverture, Gardées et
Écartées, réglages avancés du mode enregistrés sur le serveur, migration 0016."""

import sqlite3

from alembic import command

from database.candidatures_db import ajouter_candidature, lire_candidature
from tests.test_analyse_differee import analyse, en_attente, lancer


def _offre(uid, ref, mode="alternance", **champs):
    ajouter_candidature(uid, {"id": ref, "titre": f"Poste {ref}", "score": 7, "verdict": "bon",
                              "statut": "nouveau", **champs}, mode=mode)


def test_offre_vue_a_l_ouverture(utilisateur):
    client, uid = utilisateur("a@test.fr")
    _offre(uid, "O1")
    assert lire_candidature(uid, "O1")["vue"] is False          # nouvelle offre : pas encore vue
    assert client.post("/api/offre/vue", json={"id": "O1"}).json() == {"ok": True}
    assert lire_candidature(uid, "O1")["vue"] is True
    assert client.post("/api/offre/vue", json={"id": "inconnue"}).status_code == 404


def test_offre_vue_isolee(utilisateur):
    _, a = utilisateur("a@test.fr")
    _offre(a, "O1")
    _offre(a, "S1", mode="stage")
    client_b, _ = utilisateur("b@test.fr")
    assert client_b.post("/api/offre/vue", json={"id": "O1"}).status_code == 404
    assert client_b.post("/api/offre/vue?mode=stage", json={"id": "S1"}).status_code == 404
    assert lire_candidature(a, "O1")["vue"] is False and lire_candidature(a, "S1", mode="stage")["vue"] is False


def test_gardee_puis_remise_et_ecartee(utilisateur):
    client, uid = utilisateur("a@test.fr")
    _offre(uid, "O1")
    assert client.post("/api/maj_statut", json={"id": "O1", "statut": "gardee"}).json()["ok"]
    assert lire_candidature(uid, "O1")["statut"] == "gardee"
    assert client.post("/api/maj_statut", json={"id": "O1", "statut": "nouveau"}).json()["ok"]
    # « Pas pour moi » : l'archivage manuel existant
    client.post("/api/offre/archivage", json={"id": "O1", "raison": "manuel"})
    o = lire_candidature(uid, "O1")
    assert (o["statut"], o["raison_archivage"]) == ("archive", "manuel")
    assert client.post("/api/maj_statut", json={"id": "O1", "statut": "garde"}).status_code == 422


def test_une_offre_gardee_n_est_pas_ecartee_par_l_analyse(utilisateur, ia):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    en_attente(uid, "G", 1)
    client.post("/api/maj_statut", json={"id": "G", "statut": "gardee"})
    ia.reponse = analyse(score=1)                               # note basse : l'analyse archiverait
    lancer(client, uid)
    o = lire_candidature(uid, "G")
    assert o["statut"] == "gardee" and o["score"] == 1


def test_reglages_bornes_et_persistants(utilisateur):
    client, uid = utilisateur("a@test.fr")
    d = client.get("/api/reglages").json()
    assert (d["offres"], d["analyses"], d["analyse_toute_file"], d["analyse_auto"]) == (30, 30, False, False)
    r = client.post("/api/reglages", json={"offres": 10**6, "analyses": 0, "analyse_toute_file": True,
                                           "analyse_auto": True}).json()
    assert (r["offres"], r["analyses"], r["analyse_toute_file"], r["analyse_auto"]) == (500, 1, True, True)
    # Propres au mode : le stage garde ses défauts
    assert client.get("/api/reglages?mode=stage").json()["offres"] == 30
    assert client.post("/api/reglages", json={"inconnu": 1}).status_code == 422
    assert client.get("/api/profil").json()["analyse_auto"] is True
    # Affichés dans Paramètres, Réglages avancés
    page = client.get("/alternance").text
    assert 'data-reglage="offres"' in page and 'value="500"' in page and "Réglages avancés" in page


def test_analyse_sans_plafond_demande_prend_le_reglage(utilisateur, ia):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    for i in range(1, 6):
        en_attente(uid, f"R{i}", i)
    client.post("/api/reglages", json={"analyses": 2})
    ia.reponse = analyse()
    reponse, _ = lancer(client, uid)
    assert reponse["max_analyses"] == 2
    client.post("/api/reglages", json={"analyse_toute_file": True})
    reponse, _ = lancer(client, uid)
    assert reponse["max_analyses"] == 3                         # toute la file restante


def test_migration_0016_offres_existantes_vues(tmp_path):
    from database.schema import config_alembic
    chemin = tmp_path / "t.db"
    cfg = config_alembic(f"sqlite:///{chemin}")
    command.upgrade(cfg, "0015")
    cx = sqlite3.connect(chemin)
    cx.execute("INSERT INTO users (email, mot_de_passe_hash, mot_de_passe_temporaire) VALUES ('a@t.fr', 'x', 0)")
    cx.execute("INSERT INTO candidatures (user_id, mode, ref_offre) VALUES (1, 'alternance', 'R1')")
    cx.execute("INSERT INTO profils (user_id, mode, analyse_auto) VALUES (1, 'alternance', 0)")
    cx.commit()
    cx.close()
    command.upgrade(cfg, "0016")
    cx = sqlite3.connect(chemin)
    assert cx.execute("SELECT vue FROM candidatures").fetchone() == (1,)
    assert cx.execute("SELECT reglages FROM profils").fetchone() == ("{}",)
    cx.close()
    command.downgrade(cfg, "0015")
