"""IA locale (format compatible OpenAI) : configuration, erreurs classées,
un seul appel à la fois, et plus jamais de résultat inventé (offre ni
écrite, ni marquée vue, ni archivée en cas d'échec)."""

import threading
import time
from types import SimpleNamespace

import httpx
import pytest

import france_travail.scraper as scraper
import main
import shared.ia
from database.candidatures_db import ajouter_candidature, lire_candidature, lire_candidatures
from database.dedup_db import lire_offres_vues
from france_travail.analyseur import analyser_offre
from france_travail.generateur import generer_lettre
from shared import config
from shared.ia import (ErreurIABloquante, ErreurIAPassagere, IAInjoignable, ReponseInvalide, appeler_ia,
                       appeler_structure)
from shared.schemas_ia import AnalyseOffre, LettreIA
from tests.conftest import erreur_http, reponse_chat
from tests.test_envoyeur import attendre

ANALYSE = '{"score": 8, "eligible": true, "points_forts": ["a"], "points_faibles": [], "domaine": "Dev", "resume": "ok"}'
INTROUVABLE = 'model "ministral-3:8b" not found, try pulling it first'
MESSAGE = [{"role": "user", "content": "x"}]


@pytest.fixture(autouse=True)
def sans_attente(monkeypatch):
    """Retries instantanés."""
    monkeypatch.setattr(shared.ia, "time", SimpleNamespace(sleep=lambda s: None, monotonic=time.monotonic))


def echouer(ia, erreur, si=lambda corps: True):
    """La fausse IA renvoie (ou lève) `erreur` pour les appels où si(corps) est vrai."""
    ia.panne = lambda corps: erreur if si(corps) else None


def texte_envoye(corps):
    return " ".join(m["content"] for m in corps["messages"])


def connexion_refusee():
    return httpx.ConnectError("[Errno 111] Connection refused")


# ─── Configuration ───────────────────────────────────────────────────────────
def test_modeles_par_defaut():
    assert config.modele_ia("analyse") == "ministral-3:8b"
    assert config.modele_ia("lettre") == "ministral-3:8b"
    assert config.modele_ia("extraction") == "ministral-3:3b"


def test_modele_par_usage(monkeypatch):
    monkeypatch.setenv("IA_MODELE_EXTRACTION", "qwen3.5:4b")
    monkeypatch.setenv("IA_MODELE_LETTRE", "  ")   # vide : défaut
    assert config.modele_ia("extraction") == "qwen3.5:4b"
    assert config.modele_ia("lettre") == "ministral-3:8b"


def test_serveur_et_cle(ia, monkeypatch):
    appeler_ia(MESSAGE)
    assert ia.urls[-1] == "http://localhost:11434/v1/chat/completions"
    monkeypatch.setenv("IA_BASE_URL", "http://serveur:8080/v1/")
    monkeypatch.setenv("IA_API_KEY", "secret")
    entetes = {}
    monkeypatch.setattr(shared.ia, "_poster", lambda url, corps, e, delai: entetes.update(e, url=url, delai=delai)
                        or reponse_chat("ok"))
    assert appeler_ia(MESSAGE) == "ok"
    assert entetes["url"] == "http://serveur:8080/v1/chat/completions"
    assert entetes["Authorization"] == "Bearer secret"


def test_delai_configurable(monkeypatch):
    assert config.ia_delai_s() == 600
    monkeypatch.setenv("IA_DELAI_S", "1200")
    assert config.ia_delai_s() == 1200
    monkeypatch.setenv("IA_DELAI_S", "abc")
    assert config.ia_delai_s() == 600


def test_chaque_usage_appelle_son_modele(ia, monkeypatch):
    monkeypatch.setenv("IA_MODELE_ANALYSE", "modele-analyse")
    monkeypatch.setenv("IA_MODELE_LETTRE", "modele-lettre")
    monkeypatch.setenv("IA_MODELE_EXTRACTION", "modele-extraction")
    profil = {"prenom": "A", "nom": "B", "email": "a@b.fr"}
    ia.reponse = ANALYSE
    analyser_offre({"titre": "Dev", "description": "..."}, profil)
    ia.reponse = '{"contact_entreprise": "ACME", "paragraphe_entreprise": "ACME me parle."}'
    generer_lettre({"titre": "Dev", "entreprise": "ACME"}, profil)
    import spontanees.scraper_emails as se
    ia.reponse = '{"emails": [], "telephones": [], "contact_rh": null, "fiable": true}'
    se.ia_extraire_contact("page", "ACME", [])
    assert [a["model"] for a in ia.appels] == ["modele-analyse", "modele-lettre", "modele-extraction"]


