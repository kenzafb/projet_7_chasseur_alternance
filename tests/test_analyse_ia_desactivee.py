"""ANALYSE_IA=false : aucun appel à l'IA nulle part ; offres insérées
« non analysées », marquées vues, archivées seulement par mots-clés ;
lettre, réanalyse et revalidation refusées ; scraper en lecture directe."""

import pytest

import main
from database.candidatures_db import ajouter_candidature, lire_candidature, lire_candidatures
from database.dedup_db import lire_offres_vues
from database.entreprises_db import lire_entreprises, sauvegarder_enrichissement
from france_travail.analyseur import VERDICT_NON_ANALYSEE, marquer_non_analysee
from shared import config
from shared.ia import IADesactivee, appeler_ia
from tests.test_ia import _brut_ft, _lba, recherche, sans_attente  # noqa: F401  (fixtures)
from tests.test_scraper_sans_ia import _lancer, sites, user_id  # noqa: F401  (fixtures)


@pytest.fixture
def ia_coupee(monkeypatch):
    monkeypatch.setenv("ANALYSE_IA", "false")


@pytest.mark.parametrize("valeur, attendu", [(None, True), ("", True), ("true", True), ("1", True),
                                             ("false", False), ("FALSE", False), ("0", False),
                                             ("non", False), ("off", False)])
def test_interrupteur(monkeypatch, valeur, attendu):
    if valeur is None:
        monkeypatch.delenv("ANALYSE_IA", raising=False)
    else:
        monkeypatch.setenv("ANALYSE_IA", valeur)
    assert config.analyse_ia_active() is attendu


def test_appel_ia_refuse(ia_coupee, ia):
    with pytest.raises(IADesactivee, match="ANALYSE_IA=false"):
        appeler_ia([{"role": "user", "content": "x"}])
    assert ia.appels == []


# ─── Recherche ────────────────────────────────────────────────────────────────
def test_recherche_sans_analyse(ia_coupee, recherche, ia):
    recherche.sources["lba"] = [_lba(0)]
    etat = recherche.lancer()
    assert etat["message"] == "Terminé !"
    assert ia.appels == []
    offres = {c["titre"]: c for c in lire_candidatures(recherche.user_id)}
    assert set(offres) == {"Poste 0", "Poste 1", "Poste 2", "Alternance 0"}
    for o in offres.values():
        assert (o["score"], o["verdict"], o["statut"]) == (None, VERDICT_NON_ANALYSEE, "nouveau")
        assert o["points_forts"] == [] and o["resume_analyse"] == ""
    assert len(lire_offres_vues(recherche.user_id, "alternance")) == 3   # les offres FT
    # Marquées vues : un second lancement ne les reprend pas
    recherche.lancer()
    assert len(lire_candidatures(recherche.user_id)) == 4


def test_recherche_sans_analyse_respecte_la_limite(ia_coupee, recherche):
    recherche.sources["lba"] = [_lba(0)]
    recherche.lancer(max_offres=2)
    assert {c["titre"] for c in lire_candidatures(recherche.user_id)} == {"Poste 0", "Poste 1"}
    assert len(lire_offres_vues(recherche.user_id, "alternance")) == 2


def test_pas_d_archivage_fonde_sur_l_analyse():
    # Ni note basse ni hors domaine : rien ne les établit sans IA
    offre = marquer_non_analysee({"titre": "Développeur", "description": "Missions variées.", "statut": "nouveau"})
    assert offre["statut"] == "nouveau" and offre["raison_archivage"] == ""


@pytest.mark.parametrize("offre, raison", [
    ({"titre": "Dev", "description": "Poste réservé aux bénéficiaires de l'obligation d'emploi."},
     "public_specifique"),
    ({"titre": "Dev", "entreprise": "Epitech", "description": "..."}, "ecole_cfa"),
    ({"titre": "Stage développeur", "description": "..."}, "stage"),
])
def test_archivage_par_mots_cles_garde(offre, raison):
    marquer_non_analysee(offre, verbeux=False)
    assert (offre["statut"], offre["raison_archivage"]) == ("archive", raison)


def test_mode_job_aucun_archivage():
    offre = marquer_non_analysee({"titre": "Stage vente", "description": "..."}, mode="job")
    assert "statut" not in offre or offre["statut"] != "archive"


