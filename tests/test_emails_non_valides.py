"""Emails non validés (décision D15, phase 7) : jamais envoyés
automatiquement, hors du maximum d'envoi, visibles avec leur mention,
validables à la main un par un ou repassés aux règles et à l'IA plus tard."""

import pytest

import spontanees.envoi as envoyeur
import spontanees.recherche_emails as se
from database.dedup_db import lire_emails_contactes
from database.entreprises_db import (
    compter_a_valider,
    lire_entreprises,
    sauvegarder_enrichissement,
    valider_adresse,
    valider_emails,
)
from offres.analyse import reserve_public_specifique
from shared import config, validation_emails
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


def nominatives(user_id):
    """Entreprises 1 et 2 : site vérifié (D160), adresse nominative du même
    domaine, douteuse : c'est l'IA qui tranche (D162)."""
    liste = lire_entreprises(user_id)
    for i in (1, 2):
        liste[i].update(emails_trouves=[f"camille{i}@ent{i}.fr"], emails_douteux=[f"camille{i}@ent{i}.fr"],
                        site_verifie={"url": f"https://ent{i}.fr", "domaine": f"ent{i}.fr", "preuve": "siren"})
    sauvegarder_enrichissement(user_id, liste)


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
    assert "data-adresse-action" in js and all(f"api.{a}" in js for a in ("spValider", "spValiderAdresse", "spRejeterAdresse"))


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
    nominatives(user_id)
    monkeypatch.setattr(se, "scraper_et_extraire", lambda *a, **k: pytest.fail("le site ne doit pas être relu"))
    ia.file = ['{"valides": ["camille1@ent1.fr"], "meilleur_contact": "camille1@ent1.fr"}',
               '{"valides": [], "meilleur_contact": null}']
    r = _revalider(client, user_id, pipelines_neufs)
    assert r.json()["max_revalidations"] == 2
    e1, e2 = lire_entreprises(user_id)[1:]
    assert e1["emails_trouves"] == ["camille1@ent1.fr"] and e1["emails_non_valides"] is False
    assert e2["emails_trouves"] == [] and e2["emails_non_valides"] is False   # écartée par l'IA
    assert "ent1.fr" in ia.textes(0) and "camille1@ent1.fr" in ia.textes(0)   # domaine du site vérifié
    assert "Validation IA terminée : 2/2" in client.get("/api/logs").text


def test_relance_regles_d_abord(alice, ia, pipelines_neufs):
    """Règles d'abord (D162) : adresse de contact du site vérifié validée,
    autre domaine écarté, sans IA ; l'IA ne juge que la messagerie grand public."""
    client, user_id, _ = alice
    liste = lire_entreprises(user_id)
    liste[1].update(site_web="https://ent1.fr", emails_trouves=["recrutement@ent1.fr", "x@agence.fr", "gerant@gmail.com"],
                    emails_douteux=["recrutement@ent1.fr", "x@agence.fr", "gerant@gmail.com"],
                    contextes_emails={"gerant@gmail.com": "Écrivez au gérant"},
                    site_verifie={"url": "https://ent1.fr", "domaine": "ent1.fr", "preuve": "siren"})
    sauvegarder_enrichissement(user_id, liste)
    ia.reponse = '{"valides": [], "meilleur_contact": "recrutement@ent1.fr"}'
    _revalider(client, user_id, pipelines_neufs, max_revalidations=1)
    assert len(ia.appels) == 1 and "Écrivez au gérant" in ia.textes(0) and "x@agence.fr" not in ia.textes(0)
    e = lire_entreprises(user_id)[1]
    assert e["emails_trouves"] == ["recrutement@ent1.fr"] and e["emails_non_valides"] is False
    assert e["meilleur_contact"] == "recrutement@ent1.fr"      # adresse validée par les règles
    assert e["validation_emails"] == {"recrutement@ent1.fr": "regle"}


def test_relance_sans_site_verifie_tout_ecarte(alice, ia, pipelines_neufs):
    """Entreprise sans site vérifié (D160) : ses adresses douteuses sont écartées, sans IA."""
    client, user_id, _ = alice
    _revalider(client, user_id, pipelines_neufs)
    assert ia.appels == []
    assert [e["emails_trouves"] for e in lire_entreprises(user_id)] == [["rh0@ent0.fr"], [], []]
    assert "site de l'entreprise non vérifié" in client.get("/api/logs").text