def test_plus_de_mistral():
    for fichier in ("shared/ia.py", "shared/config.py", "requirements.txt"):
        texte = (config.BASE_DIR / fichier).read_text(encoding="utf-8").lower()
        assert "mistralai" not in texte and "mistral_api_key" not in texte


# ─── Classement des erreurs ──────────────────────────────────────────────────
@pytest.mark.parametrize("statut", [400, 401, 403, 404, 422])
def test_erreurs_bloquantes(ia, statut):
    echouer(ia, erreur_http(statut))
    with pytest.raises(ErreurIABloquante) as exc:
        appeler_ia(MESSAGE, tentatives=4)
    assert exc.value.statut == statut and len(ia.appels) == 1


@pytest.mark.parametrize("statut", [429, 500, 502, 503])
def test_erreurs_passageres_retentees(ia, statut):
    echouer(ia, erreur_http(statut))
    with pytest.raises(ErreurIAPassagere):
        appeler_ia(MESSAGE, tentatives=3)
    assert len(ia.appels) == 3


def test_passagere_puis_reussite(ia):
    ia.file = [erreur_http(503), reponse_chat("bonjour")]
    assert appeler_ia(MESSAGE) == "bonjour" and len(ia.appels) == 2


def test_ollama_injoignable_bloquant(ia):
    echouer(ia, connexion_refusee())
    with pytest.raises(IAInjoignable, match="IA locale injoignable : vérifie qu'Ollama tourne"):
        appeler_ia(MESSAGE, tentatives=4)
    assert len(ia.appels) == 1


def test_delai_depasse_passager_sans_retry(ia):
    echouer(ia, httpx.ReadTimeout("trop long"))
    with pytest.raises(ErreurIAPassagere, match="IA_DELAI_S"):
        appeler_ia(MESSAGE, tentatives=4)
    assert len(ia.appels) == 1


def test_messages_clairs(ia):
    echouer(ia, erreur_http(404, INTROUVABLE))
    with pytest.raises(ErreurIABloquante, match=r"ollama pull ministral-3:8b"):
        appeler_ia(MESSAGE)
    echouer(ia, erreur_http(401))
    with pytest.raises(ErreurIABloquante, match="IA_API_KEY"):
        appeler_ia(MESSAGE)
    echouer(ia, erreur_http(500, "model requires more system memory (9.1 GiB) than is available (6.2 GiB)"))
    with pytest.raises(ErreurIABloquante, match="Mémoire insuffisante"):
        appeler_ia(MESSAGE)


def test_raisonnement_retire_de_la_reponse(ia):
    ia.reponse = "<think>je réfléchis</think>\n{\"a\": 1}"
    assert appeler_ia(MESSAGE) == '{"a": 1}'


def test_reponse_illisible_passagere(ia):
    echouer(ia, httpx.Response(200, json={"rien": True}))
    with pytest.raises(ErreurIAPassagere, match="illisible"):
        appeler_ia(MESSAGE)


# ─── Un seul appel à la fois ─────────────────────────────────────────────────
def test_un_seul_appel_a_la_fois(ia, monkeypatch):
    en_cours, maximum, verrou = [0], [0], threading.Lock()

    def lent(url, corps, entetes, delai):
        with verrou:
            en_cours[0] += 1
            maximum[0] = max(maximum[0], en_cours[0])
        time.sleep(0.02)
        with verrou:
            en_cours[0] -= 1
        return reponse_chat("ok")

    monkeypatch.setattr(shared.ia, "_poster", lent)
    from tests.conftest import en_parallele
    assert en_parallele(lambda: appeler_ia(MESSAGE), 6) == []
    assert maximum[0] == 1


# ─── Réponses structurées ────────────────────────────────────────────────────
def test_schema_impose_et_reflexion_coupee(ia):
    ia.reponse = ANALYSE
    analyse = appeler_structure(MESSAGE, AnalyseOffre)
    assert analyse.score == 8
    corps = ia.appels[0]
    assert corps["response_format"]["type"] == "json_schema"
    assert corps["response_format"]["json_schema"]["schema"]["required"] == [
        "score", "eligible", "points_forts", "points_faibles", "domaine", "resume"]
    assert corps["reasoning_effort"] == "none" and corps["stream"] is False


def test_reflexion_et_format_reglables(ia, monkeypatch):
    ia.reponse = ANALYSE
    monkeypatch.setenv("IA_REFLEXION", "true")
    monkeypatch.setenv("IA_FORMAT_JSON", "json")
    appeler_structure(MESSAGE, AnalyseOffre)
    assert "reasoning_effort" not in ia.appels[-1] and ia.appels[-1]["response_format"] == {"type": "json_object"}
    monkeypatch.setenv("IA_FORMAT_JSON", "aucun")
    appeler_structure(MESSAGE, AnalyseOffre)
    assert "response_format" not in ia.appels[-1]


