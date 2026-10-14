"""scripts/verifier_ia_locale.py : serveur vérifié, vraies offres lues en
lecture seule, tableau comparatif par modèle, rien d'écrit en base."""

import importlib.util

import httpx
import pytest

from database.candidatures_db import ajouter_candidature, lire_candidatures
from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
from france_travail.analyseur import marquer_non_analysee
from shared import config
from tests.conftest import erreur_http
from tests.test_ia import texte_envoye

ANALYSE = ('{"score": 7, "eligible": true, "points_forts": ["a"], "points_faibles": [], '
           '"domaine": "Développement web", "resume": "ok"}')


def script():
    spec = importlib.util.spec_from_file_location("verifier_ia_locale",
                                                  config.BASE_DIR / "scripts" / "verifier_ia_locale.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lancer(*argv):
    lignes = []
    code = script().main(list(argv), sortie=lignes.append)
    return code, "\n".join(lignes)


@pytest.fixture
def donnees(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    for i in range(4):
        ajouter_candidature(uid, marquer_non_analysee({"id": f"R{i}", "titre": f"Développeur {i}",
                                                       "description": "...", "date_trouvee": f"2026-10-0{i + 1}T08:00:00+00:00"}))
    ajouter_entreprises(uid, [{"siret": "S1", "nom": "ACME"}])
    liste = lire_entreprises(uid)
    liste[0].update(site_web="https://acme.fr", emails_trouves=["x@gmail.com"], emails_douteux=["x@gmail.com"],
                    emails_non_valides=True, contextes_emails={"x@gmail.com": "Le gérant : x@gmail.com"})
    sauvegarder_enrichissement(uid, liste)
    return uid


def test_tableau_comparatif_sans_rien_ecrire(donnees, ia):
    ia.panne = lambda corps: ('{"valides": ["x@gmail.com"], "meilleur_contact": "x@gmail.com"}'
                              if "Adresses à juger" in texte_envoye(corps) else None)
    ia.reponse = ANALYSE
    code, sortie = lancer("--modeles", "ministral-3:8b,qwen3.5:9b")
    assert code == 0
    assert "✅ Le serveur répond" in sortie and "- ministral-3:3b" in sortie
    assert "« qwen3.5:9b » n'est pas installé : ollama pull qwen3.5:9b" in sortie
    assert "Développeur 3" in sortie and "Développeur 0" not in sortie     # les 3 plus récentes
    for modele in ("ministral-3:8b", "qwen3.5:9b"):
        assert sum(1 for a in ia.appels if a["model"] == modele) == 3 + 1        # offres, email
        assert sum(1 for a in ia.demarrages if a["model"] == modele) == 1      # test de démarrage
    assert "Test de démarrage (chargement compris, schéma JSON, sans réflexion)" in sortie
    assert "JSON valide" in sortie and "7/10" in sortie and "bon" in sortie
    assert "x@gmail.com" in sortie and "valide" in sortie
    assert "Rien n'a été écrit en base." in sortie
    assert {c["verdict"] for c in lire_candidatures(donnees)} == {"non_analysee"}   # base intacte
    assert lire_entreprises(donnees)[0]["emails_non_valides"] is True


def test_modeles_par_defaut_et_json_invalide(donnees, ia):
    ia.panne = lambda corps: "pas du json" if "OFFRE" in texte_envoye(corps) else None
    ia.reponse = '{"valides": [], "meilleur_contact": null}'
    code, sortie = lancer("--offres", "1")
    assert code == 0                               # l'email a reçu une réponse valide
    modeles = [a["model"] for a in ia.appels]
    assert modeles == ["ministral-3:8b", "ministral-3:3b"]
    assert [a["model"] for a in ia.demarrages] == ["ministral-3:8b", "ministral-3:3b"]
    assert "  non  " in sortie and "écartée" in sortie
    assert sum(1 for a in ia.appels if "OFFRE" in texte_envoye(a)) == 1   # un seul essai


def test_ollama_injoignable(donnees, ia, monkeypatch):
    import shared.ia
    monkeypatch.setattr(shared.ia, "_obtenir", lambda *a: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    code, sortie = lancer()
    assert code == 1 and "IA locale injoignable : vérifie qu'Ollama tourne" in sortie
    assert ia.appels == []


def test_ia_desactivee_ignoree_pour_le_test(donnees, ia, monkeypatch):
    monkeypatch.setenv("ANALYSE_IA", "false")
    ia.reponse = ANALYSE
    code, sortie = lancer("--offres", "1")
    assert "ANALYSE_IA=false dans le .env : ignoré pour ce test" in sortie and ia.appels


def test_sans_offre_ni_email_cas_fictif(utilisateur, ia):
    utilisateur("a@test.fr", prenom="Alice")
    ia.reponse = '{"valides": [], "meilleur_contact": null}'
    code, sortie = lancer()
    assert "Aucune offre « non analysée »" in sortie and "cas fictif" in sortie and code == 0


def test_modele_absent_passe_au_suivant(donnees, ia):
    ia.panne = lambda corps: erreur_http(404, "model not found") if corps["model"] == "absent:1b" else None
    ia.reponse = ANALYSE
    code, sortie = lancer("--modeles", "absent:1b,ministral-3:8b", "--offres", "1")
    assert "ollama pull absent:1b" in sortie and code == 0
    assert [a["model"] for a in ia.appels].count("absent:1b") == 0          # arrêté au test de démarrage


def test_lecture_seule():
    s = script()
    assert s.url_lecture_seule("sqlite:////tmp/x.db") == "sqlite:///file:/tmp/x.db?mode=ro&uri=true"
    with pytest.raises(ValueError):
        s.url_lecture_seule("postgresql://x")


def test_ecriture_impossible(donnees):
    from sqlalchemy import create_engine, exc, text
    moteur = create_engine(script().url_lecture_seule(config.DATABASE_URL))
    try:
        with moteur.connect() as cx:
            assert cx.execute(text("select count(*) from candidatures")).scalar() == 4
            with pytest.raises(exc.OperationalError, match="readonly"):
                cx.execute(text("update candidatures set verdict = 'bon'"))
    finally:
        moteur.dispose()


def test_demarrage_echoue_modele_ecarte(donnees, ia):
    ia.demarrage = "Voici : rien"
    ia.reponse = ANALYSE
    code, sortie = lancer("--offres", "1")
    assert code == 1 and "Test de démarrage échoué" in sortie and ia.appels == []
