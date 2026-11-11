"""Page Paramètres (phase 10, D122) : mot de passe (ancien obligatoire,
autres sessions déconnectées), email de connexion (mot de passe
obligatoire), compte d'envoi déplacé depuis le Profil."""

import base64
import json

import pytest

from auth.securite import empreinte_session
from database.connexion import SessionLocal
from database.models import User
from tests.conftest import MOT_DE_PASSE, ClientDeMode

NOUVEAU = "nouveau-mot-de-passe-1"


def _connecter(email, mot_de_passe=MOT_DE_PASSE):
    import main
    c = ClientDeMode(main.app)
    r = c.post("/login", data={"email": email, "mot_de_passe": mot_de_passe}, follow_redirects=False)
    return c, r.status_code == 303


def _changer(client, ancien=MOT_DE_PASSE, nouveau=NOUVEAU, confirmation=None):
    return client.post("/api/compte/mot_de_passe", json={"ancien": ancien, "nouveau": nouveau,
                                                          "confirmation": nouveau if confirmation is None else confirmation})


def _hash(uid):
    db = SessionLocal()
    try:
        return db.query(User).filter_by(id=uid).one().mot_de_passe_hash
    finally:
        db.close()


# ─── Mot de passe ─────────────────────────────────────────────────────────────
def test_mot_de_passe_refuse_sans_le_bon_ancien_ni_les_regles(utilisateur):
    client, uid = utilisateur("ada@test.fr")
    avant = _hash(uid)
    for r, attendu in ((_changer(client, ancien="mauvais"), "actuel incorrect"),
                       (_changer(client, nouveau="court"), "trop court"),
                       (_changer(client, confirmation="autre-chose-123"), "confirmation"),
                       (_changer(client, nouveau=MOT_DE_PASSE), "différent")):
        assert r.status_code == 400 and attendu in r.json()["erreur"], r.json()
    assert _hash(uid) == avant
    assert "motdepasse" not in json.dumps(_changer(client, ancien="mauvais").json())   # rien de renvoyé


def test_changement_deconnecte_les_autres_sessions(utilisateur):
    client, uid = utilisateur("ada@test.fr")
    autre, ok = _connecter("ada@test.fr")
    assert ok and autre.get("/api/compte").status_code == 200
    assert _changer(client).status_code == 200
    assert client.get("/api/compte").status_code == 200                                  # celle-ci reste ouverte
    assert autre.get("/api/compte").status_code == 401                                   # l'autre est fermée
    assert autre.get("/alternance", follow_redirects=False).headers["location"] == "/login"
    assert not _connecter("ada@test.fr")[1]                                              # ancien refusé
    assert _connecter("ada@test.fr", NOUVEAU)[1]


def test_session_sans_empreinte_fermee(utilisateur):
    """Cookie d'avant D122 (seulement user_id) : session fermée, reconnexion demandée."""
    import itsdangerous
    from shared.config import secret_key
    client, uid = utilisateur("ada@test.fr")
    signeur = itsdangerous.TimestampSigner(secret_key())
    ancien = signeur.sign(base64.b64encode(json.dumps({"user_id": uid}).encode())).decode()
    client.cookies.clear()
    client.cookies.set("session", ancien)
    assert client.get("/api/compte").status_code == 401
    bonne = signeur.sign(base64.b64encode(json.dumps(
        {"user_id": uid, "empreinte": empreinte_session(_hash(uid))}).encode())).decode()
    client.cookies.clear()
    client.cookies.set("session", bonne)
    assert client.get("/api/compte").status_code == 200


# ─── Email de connexion ───────────────────────────────────────────────────────
def test_changer_email(utilisateur):
    client, uid = utilisateur("ada@test.fr", prenom="Ada")
    utilisateur("bob@test.fr")
    def changer(email, mdp=MOT_DE_PASSE):
        return client.post("/api/compte/email", json={"email": email, "mot_de_passe": mdp})
    for r, attendu in ((changer("ada2@test.fr", "mauvais"), "Mot de passe incorrect"),
                       (changer("pas-un-email"), "invalide"),
                       (changer("BOB@test.fr"), "existe déjà"),
                       (changer("ada@test.fr"), "déjà ton email")):
        assert r.status_code == 400 and attendu in r.json()["erreur"]
    r = changer("  Ada.Nouvelle@Test.fr ")
    assert r.status_code == 200 and r.json()["email"] == "ada.nouvelle@test.fr"
    assert client.get("/api/compte").json()["email"] == "ada.nouvelle@test.fr"
    assert client.get("/api/profil").json()["email"] == "ada@test.fr"       # email de contact inchangé
    assert not _connecter("ada@test.fr")[1] and _connecter("ada.nouvelle@test.fr")[1]


def test_routes_du_compte_protegees_et_sans_mode():
    import main
    anonyme = ClientDeMode(main.app)
    anonyme.mode = None
    for url in ("/api/compte/mot_de_passe", "/api/compte/email"):
        assert anonyme.post(url, json={}).status_code == 401
    assert anonyme.get("/api/compte").status_code == 401


def test_compte_sans_mode(utilisateur):
    client, _ = utilisateur("ada@test.fr")
    client.mode = None
    assert client.get("/api/compte").status_code == 200


# ─── Page ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("mode", ["alternance", "job", "stage"])
def test_page_parametres_dans_chaque_mode(utilisateur, mode):
    client, _ = utilisateur("ada@test.fr")
    page = client.get(f"/{mode}").text
    assert 'data-page="parametres"' in page and 'data-page-content="parametres"' in page
    debut = page.index('data-page-content="parametres"')
    parametres = page[debut:page.index("</section>", debut)]
    for attendu in ('data-compte-form="email"', 'data-compte-form="mot_de_passe"', "data-ce-carte",
                    'data-ce="mot_de_passe"'):
        assert attendu in parametres, attendu
    # Compte d'envoi : plus dans le Profil
    debut = page.index('data-page-content="profil"')
    assert "data-ce-carte" not in page[debut:page.index("</section>", debut)]