@pytest.mark.parametrize("texte", ['```json\n{"valide": true}\n```', 'Voici : {"valide": true} !'])
def test_json_entoure_accepte(ia, texte):
    from shared.schemas_ia import ValidationEmail
    ia.reponse = texte
    assert appeler_structure(MESSAGE, ValidationEmail).valide is True


def test_reponse_invalide_retentee_une_fois(ia):
    ia.file = ['{"score": 11}', ANALYSE]
    assert appeler_structure(MESSAGE, AnalyseOffre).score == 8 and len(ia.appels) == 2
    ia.appels.clear()
    ia.reponse = "pas du json"
    with pytest.raises(ReponseInvalide):
        appeler_structure(MESSAGE, AnalyseOffre)
    assert len(ia.appels) == 2


def test_paragraphe_vide_invalide(ia):
    ia.reponse = '{"contact_entreprise": "ACME", "paragraphe_entreprise": "  "}'
    with pytest.raises(ReponseInvalide, match="paragraphe_entreprise"):
        appeler_structure(MESSAGE, LettreIA)


def test_parametre_refuse_retire_et_retenu(ia):
    refus = erreur_http(400, 'json: unknown field "reasoning_effort"')
    ia.panne = lambda corps: refus if "reasoning_effort" in corps else None
    ia.reponse = "ok"
    assert appeler_ia(MESSAGE, tentatives=1) == "ok"
    assert len(ia.appels) == 2 and "reasoning_effort" not in ia.appels[1]
    appeler_ia(MESSAGE, tentatives=1)
    assert len(ia.appels) == 3   # retenu : plus envoyé


def test_schema_refuse_retire(ia):
    refus = erreur_http(400, "invalid response_format: json_schema not supported")
    ia.panne = lambda corps: refus if "response_format" in corps else None
    ia.reponse = ANALYSE
    assert appeler_structure(MESSAGE, AnalyseOffre).score == 8
    assert "response_format" not in ia.appels[-1]


# ─── Analyse : aucun résultat par défaut ─────────────────────────────────────
@pytest.mark.parametrize("reponse", ['{"eligible": true}', '{"score": "beaucoup"}', "pas du json", "[1, 2]"])
def test_reponse_inexploitable_pas_de_score_invente(ia, reponse):
    ia.reponse = reponse
    with pytest.raises(ErreurIAPassagere):
        analyser_offre({"titre": "Dev", "description": "..."}, {"prenom": "A"})


@pytest.mark.parametrize("mode", ["alternance", "job"])
def test_erreur_d_analyse_remonte(ia, monkeypatch, mode):
    echouer(ia, erreur_http(404, INTROUVABLE))
    with pytest.raises(ErreurIABloquante):
        analyser_offre({"titre": "Dev", "description": "..."}, {"prenom": "A"}, mode=mode)


def _brut_ft(i, description="..."):
    return {"id": f"FT{i}", "intitule": f"Poste {i}", "lieuTravail": {"libelle": "75 - Paris 10e"},
            "entreprise": {"nom": "ACME"}, "description": description,
            "dateCreation": "2026-10-01T08:00:00.000Z"}


def _lba(i):
    return {"id": f"LBA{i}", "titre": f"Alternance {i}", "entreprise": "LBA SA", "lieu": "75012 PARIS",
            "zone": "Paris", "source": "La Bonne Alternance", "lien": "", "description": "..."}


@pytest.fixture
def recherche(utilisateur, ia, monkeypatch, pipelines_neufs):
    """Lance la recherche par la route, France Travail et LBA simulés."""
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    sources = {"ft": [_brut_ft(i) for i in range(3)], "lba": []}
    monkeypatch.setattr(scraper, "recuperer_offres", lambda criteres, log=print, **_: list(sources["ft"]))
    monkeypatch.setattr(main, "rechercher_lba", lambda profil, log=print: {"offres": list(sources["lba"]), "entreprises": [], "requetes": 0})
    ia.reponse = ANALYSE

    def lancer(**corps):
        assert client.post("/api/recherche", json=corps or None).status_code == 200
        attendre(lambda: not pipelines_neufs.etat("recherche", user_id)["en_cours"])
        return pipelines_neufs.etat("recherche", user_id)

    return SimpleNamespace(client=client, user_id=user_id, sources=sources, lancer=lancer)


