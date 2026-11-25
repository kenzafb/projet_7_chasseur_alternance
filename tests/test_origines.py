"""Entreprises à contacter : pourquoi chacune est là (D190), filtre par
origine, option du profil qui écarte les grandes entreprises transverses."""

from database.connexion import SessionLocal
from database.entreprises_db import ajouter_entreprises, calculer_stats
from database.models import Entreprise
from database.profil_db import sauvegarder_profil
from shared.criteres import normaliser_recherche
from shared.naf import codes_par_origine, origines
from spontanees.recuperation import plan_sirene

PROFIL = {"recherche": {"domaines": ["M18"]}}


def test_origines_par_code_naf():
    codes = codes_par_origine(PROFIL)
    assert origines(["sirene"], "62.01Z", "62.10Y", codes) == [{"cle": "coeur", "texte": "Informatique"}]
    assert origines(["sirene"], "", "62.10Y", codes)[0]["cle"] == "coeur"            # NAF 2025 seul
    assert origines(["sirene"], "64.19Z", "", codes) == [
        {"cle": "transverse", "texte": "Grande entreprise, service informatique interne"}]
    assert origines(["lba"], "", "", codes) == [
        {"cle": "lba", "texte": "La Bonne Alternance, recrute des alternants dans ton métier"}]
    assert [o["cle"] for o in origines(["sirene", "lba"], "62.01Z", "", codes)] == ["lba", "coeur"]
    # Code hors des secteurs du profil : tous les secteurs si la case est cochée
    assert origines(["sirene"], "01.11Z", "", codes)[0]["cle"] == "sirene"
    tous = codes_par_origine({"recherche": {"domaines": ["M18"], "tous_secteurs": True}})
    assert origines(["sirene"], "01.11Z", "", tous) == [{"cle": "tous", "texte": "Tous les secteurs"}]
    # Immobilier
    assert origines(["sirene"], "68.31Z", "", codes_par_origine({"recherche": {"domaines": ["C15"]}}))[0][
        "texte"] == "Immobilier"


def test_origines_servies_avec_les_entreprises(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    sauvegarder_profil(uid, PROFIL, mode="alternance")
    ajouter_entreprises(uid, [{"siret": "S1", "nom": "Dev SAS"}, {"siret": "S2", "nom": "Banque SA"}])
    with SessionLocal() as db:
        a, b = db.query(Entreprise).order_by(Entreprise.id).all()
        a.naf_rev2, a.sources = "62.01Z", ["sirene"]
        b.naf_rev2, b.sources = "64.19Z", ["sirene"]
        db.commit()
    prochaines = {e["nom"]: e["origines"] for e in calculer_stats(uid, "alternance")["prochaines"]}
    assert prochaines == {"Dev SAS": [{"cle": "coeur", "texte": "Informatique"}],
                          "Banque SA": [{"cle": "transverse", "texte": "Grande entreprise, service informatique interne"}]}


def test_option_sans_transverses():
    journal = []
    avec = {g for g, _ in plan_sirene({"recherche": {"domaines": ["M18"]}}, journal.append)}
    assert "transverses" in avec
    sans = {g for g, _ in plan_sirene({"recherche": {"domaines": ["M18"], "inclure_transverses": False}},
                                      journal.append)}
    assert "transverses" not in sans and "cœurs" in sans
    assert any("non cherchées, option du profil" in ligne for ligne in journal)
    assert normaliser_recherche({"inclure_transverses": "x"})["inclure_transverses"] is True
    assert normaliser_recherche({"inclure_transverses": False})["inclure_transverses"] is False


def test_page_filtre_par_origine(utilisateur):
    client, _ = utilisateur("a@test.fr")
    page = client.get("/alternance").text
    for valeur in ("coeur", "transverse", "lba", "autre"):
        assert f'<option value="{valeur}">' in page
