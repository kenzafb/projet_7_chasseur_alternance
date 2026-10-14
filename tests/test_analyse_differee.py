"""Analyse en différé des offres « non analysées » (D21, phase 7) : ordre,
limite, archivage complet, échecs sans résultat inventé, arrêt, temps
restant, lancement automatique après la recherche."""

import threading
from datetime import datetime, timezone

import httpx
import pytest

import main
from database.candidatures_db import ajouter_candidature, compter_en_attente, lire_candidature, lire_en_attente
from france_travail.analyse_differee import analyser_en_attente, duree_lisible
from france_travail.analyseur import marquer_non_analysee
from tests.conftest import erreur_http
from tests.test_envoyeur import attendre
from tests.test_ia import INTROUVABLE, echouer, recherche, sans_attente, texte_envoye  # noqa: F401  (fixtures)


def analyse(score=8, eligible=True, domaine="Développement"):
    return ('{"score": %d, "eligible": %s, "points_forts": ["a"], "points_faibles": [], '
            '"domaine": "%s", "resume": "ok"}' % (score, "true" if eligible else "false", domaine))


def en_attente(uid, ref, jour, titre=None, mode="alternance", **champs):
    offre = marquer_non_analysee({"id": ref, "titre": titre or f"Poste {ref}", "description": "...",
                                  "date_trouvee": datetime(2026, 10, jour, tzinfo=timezone.utc), **champs},
                                 mode=mode, verbeux=False)
    ajouter_candidature(uid, offre, mode=mode)


