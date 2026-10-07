"""Envoyeur : uniquement le compte de l'utilisateur qui lance, refus avant
lancement, plafond quotidien, arrêt propre sur erreur de compte."""

import time

import pytest

import spontanees.envoyeur as envoyeur
from database import compte_envoi_db
from database.dedup_db import lire_emails_contactes
from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
from shared import config
from tests.conftest import compte_verifie


def attendre(condition, delai=5.0):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(0.01)
    raise AssertionError("condition jamais remplie")


def entreprises(user_id, n, prefixe="rh"):
    """n entreprises avec chacune une adresse distincte."""
    ajouter_entreprises(user_id, [{"siret": f"S{i}", "nom": f"Ent {i}"} for i in range(n)])
    liste = lire_entreprises(user_id)
    for i, e in enumerate(liste):
        e["emails_trouves"] = [f"{prefixe}{i}@ent{i}.fr"]
    sauvegarder_enrichissement(user_id, liste)


@pytest.fixture(autouse=True)
def sans_pause(monkeypatch):
    monkeypatch.setattr(envoyeur, "PAUSE_ENTRE_MAILS", (0, 0))


@pytest.fixture
def a_et_b(utilisateur):
    client_a, id_a = utilisateur("a@test.fr", prenom="Alice", nom="A")
    client_b, id_b = utilisateur("b@test.fr", prenom="Bob", nom="B")
    return client_a, id_a, client_b, id_b


# ─── Le compte de celui qui lance, jamais un autre ───────────────────────────
def test_a_envoie_avec_ses_identifiants_jamais_ceux_de_b(a_et_b, smtp_simule):
    _, id_a, _, id_b = a_et_b
    mdp_a = compte_verifie(smtp_simule, id_a, "alice@gmail.com")
    compte_verifie(smtp_simule, id_b, "bob@gmail.com")
    entreprises(id_a, 3, "a")
    entreprises(id_b, 2, "b")

    assert envoyeur.main(id_a, limite=10)["envoyes"] == 3
    assert {c["identifiant"] for c in smtp_simule.connexions} == {"alice@gmail.com"}
    assert {(ident, de) for ident, de, _, _ in smtp_simule.messages} == {("alice@gmail.com", "alice@gmail.com")}
    assert all(m["From"] == "alice@gmail.com" for *_, m in smtp_simule.messages)
    assert compte_envoi_db.compte_pour_envoi(id_a)["mot_de_passe"] == mdp_a

    smtp_simule.connexions.clear()
    smtp_simule.messages.clear()
    assert envoyeur.main(id_b, limite=10)["envoyes"] == 2
    assert {c["identifiant"] for c in smtp_simule.connexions} == {"bob@gmail.com"}
    assert {de for _, de, _, _ in smtp_simule.messages} == {"bob@gmail.com"}


def test_mode_test_envoie_a_l_adresse_du_compte(a_et_b, smtp_simule):
    _, id_a, _, _ = a_et_b
    compte_verifie(smtp_simule, id_a, "alice@gmail.com")
    entreprises(id_a, 2)
    envoyeur.main(id_a, limite=1, test=True)
    assert [to for _, _, to, _ in smtp_simule.messages] == [["alice@gmail.com"]]
    assert not any(e["mail_envoye"] for e in lire_entreprises(id_a))


def test_plus_aucune_variable_gmail_commune():
    import pathlib
    racine = pathlib.Path(config.BASE_DIR)
    fichiers = [racine / "main.py", racine / ".env.example", racine / "README.md"]
    for dossier in ("auth", "database", "france_travail", "scripts", "shared", "spontanees", "static", "templates"):
        fichiers += [f for f in (racine / dossier).rglob("*") if f.suffix in (".py", ".js", ".html")]
    for chemin in fichiers:
        texte = chemin.read_text(encoding="utf-8")
        assert "GMAIL_SENDER" not in texte and "GMAIL_APP_PASSWORD" not in texte, chemin


# ─── Refus avant tout lancement ──────────────────────────────────────────────
def test_refus_sans_compte(a_et_b, smtp_simule, pipelines_neufs):
    client_a, id_a, _, _ = a_et_b
    entreprises(id_a, 1)
    r = client_a.post("/api/spontanees/envoyer", json={"limite": 1})
    assert r.status_code == 400 and "Aucun compte d'envoi" in r.json()["erreur"]
    assert pipelines_neufs.etat("spontanees", id_a)["en_cours"] is False
    with pytest.raises(envoyeur.ErreurUtilisateur):
        envoyeur.main(id_a, limite=1)
    assert smtp_simule.connexions == []


