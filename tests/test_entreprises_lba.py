"""Entreprises à fort potentiel de La Bonne Alternance dans les
candidatures spontanées (phase 5c) : dédoublonnage par SIRET avec Sirene,
liste des sources sans priorité, répartition par source, migrations 0008
et 0009, recherche d'offres qui n'en ajoute pas, étape « Récupérer »
(limite partagée entre LBA et Sirene)."""

import sqlite3

from alembic import command

import france_travail.scraper_lba as lba
import main
from database.entreprises_db import (ajouter_entreprises, ajouter_entreprises_lba, calculer_stats,
                                     cles_connues, lire_entreprises, noter_source)
from database.schema import config_alembic
from tests.faux_lba import entreprise
from tests.test_limites import sirene  # noqa: F401  (fixture)
from tests.test_pipelines import attendre


# ─── Entreprises dans les candidatures spontanées ─────────────────────────────
def _norm(n, **kw):
    return lba.normaliser_entreprise(entreprise(n, **kw))


def test_entreprises_lba_dedoublonnees_par_siret_sans_priorite(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": "S3", "nom": "Sirene seule"},
                              {"siret": "11111111100011", "nom": "Aussi chez LBA"}])
    brut = entreprise(1, siret="11111111100011", email="rh@aussi.fr")
    brut["apply"]["recipient_id"] = "partners_1"
    b = ajouter_entreprises_lba(uid, [lba.normaliser_entreprise(brut), _norm(2, email="jobs@deux.fr"), _norm(3)])
    assert b == {"ajoutees": 2, "deja_connues": 1, "deux_sources": 1, "avec_email": 1, "non_ajoutees": 0}
    ents = lire_entreprises(uid)
    # Ordre d'insertion, aucune source en premier (D44)
    assert [e["nom_commercial"] for e in ents] == ["Sirene seule", "Aussi chez LBA", "Société 2", "Société 3"]
    assert [e["sources"] for e in ents] == [["sirene"], ["sirene", "lba"], ["lba"], ["lba"]]
    connue = ents[1]
    assert connue["emails_trouves"] == ["rh@aussi.fr"] and connue["emails_lba"] == ["rh@aussi.fr"]
    assert connue["_extra"]["lba"]["candidature_id"] == "partners_1"
    assert ents[2]["mode"] == "alternance" and ents[2]["emails_lba"] == ["jobs@deux.fr"]
    assert ents[3]["emails_trouves"] == [] and ents[3]["_extra"]["siret"] == f"9{3:013d}"
    # Second passage : rien de nouveau, aucune source en double
    b = ajouter_entreprises_lba(uid, [_norm(2), _norm(3), lba.normaliser_entreprise(brut)])
    assert b["ajoutees"] == 0 and b["deja_connues"] == 3 and b["deux_sources"] == 0
    assert lire_entreprises(uid)[1]["sources"] == ["sirene", "lba"]
    assert cles_connues(uid) >= {"S3", "11111111100011", f"9{2:013d}", "rec2"}


