"""Entreprises à fort potentiel de La Bonne Alternance dans les
candidatures spontanées (phase 5c) : dédoublonnage par SIRET avec Sirene,
priorité de traitement et d'affichage, migration 0008, recherche d'offres
qui les verse, étape « Récupérer » (LBA d'abord, puis Sirene)."""

import sqlite3

from alembic import command

import france_travail.scraper_lba as lba
import main
from database.entreprises_db import (ajouter_entreprises, ajouter_entreprises_lba, calculer_stats,
                                     cles_connues, lire_entreprises)
from database.schema import config_alembic
from tests.faux_lba import entreprise
from tests.test_limites import sirene  # noqa: F401  (fixture)
from tests.test_pipelines import attendre


# ─── Entreprises dans les candidatures spontanées ─────────────────────────────
def _norm(n, **kw):
    return lba.normaliser_entreprise(entreprise(n, **kw))


def test_entreprises_lba_dedoublonnees_par_siret_et_prioritaires(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": "S3", "nom": "Sirene seule"},
                              {"siret": "11111111100011", "nom": "Aussi chez LBA"}])
    brut = entreprise(1, siret="11111111100011", email="rh@aussi.fr")
    brut["apply"]["recipient_id"] = "partners_1"
    b = ajouter_entreprises_lba(uid, [lba.normaliser_entreprise(brut), _norm(2, email="jobs@deux.fr"), _norm(3)])
    assert b == {"ajoutees": 2, "deja_connues": 1, "passees_en_lba": 1, "avec_email": 1, "non_ajoutees": 0}
    ents = lire_entreprises(uid)
    assert [e["nom_commercial"] for e in ents] == ["Aussi chez LBA", "Société 2", "Société 3", "Sirene seule"]
    assert [e["source"] for e in ents] == ["lba", "lba", "lba", "sirene"]
    connue = ents[0]
    assert connue["emails_trouves"] == ["rh@aussi.fr"] and connue["emails_lba"] == ["rh@aussi.fr"]
    assert connue["_extra"]["lba"]["candidature_id"] == "partners_1"
    assert ents[1]["mode"] == "alternance" and ents[1]["emails_lba"] == ["jobs@deux.fr"]
    assert ents[2]["emails_trouves"] == [] and ents[2]["_extra"]["siret"] == f"9{3:013d}"
    # Second passage : rien de nouveau
    b = ajouter_entreprises_lba(uid, [_norm(2), _norm(3)])
    assert b["ajoutees"] == 0 and b["deja_connues"] == 2 and b["passees_en_lba"] == 0
    assert cles_connues(uid) >= {"S3", "11111111100011", f"9{2:013d}", "rec2"}