def test_modele_non_autorise_arrete_tout(recherche, ia, monkeypatch):
    recherche.sources["lba"] = [_lba(0)]
    echouer(ia, erreur_http(404, INTROUVABLE))
    etat = recherche.lancer()
    assert etat["message"].startswith("Erreur : Modèle « ministral-3:8b » introuvable")
    assert len(ia.appels) == 1                                 # arrêt immédiat, LBA comprise
    assert lire_candidatures(recherche.user_id) == []               # rien d'inséré ni d'archivé
    assert lire_offres_vues(recherche.user_id, "alternance") == set()   # rien de marqué vu
    logs = recherche.client.get("/api/logs").text
    assert "Recherche arrêtée" in logs and "ollama pull" in logs
    # Configuration corrigée : les mêmes offres reviennent
    ia.panne = None   # IA rétablie
    recherche.lancer()
    assert len(lire_candidatures(recherche.user_id)) == 4


def test_cle_refusee_arrete_tout(recherche, ia, monkeypatch):
    echouer(ia, erreur_http(401))
    assert "IA_API_KEY" in recherche.lancer()["message"]
    assert lire_candidatures(recherche.user_id) == []


def test_erreur_passagere_saute_l_offre_qui_revient(recherche, ia, monkeypatch):
    echouer(ia, erreur_http(503), si=lambda kw: "Poste 1" in texte_envoye(kw))
    etat = recherche.lancer()
    assert etat["message"] == "Terminé !"
    refs = {c["titre"] for c in lire_candidatures(recherche.user_id)}
    assert refs == {"Poste 0", "Poste 2"}
    assert len(lire_offres_vues(recherche.user_id, "alternance")) == 2
    assert "Offre sautée" in recherche.client.get("/api/logs").text
    # IA rétablie : l'offre sautée revient, les autres non
    ia.panne = None   # IA rétablie
    ia.appels.clear()
    recherche.lancer()
    assert {c["titre"] for c in lire_candidatures(recherche.user_id)} == {"Poste 0", "Poste 1", "Poste 2"}


def test_echec_d_analyse_jamais_archive(recherche, ia, monkeypatch):
    """Recette : des offres en échec d'analyse avaient été archivées « public spécifique »."""
    recherche.sources["ft"] = [_brut_ft(0, "Ce poste est réservé aux bénéficiaires de l'obligation d'emploi.")]
    echouer(ia, erreur_http(429))
    recherche.lancer()
    assert lire_candidatures(recherche.user_id) == []


def test_lba_passagere_sautee(recherche, ia, monkeypatch):
    recherche.sources["ft"] = []
    recherche.sources["lba"] = [_lba(0), _lba(1)]
    echouer(ia, erreur_http(500), si=lambda kw: "Alternance 0" in texte_envoye(kw))
    recherche.lancer()
    assert [c["id"] for c in lire_candidatures(recherche.user_id)] == ["LBA1"]
    assert "Offre LBA sautée" in recherche.client.get("/api/logs").text


def test_bandeau_affiche_l_erreur_du_pipeline():
    app = (config.STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    assert "function signalerErreur" in app and "signalerErreur(rech)" in app and "signalerErreur(sp)" in app


# ─── Routes directes : rien d'enregistré ─────────────────────────────────────
def _offre_en_base(user_id):
    ajouter_candidature(user_id, {"id": "REF1", "titre": "Dev", "entreprise": "ACME", "description": "...",
                                  "score": 8, "verdict": "bon", "lettre": "", "statut": "nouveau"})


def test_reanalyse_en_echec_ne_touche_pas_l_offre(utilisateur, ia, monkeypatch):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    _offre_en_base(user_id)
    echouer(ia, erreur_http(404, INTROUVABLE))
    r = client.post("/api/analyser", json={"id": "REF1"})
    assert r.status_code == 503 and "introuvable" in r.json()["erreur"]
    echouer(ia, erreur_http(503))
    assert client.post("/api/analyser", json={"id": "REF1"}).status_code == 502
    offre = lire_candidature(user_id, "REF1")
    assert (offre["score"], offre["verdict"], offre["statut"]) == (8, "bon", "nouveau")


def test_lettre_en_echec_rien_d_enregistre(utilisateur, ia, monkeypatch):
    client, user_id = utilisateur("a@test.fr", prenom="Alice", nom="A")
    client.post("/api/profil", json={"prenom": "Alice", "nom": "A", "email": "a@test.fr"})
    _offre_en_base(user_id)
    echouer(ia, erreur_http(404, INTROUVABLE))
    r = client.post("/api/generer_lettre", json={"id": "REF1"})
    assert r.status_code == 503 and "introuvable" in r.json()["erreur"]
    ia.appels.clear()
    ia.panne = None   # IA rétablie
    ia.reponse = '{"contact_entreprise": "ACME"}'   # pas de paragraphe : pas de lettre
    assert client.post("/api/generer_lettre", json={"id": "REF1"}).status_code == 502
    offre = lire_candidature(user_id, "REF1")
    assert offre["lettre"] == "" and offre["statut"] == "nouveau"


