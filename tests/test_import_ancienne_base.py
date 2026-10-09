"""Script d'import de l'ancienne base vers une base neuve (scripts/importer_ancienne_base.py)."""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from tests.conftest import ClientDeMode
from fastapi_users.password import PasswordHelper

import main
from database.connexion import SessionLocal
from database.models import Candidature, Entreprise, Profil, User
from scripts import importer_ancienne_base as imp
from shared import config

DDL = Path(__file__).parent / "donnees" / "ancien_schema.sql"
VRAIE_BASE = config.BASE_DIR / "data" / "chasseur.db"
MOTS_DE_PASSE = {1: "ancien-mdp-un", 2: "ancien-mdp-deux", 3: "ancien-mdp-trois", 4: "ancien-mdp-quatre"}


def _pj(nom, fichier):
    return {"nom": nom, "fichier": fichier}


@pytest.fixture
def ancienne_base(tmp_path):
    """Fausse ancienne base au schéma réel exact, données factices."""
    chemin = tmp_path / "ancienne.db"
    cx = sqlite3.connect(chemin)
    cx.executescript(DDL.read_text(encoding="utf-8"))
    aide = PasswordHelper()
    for uid, mdp in MOTS_DE_PASSE.items():
        cx.execute("INSERT INTO users (id, email, mot_de_passe_hash, cree_le) VALUES (?, ?, ?, ?)",
                   (uid, f"user{uid}@test.fr", aide.hash(mdp), "2026-06-17 17:48:54.794014"))
    profils = [
        (1, "alternance", "Ada", [_pj("CV", "data/uploads/user_1/cv.pdf"),
                                  _pj("Reco", "data/uploads/user_1/reco_sans_ext"),
                                  _pj("Perdu", "data/uploads/user_1/perdu.pdf")]),
        (1, "job", "Ada", [_pj("CV", "data/uploads/user_1/cv.pdf")]),
        (2, "alternance", "Exclu", [_pj("Lettre", "data/uploads/user_2/lettre.pdf")]),
        (3, "alternance", "Grace", []),
        (4, "alternance", "Hedy", []),
    ]
    for uid, mode, prenom, pieces in profils:
        cx.execute("INSERT INTO profils (user_id, mode, prenom, nom, competences, recherche, "
                   "pieces_jointes, niveau_vise) VALUES (?, ?, ?, 'Test', ?, ?, ?, 'Bac+2')",
                   (uid, mode, prenom, json.dumps(["Python"]),
                    json.dumps({"localisation": "Paris"}), json.dumps(pieces)))
    cx.execute("INSERT INTO candidatures (user_id, ref_offre, titre) VALUES (1, 'r1', 'Offre')")
    cx.execute("INSERT INTO entreprises (user_id, nom_commercial) VALUES (1, 'ACME')")
    cx.commit()
    cx.close()

    uploads = config.UPLOADS_DIR   # tmp_path/uploads (conftest)
    (uploads / "user_1").mkdir(parents=True)
    (uploads / "user_1" / "cv.pdf").write_bytes(b"%PDF-cv")
    (uploads / "user_1" / "reco_sans_ext").write_bytes(b"%PDF-reco")
    return chemin


def _cible_de_test() -> Path:
    """Base des tests (migrée, vide) : celle que l'app utilise."""
    return imp.fichier_sqlite(config.DATABASE_URL)


