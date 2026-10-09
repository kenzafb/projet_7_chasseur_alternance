"""État d'envoi par entreprise et par mode (phase 6a) : une entreprise est
unique par utilisateur, ses données publiques sont communes aux modes ;
sélection, envoi, date et suivi sont propres à chaque mode. Un contact
dans un autre mode est signalé, jamais bloquant."""

import sqlite3
from datetime import datetime, timezone

import pytest
from alembic import command

import spontanees.envoyeur as envoyeur
import spontanees.fetch_entreprises as fetch
from database.connexion import SessionLocal
from database.dedup_db import ajouter_emails_contactes
from database.entreprises_db import (ajouter_entreprises, ajouter_entreprises_lba, calculer_stats,
                                     compter_a_scraper, lire_entreprises, lire_entreprises_envoyees,
                                     modifier_statut_suivi, sauvegarder_enrichissement)
from database.models import Entreprise, EntrepriseMode
from database.profil_db import sauvegarder_profil
from database.schema import config_alembic
from tests.conftest import compte_verifie
from tests.faux_sirene import FausseSirene, etablissement, siret_sirene


@pytest.fixture(autouse=True)
def sans_pause(monkeypatch):
    monkeypatch.setattr(envoyeur, "PAUSE_ENTRE_MAILS", (0, 0))


def _avec_emails(uid, mode="alternance"):
    liste = lire_entreprises(uid, mode)
    for i, e in enumerate(liste):
        e["emails_trouves"] = [f"rh{i}@ent{i}.fr"]
    sauvegarder_enrichissement(uid, liste)


def _compter(modele):
    with SessionLocal() as db:
        return db.query(modele).count()