def test_refus_compte_jamais_verifie(a_et_b, smtp_simule, pipelines_neufs):
    client_a, id_a, _, _ = a_et_b
    entreprises(id_a, 1)
    client_a.post("/api/compte_envoi", json={"preset": "gmail", "adresse": "alice@gmail.com",
                                            "mot_de_passe": "abcdefghijklmnop"})
    r = client_a.post("/api/spontanees/envoyer", json={"limite": 1})
    assert r.status_code == 400 and "non vérifié" in r.json()["erreur"]
    assert pipelines_neufs.etat("spontanees", id_a)["en_cours"] is False
    assert smtp_simule.connexions == []


def test_refus_sans_cle_de_chiffrement(a_et_b, smtp_simule, monkeypatch, pipelines_neufs):
    client_a, id_a, _, _ = a_et_b
    compte_verifie(smtp_simule, id_a, "alice@gmail.com")
    entreprises(id_a, 1)
    monkeypatch.delenv("CLE_CHIFFREMENT")
    r = client_a.post("/api/spontanees/envoyer", json={"limite": 1})
    assert r.status_code == 503 and "CLE_CHIFFREMENT" in r.json()["erreur"]
    assert pipelines_neufs.etat("spontanees", id_a)["en_cours"] is False
    with pytest.raises(envoyeur.ChiffrementIndisponible):
        envoyeur.main(id_a, limite=1)
    assert smtp_simule.connexions == []


def test_lancement_par_la_route_avec_le_mode_courant(a_et_b, smtp_simule, pipelines_neufs):
    client_a, id_a, _, _ = a_et_b
    compte_verifie(smtp_simule, id_a, "alice@gmail.com")
    entreprises(id_a, 2)
    client_a.post("/api/mode", json={"mode": "job"})
    client_a.post("/api/profil", json={"email_type": "Corps du mode job."})
    assert client_a.post("/api/spontanees/envoyer", json={"limite": 2}).status_code == 200
    attendre(lambda: not pipelines_neufs.etat("spontanees", id_a)["en_cours"])
    assert pipelines_neufs.etat("spontanees", id_a)["message"] == "Envoi terminé !"
    assert len(smtp_simule.messages) == 2
    assert all(m.get_content().strip() == "Corps du mode job." for *_, m in smtp_simule.messages)


# ─── Plafond quotidien ───────────────────────────────────────────────────────
def test_plafond_quotidien_respecte(a_et_b, smtp_simule, monkeypatch, pipelines_neufs):
    client_a, id_a, _, id_b = a_et_b
    monkeypatch.setattr(config, "PLAFOND_ENVOIS_JOUR", 3)
    compte_verifie(smtp_simule, id_a, "alice@gmail.com")
    compte_verifie(smtp_simule, id_b, "bob@gmail.com")
    entreprises(id_a, 6)
    logs = []

    assert envoyeur.main(id_a, limite=2, log_fn=logs.append) == {"envoyes": 2, "echecs": 0, "arret": "limite"}
    bilan = envoyeur.main(id_a, limite=10, log_fn=logs.append)
    assert bilan == {"envoyes": 1, "echecs": 0, "arret": "plafond"}
    assert any("Plafond de 3 mails par jour atteint" in l for l in logs)
    assert len(smtp_simule.messages) == 3
    assert compte_envoi_db.envois_du_jour(id_a) == 3
    assert sum(e["mail_envoye"] for e in lire_entreprises(id_a)) == 3   # rien de perdu

    # Lancement suivant le même jour : refusé avant de démarrer
    r = client_a.post("/api/spontanees/envoyer", json={"limite": 1})
    assert r.status_code == 400 and "Plafond" in r.json()["erreur"]
    assert pipelines_neufs.etat("spontanees", id_a)["en_cours"] is False
    # Le plafond est par utilisateur : B n'est pas bloqué
    entreprises(id_b, 1)
    assert envoyeur.main(id_b, limite=5)["envoyes"] == 1