def test_relance_ia_en_echec_passager_reste_a_valider(alice, ia, pipelines_neufs):
    client, user_id, _ = alice
    nominatives(user_id)
    echouer(ia, erreur_http(503))
    _revalider(client, user_id, pipelines_neufs)
    assert [e["emails_non_valides"] for e in lire_entreprises(user_id)] == [False, True, True]
    assert lire_entreprises(user_id)[1]["emails_trouves"] == ["camille1@ent1.fr"]
    assert len(client.get("/api/spontanees/a_valider").json()) == 2


def test_relance_ia_bloquante_un_message_et_arret(alice, ia, pipelines_neufs):
    client, user_id, _ = alice
    nominatives(user_id)
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
    source = (config.BASE_DIR / "offres" / "analyse.py").read_text(encoding="utf-8").lower()
    assert "maazi" not in source


def test_provenance_affichee_par_adresse(alice, ia, pipelines_neufs):
    client, user_id, ids = alice
    nominatives(user_id)
    liste = lire_entreprises(user_id)
    liste[0]["validation_emails"] = {"rh0@ent0.fr": "regle"}
    sauvegarder_enrichissement(user_id, liste)
    ia.file = ['{"valides": ["camille1@ent1.fr"], "meilleur_contact": "camille1@ent1.fr"}']
    _revalider(client, user_id, pipelines_neufs, max_revalidations=1)
    client.post("/api/spontanees/valider", json={"id": ids[2]})
    lignes = {e["id"]: e["adresses"] for e in client.get("/api/spontanees/stats").json()["prochaines"]}
    assert lignes[ids[0]] == [{"adresse": "rh0@ent0.fr", "validation": "regle", "meilleur": False}]
    assert lignes[ids[1]] == [{"adresse": "camille1@ent1.fr", "validation": "ia", "meilleur": True}]
    assert lignes[ids[2]] == [{"adresse": "camille2@ent2.fr", "validation": "manuelle", "meilleur": False}]
    js = (config.STATIC_DIR / "js" / "spontanees.js").read_text(encoding="utf-8")
    assert "validée par règle" in js and "validée par l'IA" in js and "validée à la main" in js


# ─── Adresses écartées par l'IA : visibles, validables quand même ────────────
def test_ecartee_par_l_ia_visible_et_validable(alice, ia, pipelines_neufs, smtp_simule, utilisateur):
    client, user_id, ids = alice
    nominatives(user_id)
    ia.file = ['{"valides": [], "meilleur_contact": null}', '{"valides": ["camille2@ent2.fr"], "meilleur_contact": null}']
    _revalider(client, user_id, pipelines_neufs)
    e1 = lire_entreprises(user_id)[1]
    assert e1["emails_trouves"] == [] and e1["emails_ecartes_ia"] == ["camille1@ent1.fr"]
    a_valider = {e["id"]: e for e in client.get("/api/spontanees/a_valider").json()}
    assert list(a_valider) == [ids[1]]                                  # plus de douteuse, mais visible
    assert a_valider[ids[1]]["adresses"] == [{"adresse": "camille1@ent1.fr", "validation": "ecartee_ia", "meilleur": False}]
    assert client.get("/api/spontanees/stats").json()["a_valider"] == 0   # rien à repasser à l'IA
    assert envoyeur.compter_a_envoyer(user_id, "alternance") == 2         # écartée : jamais envoyée
    # Une autre personne ne peut pas la valider
    client_b, _ = utilisateur("b@test.fr")
    assert client_b.post("/api/spontanees/valider_adresse", json={"id": ids[1], "adresse": "camille1@ent1.fr"}).status_code == 404
    # Validée quand même, à la main
    assert client.post("/api/spontanees/valider_adresse", json={"id": ids[1], "adresse": "camille1@ent1.fr"}).json() == {"ok": True}
    e1 = lire_entreprises(user_id)[1]
    assert e1["emails_trouves"] == ["camille1@ent1.fr"] and e1["validation_emails"]["camille1@ent1.fr"] == "manuelle"
    assert client.get("/api/spontanees/a_valider").json() == []
    assert envoyeur.compter_a_envoyer(user_id, "alternance") == 3
    assert client.post("/api/spontanees/valider_adresse", json={"id": ids[1], "adresse": "camille1@ent1.fr"}).status_code == 404
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


