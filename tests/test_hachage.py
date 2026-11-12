"""Hachage des mots de passe par pwdlib à la place de fastapi-users
(audit phase 12, lot 8, D140) : les hashs déjà en base restent valides."""

import pytest

from auth import securite

# Créés le 12 novembre 2026 avec la version alors installée, juste avant le
# retrait de fastapi-users : PasswordHelper().hash de fastapi-users 15.0.5
# (argon2id, ce que /register a toujours produit), et bcrypt par le hacheur
# que PasswordHelper accepte en vérification (comptes plus anciens).
HASH_ARGON2_FASTAPI_USERS = ("$argon2id$v=19$m=65536,t=3,p=4$PjHuJ0/7s7FH5Wc1S102Uw$"
                             "y2gwZoPgdf+1ebmqXsdSO3K0ba2o9E9Qv3VKUK6I6uk")
HASH_BCRYPT = "$2b$12$TrZQoQCOmJgf4CcD8R/JGe8yA0IEwrEwCDUJxiH1wqGegNVW8pPgO"


@pytest.mark.parametrize("hash_stocke,mot_de_passe", [
    (HASH_ARGON2_FASTAPI_USERS, "ancien-mot-de-passe-1"),
    (HASH_BCRYPT, "ancien-mot-de-passe-2"),
])
def test_hashs_existants_acceptes(hash_stocke, mot_de_passe):
    assert securite.verifier_mot_de_passe(mot_de_passe, hash_stocke) is True
    assert securite.verifier_mot_de_passe(mot_de_passe + "x", hash_stocke) is False
    assert securite.verifier_mot_de_passe("", hash_stocke) is False


def test_nouveaux_hashs_argon2id_memes_parametres():
    h = securite.hacher_mot_de_passe("nouveau-mot-de-passe")
    assert h.startswith("$argon2id$v=19$m=65536,t=3,p=4$")       # mêmes paramètres qu'avec fastapi-users
    assert h != securite.hacher_mot_de_passe("nouveau-mot-de-passe")   # sel aléatoire
    assert securite.verifier_mot_de_passe("nouveau-mot-de-passe", h)


def test_connexion_avec_un_hash_existant(utilisateur):
    """Un compte dont le hash vient de fastapi-users se connecte toujours."""
    from database.connexion import SessionLocal
    from database.models import User
    from tests.conftest import ClientDeMode
    import main
    _, uid = utilisateur("ancien@test.fr")
    db = SessionLocal()
    try:
        db.query(User).filter_by(id=uid).one().mot_de_passe_hash = HASH_ARGON2_FASTAPI_USERS
        db.commit()
    finally:
        db.close()
    c = ClientDeMode(main.app)
    r = c.post("/login", data={"email": "ancien@test.fr", "mot_de_passe": "ancien-mot-de-passe-1"},
               follow_redirects=False)
    assert r.status_code == 303 and c.get("/api/compte").status_code == 200


def test_compatibilite_croisee_avec_fastapi_users_si_installe():
    """Là où fastapi-users est encore installé (venv d'avant D140) : ses
    hashs sont acceptés par pwdlib, et inversement."""
    password = pytest.importorskip("fastapi_users.password")
    ancien = password.PasswordHelper()
    for mdp in ("motdepasse-solide", "été-àçcentué-€"):
        assert securite.verifier_mot_de_passe(mdp, ancien.hash(mdp))
        assert ancien.verify_and_update(mdp, securite.hacher_mot_de_passe(mdp))[0]
