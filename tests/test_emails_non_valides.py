"""Emails non validés par l'IA (décision D15) : jamais envoyés
automatiquement, hors du maximum d'envoi, visibles avec leur mention,
validables à la main un par un ou repassés à l'IA plus tard."""

import pytest

import spontanees.envoyeur as envoyeur
import spontanees.scraper_emails as se
from database.dedup_db import lire_emails_contactes
from database.entreprises_db import lire_entreprises, sauvegarder_enrichissement
from france_travail.analyseur import reserve_public_specifique
from shared import config
from tests.conftest import compte_verifie
from tests.test_envoyeur import attendre, entreprises
from tests.test_mistral import TIER, echouer, erreur_http
from tests.test_scraper_sans_ia import sites  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def sans_pause(monkeypatch):
    monkeypatch.setattr(envoyeur, "PAUSE_ENTRE_MAILS", (0, 0))


@pytest.fixture
def alice(utilisateur, smtp_simule):
    """Alice, compte d'envoi en envoi réel, 3 entreprises dont rh1 et rh2 non validées."""
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    compte_verifie(smtp_simule, user_id, "alice@gmail.com")
    entreprises(user_id, 3)
    liste = lire_entreprises(user_id)
    for i, e in enumerate(liste):
        e["site_web"] = f"https://acme{i}.fr"
        e["emails_non_valides"] = i > 0
    sauvegarder_enrichissement(user_id, liste)
    return client, user_id, [e["_id"] for e in liste]


def test_jamais_envoyes_automatiquement(alice, smtp_simule):
    _, user_id, _ = alice
    logs = []
    assert envoyeur.main(user_id, limite=10, log_fn=logs.append)["envoyes"] == 1
    assert [to for _, _, to, _ in smtp_simule.messages] == [["rh0@ent0.fr"]]
    assert lire_emails_contactes(user_id, "alternance") == {"rh0@ent0.fr"}
    assert any("2 entreprise(s) aux emails non validés ignorée(s)" in l for l in logs)
    assert [e["mail_envoye"] for e in lire_entreprises(user_id)] == [True, False, False]


def test_ni_en_mode_test(alice, smtp_simule):
    _, user_id, _ = alice
    envoyeur.main(user_id, limite=10, test=True)
    assert len(smtp_simule.messages) == 1


def test_hors_du_maximum_d_envoi(alice):
    client, user_id, _ = alice
    stats = client.get("/api/spontanees/stats").json()
    assert stats["a_envoyer"] == 1 and stats["a_valider"] == 2
    assert envoyeur.compter_a_envoyer(user_id, "alternance") == 1


def test_visibles_avec_leur_mention(alice):
    client, _, ids = alice
    a_valider = client.get("/api/spontanees/a_valider").json()
    assert [e["id"] for e in a_valider] == ids[1:]
    assert a_valider[0]["emails"] == ["rh1@ent1.fr"]
    page = (config.TEMPLATES_DIR / "partials" / "spontanees.html").read_text(encoding="utf-8")
    js = (config.STATIC_DIR / "js" / "spontanees.js").read_text(encoding="utf-8")
    assert "data-a-valider" in page and 'data-action="revalider"' in page
    assert "non validé" in js and "data-valider" in js and "api.spValider" in js


def test_validation_manuelle_une_par_une(alice, smtp_simule):
    client, user_id, ids = alice
    assert client.post("/api/spontanees/valider", json={"id": ids[1]}).json() == {"ok": True}
    assert [e["id"] for e in client.get("/api/spontanees/a_valider").json()] == [ids[2]]
    assert client.get("/api/spontanees/stats").json()["a_envoyer"] == 2
    assert envoyeur.main(user_id, limite=10)["envoyes"] == 2
    assert sorted(to[0] for _, _, to, _ in smtp_simule.messages) == ["rh0@ent0.fr", "rh1@ent1.fr"]


def test_validation_manuelle_refusee_hors_attente(alice, utilisateur):
    client, _, ids = alice
    assert client.post("/api/spontanees/valider", json={"id": ids[0]}).status_code == 404   # déjà validée
    assert client.post("/api/spontanees/valider", json={"id": 99999}).status_code == 404
    client_b, _ = utilisateur("b@test.fr")
    assert client_b.post("/api/spontanees/valider", json={"id": ids[1]}).status_code == 404   # pas à B
    assert client_b.get("/api/spontanees/a_valider").json() == []
    assert len(client.get("/api/spontanees/a_valider").json()) == 2


# ─── Relancer la validation par l'IA ─────────────────────────────────────────
def _revalider(client, user_id, pipelines, **corps):
    r = client.post("/api/spontanees/revalider", json=corps)
    attendre(lambda: not pipelines.etat("spontanees", user_id)["en_cours"])
    return r


def test_relance_ia_valide_et_remplace(alice, sites, mistral, pipelines_neufs):  # noqa: F811
    client, user_id, _ = alice
    mistral.reponse = '{"emails": ["recrutement@acme1.fr"], "telephones": [], "contact_rh": null, "fiable": true}'
    r = _revalider(client, user_id, pipelines_neufs, max_revalidations=1)
    assert r.json()["max_revalidations"] == 1
    e = lire_entreprises(user_id)[1]
    assert e["emails_trouves"] == ["recrutement@acme1.fr"] and e["emails_non_valides"] is False
    assert lire_entreprises(user_id)[2]["emails_non_valides"] is True   # au-delà de la limite
    assert "Validation IA terminée : 1/1" in client.get("/api/logs").text


def test_relance_ia_en_echec_passager_reste_a_valider(alice, sites, mistral, monkeypatch, pipelines_neufs):  # noqa: F811
    client, user_id, _ = alice
    echouer(mistral, monkeypatch, erreur_http(503))
    _revalider(client, user_id, pipelines_neufs)
    assert [e["emails_non_valides"] for e in lire_entreprises(user_id)] == [False, True, True]
    assert lire_entreprises(user_id)[1]["emails_trouves"] == ["rh1@ent1.fr"]


def test_relance_ia_bloquante_un_message_et_arret(alice, sites, mistral, monkeypatch, pipelines_neufs):  # noqa: F811
    client, user_id, _ = alice
    echouer(mistral, monkeypatch, erreur_http(403, TIER))
    _revalider(client, user_id, pipelines_neufs)
    assert len(mistral.appels) == 1
    assert client.get("/api/logs").text.count("Mistral refuse les appels") == 1
    assert len(client.get("/api/spontanees/a_valider").json()) == 2


def test_relance_bornee_et_refusee_sans_attente(alice, utilisateur, monkeypatch, pipelines_neufs):
    client, user_id, _ = alice
    recues = []
    monkeypatch.setattr(se, "revalider", lambda user_id, **kw: recues.append(kw["max_n"]))
    r = _revalider(client, user_id, pipelines_neufs, max_revalidations=50)
    assert r.json()["max_revalidations"] == 2 and recues == [2]
    assert "(demandé : 50, ramené à 2)" in client.get("/api/logs").text
    client_b, _ = utilisateur("b@test.fr")
    r = client_b.post("/api/spontanees/revalider", json={})
    assert r.status_code == 400 and "Aucun email en attente" in r.json()["erreur"]


# ─── Décision D17 : « maazi » retiré de la règle ─────────────────────────────
def test_maazi_ne_declenche_plus_l_archivage():
    assert reserve_public_specifique("Programme MAAZI, accompagnement des alternants.") is False
    source = (config.BASE_DIR / "france_travail" / "analyseur.py").read_text(encoding="utf-8").lower()
    assert "maazi" not in source
