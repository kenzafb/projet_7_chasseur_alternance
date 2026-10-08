"""Mode test d'envoi : option du compte d'envoi, mails redirigés vers
l'adresse d'expédition avec le vrai destinataire dans l'objet, aucune
adresse enregistrée comme contactée, aucune entreprise marquée envoyée."""

import pytest

import spontanees.envoyeur as envoyeur
from database.dedup_db import ajouter_emails_contactes, lire_emails_contactes
from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
from tests.conftest import compte_verifie
from tests.test_envoyeur import attendre, entreprises


@pytest.fixture(autouse=True)
def sans_pause(monkeypatch):
    monkeypatch.setattr(envoyeur, "PAUSE_ENTRE_MAILS", (0, 0))


@pytest.fixture
def alice(utilisateur, smtp_simule):
    client, user_id = utilisateur("a@test.fr", prenom="Alice", nom="A")
    compte_verifie(smtp_simule, user_id, "alice@gmail.com")
    return client, user_id


def activer(client, actif=True):
    r = client.post("/api/compte_envoi/mode_test", json={"actif": actif})
    assert r.status_code == 200, r.text
    return r.json()["compte"]


# ─── L'option ────────────────────────────────────────────────────────────────
def test_option_coupee_par_defaut_et_reglable(alice):
    client, _ = alice
    assert client.get("/api/compte_envoi").json()["compte"]["mode_test"] is False
    compte = activer(client)
    assert compte["mode_test"] is True and compte["verifie"] is True   # la vérification reste
    assert client.get("/api/compte_envoi").json()["compte"]["mode_test"] is True
    assert activer(client, False)["mode_test"] is False


def test_option_sans_compte_refusee(utilisateur):
    client, _ = utilisateur("a@test.fr")
    r = client.post("/api/compte_envoi/mode_test", json={"actif": True})
    assert r.status_code == 400 and "compte d'envoi" in r.json()["erreur"]


def test_option_validee(alice):
    client, _ = alice
    assert client.post("/api/compte_envoi/mode_test", json={"actif": True, "x": 1}).status_code == 422
    assert client.post("/api/compte_envoi/mode_test", json={}).status_code == 422


def test_option_propre_a_chaque_utilisateur(alice, utilisateur, smtp_simule):
    client_a, _ = alice
    client_b, id_b = utilisateur("b@test.fr")
    compte_verifie(smtp_simule, id_b, "bob@gmail.com")
    activer(client_a)
    assert client_b.get("/api/compte_envoi").json()["compte"]["mode_test"] is False


def test_enregistrer_le_compte_garde_le_mode_test(alice):
    client, _ = alice
    activer(client)
    client.post("/api/compte_envoi", json={"preset": "gmail", "adresse": "alice@gmail.com",
                                          "nom_affiche": "Alice"})
    assert client.get("/api/compte_envoi").json()["compte"]["mode_test"] is True


# ─── L'envoi ─────────────────────────────────────────────────────────────────
def test_redirection_vers_soi_avec_le_vrai_destinataire_dans_l_objet(alice, smtp_simule):
    client, user_id = alice
    activer(client)
    entreprises(user_id, 2)
    logs = []
    bilan = envoyeur.main(user_id, limite=10, log_fn=logs.append)

    assert bilan["envoyes"] == 2
    assert [to for _, _, to, _ in smtp_simule.messages] == [["alice@gmail.com"], ["alice@gmail.com"]]
    objets = sorted(m["Subject"] for *_, m in smtp_simule.messages)
    assert objets == ["[TEST → rh0@ent0.fr] Candidature spontanée en alternance",
                      "[TEST → rh1@ent1.fr] Candidature spontanée en alternance"]
    assert all(m["To"] == "alice@gmail.com" for *_, m in smtp_simule.messages)
    # Aucune adresse enregistrée comme contactée, aucune entreprise marquée
    assert lire_emails_contactes(user_id, "alternance") == set()
    assert not any(e["mail_envoye"] or e["mail_envoye_le"] or e["mail_destinataires"]
                   for e in lire_entreprises(user_id))
    texte = "\n".join(logs)
    assert "MODE TEST" in texte and "vrai destinataire : rh0@ent0.fr" in texte


