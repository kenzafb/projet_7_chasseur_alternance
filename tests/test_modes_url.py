"""Une URL par mode (phase 6a) : page d'accueil, /alternance, /job, /stage
« bientôt disponible », anciennes URL redirigées ; le mode vient de l'URL,
deux onglets dans deux modes ne se gênent pas."""

import main
from database.profil_db import lire_profil
from tests.conftest import CODE, MOT_DE_PASSE, ClientDeMode


def test_accueil_propose_les_modes(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = client.get("/").text
    for cle in ("alternance", "job", "stage"):
        assert f'href="/{cle}"' in page
    assert "bientôt disponible" in page
    assert 'location.replace("/alternance#" + page)' in page      # anciens liens « /#page »


def test_page_de_chaque_mode(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    for mode, titre in (("alternance", "Chasseur d'Alternance"), ("job", "Chasseur de Job")):
        page = client.get(f"/{mode}").text
        assert f'data-mode="{mode}"' in page and f"<title>{titre}" in page.replace("&#39;", "'")
        assert f'class="mode-switch__btn is-active" href="/{mode}"' in page
    page = client.get("/stage").text
    assert "bientôt disponible" in page and 'data-bientot="stage"' in page and "data-mode=" not in page


def test_anciennes_url_redirigees(client, code_invitation):
    r = client.post("/register", data={"email": "n@test.fr", "mot_de_passe": MOT_DE_PASSE,
                                       "code_invitation": CODE}, follow_redirects=False)
    assert r.headers["location"] == "/alternance?bienvenue=1"
    r = client.get("/?bienvenue=1", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/alternance?bienvenue=1"
    # Plus de bascule de mode en session
    assert client.post("/api/mode", json={"mode": "job"}).status_code == 405
    assert client.get("/api/mode", params={"mode": "job"}).json()["label"] == "Chasseur de Job"


def test_deux_onglets_deux_modes(utilisateur):
    alternance, uid = utilisateur("a@test.fr", prenom="Alice")
    job = ClientDeMode(main.app, cookies=alternance.cookies)      # même session, autre onglet
    job.mode = "job"
    assert alternance.post("/api/profil", json={"prenom": "Alice", "ville": "Paris"}).status_code == 200
    assert job.post("/api/profil", json={"prenom": "Alice", "ville": "Lyon"}).status_code == 200
    assert alternance.post("/api/profil", json={"prenom": "Alice", "ville": "Paris 11"}).json() == {"ok": True}
    assert lire_profil(uid, mode="alternance")["ville"] == "Paris 11"
    assert lire_profil(uid, mode="job")["ville"] == "Lyon"
    assert job.get("/api/profil").json()["ville"] == "Lyon"
    assert alternance.get("/api/profil").json()["ville"] == "Paris 11"


def test_pipeline_d_un_autre_mode_signale(utilisateur, monkeypatch):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    main.pipelines.demarrer("spontanees", uid, etape="fetch", mode="job")
    r = client.post("/api/spontanees/fetch", json={"max_entreprises": 1})
    assert r.status_code == 400 and r.json()["erreur"] == "Pipeline déjà en cours (mode job)"
    assert client.get("/api/statut_pipelines").json()["spontanees"]["mode"] == "job"