def test_entreprise_unique_donnees_communes_etat_par_mode(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    assert ajouter_entreprises(uid, [{"siret": "S1", "nom": "ACME"}]) == 1
    _avec_emails(uid)
    # Même SIRET en job : pas de doublon, sélectionnée, emails déjà scrapés repris
    assert ajouter_entreprises(uid, [{"siret": "S1", "nom": "ACME"}], mode="job") == 1
    assert ajouter_entreprises(uid, [{"siret": "S1", "nom": "ACME"}], mode="job") == 0   # déjà dans le mode
    assert _compter(Entreprise) == 1 and _compter(EntrepriseMode) == 2
    job = lire_entreprises(uid, "job")
    assert job[0]["emails_trouves"] == ["rh0@ent0.fr"] and job[0]["mode"] == "job"
    assert compter_a_scraper(uid, "job") == 0                       # jamais scrapée deux fois
    assert lire_entreprises(uid, "stage") == []


def test_envoi_propre_au_mode_et_etiquette_sans_blocage(utilisateur, smtp_simule):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    compte_verifie(smtp_simule, uid, "alice@gmail.com")
    ajouter_entreprises(uid, [{"siret": f"S{i}", "nom": f"Ent {i}"} for i in range(2)])
    _avec_emails(uid)
    assert envoyeur.main(uid, limite=1, mode="alternance")["envoyes"] == 1

    ajouter_entreprises(uid, [{"siret": f"S{i}"} for i in range(2)], mode="job")
    job = lire_entreprises(uid, "job")
    assert [e["mail_envoye"] for e in job] == [False, False]        # l'envoi d'alternance ne compte pas
    jour = lire_entreprises(uid)[0]["mail_envoye_le"][:10]
    assert job[0]["contacts_autres_modes"] == [{"mode": "alternance", "date": jour, "historique": False}]
    assert job[1]["contacts_autres_modes"] == []
    # Étiquette dans la page Spontanées du mode job, l'envoi n'est pas bloqué
    stats = calculer_stats(uid, "job")
    assert stats["prochaines"][0]["contacts_autres_modes"][0]["mode"] == "alternance"
    assert envoyeur.compter_a_envoyer(uid, "job") == 2
    assert envoyeur.main(uid, limite=5, mode="job")["envoyes"] == 2
    assert [to for _, _, to, _ in smtp_simule.messages] == [["rh0@ent0.fr"], ["rh0@ent0.fr"], ["rh1@ent1.fr"]]
    # Chaque mode a son propre suivi
    assert len(lire_entreprises_envoyees(uid, "alternance")) == 1
    assert len(lire_entreprises_envoyees(uid, "job")) == 2
    eid = lire_entreprises(uid)[0]["_id"]
    assert modifier_statut_suivi(uid, eid, "entretien", "job")
    assert lire_entreprises_envoyees(uid, "alternance")[0]["statut_suivi"] == "envoye"
    assert modifier_statut_suivi(uid, eid, "refus", "stage") is False   # pas sélectionnée en stage


def test_adresse_contactee_dans_un_autre_mode_signalee(utilisateur):
    """Une entreprise sélectionnée plus tard, dont une adresse a déjà été
    contactée dans un autre mode (import de l'historique, par exemple)."""
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": "S1"}], mode="job")
    _avec_emails(uid, "job")
    ajouter_emails_contactes(uid, "alternance", ["RH0@ent0.fr"])
    e, = lire_entreprises(uid, "job")
    assert e["contacts_autres_modes"][0]["mode"] == "alternance"
    assert envoyeur.compter_a_envoyer(uid, "job") == 1


def test_routes_par_mode(utilisateur, smtp_simule):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": "S1", "nom": "ACME"}, {"siret": "S2", "nom": "Beta"}])
    ajouter_entreprises(uid, [{"siret": "S2"}], mode="job")
    client.mode = "job"
    stats = client.get("/api/spontanees/stats").json()
    assert stats["raw"] == 1 and [p["nom"] for p in stats["prochaines"]] == ["Beta"]
    client.mode = "alternance"
    assert client.get("/api/spontanees/stats").json()["raw"] == 2


def test_isolation_du_suivi_entre_utilisateurs(utilisateur):
    client_a, id_a = utilisateur("a@test.fr", prenom="Alice")
    client_b, id_b = utilisateur("b@test.fr", prenom="Bob")
    ajouter_entreprises(id_a, [{"siret": "S1"}])
    eid = lire_entreprises(id_a)[0]["_id"]
    assert client_b.post("/api/spontanees/suivi/statut", json={"id": eid, "statut": "refus"}).json() == {"ok": False}
    assert ajouter_entreprises(id_b, [{"siret": "S1"}]) == 1          # même SIRET, autre utilisateur
    assert _compter(Entreprise) == 2


def test_sirene_en_job_reprend_une_entreprise_de_l_alternance(utilisateur, monkeypatch):
    monkeypatch.setenv("INSEE_API_KEY", "cle-insee")
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAFRev2")
    monkeypatch.setattr(fetch.P, "PAUSE_S", 0)
    api = FausseSirene([etablissement(1), etablissement(2)])
    monkeypatch.setattr(fetch.requests, "get", api.get)
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": siret_sirene(1), "nom": "Déjà là"}])
    _avec_emails(uid)
    sauvegarder_profil(uid, {"recherche": {"domaines": ["M18"], "departements": ["75"]}}, mode="job")
    fetch.main(uid, max_entreprises=5, log_fn=lambda m: None, mode="job")
    job = lire_entreprises(uid, "job")
    assert sorted(e["_extra"]["siret"] for e in job) == [siret_sirene(1), siret_sirene(2)]
    assert _compter(Entreprise) == 2                                 # aucune en double
    assert next(e for e in job if e["_extra"]["siret"] == siret_sirene(1))["emails_trouves"] == ["rh0@ent0.fr"]
    assert len(lire_entreprises(uid)) == 1                           # l'alternance n'a rien reçu


def test_lba_selectionne_une_entreprise_connue_dans_un_autre_mode(utilisateur):
    from tests.faux_lba import entreprise
    import france_travail.scraper_lba as lba
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": f"{i:09d}00012"} for i in (1, 2)], mode="job")
    b = ajouter_entreprises_lba(uid, [lba.normaliser_entreprise(entreprise(i, siret=f"{i:09d}00012"))
                                      for i in (1, 2)], maximum=1)
    assert b["ajoutees"] == 1 and b["non_ajoutees"] == 1 and b["deja_connues"] == 0
    assert len(lire_entreprises(uid)) == 1 and _compter(Entreprise) == 2


# ─── Migration 0011 ───────────────────────────────────────────────────────────
def test_migration_0011_vers_le_mode_alternance(tmp_path):
    chemin = tmp_path / "v10.db"
    cfg = config_alembic(f"sqlite:///{chemin}")
    command.upgrade(cfg, "0010")
    cx = sqlite3.connect(chemin)
    cx.execute("INSERT INTO users (id, email, mot_de_passe_hash) VALUES (1, 'a@test.fr', 'x')")
    cx.execute("INSERT INTO entreprises (user_id, mode, nom_commercial, mail_envoye, mail_envoye_le, statut_suivi, "
               "extra) VALUES (1, 'alternance', 'Envoyée', 1, '2026-05-29 08:10:00.000000', 'entretien', "
               "'{\"siret\": \"S1\", \"mail_destinataires\": [\"rh@a.fr\"], \"mail_note\": \"ok\"}')")
    cx.execute("INSERT INTO entreprises (user_id, mode, nom_commercial, mail_envoye, extra) "
               "VALUES (1, 'alternance', 'Neuve', 0, '{\"siret\": \"S2\"}')")
    cx.commit()
    cx.close()

    command.upgrade(cfg, "0011")
    cx = sqlite3.connect(chemin)
    assert cx.execute("SELECT entreprise_id, user_id, mode, mail_envoye, mail_envoye_le, statut_suivi, "
                      "mail_destinataires, mail_note, historique FROM entreprises_modes ORDER BY id").fetchall() == [
        (1, 1, "alternance", 1, "2026-05-29 08:10:00.000000", "entretien", '["rh@a.fr"]', "ok", 0),
        (2, 1, "alternance", 0, None, "envoye", "[]", "", 0)]
    assert cx.execute("SELECT extra FROM entreprises WHERE id = 1").fetchone() == ('{"siret": "S1"}',)
    colonnes = {r[1] for r in cx.execute("PRAGMA table_info(entreprises)")}
    assert not colonnes & {"mode", "mail_envoye", "mail_envoye_le", "statut_suivi"}
    cx.execute("INSERT INTO entreprises_modes (entreprise_id, user_id, mode, mail_envoye) VALUES (2, 1, 'job', 1)")
    with pytest.raises(sqlite3.IntegrityError):
        cx.execute("INSERT INTO entreprises_modes (entreprise_id, user_id, mode) VALUES (1, 1, 'alternance')")
    cx.commit()
    cx.close()

    # Retour arrière : l'état du mode alternance revient dans entreprises
    command.downgrade(cfg, "0010")
    cx = sqlite3.connect(chemin)
    assert cx.execute("SELECT mode, mail_envoye, statut_suivi, json_extract(extra, '$.mail_destinataires') "
                      "FROM entreprises ORDER BY id").fetchall() == [
        ("alternance", 1, "entretien", '["rh@a.fr"]'), ("alternance", 0, "envoye", None)]
    cx.close()


def test_suppression_d_une_entreprise_en_cascade(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": "S1"}])
    ajouter_entreprises(uid, [{"siret": "S1"}], mode="job")
    from sqlalchemy import text
    from database.connexion import engine
    with engine.begin() as cx:
        cx.execute(text("DELETE FROM entreprises"))
        assert cx.execute(text("SELECT COUNT(*) FROM entreprises_modes")).scalar_one() == 0