def test_non_analysees_triees_en_dernier(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_candidature(uid, marquer_non_analysee({"id": "NA", "titre": "x", "description": ""}))
    ajouter_candidature(uid, {"id": "A", "titre": "y", "score": 3, "verdict": "faible"})
    assert [c["id"] for c in lire_candidatures(uid)] == ["A", "NA"]


# ─── Routes directes ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("route", ["/api/lettre/paragraphe", "/api/analyser"])
def test_lettre_et_reanalyse_refusees(ia_coupee, utilisateur, ia, route):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    client.post("/api/profil", json={"prenom": "Alice", "nom": "A", "email": "a@test.fr", "lettre_type": "{paragraphe}"})
    ajouter_candidature(uid, marquer_non_analysee({"id": "REF1", "titre": "Dev", "description": "..."}))
    r = client.post(route, json={"id": "REF1"})
    assert r.status_code == 503 and "IA est désactivée" in r.json()["erreur"]
    assert ia.appels == []
    assert lire_candidature(uid, "REF1")["verdict"] == VERDICT_NON_ANALYSEE


def test_interface(ia_coupee, utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = client.get("/alternance").text
    assert 'data-analyse-ia="non"' in page and "data-bandeau-ia" in page and "IA désactivée" in page
    assert 'data-action="revalider"' not in page
    js = (config.STATIC_DIR / "js" / "offres.js").read_text(encoding="utf-8")
    assert "non analysée" in js and "écris toi-même le paragraphe personnalisé" in js


def test_interface_ia_active(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = client.get("/alternance").text
    assert 'data-analyse-ia="oui"' in page and "data-bandeau-ia" not in page
    assert 'data-action="revalider"' in page


# ─── Scraper et validation des emails ────────────────────────────────────────
def test_scraper_regles_seules(ia_coupee, sites, user_id, ia):
    sites.douteux = {"acme2.fr", "acme3.fr"}
    entreprises, logs = _lancer(user_id)
    assert ia.appels == []
    assert entreprises["ACME 1"]["emails_trouves"] and entreprises["ACME 1"]["emails_non_valides"] is False
    for nom in ("ACME 2", "ACME 3"):
        assert entreprises[nom]["emails_trouves"] and entreprises[nom]["emails_non_valides"] is True
    assert logs.count("IA désactivée") == 1 and "IA indisponible" not in logs


def test_revalidation_refusee(ia_coupee, user_id, ia, utilisateur):
    liste = lire_entreprises(user_id)
    liste[0].update(emails_trouves=["a@acme1.fr"], emails_non_valides=True, traite=True)
    sauvegarder_enrichissement(user_id, liste)
    from spontanees.scraper_emails import revalider
    logs = []
    revalider(user_id, log_fn=logs.append)
    assert ia.appels == [] and "IA désactivée" in logs[0]
    assert lire_entreprises(user_id)[0]["emails_non_valides"] is True


def test_route_revalider_refusee(ia_coupee, utilisateur):
    client, _ = utilisateur("b@test.fr", prenom="Bob")
    r = client.post("/api/spontanees/revalider", json={})
    assert r.status_code == 400 and "IA est désactivée" in r.json()["erreur"]


# ─── Plafond de la recherche, avec ou sans IA (D20) ──────────────────────────
@pytest.mark.parametrize("coupee", [True, False])
def test_limite_de_la_recherche_avec_ou_sans_ia(recherche, monkeypatch, coupee):
    if coupee:
        monkeypatch.setenv("ANALYSE_IA", "false")
    recherche.sources["ft"] = [_brut_ft(i) for i in range(150)]
    defaut = 100 if coupee else 30          # avec l'IA : 30, à analyser ensuite
    r = recherche.client.post("/api/recherche", json=None)
    assert r.json()["max_offres"] == defaut
    from tests.test_envoyeur import attendre
    attendre(lambda: not main.pipelines.etat("recherche", recherche.user_id)["en_cours"])
    assert len(lire_candidatures(recherche.user_id)) == defaut
    r = recherche.client.post("/api/recherche", json={"max_offres": 10**6})
    assert r.json()["max_offres"] == 500
    attendre(lambda: not main.pipelines.etat("recherche", recherche.user_id)["en_cours"])
    assert "ramené à 500" in recherche.client.get("/api/logs").text


def test_interface_plafond_de_la_recherche(ia_coupee, utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = client.get("/alternance").text
    assert "Offres ajoutées au plus par recherche (max 500)" in page
    assert 'data-limite="offres" value="100"' in page and 'max="500"' in page


# ─── Analyse des offres en attente ───────────────────────────────────────────
def test_analyse_en_attente_refusee(ia_coupee, utilisateur, ia):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_candidature(uid, marquer_non_analysee({"id": "REF1", "titre": "Dev", "description": "..."}))
    r = client.post("/api/analyse", json={})
    assert r.status_code == 400 and "IA est désactivée" in r.json()["erreur"]
    assert ia.appels == [] and lire_candidature(uid, "REF1")["verdict"] == VERDICT_NON_ANALYSEE
    page = client.get("/alternance").text
    assert "data-analyse-lancer" not in page and "les offres restent sans note" in page


def test_analyse_automatique_pas_lancee_sans_ia(ia_coupee, recherche, ia):
    recherche.client.post("/api/profil", json={"prenom": "Alice", "analyse_auto": True})
    recherche.lancer()
    assert ia.appels == [] and len(lire_candidatures(recherche.user_id)) == 3
    assert "Analyse automatique non lancée" in recherche.client.get("/api/logs").text
