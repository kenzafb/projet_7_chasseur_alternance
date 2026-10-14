"""Emails non validés (décision D15, phase 7) : jamais envoyés
automatiquement, hors du maximum d'envoi, visibles avec leur mention,
validables à la main un par un ou repassés aux règles et à l'IA plus tard."""

import pytest

import spontanees.envoyeur as envoyeur
import spontanees.scraper_emails as se
from database.dedup_db import lire_emails_contactes
from database.entreprises_db import lire_entreprises, sauvegarder_enrichissement
from france_travail.analyseur import reserve_public_specifique
from shared import config
from tests.conftest import compte_verifie
from tests.test_envoyeur import attendre, entreprises
from tests.test_ia import INTROUVABLE, echouer, erreur_http


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


def test_relance_ia_valide_ou_ecarte_sans_relire_le_site(alice, ia, pipelines_neufs, monkeypatch):
    client, user_id, _ = alice
    monkeypatch.setattr(se, "get_page", lambda *a, **k: pytest.fail("le site ne doit pas être relu"))
    ia.file = ['{"valides": ["rh1@ent1.fr"], "meilleur_contact": "rh1@ent1.fr"}',
               '{"valides": [], "meilleur_contact": null}']
    r = _revalider(client, user_id, pipelines_neufs)
    assert r.json()["max_revalidations"] == 2
    e1, e2 = lire_entreprises(user_id)[1:]
    assert e1["emails_trouves"] == ["rh1@ent1.fr"] and e1["emails_non_valides"] is False
    assert e2["emails_trouves"] == [] and e2["emails_non_valides"] is False   # écartée par l'IA
    assert "acme1.fr" in ia.textes(0) and "rh1@ent1.fr" in ia.textes(0)
    assert "Validation IA terminée : 2/2" in client.get("/api/logs").text


def test_relance_regles_d_abord(alice, ia, pipelines_neufs):
    """Une adresse validée d'office par les règles n'est pas soumise à l'IA."""
    client, user_id, _ = alice
    liste = lire_entreprises(user_id)
    liste[1].update(site_web="https://ent1.fr", emails_trouves=["recrutement@ent1.fr", "x@agence.fr"],
                    emails_douteux=["recrutement@ent1.fr", "x@agence.fr"],
                    contextes_emails={"x@agence.fr": "Site réalisé par l'agence"})
    sauvegarder_enrichissement(user_id, liste)
    ia.reponse = '{"valides": [], "meilleur_contact": "recrutement@ent1.fr"}'
    _revalider(client, user_id, pipelines_neufs, max_revalidations=1)
    assert len(ia.appels) == 1 and "Site réalisé par l'agence" in ia.textes(0)
    e = lire_entreprises(user_id)[1]
    assert e["emails_trouves"] == ["recrutement@ent1.fr"] and e["emails_non_valides"] is False
    assert e["meilleur_contact"] == "recrutement@ent1.fr"      # adresse validée par les règles
    assert e["validation_emails"] == {"recrutement@ent1.fr": "regle"}


def test_relance_ia_en_echec_passager_reste_a_valider(alice, ia, pipelines_neufs):
    client, user_id, _ = alice
    echouer(ia, erreur_http(503))
    _revalider(client, user_id, pipelines_neufs)
    assert [e["emails_non_valides"] for e in lire_entreprises(user_id)] == [False, True, True]
    assert lire_entreprises(user_id)[1]["emails_trouves"] == ["rh1@ent1.fr"]
    assert len(client.get("/api/spontanees/a_valider").json()) == 2


def test_relance_ia_bloquante_un_message_et_arret(alice, ia, pipelines_neufs):
    client, user_id, _ = alice
    echouer(ia, erreur_http(404, INTROUVABLE))
    _revalider(client, user_id, pipelines_neufs)
    assert len(ia.demarrages) == 1 and ia.appels == []   # arrêté au test de démarrage
    assert client.get("/api/logs").text.count("IA indisponible") == 1
    assert len(client.get("/api/spontanees/a_valider").json()) == 2


def test_seules_les_adresses_validees_partent(alice, smtp_simule):
    """Une entreprise avec une adresse validée et une douteuse est envoyée,
    à l'adresse validée seulement."""
    _, user_id, _ = alice
    liste = lire_entreprises(user_id)
    liste[1].update(emails_trouves=["contact@ent1.fr", "douteux@gmail.com"], emails_douteux=["douteux@gmail.com"])
    sauvegarder_enrichissement(user_id, liste)
    assert envoyeur.compter_a_envoyer(user_id, "alternance") == 2
    envoyeur.main(user_id, limite=10)
    assert sorted(to[0] for _, _, to, _ in smtp_simule.messages) == ["contact@ent1.fr", "rh0@ent0.fr"]
    assert "douteux@gmail.com" not in lire_emails_contactes(user_id, "alternance")


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