@pytest.fixture
def alice(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    return client, uid


def lancer(client, uid, **corps):
    r = client.post("/api/analyse", json=corps)
    assert r.status_code == 200, r.text
    attendre(lambda: not main.pipelines.etat("analyse", uid)["en_cours"])
    return r.json(), main.pipelines.etat("analyse", uid)


# ─── File d'attente ──────────────────────────────────────────────────────────
def test_plus_recentes_d_abord_archivees_exclues(alice):
    _, uid = alice
    en_attente(uid, "A", 1)
    en_attente(uid, "B", 9)
    en_attente(uid, "C", 5)
    en_attente(uid, "D", 12, titre="Dev", description="Poste réservé aux bénéficiaires de l'obligation d'emploi.")
    ajouter_candidature(uid, {"id": "E", "titre": "déjà notée", "score": 7, "verdict": "bon"})
    assert lire_candidature(uid, "D")["statut"] == "archive"   # archivée à l'insertion : pas analysée
    assert [o["id"] for o in lire_en_attente(uid, "alternance")] == ["B", "C", "A"]
    assert [o["id"] for o in lire_en_attente(uid, "alternance", limite=2)] == ["B", "C"]
    assert compter_en_attente(uid, "alternance") == 3 and compter_en_attente(uid, "job") == 0


def test_analyse_par_la_route(alice, ia):
    client, uid = alice
    for ref, jour in (("A", 1), ("B", 2), ("C", 3)):
        en_attente(uid, ref, jour)
    ia.reponse = analyse(8)
    reponse, etat = lancer(client, uid, max_analyses=2)
    assert reponse == {"status": "démarré", "max_analyses": 2, "en_attente": 3}
    assert [texte_envoye(a).count("Poste C") for a in ia.appels] == [1, 0]   # C, puis B
    for ref, attendu in (("C", "bon"), ("B", "bon"), ("A", "non_analysee")):
        assert lire_candidature(uid, ref)["verdict"] == attendu
    c = lire_candidature(uid, "C")
    assert (c["score"], c["domaine"], c["points_forts"], c["resume_analyse"]) == (8, "Développement", ["a"], "ok")
    assert etat["message"].startswith("Terminée : 2 offres analysées")
    assert (etat["faites"], etat["total"], etat["pourcentage"]) == (2, 2, 100)
    assert "[1/2] « Poste C » : 8/10, bon" in client.get("/api/logs").text


def test_limite_bornee_par_le_nombre_en_attente(alice, ia):
    client, uid = alice
    en_attente(uid, "A", 1)
    ia.reponse = analyse()
    reponse, _ = lancer(client, uid, max_analyses=10**6)
    assert reponse["max_analyses"] == 1
    assert "ramené à 1" in client.get("/api/logs").text


def test_refus_avant_lancement(alice, ia):
    client, uid = alice
    r = client.post("/api/analyse", json={})
    assert r.status_code == 400 and "Aucune offre en attente" in r.json()["erreur"]
    assert client.post("/api/analyse", json={"max_offres": 3}).status_code == 422
    en_attente(uid, "A", 1)
    main.pipelines.demarrer("analyse", uid, mode="job")
    r = client.post("/api/analyse", json={})
    assert r.status_code == 400 and "Analyse déjà en cours (mode job)" in r.json()["erreur"]
    assert ia.appels == []


# ─── Archivage complet après l'analyse ───────────────────────────────────────
@pytest.mark.parametrize("mode, reponse, raison", [
    ("alternance", analyse(7, domaine="Hors domaine"), "hors_domaine"),
    ("alternance", analyse(2, eligible=False), "note_basse"),
    ("job", analyse(1, eligible=False), "note_basse"),
    ("stage", analyse(6, domaine="Hors domaine"), "hors_domaine"),
])
def test_archivage_fonde_sur_l_analyse(alice, ia, mode, reponse, raison):
    client, uid = alice
    client.mode = mode
    client.post("/api/profil", json={"prenom": "Alice"})
    en_attente(uid, "A", 1, mode=mode)
    ia.reponse = reponse
    lancer(client, uid)
    o = lire_candidature(uid, "A", mode=mode)
    assert (o["statut"], o["raison_archivage"]) == ("archive", raison)


@pytest.mark.parametrize("mode, archivee", [("alternance", True), ("stage", False)])
def test_ecole_archivee_en_alternance_seulement(alice, ia, mode, archivee):
    client, uid = alice
    client.mode = mode
    client.post("/api/profil", json={"prenom": "Alice"})
    en_attente(uid, "A", 1, mode=mode, titre="Développeur", entreprise="Epitech")
    if mode == "alternance":
        # À l'insertion déjà ; on remet l'offre en attente pour voir l'effet de l'analyse
        main.modifier_candidature(uid, "A", {"statut": "nouveau", "raison_archivage": ""}, mode=mode)
    ia.reponse = analyse(8)
    lancer(client, uid)
    assert (lire_candidature(uid, "A", mode=mode)["statut"] == "archive") is archivee


def test_offre_deplacee_par_l_utilisateur_pas_archivee(alice, ia):
    client, uid = alice
    en_attente(uid, "A", 1)
    main.modifier_candidature(uid, "A", {"statut": "en_cours"})
    ia.reponse = analyse(1, eligible=False)
    lancer(client, uid)
    o = lire_candidature(uid, "A")
    assert (o["statut"], o["score"], o["verdict"]) == ("en_cours", 1, "ineligible")


# ─── Échecs : rien d'inventé ─────────────────────────────────────────────────
def test_reponse_invalide_offre_sautee_puis_reprise(alice, ia):
    client, uid = alice
    en_attente(uid, "A", 1)
    en_attente(uid, "B", 2)
    ia.panne = lambda corps: '{"score": "huit"}' if "Poste B" in texte_envoye(corps) else None
    ia.reponse = analyse(6)
    _, etat = lancer(client, uid)
    assert lire_candidature(uid, "B")["verdict"] == "non_analysee" and lire_candidature(uid, "B")["score"] is None
    assert lire_candidature(uid, "A")["score"] == 6
    assert len(ia.appels) == 3                        # B demandée deux fois, A une fois
    assert "1 sautées" in etat["message"] and "« Poste B » sautée" in client.get("/api/logs").text
    ia.panne = None
    lancer(client, uid)
    assert lire_candidature(uid, "B")["score"] == 6


@pytest.mark.parametrize("panne, message", [
    (httpx.ConnectError("refused"), "IA locale injoignable : vérifie qu'Ollama tourne"),
    (erreur_http(404, INTROUVABLE), "Modèle « ministral-3:8b » introuvable"),
])
def test_erreur_bloquante_arrete_tout(alice, ia, panne, message):
    client, uid = alice
    en_attente(uid, "A", 1)
    en_attente(uid, "B", 2)
    echouer(ia, panne)
    _, etat = lancer(client, uid)
    assert etat["message"].startswith("Erreur : ") and message in etat["message"]
    assert len(ia.demarrages) == 1 and ia.appels == []                                 # arrêt immédiat
    assert compter_en_attente(uid, "alternance") == 2             # rien d'écrit
    assert "Analyse arrêtée" in client.get("/api/logs").text


def test_demarrage_echoue_analyse_non_lancee(alice, ia):
    client, uid = alice
    en_attente(uid, "A", 1)
    ia.demarrage = "Bien sûr ! Voici le JSON demandé."
    _, etat = lancer(client, uid)
    assert etat["message"].startswith("Erreur : Test de démarrage échoué")
    assert ia.appels == [] and compter_en_attente(uid, "alternance") == 1


# ─── Arrêt et temps restant ──────────────────────────────────────────────────
def test_arret_apres_l_offre_en_cours(alice, ia, monkeypatch):
    client, uid = alice
    for i in range(1, 5):
        en_attente(uid, f"R{i}", i)
    premiere, liberer = threading.Event(), threading.Event()
    import shared.ia

    def lente(url, corps, entetes, delai):
        from tests.conftest import reponse_chat
        if "TEST DE DÉMARRAGE" in corps["messages"][-1]["content"]:
            return reponse_chat('{"nombre": 7, "mot": "ok"}')
        ia.appels.append(corps)
        premiere.set()
        liberer.wait(5)
        from tests.conftest import reponse_chat
        return reponse_chat(analyse(7))

    monkeypatch.setattr(shared.ia, "_poster", lente)
    assert client.post("/api/analyse", json={}).status_code == 200
    assert premiere.wait(5)
    assert client.post("/api/analyse/stop").json() == {"ok": True, "en_cours": True}
    liberer.set()
    attendre(lambda: not main.pipelines.etat("analyse", uid)["en_cours"])
    assert len(ia.appels) == 1 and compter_en_attente(uid, "alternance") == 3
    assert main.pipelines.etat("analyse", uid)["message"].startswith("Arrêtée : 1 offres analysées")
    assert client.post("/api/analyse/stop").json()["en_cours"] is False


def test_temps_restant_estime(alice, ia):
    _, uid = alice
    for i in range(1, 4):
        en_attente(uid, f"R{i}", i)
    ia.reponse = analyse()
    temps = iter([0, 90, 200, 300])   # début, puis fin de chaque offre (secondes)
    suivi = []
    analyser_en_attente(uid, "alternance", {"prenom": "Alice"}, 3, horloge=lambda: next(temps),
                        on_progress=lambda f, t, r: suivi.append((f, t, r)), log=lambda m: None)
    assert suivi == [(0, 3, None), (1, 3, 180.0), (2, 3, 100.0), (3, 3, 0.0)]
    assert duree_lisible(None) == "" and duree_lisible(20) == "moins d'une minute"
    assert duree_lisible(180) == "environ 3 min" and duree_lisible(4000) == "environ 1 h 07"


def test_progression_dans_l_etat(alice, ia, monkeypatch):
    client, uid = alice
    for i in range(1, 3):
        en_attente(uid, f"R{i}", i)
    vus = []
    reel = main.pipelines.maj
    monkeypatch.setattr(main.pipelines, "maj", lambda t, u, **c: (vus.append(c.get("message")), reel(t, u, **c)))
    ia.reponse = analyse()
    lancer(client, uid)
    assert any(m and m.startswith("Analyse 1/2") and "restantes" in m for m in vus)
    statut = client.get("/api/analyse/statut").json()
    assert statut["en_attente"] == 0 and statut["en_cours"] is False
    assert "analyse" in client.get("/api/statut_pipelines").json()


# ─── Lancement automatique après la recherche ────────────────────────────────
def test_analyse_automatique_apres_la_recherche(recherche, ia):
    recherche.client.post("/api/profil", json={"prenom": "Alice", "analyse_auto": True})
    assert recherche.client.get("/api/profil").json()["analyse_auto"] is True
    ia.reponse = analyse(9)
    recherche.lancer()
    attendre(lambda: not main.pipelines.etat("analyse", recherche.user_id)["en_cours"])
    assert compter_en_attente(recherche.user_id, "alternance") == 0
    assert len(ia.appels) == 3
    assert "(automatique après la recherche)" in recherche.client.get("/api/logs").text


def test_pas_d_analyse_automatique_sans_l_option(recherche, ia):
    assert recherche.client.get("/api/profil").json()["analyse_auto"] is False
    recherche.lancer()
    assert ia.appels == [] and not main.pipelines.etat("analyse", recherche.user_id)["en_cours"]
    assert compter_en_attente(recherche.user_id, "alternance") == 3


def test_option_propre_au_mode(alice):
    client, _ = alice
    client.post("/api/profil", json={"prenom": "Alice", "analyse_auto": True})
    client.mode = "job"
    assert client.get("/api/profil").json().get("analyse_auto") in (None, False)


# ─── Interface ───────────────────────────────────────────────────────────────
def test_interface(alice):
    client, _ = alice
    page = client.get("/alternance").text
    assert "data-analyse-lancer" in page and 'data-limite="analyses" value="10"' in page
    assert "ministral-3:8b" in page and 'data-profil-case="analyse_auto"' in page
    from shared import config
    app = (config.STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    assert "api.analyseStop()" in app and "api.analyseAttente(" in app
    offres = (config.STATIC_DIR / "js" / "offres.js").read_text(encoding="utf-8")
    assert "Analyse en cours… (1 à 2 min)" in offres
