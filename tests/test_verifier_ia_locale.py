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
           '"domaine": "Développement web", "resume": "ok", "niveau_requis": "non_precise", "duree_mois": null, "date_debut_offre": null, "alternance_seulement": false, "niveau_exigence": "non_precise"}')


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
    assert modeles == ["ministral-3:3b", "ministral-3:3b"]          # analyse et emails : le 3b (D101)
    assert [a["model"] for a in ia.demarrages] == ["ministral-3:3b"]   # testé une fois
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


# ─── --nombre, colonne du niveau, --lettre à l'aveugle ───────────────────────
def test_nombre_d_offres(donnees, ia):
    ia.reponse = ANALYSE
    lancer("--nombre", "4")
    assert sum(1 for a in ia.appels if "OFFRE" in texte_envoye(a)) == 4
    ia.appels.clear()
    lancer("--offres", "2")                       # ancien nom gardé
    assert sum(1 for a in ia.appels if "OFFRE" in texte_envoye(a)) == 2


def test_colonnes_niveau_duree_et_raison(donnees, ia):
    from database.profil_db import sauvegarder_profil
    sauvegarder_profil(donnees, {"prenom": "Alice", "niveau_etudes": "Bac+2 en cours"})
    from database.candidatures_db import modifier_candidature
    modifier_candidature(donnees, "R3", {"description": "Stage de 6 mois, Master 2 ou école d'ingénieurs exigé."})
    ia.reponse = ANALYSE.replace('"niveau_requis": "non_precise", "duree_mois": null',
                                 '"niveau_requis": "bac+5", "duree_mois": 6').replace(
        '"niveau_exigence": "non_precise"', '"niveau_exigence": "exige"')
    _, sortie = lancer("--nombre", "1")
    assert "Niveau requis" in sortie and "Exigence" in sortie and "Durée (mois)" in sortie and "Inéligible (Python)" in sortie
    ligne = next(l for l in sortie.splitlines() if l.strip().startswith("ministral-3:3b  O1"))
    assert "bac+5" in ligne and "exige" in ligne and "  6  " in ligne and "Bac+5 exigé, profil Bac+2" in ligne
    assert "3/10" in ligne


def _lettre(corps):
    modele = corps["model"]
    return ('{"paragraphe": "Texte de %s."}' % modele
            if "lettre de motivation" in texte_envoye(corps) else None)


@pytest.fixture
def profil_complet(donnees, utilisateur):
    from database.profil_db import sauvegarder_profil
    sauvegarder_profil(donnees, {"prenom": "Alice", "nom": "Martin", "email": "a@test.fr"})
    return donnees


def test_lettre_a_l_aveugle(profil_complet, ia):
    ia.panne = _lettre
    lignes = []
    s = script()
    tirage = lambda etiquettes: etiquettes.reverse()        # m1 -> C, m2 -> B, m3 -> A
    import shared.config as c
    o = s.lire_offre(c.DATABASE_URL, "R0")
    assert o["offre"]["titre"] == "Développeur 0"
    assert s.comparer_lettres(o, ["m1", "m2", "m3"], lignes.append, tirage) == 0
    sortie = "\n".join(lignes)
    corps, fin = sortie.split("Correspondance (à lire après le jugement) :")
    assert corps.index("── A ──\nTexte de m3.") < corps.index("── B ──\nTexte de m2.") < corps.index("── C ──\nTexte de m1.")
    assert "A = m3" in fin and "B = m2" in fin and "C = m1" in fin
    assert {a["model"] for a in ia.appels} == {"m1", "m2", "m3"} and len(ia.appels) == 3
    assert {c_["verdict"] for c_ in lire_candidatures(profil_complet)} == {"non_analysee"}   # rien d'écrit


def test_lettre_par_la_ligne_de_commande(profil_complet, ia):
    ia.panne = _lettre
    code, sortie = lancer("--lettre", "--modeles", "ministral-3:8b,ministral-3:3b", "--offre", "R1")
    assert code == 0 and "Développeur 1" in sortie
    blind = sortie.split("Paragraphes, à lire à l'aveugle")[1].split("Correspondance")[0]
    assert "── A ──" in blind and "── B ──" in blind and "ministral" not in blind.replace("Texte de ministral", "")
    assert "A = ministral-3:" in sortie and "B = ministral-3:" in sortie
    assert not any("Tu évalues" in texte_envoye(a) for a in ia.appels)   # pas d'analyse en mode --lettre
    code, sortie = lancer("--lettre")                               # sans --offre : la plus récente en attente
    assert code == 0 and "Développeur 3" in sortie and "A = ministral-3:8b" in sortie
    code, sortie = lancer("--lettre", "--offre", "INCONNUE")
    assert code == 1 and "Offre introuvable : INCONNUE" in sortie
