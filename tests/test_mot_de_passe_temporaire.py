"""Mot de passe oublié, version locale (phase 10, D123) : script de
l'administratrice, mot de passe temporaire affiché une fois, changement
obligatoire à la connexion suivante, rien en clair ailleurs."""

import logging
import sqlite3

from alembic import command

from database.connexion import SessionLocal
from database.models import User
from database.schema import config_alembic
from scripts import reinitialiser_mot_de_passe as script
from tests.conftest import MOT_DE_PASSE, ClientDeMode

NOUVEAU = "nouveau-mot-de-passe-1"


def _lancer(*argv, reponse="o"):
    sorties = []
    code = script.main(list(argv), entree=lambda _: reponse, afficher=sorties.append)
    return code, sorties


def _temporaire(sorties):
    return sorties[1].strip()


def _client():
    import main
    return ClientDeMode(main.app)


def _drapeau(email):
    db = SessionLocal()
    try:
        return db.query(User).filter_by(email=email).one().mot_de_passe_temporaire
    finally:
        db.close()


def test_script_affiche_une_seule_fois_et_rien_dans_les_journaux(utilisateur, caplog):
    utilisateur("ada@test.fr")
    with caplog.at_level(logging.DEBUG):
        code, sorties = _lancer("ADA@test.fr ", "--oui")
    assert code == 0
    temporaire = _temporaire(sorties)
    assert len(temporaire) == 19 and temporaire.count("-") == 3
    assert not set(temporaire.replace("-", "")) & set("0O1lI")
    assert sum(temporaire in s for s in sorties) == 1                     # affiché une fois
    assert temporaire not in caplog.text                                  # aucun journal
    assert _drapeau("ada@test.fr") is True
    db = SessionLocal()
    try:
        assert temporaire not in db.query(User).filter_by(email="ada@test.fr").one().mot_de_passe_hash
    finally:
        db.close()


def test_script_compte_inconnu_ou_abandon(utilisateur):
    utilisateur("ada@test.fr")
    assert _lancer("inconnu@test.fr", "--oui")[0] == 1
    code, sorties = _lancer("ada@test.fr", reponse="n")
    assert code == 1 and "Abandon" in sorties[0] and _drapeau("ada@test.fr") is False
    assert _lancer("ada@test.fr", reponse="o")[0] == 0 and _drapeau("ada@test.fr") is True


def test_connexion_avec_le_temporaire_puis_changement_obligatoire(utilisateur):
    session, _ = utilisateur("ada@test.fr")
    temporaire = _temporaire(_lancer("ada@test.fr", "--oui")[1])
    assert session.get("/api/profil").status_code == 401                 # sessions ouvertes fermées
    c = _client()
    assert c.post("/login", data={"email": "ada@test.fr", "mot_de_passe": MOT_DE_PASSE},
                  follow_redirects=False).status_code == 200              # ancien refusé
    r = c.post("/login", data={"email": "ada@test.fr", "mot_de_passe": temporaire}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/mot-de-passe-temporaire"
    # Tout le reste est bloqué
    assert c.get("/api/profil").status_code == 403
    assert c.post("/api/compte/mot_de_passe", json={}).status_code == 403
    assert c.get("/alternance", follow_redirects=False).headers["location"] == "/mot-de-passe-temporaire"
    assert "Choisis ton mot de passe" in c.get("/mot-de-passe-temporaire").text
    # Refus : mauvais temporaire, nouveau trop court, confirmation différente
    for donnees, attendu in (({"ancien": "faux", "nouveau": NOUVEAU, "confirmation": NOUVEAU}, "temporaire incorrect"),
                             ({"ancien": temporaire, "nouveau": "court", "confirmation": "court"}, "trop court"),
                             ({"ancien": temporaire, "nouveau": NOUVEAU, "confirmation": "autre-123456"}, "confirmation")):
        r = c.post("/mot-de-passe-temporaire", data=donnees, follow_redirects=False)
        assert r.status_code == 400 and attendu in r.text
    assert _drapeau("ada@test.fr") is True
    r = c.post("/mot-de-passe-temporaire", data={"ancien": temporaire, "nouveau": NOUVEAU, "confirmation": NOUVEAU},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert _drapeau("ada@test.fr") is False
    assert c.get("/api/profil").status_code == 200                       # session gardée
    assert c.get("/mot-de-passe-temporaire", follow_redirects=False).headers["location"] == "/"
    autre = _client()
    assert autre.post("/login", data={"email": "ada@test.fr", "mot_de_passe": temporaire},
                      follow_redirects=False).status_code == 200          # temporaire plus valable
    assert autre.post("/login", data={"email": "ada@test.fr", "mot_de_passe": NOUVEAU},
                      follow_redirects=False).headers["location"] == "/"


def test_page_temporaire_sans_session():
    assert _client().get("/mot-de-passe-temporaire", follow_redirects=False).headers["location"] == "/login"


def test_lien_mot_de_passe_oublie():
    c = _client()
    assert 'href="/mot-de-passe-oublie"' in c.get("/login").text
    page = c.get("/mot-de-passe-oublie").text
    assert "Contacte l'administratrice" in page and "mot de passe temporaire" in page


def test_migration_0015(tmp_path):
    chemin = tmp_path / "v14.db"
    cfg = config_alembic(f"sqlite:///{chemin}")
    command.upgrade(cfg, "0014")
    cx = sqlite3.connect(chemin)
    cx.execute("INSERT INTO users (id, email, mot_de_passe_hash) VALUES (1, 'a@test.fr', 'x')")
    cx.execute("INSERT INTO profils (user_id, mode, prenom) VALUES (1, 'alternance', 'Ada')")
    cx.execute("INSERT INTO candidatures (user_id, mode, ref_offre, titre) VALUES (1, 'alternance', 'r1', 'Dev')")
    cx.commit()
    cx.close()

    def enfants():
        cx = sqlite3.connect(chemin)
        try:
            return (cx.execute("SELECT prenom FROM profils").fetchall(),
                    cx.execute("SELECT ref_offre FROM candidatures").fetchall())
        finally:
            cx.close()
    command.upgrade(cfg, "0015")
    cx = sqlite3.connect(chemin)
    assert cx.execute("SELECT mot_de_passe_temporaire FROM users").fetchall() == [(0,)]
    cx.close()
    # La table users n'est pas recréée : rien d'effacé en cascade
    assert enfants() == ([("Ada",)], [("r1",)])
    command.downgrade(cfg, "0014")
    cx = sqlite3.connect(chemin)
    assert "mot_de_passe_temporaire" not in {r[1] for r in cx.execute("PRAGMA table_info(users)")}
    cx.close()
    assert enfants() == ([("Ada",)], [("r1",)])
