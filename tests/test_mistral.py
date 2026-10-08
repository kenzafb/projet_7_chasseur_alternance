"""Mistral : modèle par usage, erreurs classées, et plus jamais de résultat
inventé (offre ni écrite, ni marquée vue, ni archivée en cas d'échec)."""

import time
from types import SimpleNamespace

import httpx
import pytest
from mistralai.client import errors

import france_travail.analyseur
import france_travail.scraper as scraper
import main
import shared.ia
from database.candidatures_db import ajouter_candidature, lire_candidature, lire_candidatures
from database.dedup_db import lire_offres_vues
from france_travail.analyseur import analyser_offre
from france_travail.generateur import generer_lettre
from shared import config
from shared.ia import ErreurIABloquante, ErreurIAPassagere, appeler_mistral, classer
from tests.test_envoyeur import attendre

ANALYSE = '{"score": 8, "eligible": true, "points_forts": ["a"], "points_faibles": [], "domaine": "Dev", "resume": "ok"}'
TIER = ('{"object":"error","message":"This model is not available in your subscription tier",'
        '"type":"invalid_request_error","param":null,"code":"1910"}')


def erreur_http(statut, corps='{"message": "erreur"}'):
    """Exception telle que le SDK mistralai 2.x la lève."""
    reponse = httpx.Response(statut, text=corps,
                             request=httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions"))
    return errors.MistralError("API error occurred", reponse)


@pytest.fixture(autouse=True)
def sans_attente(monkeypatch):
    """Retries et pauses instantanés."""
    monkeypatch.setattr(shared.ia, "time", SimpleNamespace(sleep=lambda s: None, monotonic=time.monotonic))
    monkeypatch.setattr(france_travail.analyseur, "PAUSE_MISTRAL", 0)
    for var in ("MODELE_MISTRAL", "MODELE_MISTRAL_ANALYSE", "MODELE_MISTRAL_LETTRE", "MODELE_MISTRAL_EXTRACTION"):
        monkeypatch.delenv(var, raising=False)


def echouer(mistral, monkeypatch, erreur, si=lambda kw: True):
    """Le faux Mistral lève `erreur` pour les appels où si(kwargs) est vrai."""
    reussir = mistral.chat.complete

    def complete(**kwargs):
        mistral.appels.append(kwargs)
        if si(kwargs):
            raise erreur
        mistral.appels.pop()
        return reussir(**kwargs)

    monkeypatch.setattr(mistral.chat, "complete", complete)


def texte_envoye(kwargs):
    return " ".join(m["content"] for m in kwargs["messages"])


# ─── Modèles ─────────────────────────────────────────────────────────────────
def test_modeles_par_defaut():
    assert config.modele_mistral("analyse") == "mistral-medium-latest"
    assert config.modele_mistral("lettre") == "mistral-medium-latest"
    assert config.modele_mistral("extraction") == "mistral-small-latest"


def test_modele_commun_puis_par_usage(monkeypatch):
    monkeypatch.setenv("MODELE_MISTRAL", "open-mistral-nemo")
    assert {config.modele_mistral(u) for u in config.USAGES_MISTRAL} == {"open-mistral-nemo"}
    monkeypatch.setenv("MODELE_MISTRAL_EXTRACTION", "ministral-8b-latest")
    assert config.modele_mistral("extraction") == "ministral-8b-latest"
    assert config.modele_mistral("analyse") == "open-mistral-nemo"
    monkeypatch.setenv("MODELE_MISTRAL_LETTRE", "  ")   # vide : retombe sur MODELE_MISTRAL
    assert config.modele_mistral("lettre") == "open-mistral-nemo"


def test_chaque_usage_appelle_son_modele(mistral, monkeypatch):
    monkeypatch.setenv("MODELE_MISTRAL_ANALYSE", "modele-analyse")
    monkeypatch.setenv("MODELE_MISTRAL_LETTRE", "modele-lettre")
    monkeypatch.setenv("MODELE_MISTRAL_EXTRACTION", "modele-extraction")
    profil = {"prenom": "A", "nom": "B", "email": "a@b.fr"}
    mistral.reponse = ANALYSE
    analyser_offre({"titre": "Dev", "description": "..."}, profil)
    mistral.reponse = '{"contact_entreprise": "ACME", "paragraphe_entreprise": "ACME me parle."}'
    generer_lettre({"titre": "Dev", "entreprise": "ACME"}, profil)
    import spontanees.scraper_emails as se
    monkeypatch.setattr(se, "PAUSE_MISTRAL", 0)
    mistral.reponse = '{"emails": [], "telephones": [], "contact_rh": null, "fiable": true}'
    se.mistral_extraire_contact("page", "ACME", [])
    assert [a["model"] for a in mistral.appels] == ["modele-analyse", "modele-lettre", "modele-extraction"]


def test_plus_de_modele_en_dur():
    assert not hasattr(config, "MODELE_MISTRAL")
    for fichier in ("shared/ia.py", "spontanees/scraper_emails.py", "france_travail/analyseur.py",
                    "france_travail/generateur.py"):
        assert "mistral-large-latest" not in (config.BASE_DIR / fichier).read_text(encoding="utf-8")


# ─── Classement des erreurs ──────────────────────────────────────────────────
@pytest.mark.parametrize("statut", [400, 401, 403, 404, 422])
def test_erreurs_bloquantes(statut):
    erreur, retenter = classer(erreur_http(statut), "m")
    assert isinstance(erreur, ErreurIABloquante) and not retenter and erreur.statut == statut


@pytest.mark.parametrize("statut", [429, 500, 502, 503])
def test_erreurs_passageres(statut):
    erreur, retenter = classer(erreur_http(statut), "m")
    assert isinstance(erreur, ErreurIAPassagere) and retenter


def test_reseau_passager():
    requete = httpx.Request("POST", "https://api.mistral.ai")
    for err in (httpx.ConnectError("x", request=requete), httpx.ReadTimeout("x", request=requete)):
        erreur, retenter = classer(err, "m")
        assert isinstance(erreur, ErreurIAPassagere) and retenter


def test_messages_clairs():
    assert "non autorisé pour l'abonnement" in str(classer(erreur_http(403, TIER), "mistral-large-latest")[0])
    assert "mistral-large-latest" in str(classer(erreur_http(403, TIER), "mistral-large-latest")[0])
    assert "MISTRAL_API_KEY" in str(classer(erreur_http(401), "m")[0])
    assert "introuvable" in str(classer(erreur_http(404), "m")[0])


def test_bloquante_sans_retry_passagere_retentee(mistral, monkeypatch):
    echouer(mistral, monkeypatch, erreur_http(403, TIER))
    with pytest.raises(ErreurIABloquante):
        appeler_mistral([{"role": "user", "content": "x"}], tentatives=4)
    assert len(mistral.appels) == 1
    mistral.appels.clear()
    echouer(mistral, monkeypatch, erreur_http(503))
    with pytest.raises(ErreurIAPassagere):
        appeler_mistral([{"role": "user", "content": "x"}], tentatives=4)
    assert len(mistral.appels) == 4


# ─── Analyse : aucun résultat par défaut ─────────────────────────────────────
@pytest.mark.parametrize("reponse", ['{"eligible": true}', '{"score": "beaucoup"}', "pas du json", "[1, 2]"])
def test_reponse_inexploitable_pas_de_score_invente(mistral, reponse):
    mistral.reponse = reponse
    with pytest.raises(ErreurIAPassagere):
        analyser_offre({"titre": "Dev", "description": "..."}, {"prenom": "A"})


@pytest.mark.parametrize("mode", ["alternance", "job"])
def test_erreur_d_analyse_remonte(mistral, monkeypatch, mode):
    echouer(mistral, monkeypatch, erreur_http(403, TIER))
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
def recherche(utilisateur, mistral, monkeypatch, pipelines_neufs):
    """Lance la recherche par la route, France Travail et LBA simulés."""
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    sources = {"ft": [_brut_ft(i) for i in range(3)], "lba": []}
    monkeypatch.setattr(scraper, "recuperer_offres", lambda criteres, log=print, **_: list(sources["ft"]))
    monkeypatch.setattr(main, "rechercher_lba", lambda profil, log=print: {"offres": list(sources["lba"]), "entreprises": [], "requetes": 0})
    mistral.reponse = ANALYSE

    def lancer(**corps):
        assert client.post("/api/recherche", json=corps or None).status_code == 200
        attendre(lambda: not pipelines_neufs.etat("recherche", user_id)["en_cours"])
        return pipelines_neufs.etat("recherche", user_id)

    return SimpleNamespace(client=client, user_id=user_id, sources=sources, lancer=lancer)


def test_modele_non_autorise_arrete_tout(recherche, mistral, monkeypatch):
    recherche.sources["lba"] = [_lba(0)]
    echouer(mistral, monkeypatch, erreur_http(403, TIER))
    etat = recherche.lancer()
    assert etat["message"].startswith("Erreur : Modèle Mistral « mistral-medium-latest » non autorisé")
    assert len(mistral.appels) == 1                                 # arrêt immédiat, LBA comprise
    assert lire_candidatures(recherche.user_id) == []               # rien d'inséré ni d'archivé
    assert lire_offres_vues(recherche.user_id, "alternance") == set()   # rien de marqué vu
    logs = recherche.client.get("/api/logs").text
    assert "Recherche arrêtée" in logs and "non autorisé" in logs
    # Configuration corrigée : les mêmes offres reviennent
    monkeypatch.setattr(mistral.chat, "complete", mistral._complete)   # Mistral rétabli
    recherche.lancer()
    assert len(lire_candidatures(recherche.user_id)) == 4


def test_cle_refusee_arrete_tout(recherche, mistral, monkeypatch):
    echouer(mistral, monkeypatch, erreur_http(401))
    assert "MISTRAL_API_KEY" in recherche.lancer()["message"]
    assert lire_candidatures(recherche.user_id) == []


def test_erreur_passagere_saute_l_offre_qui_revient(recherche, mistral, monkeypatch):
    echouer(mistral, monkeypatch, erreur_http(503), si=lambda kw: "Poste 1" in texte_envoye(kw))
    etat = recherche.lancer()
    assert etat["message"] == "Terminé !"
    refs = {c["titre"] for c in lire_candidatures(recherche.user_id)}
    assert refs == {"Poste 0", "Poste 2"}
    assert len(lire_offres_vues(recherche.user_id, "alternance")) == 2
    assert "Offre sautée" in recherche.client.get("/api/logs").text
    # Mistral rétabli : l'offre sautée revient, les autres non
    monkeypatch.setattr(mistral.chat, "complete", mistral._complete)   # Mistral rétabli
    mistral.appels.clear()
    recherche.lancer()
    assert {c["titre"] for c in lire_candidatures(recherche.user_id)} == {"Poste 0", "Poste 1", "Poste 2"}


def test_echec_d_analyse_jamais_archive(recherche, mistral, monkeypatch):
    """Recette : des offres en échec d'analyse avaient été archivées « public spécifique »."""
    recherche.sources["ft"] = [_brut_ft(0, "Ce poste est réservé aux bénéficiaires de l'obligation d'emploi.")]
    echouer(mistral, monkeypatch, erreur_http(429))
    recherche.lancer()
    assert lire_candidatures(recherche.user_id) == []


def test_lba_passagere_sautee(recherche, mistral, monkeypatch):
    recherche.sources["ft"] = []
    recherche.sources["lba"] = [_lba(0), _lba(1)]
    echouer(mistral, monkeypatch, erreur_http(500), si=lambda kw: "Alternance 0" in texte_envoye(kw))
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


def test_reanalyse_en_echec_ne_touche_pas_l_offre(utilisateur, mistral, monkeypatch):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    _offre_en_base(user_id)
    echouer(mistral, monkeypatch, erreur_http(403, TIER))
    r = client.post("/api/analyser", json={"id": "REF1"})
    assert r.status_code == 503 and "non autorisé" in r.json()["erreur"]
    echouer(mistral, monkeypatch, erreur_http(503))
    assert client.post("/api/analyser", json={"id": "REF1"}).status_code == 502
    offre = lire_candidature(user_id, "REF1")
    assert (offre["score"], offre["verdict"], offre["statut"]) == (8, "bon", "nouveau")


def test_lettre_en_echec_rien_d_enregistre(utilisateur, mistral, monkeypatch):
    client, user_id = utilisateur("a@test.fr", prenom="Alice", nom="A")
    client.post("/api/profil", json={"prenom": "Alice", "nom": "A", "email": "a@test.fr"})
    _offre_en_base(user_id)
    echouer(mistral, monkeypatch, erreur_http(403, TIER))
    r = client.post("/api/generer_lettre", json={"id": "REF1"})
    assert r.status_code == 503 and "non autorisé" in r.json()["erreur"]
    mistral.appels.clear()
    monkeypatch.setattr(mistral.chat, "complete", mistral._complete)   # Mistral rétabli
    mistral.reponse = '{"contact_entreprise": "ACME"}'   # pas de paragraphe : pas de lettre
    assert client.post("/api/generer_lettre", json={"id": "REF1"}).status_code == 502
    offre = lire_candidature(user_id, "REF1")
    assert offre["lettre"] == "" and offre["statut"] == "nouveau"


# ─── scripts/verifier_mistral.py ─────────────────────────────────────────────
def _script(monkeypatch, autorises, passageres=()):
    """Lance le script avec un faux client : 403 hors de `autorises`,
    erreur passagère pour les modèles de `passageres` ({modèle: statut})."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("verifier_mistral", config.BASE_DIR / "scripts" / "verifier_mistral.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    passageres = dict(passageres)

    def complete(model, messages, max_tokens):
        if model in passageres:
            raise erreur_http(passageres[model])
        if model not in autorises:
            raise erreur_http(403, TIER)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))])

    faux = SimpleNamespace(
        models=SimpleNamespace(list=lambda: SimpleNamespace(data=[SimpleNamespace(id=m) for m in autorises])),
        chat=SimpleNamespace(complete=complete))
    monkeypatch.setattr(script, "client", faux)
    monkeypatch.setenv("MISTRAL_API_KEY", "factice")
    lignes = []
    return script.main(sortie=lignes.append), "\n".join(lignes)


def test_script_tout_ok(monkeypatch):
    code, sortie = _script(monkeypatch, ["mistral-medium-latest", "mistral-small-latest"])
    assert code == 0 and "Tout est prêt." in sortie
    assert "OK  analyse    mistral-medium-latest" in sortie and "OK  extraction mistral-small-latest" in sortie


def test_script_modele_refuse(monkeypatch):
    code, sortie = _script(monkeypatch, ["mistral-small-latest"])
    assert code == 1
    assert "ÉCHEC analyse    mistral-medium-latest" in sortie and "non autorisé" in sortie
    assert "absent de la liste de la clé" in sortie and "factice" not in sortie


def test_script_sans_cle(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("verifier_mistral", config.BASE_DIR / "scripts" / "verifier_mistral.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    monkeypatch.delenv("MISTRAL_API_KEY")
    lignes = []
    assert script.main(sortie=lignes.append) == 1 and "MISTRAL_API_KEY absente" in lignes[0]


TOUS = ["mistral-medium-latest", "mistral-small-latest"]


@pytest.mark.parametrize("statut", [429, 503])
def test_script_erreur_passagere_ne_renvoie_pas_au_env(monkeypatch, statut):
    code, sortie = _script(monkeypatch, TOUS, {"mistral-medium-latest": statut})
    assert code == 1 and "erreur passagère" in sortie
    assert ".env :" not in sortie and "À corriger" not in sortie
    assert "limite de débit ou le quota Mistral est atteint" in sortie
    assert "Réessaie plus tard" in sortie and "console Mistral" in sortie


def test_script_erreurs_bloquante_et_passagere(monkeypatch):
    code, sortie = _script(monkeypatch, ["mistral-small-latest"], {"mistral-small-latest": 429})
    assert code == 1
    assert "À corriger dans le .env" in sortie and "limite de débit" in sortie


def test_script_passe_par_le_limiteur(monkeypatch):
    reservations = []
    monkeypatch.setattr(shared.ia, "limiteur", SimpleNamespace(attendre=lambda: reservations.append(1)))
    code, _ = _script(monkeypatch, TOUS)
    # liste des modèles + un appel par modèle distinct (medium, small)
    assert code == 0 and len(reservations) == 3