# ─── D216 : site vérifié par son titre seul, quelle que soit l'extension ──────
TITRE_EU = {"url": "https://www.ent.eu", "domaine": "ent.eu", "source": "recherche", "verifie": True, "preuve": "nom_titre"}


@pytest.mark.parametrize("site, attendu", [
    (TITRE_EU, True),
    ({**TITRE_EU, "domaine": "ent.fr"}, True),
    ({**TITRE_EU, "preuve": "titre_adresse"}, False),
    ({**TITRE_EU, "preuve": "domaine_adresse"}, False),
    ({**TITRE_EU, "preuve": "siren"}, False),
    ({**TITRE_EU, "preuve": "wikidata"}, False),
    ({**TITRE_EU, "verifie": False}, False),
    (None, False)])
def test_titre_seul(site, attendu):
    assert validation_emails.titre_seul(site) is attendu


def _eu(user_id, provenance, **champs):
    liste = lire_entreprises(user_id)
    liste[0].update(emails_trouves=["contact@ent.eu"], emails_douteux=[], emails_non_valides=False,
                    validation_emails=provenance, site_verifie=TITRE_EU, **champs)
    sauvegarder_enrichissement(user_id, liste[:1])
    return liste[0]["_id"]


@pytest.mark.parametrize("provenance", ["regle", "ia"])
def test_adresse_d_avant_jamais_envoyee_puis_validee_a_la_main(alice, smtp_simule, provenance):
    """Adresse déjà validée d'office en base (konicaminolta.eu) : ni l'envoi
    groupé ni la liste de la campagne, mais visible et validable."""
    client, user_id, _ = alice
    ident = _eu(user_id, {"contact@ent.eu": provenance})
    assert envoyeur.pretes(user_id, "alternance") == [] and envoyeur.compter_a_envoyer(user_id, "alternance") == 0
    assert envoyeur.main(user_id, limite=10)["envoyes"] == 0 and smtp_simule.messages == []
    ligne = next(x for x in client.get("/api/spontanees/a_valider").json() if x["id"] == ident)
    assert ligne["emails"] == ["contact@ent.eu"] and ligne["a_la_main"] and ligne["adresses"][0]["validation"] == "douteuse"
    assert valider_adresse(user_id, ident, "contact@ent.eu")
    assert [p["adresses"] for p in envoyeur.pretes(user_id, "alternance")] == [["contact@ent.eu"]]


def test_tout_valider_a_la_main(alice):
    _, user_id, _ = alice
    ident = _eu(user_id, {"contact@ent.eu": "regle"})
    assert valider_emails(user_id, ident) and [p["id"] for p in envoyeur.pretes(user_id, "alternance")] == [ident]


def test_l_ia_ne_les_revoit_pas(alice, monkeypatch):
    _, user_id, _ = alice
    avant = compter_a_valider(user_id, "alternance")
    _eu(user_id, {"contact@ent.eu": "regle"})
    assert compter_a_valider(user_id, "alternance") == avant            # le maximum d'une revalidation
    vues = []
    monkeypatch.setattr(config, "ANALYSE_IA", True, raising=False)
    monkeypatch.setattr(se, "analyse_ia_active", lambda: True)
    monkeypatch.setattr(se, "trier", lambda emails, *a, **k: vues.append(emails) or {
        "valides": [], "douteux": list(emails), "contextes": {}, "provenance": {}, "ecartes_ia": [], "ecartes": [],
        "meilleur_contact": None})
    se.revalider(user_id)
    assert vues and ["contact@ent.eu"] not in vues


def test_adresse_de_la_bonne_alternance_pas_concernee():
    e = {"emails_trouves": ["rh@ent.eu"], "emails_douteux": [], "validation_emails": {}, "site_verifie": TITRE_EU}
    assert validation_emails.emails_valides(e) == ["rh@ent.eu"]


