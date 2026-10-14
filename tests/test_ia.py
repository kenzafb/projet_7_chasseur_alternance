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

ANALYSE = '{"score": 8, "eligible": true, "points_forts": ["a"], "points_faibles": [], "domaine": "Dev", "resume": "ok", "niveau_requis": "non_precise", "duree_mois": null, "date_debut_offre": null, "alternance_seulement": false}'
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
    assert ia.urls[-1] == "http://localhost:11434/api/chat"          # API native par défaut
    monkeypatch.setenv("IA_BASE_URL", "http://localhost:11434/v1")   # ancien réglage : /v1 retiré
    appeler_ia(MESSAGE)
    assert ia.urls[-1] == "http://localhost:11434/api/chat"
    monkeypatch.setenv("IA_API", "openai")
    monkeypatch.setenv("IA_BASE_URL", "http://serveur:8080/v1/")
    monkeypatch.setenv("IA_API_KEY", "secret")
    entetes = {}
    from tests.conftest import reponse_chat as rc
    monkeypatch.setattr(shared.ia, "_poster", lambda url, corps, e, delai: entetes.update(e, url=url, delai=delai)
                        or rc("ok", native=False))
    assert appeler_ia(MESSAGE) == "ok"
    assert entetes["url"] == "http://serveur:8080/v1/chat/completions"
    assert entetes["Authorization"] == "Bearer secret"


def test_requete_native(ia, monkeypatch):
    ia.reponse = ANALYSE
    appeler_structure(MESSAGE, AnalyseOffre, temperature=0.1, max_tokens=50)
    corps = ia.appels[0]
    assert corps["think"] is False and corps["stream"] is False      # premier niveau, pas dans options
    assert corps["format"]["required"] == ["score", "eligible", "points_forts", "points_faibles", "domaine", "resume",
                                           "niveau_requis", "duree_mois", "date_debut_offre", "alternance_seulement"]
    assert corps["format"]["properties"]["niveau_requis"]["enum"] == ["bac", "bac+2", "bac+3", "bac+4", "bac+5",
                                                                      "non_precise"]
    assert corps["options"] == {"num_ctx": 8192, "temperature": 0.1, "num_predict": 50}
    assert corps["keep_alive"] == "10m"
    assert "tools" not in corps and "response_format" not in corps and "reasoning_effort" not in corps
    monkeypatch.setenv("IA_NUM_CTX", "16384")
    monkeypatch.setenv("IA_KEEP_ALIVE", "30m")
    appeler_ia(MESSAGE)
    assert ia.appels[-1]["options"] == {"num_ctx": 16384} and ia.appels[-1]["keep_alive"] == "30m"
    assert "format" not in ia.appels[-1]


def test_requete_openai(ia, monkeypatch):
    monkeypatch.setenv("IA_API", "openai")
    ia.reponse = ANALYSE
    appeler_structure(MESSAGE, AnalyseOffre, temperature=0.6)
    corps = ia.appels[0]
    assert ia.urls[0] == "http://localhost:11434/v1/chat/completions"
    assert corps["response_format"]["type"] == "json_schema" and corps["reasoning_effort"] == "none"
    assert corps["temperature"] == 0.6 and "think" not in corps and "format" not in corps


def test_jamais_tools_et_format_ensemble(ia):
    with pytest.raises(ValueError, match="tools"):
        appeler_structure(MESSAGE, AnalyseOffre, tools=[{"type": "function"}])
    assert ia.appels == []


def test_liste_des_modeles_native(ia):
    assert shared.ia.lister_modeles() == ["ministral-3:3b", "ministral-3:8b"]
    assert ia.urls[-1] == "http://localhost:11434/api/tags"


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
    from shared.validation_emails import avis_ia
    ia.reponse = '{"valides": ["x@gmail.com"], "meilleur_contact": null}'
    avis_ia("ACME", "acme.fr", ["x@gmail.com"], [])
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


@pytest.mark.parametrize("reponse", [reponse_chat('{"a": 1}', reflexion="je réfléchis"),
                                     "<think>je réfléchis</think>\n{\"a\": 1}"])
def test_reflexion_non_coupee_bloquante(ia, reponse, monkeypatch):
    ia.reponse = reponse
    with pytest.raises(ErreurIABloquante, match="réflexion .* n'est pas coupée"):
        appeler_ia(MESSAGE)
    monkeypatch.setenv("IA_REFLEXION", "true")     # réflexion voulue : retirée du texte
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
def test_reflexion_gardee_sur_demande(ia, monkeypatch):
    monkeypatch.setenv("IA_REFLEXION", "true")
    appeler_ia(MESSAGE)
    assert "think" not in ia.appels[-1]