def _empreinte(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def test_ddl_de_reference_identique_a_la_vraie_base():
    """Garde-fou : le DDL figé dans tests/donnees reste celui de data/chasseur.db (lecture seule)."""
    if not VRAIE_BASE.exists():
        pytest.skip("data/chasseur.db absente")
    cx = sqlite3.connect(f"file:{VRAIE_BASE}?mode=ro", uri=True)
    reel = [r[0] for r in cx.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY rowid")]
    cx.close()
    fige = DDL.read_text(encoding="utf-8")
    assert all(instruction in fige for instruction in reel)


def test_import_users_et_profils(ancienne_base):
    rapport = imp.importer(str(ancienne_base), str(_cible_de_test()), sortie=lambda *_: None)

    db = SessionLocal()
    try:
        users = {u.id: u for u in db.query(User).all()}
        assert sorted(users) == [1, 3, 4]   # user 2 exclu, ids conservés
        source = sqlite3.connect(ancienne_base)
        for uid, (h,) in ((u, source.execute("SELECT mot_de_passe_hash FROM users WHERE id=?", (u,)).fetchone())
                          for u in users):
            assert users[uid].mot_de_passe_hash == h
        assert users[1].cree_le is not None

        profils = {(p.user_id, p.mode): p for p in db.query(Profil).all()}
        assert sorted(profils) == [(1, "alternance"), (1, "job"), (3, "alternance"), (4, "alternance")]
        p = profils[(1, "alternance")]
        assert p.competences == ["Python"] and p.recherche == {"localisation": "Paris"}
        assert p.niveau_vise == "Bac+2"
        assert [pj["fichier"] for pj in p.pieces_jointes] == [
            "user_1/cv.pdf", "user_1/reco_sans_ext", "user_1/perdu.pdf"]
        # Ni candidatures ni entreprises
        assert db.query(Candidature).count() == 0 and db.query(Entreprise).count() == 0
    finally:
        db.close()

    assert [c[2] for c in rapport["trouvees"]] == ["CV", "Reco", "CV"]
    assert [c[2] for c in rapport["manquantes"]] == ["Perdu"]
    assert [c[2] for c in rapport["sans_extension"]] == ["Reco"]
    # Fichiers non modifiés
    assert (config.UPLOADS_DIR / "user_1" / "reco_sans_ext").read_bytes() == b"%PDF-reco"


def test_connexion_avec_ancien_mot_de_passe(ancienne_base):
    imp.importer(str(ancienne_base), str(_cible_de_test()), sortie=lambda *_: None)
    with ClientDeMode(main.app) as c:
        r = c.post("/login", data={"email": "user3@test.fr", "mot_de_passe": MOTS_DE_PASSE[3]},
                   follow_redirects=False)
        assert r.status_code == 303
        assert c.get("/api/profil").json()["prenom"] == "Grace"
    with ClientDeMode(main.app) as c:
        r = c.post("/login", data={"email": "user2@test.fr", "mot_de_passe": MOTS_DE_PASSE[2]},
                   follow_redirects=False)
        assert r.status_code == 200   # user 2 non importé : connexion refusée
        assert c.get("/api/profil").status_code == 401


def test_piece_jointe_importee_servie_par_l_app(ancienne_base):
    imp.importer(str(ancienne_base), str(_cible_de_test()), sortie=lambda *_: None)
    with ClientDeMode(main.app) as c:
        c.post("/login", data={"email": "user1@test.fr", "mot_de_passe": MOTS_DE_PASSE[1]})
        r = c.get("/api/profil/piece", params={"nom": "CV"})
        assert r.status_code == 200 and r.content == b"%PDF-cv"
        assert c.get("/api/profil/piece", params={"nom": "Perdu"}).status_code == 404


def test_refus_si_cible_non_vide(ancienne_base):
    cible = _cible_de_test()
    imp.importer(str(ancienne_base), str(cible), sortie=lambda *_: None)
    avant = _empreinte(cible)
    with pytest.raises(imp.Refus, match="déjà"):
        imp.importer(str(ancienne_base), str(cible), sortie=lambda *_: None)
    assert _empreinte(cible) == avant
    assert imp.main(["--source", str(ancienne_base), "--cible", str(cible)]) == 1


def test_refus_si_source_egale_cible(ancienne_base, tmp_path):
    avant = _empreinte(ancienne_base)
    with pytest.raises(imp.Refus, match="même fichier"):
        imp.importer(str(ancienne_base), str(ancienne_base), sortie=lambda *_: None)
    lien = tmp_path / "lien.db"
    lien.symlink_to(ancienne_base)
    with pytest.raises(imp.Refus, match="même fichier"):
        imp.importer(str(ancienne_base), f"sqlite:///{lien}", sortie=lambda *_: None)
    assert _empreinte(ancienne_base) == avant


def test_dry_run_n_ecrit_rien(ancienne_base, tmp_path):
    source_avant = _empreinte(ancienne_base)

    # Cible absente : pas créée
    absente = tmp_path / "neuve.db"
    lignes = []
    rapport = imp.importer(str(ancienne_base), str(absente), dry_run=True, sortie=lignes.append)
    assert not absente.exists()
    assert [u[0] for u in rapport["users"]] == [1, 3, 4] and len(rapport["profils"]) == 4
    assert "rien n'a été écrit" in lignes[0]

    # Cible existante et vide : inchangée
    cible = _cible_de_test()
    avant = _empreinte(cible)
    assert imp.main(["--source", str(ancienne_base), "--cible", str(cible), "--dry-run"]) == 0
    assert _empreinte(cible) == avant
    db = SessionLocal()
    try:
        assert db.query(User).count() == 0
    finally:
        db.close()
    assert _empreinte(ancienne_base) == source_avant


def test_import_dans_une_cible_neuve_la_migre(ancienne_base, tmp_path):
    neuve = tmp_path / "neuve.db"
    imp.importer(str(ancienne_base), str(neuve), sortie=lambda *_: None)
    cx = sqlite3.connect(neuve)
    assert cx.execute("SELECT version_num FROM alembic_version").fetchone() is not None
    assert [r[0] for r in cx.execute("SELECT id FROM users ORDER BY id")] == [1, 3, 4]
    cx.close()