def test_lecture_du_site_rien_de_valide_sans_appel_a_l_ia(monkeypatch):
    monkeypatch.setattr(validation_emails, "avis_ia", lambda *a, **k: pytest.fail("IA appelée"))
    tri = validation_emails.trier(["contact@ent.eu", "camille@ent.eu", "x@autre.fr"], "ent.eu", nom="Ent", verifie=True,
                                  a_la_main=True)
    assert tri["valides"] == [] and tri["douteux"] == ["contact@ent.eu", "camille@ent.eu"]
    assert [a for a, _ in tri["ecartes"]] == ["x@autre.fr"]


def test_le_scraper_les_met_a_valider(monkeypatch):
    import spontanees.site_officiel as S
    from tests.faux_web import FauxWeb, brancher, site
    for racine in ("https://acme-labo.eu", "https://acme-labo.fr"):
        mail = f"contact@{racine.split('//')[1]}"
        brancher(monkeypatch, FauxWeb(site(racine=racine, nom="ACME LABO", siren_dans_mentions=False, emails=(mail,))))
        v = S.verifier(racine, {"nom": "ACME LABO", "siren": "123456789"}, S.RECHERCHE)
        assert v.preuve == "nom_titre"
        r = se.scraper_et_extraire(v, "ACME LABO", ia=True)
        assert r["emails"] == [mail] and r["douteux"] == [mail]


def test_titre_et_adresse_sirene_part_normalement(monkeypatch):
    """Cas samsic.fr : le site porte l'adresse Sirene de l'établissement."""
    import spontanees.site_officiel as S
    from tests.faux_web import FauxWeb, brancher, site
    pages = site(racine="https://acme-labo.fr", nom="ACME LABO", siren_dans_mentions=False, emails=("contact@acme-labo.fr",))
    pages = {u: p.replace("</body>", "<p>85 Bd du Montparnasse 75006 Paris</p></body>") if isinstance(p, str) else p
             for u, p in pages.items()}
    brancher(monkeypatch, FauxWeb(pages))
    e = {"nom": "ACME LABO", "siren": "123456789", "code_postal": "75006"}
    v = S.verifier("https://acme-labo.fr", e, S.RECHERCHE)
    assert v.verifie and v.preuve == "titre_adresse" and "75006" in v.detail
    assert se.scraper_et_extraire(v, "ACME LABO", ia=True)["douteux"] == []
    assert S.verifier("https://acme-labo.fr", {**e, "code_postal": "75015"}, S.RECHERCHE).preuve == "nom_titre"


def _rejeter(client, ident, adresse):
    return client.post("/api/spontanees/rejeter_adresse", json={"id": ident, "adresse": adresse})


def test_rejeter_puis_valider_quand_meme(alice):
    client, user_id, ids = alice
    ident = _eu(user_id, {"contact@ent.eu": "regle"})
    assert _rejeter(client, ident, "contact@ent.eu").json() == {"ok": True}
    e = lire_entreprises(user_id)[0]
    assert e["emails_trouves"] == [] and e["emails_douteux"] == [] and e["validation_emails"] == {}
    assert not e["emails_non_valides"] and envoyeur.pretes(user_id, "alternance") == []
    ligne = next(x for x in client.get("/api/spontanees/a_valider").json() if x["id"] == ident)
    assert ligne["emails"] == [] and ligne["rejetees"] == ["contact@ent.eu"] and ligne["adresses"] == []
    assert _rejeter(client, ident, "contact@ent.eu").status_code == 404          # déjà traitée
    assert valider_adresse(user_id, ident, "contact@ent.eu")
    ligne = [x for x in client.get("/api/spontanees/a_valider").json() if x["id"] == ident]
    assert ligne == [] and [p["adresses"] for p in envoyeur.pretes(user_id, "alternance")] == [["contact@ent.eu"]]


def test_rejeter_une_adresse_laisse_les_autres(alice):
    client, user_id, ids = alice
    liste = lire_entreprises(user_id)
    liste[1].update(emails_trouves=["a@gmail.com", "b@gmail.com"], emails_douteux=["a@gmail.com", "b@gmail.com"],
                    contextes_emails={"a@gmail.com": "x", "b@gmail.com": "y"}, meilleur_contact="a@gmail.com")
    sauvegarder_enrichissement(user_id, liste[1:2])
    assert _rejeter(client, ids[1], "a@gmail.com").json() == {"ok": True}
    e = lire_entreprises(user_id)[1]
    assert e["emails_trouves"] == e["emails_douteux"] == ["b@gmail.com"] and e["emails_non_valides"] is True
    assert e["contextes_emails"] == {"b@gmail.com": "y"} and e["meilleur_contact"] is None