def test_limite_d_entreprises_lba(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    b = ajouter_entreprises_lba(uid, [_norm(i) for i in range(5)], maximum=2)
    assert b["ajoutees"] == 2 and b["non_ajoutees"] == 3


def test_email_lba_pas_ajoute_a_une_entreprise_deja_contactee(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises_lba(uid, [_norm(1)])
    from database.connexion import SessionLocal
    from database.models import Entreprise
    with SessionLocal() as db:
        e = db.query(Entreprise).one()
        e.mail_envoye, e.emails_trouves = True, ["ancien@soc.fr"]
        db.commit()
    ajouter_entreprises_lba(uid, [_norm(1, email="nouveau@soc.fr")])
    e = lire_entreprises(uid)[0]
    assert e["emails_trouves"] == ["ancien@soc.fr"] and e["emails_lba"] == ["nouveau@soc.fr"]


def test_stats_et_affichage_prioritaire(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": f"S{i}", "nom": f"Sirene {i}"} for i in range(3)])
    ajouter_entreprises_lba(uid, [_norm(1, email="rh@un.fr")])
    stats = calculer_stats(uid)
    assert stats["lba"] == 1 and stats["raw"] == 4
    assert stats["prochaines"][0] == {"nom": "Société 1", "ville": "VILLE", "email": "rh@un.fr",
                                      "envoye": False, "lba": True, "email_lba": True}
    assert [p["lba"] for p in stats["prochaines"]] == [True, False, False, False]
    assert client.get("/api/spontanees/stats").json()["prochaines"][0]["lba"] is True
    page = client.get("/").text
    assert 'data-filter="lba"' in page and 'data-sp="lba"' in page


def test_migration_0008(tmp_path):
    chemin = tmp_path / "v7.db"
    cfg = config_alembic(f"sqlite:///{chemin}")
    command.upgrade(cfg, "0007")
    cx = sqlite3.connect(chemin)
    cx.execute("INSERT INTO users (id, email, mot_de_passe_hash) VALUES (1, 'a@test.fr', 'x')")
    cx.execute("INSERT INTO entreprises (user_id, mode, nom_commercial) VALUES (1, 'alternance', 'Ancienne')")
    cx.commit()
    cx.close()
    command.upgrade(cfg, "0008")
    cx = sqlite3.connect(chemin)
    assert cx.execute("SELECT nom_commercial, source FROM entreprises").fetchall() == [("Ancienne", "sirene")]
    cx.close()
    command.downgrade(cfg, "0007")
    cx = sqlite3.connect(chemin)
    colonnes = {r[1] for r in cx.execute("PRAGMA table_info(entreprises)")}
    assert "source" not in colonnes and cx.execute("SELECT COUNT(*) FROM entreprises").fetchone() == (1,)
    cx.close()


# ─── Pipelines ────────────────────────────────────────────────────────────────
def _logs(uid):
    return "\n".join(str(l) for l in main.pipelines.logs(uid))


def test_recherche_verse_les_entreprises_dans_les_spontanees(utilisateur, monkeypatch, pipelines_neufs):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    monkeypatch.setattr(main, "lancer_recherche", lambda *a, **k: [])
    monkeypatch.setattr(main, "rechercher_lba", lambda profil, log=print: {
        "offres": [], "entreprises": [_norm(1), _norm(2, email="rh@deux.fr")], "requetes": 19})
    client.post("/api/recherche")
    attendre(lambda: not main.pipelines.etat("recherche", uid)["en_cours"])
    assert [e["source"] for e in lire_entreprises(uid)] == ["lba", "lba"]
    logs = _logs(uid)
    assert "2 entreprises à fort potentiel ajoutées aux candidatures spontanées" in logs
    assert "dont 1 avec un email fourni par LBA" in logs
    assert "Aucune offre LBA récupérée" in logs                          # LBA a tourné, sans offre


def test_pas_de_aucune_offre_apres_lba_ignoree(utilisateur, monkeypatch, pipelines_neufs):
    """Point 8 : « Aucune offre LBA récupérée » seulement si LBA a tourné."""
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    monkeypatch.setattr(main, "lancer_recherche", lambda *a, max_analyse, **k: [{}] * max_analyse)
    appels = []
    monkeypatch.setattr(main, "rechercher_lba", lambda profil, log=print: appels.append(1))
    client.post("/api/recherche", json={"max_analyses": 3})
    attendre(lambda: not main.pipelines.etat("recherche", uid)["en_cours"])
    logs = _logs(uid)
    assert "LBA ignorée : limite de 3 offres" in logs
    assert "Aucune offre LBA récupérée" not in logs and appels == []
    # LBA ignorée pour une autre raison (clé absente) : pas de message en plus non plus
    monkeypatch.setattr(main, "lancer_recherche", lambda *a, **k: [])
    monkeypatch.setattr(main, "rechercher_lba", lambda profil, log=print: log("⚠️  LBA ignorée : clé"))
    client.post("/api/recherche")
    attendre(lambda: not main.pipelines.etat("recherche", uid)["en_cours"])
    assert "Aucune offre LBA récupérée" not in _logs(uid)


def test_recuperer_lba_d_abord_puis_sirene(utilisateur, monkeypatch, sirene):  # noqa: F811
    import spontanees.fetch_entreprises as fetch
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    options = {}

    def faux(profil, log=print, stop_event=None, **kw):
        options.update(kw)
        return {"offres": [], "entreprises": [_norm(i) for i in range(3)], "requetes": 1}
    monkeypatch.setattr(lba, "rechercher_pour_profil", faux)
    logs = []
    fetch.main(uid, max_entreprises=5, log_fn=logs.append)
    ents = lire_entreprises(uid)
    assert [e["source"] for e in ents] == ["lba"] * 3 + ["sirene"] * 2
    assert options["redecouper_entreprises"] is True and options["objectif_entreprises"] == 5
    assert any("3 nouvelles entreprises à fort potentiel" in l for l in logs)
    # La limite atteinte avec LBA : Sirene n'est pas interrogé
    appels = sirene.appels
    monkeypatch.setattr(lba, "rechercher_pour_profil", lambda profil, log=print, stop_event=None, **kw: {
        "offres": [], "entreprises": [_norm(10 + i) for i in range(4)], "requetes": 1})
    fetch.main(uid, max_entreprises=2, log_fn=logs.append)
    assert sirene.appels == appels and len(lire_entreprises(uid)) == 7
    assert any("Sirene non interrogé" in l for l in logs)