def test_provenance_affichee_par_adresse(alice, ia, pipelines_neufs):
    client, user_id, ids = alice
    liste = lire_entreprises(user_id)
    liste[0]["validation_emails"] = {"rh0@ent0.fr": "regle"}
    sauvegarder_enrichissement(user_id, liste)
    ia.file = ['{"valides": ["rh1@ent1.fr"], "meilleur_contact": "rh1@ent1.fr"}']
    _revalider(client, user_id, pipelines_neufs, max_revalidations=1)
    client.post("/api/spontanees/valider", json={"id": ids[2]})
    lignes = {e["id"]: e["adresses"] for e in client.get("/api/spontanees/stats").json()["prochaines"]}
    assert lignes[ids[0]] == [{"adresse": "rh0@ent0.fr", "validation": "regle", "meilleur": False}]
    assert lignes[ids[1]] == [{"adresse": "rh1@ent1.fr", "validation": "ia", "meilleur": True}]
    assert lignes[ids[2]] == [{"adresse": "rh2@ent2.fr", "validation": "manuelle", "meilleur": False}]
    js = (config.STATIC_DIR / "js" / "spontanees.js").read_text(encoding="utf-8")
    assert "validée par règle" in js and "validée par l'IA" in js and "validée à la main" in js


# ─── Adresses écartées par l'IA : visibles, validables quand même ────────────
def test_ecartee_par_l_ia_visible_et_validable(alice, ia, pipelines_neufs, smtp_simule, utilisateur):
    client, user_id, ids = alice
    ia.file = ['{"valides": [], "meilleur_contact": null}', '{"valides": ["rh2@ent2.fr"], "meilleur_contact": null}']
    _revalider(client, user_id, pipelines_neufs)
    e1 = lire_entreprises(user_id)[1]
    assert e1["emails_trouves"] == [] and e1["emails_ecartes_ia"] == ["rh1@ent1.fr"]
    a_valider = {e["id"]: e for e in client.get("/api/spontanees/a_valider").json()}
    assert list(a_valider) == [ids[1]]                                  # plus de douteuse, mais visible
    assert a_valider[ids[1]]["adresses"] == [{"adresse": "rh1@ent1.fr", "validation": "ecartee_ia", "meilleur": False}]
    assert client.get("/api/spontanees/stats").json()["a_valider"] == 0   # rien à repasser à l'IA
    assert envoyeur.compter_a_envoyer(user_id, "alternance") == 2         # écartée : jamais envoyée
    # Une autre personne ne peut pas la valider
    client_b, _ = utilisateur("b@test.fr")
    assert client_b.post("/api/spontanees/valider_adresse", json={"id": ids[1], "adresse": "rh1@ent1.fr"}).status_code == 404
    # Validée quand même, à la main
    assert client.post("/api/spontanees/valider_adresse", json={"id": ids[1], "adresse": "rh1@ent1.fr"}).json() == {"ok": True}
    e1 = lire_entreprises(user_id)[1]
    assert e1["emails_trouves"] == ["rh1@ent1.fr"] and e1["validation_emails"]["rh1@ent1.fr"] == "manuelle"
    assert client.get("/api/spontanees/a_valider").json() == []
    assert envoyeur.compter_a_envoyer(user_id, "alternance") == 3
    assert client.post("/api/spontanees/valider_adresse", json={"id": ids[1], "adresse": "rh1@ent1.fr"}).status_code == 404
    js = (config.STATIC_DIR / "js" / "spontanees.js").read_text(encoding="utf-8")
    assert "écartée par l'IA" in js and "Valider quand même" in js and "api.spValiderAdresse" in js


def test_validation_d_une_seule_douteuse(alice):
    client, user_id, ids = alice
    liste = lire_entreprises(user_id)
    liste[1].update(emails_trouves=["a@gmail.com", "b@gmail.com"], emails_douteux=["a@gmail.com", "b@gmail.com"])
    sauvegarder_enrichissement(user_id, liste)
    assert client.post("/api/spontanees/valider_adresse", json={"id": ids[1], "adresse": "a@gmail.com"}).json()["ok"]
    e = lire_entreprises(user_id)[1]
    assert e["emails_douteux"] == ["b@gmail.com"] and e["emails_non_valides"] is True
    assert envoyeur.emails_valides(e) == ["a@gmail.com"]