def test_plafond_le_lendemain(a_et_b, smtp_simule, monkeypatch):
    from datetime import date
    _, id_a, _, _ = a_et_b
    monkeypatch.setattr(config, "PLAFOND_ENVOIS_JOUR", 1)
    compte_verifie(smtp_simule, id_a, "alice@gmail.com")
    entreprises(id_a, 2)
    monkeypatch.setattr(compte_envoi_db, "_aujourdhui", lambda: date(2026, 10, 8))
    assert envoyeur.main(id_a, limite=5)["envoyes"] == 1
    monkeypatch.setattr(compte_envoi_db, "_aujourdhui", lambda: date(2026, 10, 9))
    assert envoyeur.main(id_a, limite=5)["envoyes"] == 1


def test_plafond_par_defaut_et_reglable():
    import os
    import subprocess
    import sys

    def plafond(**env):
        r = subprocess.run([sys.executable, "-c", "from shared import config; print(config.PLAFOND_ENVOIS_JOUR)"],
                           cwd=config.BASE_DIR, env={**os.environ, **env}, capture_output=True, text=True)
        return int(r.stdout)
    assert plafond() == 50
    assert plafond(PLAFOND_ENVOIS_JOUR="12") == 12


# ─── Erreurs de compte : arrêt propre ────────────────────────────────────────
def test_erreur_d_authentification_arrete_le_pipeline(a_et_b, smtp_simule, capsys):
    _, id_a, _, _ = a_et_b
    mdp = compte_verifie(smtp_simule, id_a, "alice@gmail.com")
    entreprises(id_a, 4)
    logs = []
    envoyeur.main(id_a, limite=1, log_fn=logs.append)        # un premier mail part
    smtp_simule.comptes["alice@gmail.com"] = "mot-de-passe-revoque"

    with pytest.raises(envoyeur.EnvoiInterrompu) as e:
        envoyeur.main(id_a, limite=10, log_fn=logs.append)
    assert "Authentification refusée" in str(e.value) and "Tester la connexion" in str(e.value)
    assert len(smtp_simule.connexions) == 2                  # une seule tentative, pas de boucle
    assert len(smtp_simule.messages) == 1
    assert sum(x["mail_envoye"] for x in lire_entreprises(id_a)) == 1
    assert compte_envoi_db.lire_compte(id_a)["verifie"] is False
    assert compte_envoi_db.envois_du_jour(id_a) == 1          # l'échec est rendu au compteur
    texte = "\n".join(logs) + str(e.value) + capsys.readouterr().out
    assert mdp not in texte and "mot-de-passe-revoque" not in texte


def test_erreur_d_authentification_via_la_route(a_et_b, smtp_simule, pipelines_neufs):
    client_a, id_a, _, _ = a_et_b
    mdp = compte_verifie(smtp_simule, id_a, "alice@gmail.com")
    entreprises(id_a, 3)
    smtp_simule.comptes["alice@gmail.com"] = "autre"
    assert client_a.post("/api/spontanees/envoyer", json={"limite": 3}).status_code == 200
    attendre(lambda: not pipelines_neufs.etat("spontanees", id_a)["en_cours"])
    etat = client_a.get("/api/spontanees/statut").json()
    assert etat["message"].startswith("Erreur envoi : Authentification refusée")
    logs = client_a.get("/api/logs").text
    assert "Vérifie le compte d'envoi" in logs and mdp not in logs
    assert len(smtp_simule.connexions) == 1
    # Le compte n'est plus vérifié : lancement suivant refusé
    assert client_a.post("/api/spontanees/envoyer", json={"limite": 1}).status_code == 400


def test_serveur_injoignable_arrete_aussi(a_et_b, smtp_simule):
    _, id_a, _, _ = a_et_b
    compte_verifie(smtp_simule, id_a, "alice@gmail.com")
    entreprises(id_a, 3)
    smtp_simule.injoignable = True
    with pytest.raises(envoyeur.EnvoiInterrompu, match="injoignable"):
        envoyeur.main(id_a, limite=10)
    assert compte_envoi_db.lire_compte(id_a)["verifie"] is True
    assert compte_envoi_db.envois_du_jour(id_a) == 0


def test_destinataire_refuse_passe_a_la_suivante(a_et_b, smtp_simule):
    _, id_a, _, _ = a_et_b
    compte_verifie(smtp_simule, id_a, "alice@gmail.com")
    entreprises(id_a, 3)
    smtp_simule.refuses.add("rh0@ent0.fr")
    bilan = envoyeur.main(id_a, limite=10)
    assert bilan == {"envoyes": 2, "echecs": 1, "arret": None}
    assert lire_emails_contactes(id_a) == {"rh1@ent1.fr", "rh2@ent2.fr"}
    assert compte_envoi_db.envois_du_jour(id_a) == 2