@pytest.mark.parametrize("texte", ['```json\n{"contact_entreprise": "A", "paragraphe_entreprise": "p"}\n```',
                                   'Voici : {"contact_entreprise": "A", "paragraphe_entreprise": "p"} !'])
def test_json_entoure_accepte(ia, texte):
    from shared.schemas_ia import LettreIA
    ia.reponse = texte
    assert appeler_structure(MESSAGE, LettreIA).paragraphe_entreprise == "p"


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


@pytest.mark.parametrize("parametre, detail, message", [
    ("think", '"ministral-3:8b" does not support thinking', "refuse de couper la réflexion"),
    ("format", "invalid format: schema not supported", "refuse le schéma JSON imposé"),
])
def test_parametre_refuse_bloquant_jamais_retire(ia, parametre, detail, message):
    ia.panne = lambda corps: erreur_http(400, detail) if parametre in corps else None
    with pytest.raises(ErreurIABloquante, match=message):
        shared.ia.appeler_ia(MESSAGE, schema=AnalyseOffre, tentatives=3)
    assert len(ia.appels) == 1 and parametre in ia.appels[0]   # pas de nouvel essai sans le paramètre


# ─── Test de démarrage ───────────────────────────────────────────────────────
def test_demarrage_avant_le_premier_appel_structure(ia):
    ia.reponse = ANALYSE
    appeler_structure(MESSAGE, AnalyseOffre)
    appeler_structure(MESSAGE, AnalyseOffre)
    assert len(ia.demarrages) == 1 and len(ia.appels) == 2          # une fois par modèle et par processus
    corps = ia.demarrages[0]
    assert corps["format"]["required"] == ["nombre", "mot"] and corps["think"] is False
    appeler_structure(MESSAGE, AnalyseOffre, modele="autre:1b")
    assert len(ia.demarrages) == 2


@pytest.mark.parametrize("reponse, message", [
    ('Voici : {"nombre": 7, "mot": "ok"}', "n'est pas l'objet JSON demandé"),   # texte autour
    ('{"nombre": "sept"}', "n'est pas l'objet JSON demandé"),
    (reponse_chat('{"nombre": 7, "mot": "ok"}', reflexion="hmm"), "pas coupée"),
])
def test_demarrage_echoue_rien_n_est_analyse(ia, reponse, message):
    ia.demarrage = reponse
    with pytest.raises(ErreurIABloquante, match=message):
        appeler_structure(MESSAGE, AnalyseOffre)
    assert ia.appels == []
    ia.demarrage = '{"nombre": 7, "mot": "ok"}'      # serveur corrigé : le test est refait
    ia.reponse = ANALYSE
    assert appeler_structure(MESSAGE, AnalyseOffre).score == 8


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


def test_la_recherche_n_appelle_jamais_l_ia(recherche, ia):
    """D21 : offres toujours ajoutées « non analysées », même IA active ou en panne."""
    recherche.sources["lba"] = [_lba(0)]
    echouer(ia, connexion_refusee())
    assert recherche.lancer()["message"] == "Terminé !"
    assert ia.appels == []
    offres = lire_candidatures(recherche.user_id)
    assert len(offres) == 4 and {o["verdict"] for o in offres} == {"non_analysee"}
    assert len(lire_offres_vues(recherche.user_id, "alternance")) == 3


def test_bandeau_affiche_l_erreur_du_pipeline():
    app = (config.STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    assert "function signalerErreur" in app
    assert all(f"signalerErreur({p})" in app for p in ("rech", "an", "sp"))


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




# ─── Contrôles en Python ─────────────────────────────────────────────────────
@pytest.mark.parametrize("score, attendu, verdict", [(15, 10, "excellent"), (-3, 0, "ineligible"), (0, 0, "ineligible")])
def test_score_borne_en_python(ia, score, attendu, verdict):
    ia.reponse = ANALYSE.replace('"score": 8', f'"score": {score}')
    analyse = analyser_offre({"titre": "Dev", "description": "..."}, {"prenom": "A"})
    assert (analyse["score"], analyse["verdict"]) == (attendu, verdict)
    assert "minimum" not in str(AnalyseOffre.model_json_schema()) and "maximum" not in str(AnalyseOffre.model_json_schema())
