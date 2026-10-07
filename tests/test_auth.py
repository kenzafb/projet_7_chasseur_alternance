"""Inscription sur invitation, connexion, déconnexion, démarrage sans SECRET_KEY."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from database.connexion import SessionLocal
from database.models import User
from tests.conftest import CODE, MOT_DE_PASSE

RACINE = Path(__file__).resolve().parent.parent


def _nb_users():
    db = SessionLocal()
    try:
        return db.query(User).count()
    finally:
        db.close()


def _inscription(client, **champs):
    data = {"email": "nouveau@test.fr", "mot_de_passe": MOT_DE_PASSE, **champs}
    return client.post("/register", data=data, follow_redirects=False)


# ─── Inscription ──────────────────────────────────────────────────────────────
def test_inscription_desactivee_sans_code_invitation(client, monkeypatch):
    monkeypatch.delenv("CODE_INVITATION", raising=False)
    page = client.get("/register")
    assert "inscriptions sont fermées" in page.text
    assert 'name="mot_de_passe"' not in page.text
    r = _inscription(client, code_invitation="nimporte")
    assert r.status_code == 403
    assert _nb_users() == 0


def test_inscription_desactivee_si_code_vide(client, monkeypatch):
    monkeypatch.setenv("CODE_INVITATION", "   ")
    assert _inscription(client, code_invitation="").status_code == 403
    assert _nb_users() == 0


def test_inscription_refusee_sans_code(client, code_invitation):
    r = _inscription(client)
    assert r.status_code == 403
    assert "invitation invalide" in r.text
    assert _nb_users() == 0


def test_inscription_refusee_mauvais_code(client, code_invitation):
    r = _inscription(client, code_invitation="mauvais-code")
    assert r.status_code == 403
    assert _nb_users() == 0


def test_inscription_refusee_mot_de_passe_court(client, code_invitation):
    r = _inscription(client, code_invitation=CODE, mot_de_passe="123456789")
    assert r.status_code == 400
    assert "10 caractères" in r.text
    assert _nb_users() == 0


def test_inscription_acceptee_bon_code(client, code_invitation):
    r = _inscription(client, code_invitation=CODE, prenom="Ada")
    assert r.status_code == 303
    assert _nb_users() == 1
    # Connecté directement, avec son profil créé
    profil = client.get("/api/profil").json()
    assert profil["prenom"] == "Ada"
    assert profil["email"] == "nouveau@test.fr"


def test_inscription_email_deja_pris(client, code_invitation):
    _inscription(client, code_invitation=CODE)
    client.cookies.clear()
    assert _inscription(client, code_invitation=CODE).status_code == 400
    assert _nb_users() == 1


# ─── Connexion / déconnexion ──────────────────────────────────────────────────
def test_connexion_puis_deconnexion(client, utilisateur):
    utilisateur("ada@test.fr")
    assert client.get("/api/profil").status_code == 401

    r = client.post("/login", data={"email": "ada@test.fr", "mot_de_passe": "mauvais"},
                    follow_redirects=False)
    assert r.status_code == 200 and "incorrect" in r.text
    assert client.get("/api/profil").status_code == 401

    r = client.post("/login", data={"email": "ADA@test.fr ", "mot_de_passe": MOT_DE_PASSE},
                    follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/api/profil").status_code == 200
    assert client.get("/", follow_redirects=False).status_code == 200

    r = client.get("/logout", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client.get("/api/profil").status_code == 401


def test_cookie_session(client, utilisateur):
    utilisateur("ada@test.fr")
    r = client.post("/login", data={"email": "ada@test.fr", "mot_de_passe": MOT_DE_PASSE},
                    follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "secure" not in cookie   # COOKIE_SECURE=false en test


# ─── SECRET_KEY ───────────────────────────────────────────────────────────────
def _demarrer(secret_key):
    """Importe main dans un processus neuf (sans le vrai .env), renvoie le résultat."""
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if secret_key is not None:
        env["SECRET_KEY"] = secret_key
    return subprocess.run([sys.executable, "-c", "import main"], cwd=RACINE, env=env,
                          capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("secret_key", [None, "", "trop-courte-31-caracteres-xxxxx"])
def test_demarrage_refuse_sans_secret_key_valide(secret_key):
    r = _demarrer(secret_key)
    assert r.returncode != 0
    assert "SECRET_KEY absente ou trop courte" in r.stderr


def test_demarrage_accepte_secret_key_valide():
    r = _demarrer("k" * 32)
    assert r.returncode == 0, r.stderr