def test_sirene_note_sa_source_sur_une_entreprise_lba(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises_lba(uid, [_norm(1, siret="22222222200022"), _norm(2)])
    assert noter_source(uid, ["22222222200022", "inconnu"], "sirene") == 1
    assert noter_source(uid, ["22222222200022"], "sirene") == 0
    assert [e["sources"] for e in lire_entreprises(uid)] == [["lba", "sirene"], ["lba"]]


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


def test_stats_par_source_et_affichage(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": f"S{i}", "nom": f"Sirene {i}"} for i in range(3)]
                        + [{"siret": "33333333300033", "nom": "Les deux"}])
    ajouter_entreprises_lba(uid, [_norm(1, email="rh@un.fr"), _norm(2, siret="33333333300033")])
    from database.connexion import SessionLocal
    from database.models import Entreprise
    with SessionLocal() as db:
        lignes = db.query(Entreprise).order_by(Entreprise.id).all()
        lignes[0].emails_trouves, lignes[0].mail_envoye, lignes[0].statut_suivi = ["a@s0.fr"], True, "entretien"
        lignes[1].emails_trouves, lignes[1].mail_envoye, lignes[1].statut_suivi = ["a@s1.fr"], True, "refus"
        lignes[3].emails_trouves, lignes[3].mail_envoye, lignes[3].statut_suivi = ["a@d.fr"], True, "reponse"
        lignes[4].mail_envoye = True                                    # Société 1 (LBA), sans réponse
        db.commit()
    stats = calculer_stats(uid)
    assert stats["raw"] == 5
    assert stats["par_source"] == {
        "sirene":   {"entreprises": 4, "avec_email": 3, "envoyes": 3, "reponses": 3, "entretiens": 1},
        "lba":      {"entreprises": 2, "avec_email": 2, "envoyes": 2, "reponses": 1, "entretiens": 0},
        "les_deux": {"entreprises": 1, "avec_email": 1, "envoyes": 1, "reponses": 1, "entretiens": 0},
    }
    # Prochaines entreprises dans l'ordre d'insertion, sources affichées
    assert [p["nom"] for p in stats["prochaines"]] == ["Sirene 2"]
    reponse = client.get("/api/spontanees/stats").json()
    assert reponse["par_source"]["lba"]["entreprises"] == 2
    assert {tuple(d["sources"]) for d in reponse["dernieres"]} == {("sirene",), ("sirene", "lba"), ("lba",)}
    page = client.get("/").text
    assert 'data-filter="lba"' in page and 'data-filter="sirene"' in page and "data-par-source" in page


def test_migration_0009_sources_en_liste(tmp_path):
    chemin = tmp_path / "v8.db"
    cfg = config_alembic(f"sqlite:///{chemin}")
    command.upgrade(cfg, "0008")
    cx = sqlite3.connect(chemin)
    cx.execute("INSERT INTO users (id, email, mot_de_passe_hash) VALUES (1, 'a@test.fr', 'x')")
    cx.execute("INSERT INTO entreprises (user_id, mode, nom_commercial) VALUES (1, 'alternance', 'Sirene')")
    cx.execute("INSERT INTO entreprises (user_id, mode, nom_commercial, source) VALUES (1, 'alternance', 'LBA', 'lba')")
    cx.commit()
    cx.close()
    command.upgrade(cfg, "0009")
    cx = sqlite3.connect(chemin)
    assert cx.execute("SELECT nom_commercial, sources FROM entreprises ORDER BY id").fetchall() == [
        ("Sirene", '["sirene"]'), ("LBA", '["lba"]')]
    cx.execute("UPDATE entreprises SET sources = '[\"sirene\", \"lba\"]' WHERE nom_commercial = 'Sirene'")
    cx.commit()
    cx.close()
    command.downgrade(cfg, "0008")
    cx = sqlite3.connect(chemin)
    assert cx.execute("SELECT nom_commercial, source FROM entreprises ORDER BY id").fetchall() == [
        ("Sirene", "lba"), ("LBA", "lba")]
    cx.close()


# ─── Pipelines ────────────────────────────────────────────────────────────────
def _logs(uid):
    return "\n".join(str(l) for l in main.pipelines.logs(uid))


def test_recherche_d_offres_n_ajoute_aucune_entreprise(utilisateur, monkeypatch, pipelines_neufs):
    """D46 : seule l'étape « Récupérer » ajoute des entreprises."""
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    monkeypatch.setattr(main, "lancer_recherche", lambda *a, **k: [])
    monkeypatch.setattr(main, "rechercher_lba", lambda profil, log=print: {
        "offres": [], "entreprises": [_norm(1)], "requetes": 19})
    client.post("/api/recherche")
    attendre(lambda: not main.pipelines.etat("recherche", uid)["en_cours"])
    assert lire_entreprises(uid) == []
    assert "Aucune offre LBA récupérée" in _logs(uid)                     # LBA a tourné, sans offre


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


def test_recuperer_partage_la_limite_entre_lba_et_sirene(utilisateur, monkeypatch, sirene):  # noqa: F811
    """D44 : aucune source prioritaire ; LBA a droit à la moitié de la
    limite, Sirene au reste. Une entreprise trouvée par les deux garde les
    deux sources. Durée et requêtes de LBA dans les logs."""
    import spontanees.fetch_entreprises as fetch
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    options = {}
    # Sirene simulé renvoie les SIRET 00000000000000, 00000000000001...
    lba_ents = [_norm(1, siret="00000000000001")] + [_norm(10 + i) for i in range(3)]

    def faux(profil, log=print, stop_event=None, **kw):
        options.update(kw)
        return {"offres": [], "entreprises": lba_ents, "requetes": 42, "duree_s": 75.0}
    monkeypatch.setattr(lba, "rechercher_pour_profil", faux)
    logs = []
    fetch.main(uid, max_entreprises=5, log_fn=logs.append)
    assert options["redecouper_entreprises"] is True and options["objectif_entreprises"] == 3
    ents = lire_entreprises(uid)
    assert len(ents) == 5
    assert sum(e["sources"] == ["lba"] for e in ents) == 2
    assert next(e for e in ents if e["_extra"]["siret"] == "00000000000001")["sources"] == ["lba", "sirene"]
    assert sum(e["sources"] == ["sirene"] for e in ents) == 2
    texte = "\n".join(logs)
    assert "La Bonne Alternance terminée : 42 requêtes en 1 min 15 s" in texte
    assert "rayon minimal 1 km, au plus 300 requêtes" in texte
    assert "1 laissées pour le prochain lancement" in texte
    # Limite atteinte par LBA seule (limite de 1, part LBA 1) : Sirene n'est pas interrogé
    appels = sirene.appels
    lba_ents[:] = [_norm(20)]
    fetch.main(uid, max_entreprises=1, log_fn=logs.append)
    assert sirene.appels == appels and any("Sirene non interrogé" in l for l in logs)