def test_relance_reelle_apres_le_mode_test(alice, smtp_simule):
    """Le mode test ne laisse aucune trace : l'envoi réel qui suit vise les entreprises."""
    client, user_id = alice
    activer(client)
    entreprises(user_id, 2)
    envoyeur.main(user_id, limite=10)
    smtp_simule.messages.clear()

    activer(client, False)
    assert envoyeur.main(user_id, limite=10)["envoyes"] == 2
    assert sorted(to[0] for _, _, to, _ in smtp_simule.messages) == ["rh0@ent0.fr", "rh1@ent1.fr"]
    assert all(not m["Subject"].startswith("[TEST") for *_, m in smtp_simule.messages)
    assert lire_emails_contactes(user_id, "alternance") == {"rh0@ent0.fr", "rh1@ent1.fr"}
    assert all(e["mail_envoye"] for e in lire_entreprises(user_id))


def test_entreprise_deja_contactee_non_marquee_en_mode_test(alice, smtp_simule):
    client, user_id = alice
    activer(client)
    entreprises(user_id, 1)
    ajouter_emails_contactes(user_id, "alternance", ["rh0@ent0.fr"])
    envoyeur.main(user_id, limite=10)
    assert smtp_simule.messages == []
    assert lire_entreprises(user_id)[0]["mail_envoye"] is False


def test_adresse_partagee_visee_une_seule_fois(alice, smtp_simule):
    client, user_id = alice
    activer(client)
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "Un"}, {"siret": "S2", "nom": "Deux"}])
    liste = lire_entreprises(user_id)
    for e in liste:
        e["emails_trouves"] = ["rh@groupe.fr"]
    sauvegarder_enrichissement(user_id, liste)
    assert envoyeur.main(user_id, limite=10)["envoyes"] == 1
    assert lire_emails_contactes(user_id, "alternance") == set()


def test_parametre_test_sans_option(alice, smtp_simule):
    """test=True (CLI --test) suffit, même option coupée."""
    _, user_id = alice
    entreprises(user_id, 1)
    envoyeur.main(user_id, limite=1, test=True)
    assert smtp_simule.messages[0][3]["Subject"].startswith("[TEST → rh0@ent0.fr]")
    assert lire_emails_contactes(user_id, "alternance") == set()


def test_mode_test_par_la_route_affiche_et_journalise(alice, smtp_simule, pipelines_neufs):
    client, user_id = alice
    activer(client)
    entreprises(user_id, 1)
    r = client.post("/api/spontanees/envoyer", json={"limite": 1})
    assert r.status_code == 200 and r.json()["mode_test"] is True
    attendre(lambda: not pipelines_neufs.etat("spontanees", user_id)["en_cours"])
    etat = client.get("/api/spontanees/statut").json()
    assert etat["mode_test"] is True and etat["message"] == "Envoi de test terminé !"
    assert client.get("/api/spontanees/stats").json()["mode_test"] is True
    logs = client.get("/api/logs").text
    assert "MODE TEST" in logs and "alice@gmail.com" in logs
    assert smtp_simule.messages[0][2] == ["alice@gmail.com"]
    assert lire_entreprises(user_id)[0]["mail_envoye"] is False


def test_envoi_reel_par_la_route_sans_mode_test(alice, smtp_simule, pipelines_neufs):
    client, user_id = alice
    entreprises(user_id, 1)
    r = client.post("/api/spontanees/envoyer", json={"limite": 1})
    assert r.json()["mode_test"] is False
    attendre(lambda: not pipelines_neufs.etat("spontanees", user_id)["en_cours"])
    assert pipelines_neufs.etat("spontanees", user_id)["mode_test"] is False
    assert "MODE TEST" not in client.get("/api/logs").text
    assert smtp_simule.messages[0][2] == ["rh0@ent0.fr"]


def test_interface_affiche_le_mode_test():
    from shared import config
    profil = (config.TEMPLATES_DIR / "partials" / "profil.html").read_text(encoding="utf-8")
    spontanees = (config.TEMPLATES_DIR / "partials" / "spontanees.html").read_text(encoding="utf-8")
    assert "data-ce-mode-test" in profil and "Mode test" in profil
    assert "data-sp-mode-test" in spontanees and "Mode test actif" in spontanees
