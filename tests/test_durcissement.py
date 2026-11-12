"""Durcissement (audit phase 12, lot 3, D134) : requêtes d'une autre
origine refusées, déconnexion en POST, essais de connexion limités,
téléversement borné."""

import pytest

from auth import securite
from tests.conftest import MOT_DE_PASSE, ClientDeMode
import routes.profil as routes_profil

AUTRE = {"origin": "http://localhost:3000"}
MEME = {"origin": "http://testserver"}


def _client():
    import main
    return ClientDeMode(main.app)


# ─── Origine ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("entetes,attendu", [
    (AUTRE, 403), ({"origin": "null"}, 403), ({"referer": "http://localhost:3000/page"}, 403),
    ({"origin": "http://testserver.attaquant.fr"}, 403),
    (MEME, 200), ({"referer": "http://testserver/alternance"}, 200), ({}, 200),
])
def test_origine_des_requetes_non_sures(utilisateur, entetes, attendu):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    r = client.post("/api/profil", json={"prenom": "Pirate"}, headers=entetes)
    assert r.status_code == attendu
    if attendu == 403:
        assert "autre page" in r.json()["erreur"]
        assert client.get("/api/profil").json()["prenom"] == "Alice"


def test_televersement_et_formulaires_d_une_autre_origine(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    r = client.post("/api/profil/upload", data={"nom": "CV"},
                    files={"fichier": ("cv.pdf", b"%PDF-1.4", "application/pdf")}, headers=AUTRE)
    assert r.status_code == 403 and client.get("/api/profil").json()["pieces_jointes"] == []
    assert client.post("/logout", headers=AUTRE, follow_redirects=False).status_code == 403
    assert client.get("/api/profil").status_code == 200                     # toujours connecté
    r = _client().post("/login", data={"email": "a@test.fr", "mot_de_passe": MOT_DE_PASSE}, headers=AUTRE)
    assert r.status_code == 403 and "autre page" in r.text
    assert client.get("/api/profil", headers=AUTRE).status_code == 200      # lecture : permise


# ─── Déconnexion ──────────────────────────────────────────────────────────────
def test_deconnexion_en_post_seulement(utilisateur):
    client, _ = utilisateur("a@test.fr")
    assert client.get("/logout", follow_redirects=False).status_code == 405
    assert client.get("/api/profil").status_code == 200
    r = client.post("/logout", headers=MEME, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client.get("/api/profil").status_code == 401


@pytest.mark.parametrize("chemin", ["/alternance", "/job", "/stage", "/"])
def test_bouton_de_deconnexion_en_formulaire_post(utilisateur, chemin):
    client, _ = utilisateur("a@test.fr")
    page = client.get(chemin).text
    assert '<form method="post" action="/logout"' in page or 'method="post" action="/logout"' in page
    assert 'href="/logout"' not in page


# ─── Connexion ────────────────────────────────────────────────────────────────
def _connexion(client, mdp, email="a@test.fr"):
    return client.post("/login", data={"email": email, "mot_de_passe": mdp}, follow_redirects=False)


def test_essais_limites_puis_debloques(utilisateur, monkeypatch):
    utilisateur("a@test.fr")
    horloge = [1000.0]
    monkeypatch.setattr(securite.time, "monotonic", lambda: horloge[0])
    c = _client()
    for _ in range(securite.ESSAIS_MAX):
        assert _connexion(c, "mauvais").status_code == 200
    r = _connexion(c, MOT_DE_PASSE)                        # bon mot de passe, mais bloqué
    assert r.status_code == 429 and "essais : réessaie dans 15 min" in r.text
    assert _connexion(c, MOT_DE_PASSE, email="autre@test.fr").status_code == 200   # autre email : compteur à part
    horloge[0] += securite.FENETRE_S
    assert _connexion(c, MOT_DE_PASSE).status_code == 303
    # Réussite : compteur remis à zéro
    for _ in range(securite.ESSAIS_MAX - 1):
        _connexion(_client(), "mauvais")
    assert _connexion(_client(), MOT_DE_PASSE).status_code == 303
    assert _connexion(_client(), "mauvais").status_code == 200


def test_email_inconnu_verifie_un_hash(monkeypatch):
    appels = []
    vrai = securite.verifier_mot_de_passe
    monkeypatch.setattr(securite, "verifier_mot_de_passe", lambda m, h: appels.append(h) or vrai(m, h))
    assert securite.authentifier("personne@test.fr", "x") is None
    assert len(appels) == 1 and appels[0] == securite._hash_pour_email_inconnu()


# ─── Téléversement ────────────────────────────────────────────────────────────
def test_televersement_nom_et_taille(utilisateur):
    import main
    client, _ = utilisateur("a@test.fr")
    r = client.post("/api/profil/upload", data={"nom": "x" * 101}, files={"fichier": ("cv.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 400 and "Nom trop long" in r.json()["erreur"]
    gros = b"%PDF" + b"0" * routes_profil.TAILLE_MAX_PJ
    r = client.post("/api/profil/upload", data={"nom": "CV"}, files={"fichier": ("cv.pdf", gros, "application/pdf")})
    assert r.status_code == 400 and "trop volumineux" in r.json()["erreur"]
    r = client.post("/api/profil/upload", data={"nom": "x" * 100}, files={"fichier": ("cv.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 200


def test_nom_tire_du_fichier_raccourci(utilisateur):
    client, _ = utilisateur("a@test.fr")
    r = client.post("/api/profil/upload", data={"nom": ""},
                    files={"fichier": ("n" * 150 + ".pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 200 and r.json()["nom"] == "n" * 100