def test_rejeter_entreprise_d_avant_la_phase_7(alice):
    client, user_id, ids = alice
    liste = lire_entreprises(user_id)
    liste[1].update(emails_trouves=["a@gmail.com", "b@gmail.com"])
    sauvegarder_enrichissement(user_id, liste[1:2])
    assert lire_entreprises(user_id)[1]["emails_douteux"] is None
    assert _rejeter(client, ids[1], "a@gmail.com").json() == {"ok": True}
    assert envoyeur.emails_valides(lire_entreprises(user_id)[1]) == []            # b@ attend toujours


def test_rejeter_une_adresse_ecartee_par_l_ia(alice):
    client, user_id, ids = alice
    liste = lire_entreprises(user_id)
    liste[0].update(emails_ecartes_ia=["c@gmail.com"])
    sauvegarder_enrichissement(user_id, liste[:1])
    assert _rejeter(client, ids[0], "c@gmail.com").json() == {"ok": True}
    e = lire_entreprises(user_id)[0]
    assert e["emails_ecartes_ia"] == [] and e["emails_trouves"] == ["rh0@ent0.fr"]
    assert _rejeter(client, ids[0], "rh0@ent0.fr").status_code == 404             # adresse validée : pas concernée


def test_adresse_rejetee_jamais_reprise(alice):
    """Nouvelle recherche d'emails, liste lue avant le rejet, ou La Bonne Alternance."""
    from database.entreprises_db import ajouter_entreprises_lba
    client, user_id, _ = alice
    ident = _eu(user_id, {"contact@ent.eu": "regle"})
    ancienne = lire_entreprises(user_id)[:1]
    assert _rejeter(client, ident, "contact@ent.eu").json() == {"ok": True}
    ancienne[0].update(emails_trouves=["contact@ent.eu", "rh@ent.eu"], emails_douteux=["contact@ent.eu", "rh@ent.eu"],
                       emails_ecartes_ia=["contact@ent.eu"], validation_emails={"contact@ent.eu": "regle"})
    sauvegarder_enrichissement(user_id, ancienne)
    e = lire_entreprises(user_id)[0]
    assert e["emails_trouves"] == e["emails_douteux"] == ["rh@ent.eu"]
    assert e["emails_ecartes_ia"] == [] and e["validation_emails"] == {}
    from database.connexion import SessionLocal
    from database.models import Entreprise
    db = SessionLocal()
    db.get(Entreprise, ident).siren = "111222333"
    db.commit()
    db.close()
    ajouter_entreprises_lba(user_id, [{"siret": "11122233300011", "siren": "111222333", "nom": "ENT", "email": "contact@ent.eu"}])
    assert lire_entreprises(user_id)[0]["emails_trouves"] == ["rh@ent.eu"]


def test_rejeter_entreprise_d_un_autre(alice, utilisateur):
    _, user_id, _ = alice
    ident = _eu(user_id, {"contact@ent.eu": "regle"})
    client_b, _ = utilisateur("b@test.fr", prenom="Bob")
    assert _rejeter(client_b, ident, "contact@ent.eu").status_code == 404
    assert lire_entreprises(user_id)[0]["emails_trouves"] == ["contact@ent.eu"]


def test_adresse_a_valider_pas_affichee_prete(alice):
    """Interface : l'entreprise n'est « prête à envoyer » que par une adresse validée."""
    client, user_id, _ = alice
    ident = _eu(user_id, {"contact@ent.eu": "regle"})
    ligne = next(e for e in client.get("/api/spontanees/stats").json()["prochaines"] if e["id"] == ident)
    assert ligne["email"] == "" and ligne["adresses"][0]["validation"] == "douteuse"
    assert valider_adresse(user_id, ident, "contact@ent.eu")
    ligne = next(e for e in client.get("/api/spontanees/stats").json()["prochaines"] if e["id"] == ident)
    assert ligne["email"] == "contact@ent.eu"


def test_onglet_adresses_a_valider():
    page = (config.TEMPLATES_DIR / "partials" / "spontanees.html").read_text(encoding="utf-8")
    assert 'data-filter="a_valider"' in page and 'data-sp-nombre="a_valider"' in page
