"""scripts/verifier_france_travail.py contre l'API simulée : paramètre de
domaine, valeurs multiples, tranche d'effectif, découpage, propositions."""

import json

import pytest

from scripts import verifier_france_travail as vf
from tests.faux_france_travail import DEPTS, FausseAPI, Reponse, offre

ID, SECRET = "id-client-tres-secret", "secret-client-tres-secret"


def jeu():
    offres, n = [], 0
    for i, dept in enumerate(DEPTS):
        for domaine, nature, type_c, secteur, themes in [
            ("M18", "E2", "CDD", "62", ()), ("M18", "FS", "CDD", "62", ("17",)),
            ("C15", "E1", "CDI", "68", ()), ("J11", "E1", "MIS", "86", ("13",)),
            ("D12", "E1", "SAI", "47", ("13", "17")), ("H12", "E2", "CDD", "41", ()),
            ("M13", "E1", "CDD", "70", ()),
        ]:
            tranche = "NN" if n % 5 == 0 else (None if n % 7 == 0 else "10 à 19 salariés")
            offres.append(offre(n, dept=dept, domaine=domaine, nature=nature, type_contrat=type_c,
                                secteur=secteur, themes=themes, jours=i, tranche=tranche))
            n += 1
    return offres


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("FT_CLIENT_ID", ID)
    monkeypatch.setenv("FT_CLIENT_SECRET", SECRET)
    return FausseAPI(jeu())


def lancer(api, tmp_path):
    sorties = []
    code = vf.main(session=api, sortie=tmp_path, pause=0, afficher=sorties.append)
    fichier = tmp_path / "verification_api.json"
    return code, "\n".join(sorties), json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else None


def test_parametres_trouves_et_listes_acceptees(api, tmp_path):
    code, sortie, res = lancer(api, tmp_path)
    assert code == 0
    assert res["domaine"]["param_domaine"] == "domaine"
    assert res["domaine"]["param_grand_domaine"] == "grandDomaine"
    assert res["domaine"]["grand_domaine_contient_domaine"] is True
    couv = res["domaine"]["couverture"]
    assert couv["grands_domaines"]["somme"] == couv["grands_domaines"]["total_sans_filtre"] == 56
    assert couv["departements"]["somme"] == 56
    prop = res["propositions"]
    assert prop["VALEURS_PAR_REQUETE"]["natureContrat"] == 2
    assert prop["VALEURS_PAR_REQUETE"]["typeContrat"] == 3
    assert prop["VALEURS_PAR_REQUETE"]["domaine"] == 5
    assert prop["VALEURS_PAR_REQUETE"]["secteurActivite"] == 5
    assert prop["VALEURS_PAR_REQUETE"]["theme"] == 2
    assert "À reporter dans france_travail/parametres_api.py" in sortie
    assert "PARAM_DOMAINE = 'domaine'   # inchangé" in sortie


def test_parametre_ignore_et_premiere_valeur_seulement(api, tmp_path):
    api.params_reconnus -= {"domaine"}            # domaine=M18 ignoré par l'API
    api.multiples = {"typeContrat"}               # natureContrat=E2,FS : E2 seulement
    code, sortie, res = lancer(api, tmp_path)
    essais = {f"{k}={v}": e for e in res["domaine"]["essais"] for k, v in e["params"].items() if k != "region"}
    assert essais["domaine=M18"]["effet"] == "ignoré (total inchangé)"
    assert res["domaine"]["param_domaine"] == "grandDomaine"   # grandDomaine=M18 filtre
    assert res["multiples"]["natureContrat"]["max"] == 1
    assert "première valeur" in res["multiples"]["natureContrat"]["verdict"]
    assert res["propositions"]["VALEURS_PAR_REQUETE"]["natureContrat"] == 1
    assert res["propositions"]["VALEURS_PAR_REQUETE"]["typeContrat"] == 3


def test_liste_refusee(api, tmp_path):
    api.multiples, api.multiples_refuses = set(), True
    _, _, res = lancer(api, tmp_path)
    assert res["multiples"]["typeContrat"]["refuse"] is True
    assert res["propositions"]["VALEURS_PAR_REQUETE"]["typeContrat"] == 1


def test_tranche_effectif(api, tmp_path):
    _, sortie, res = lancer(api, tmp_path)
    t = res["tranche_effectif"]
    assert t["champ_propose"] == "trancheEffectifEtab"
    champ = t["champs"]["trancheEffectifEtab"]
    assert champ["presence"] < champ["sur"]                 # absent de certaines offres
    assert "NN" in champ["non_reconnues"]
    assert res["propositions"]["CHAMP_TRANCHE_EFFECTIF"] == "trancheEffectifEtab"
    assert "trancheEffectifEtab : présent dans" in sortie


def test_decoupage(api, tmp_path):
    _, sortie, res = lancer(api, tmp_path)
    d = res["decoupage"]
    assert d["departement=75"]["total"] == 7
    assert d["fenetre_7_jours"]["statut"] in (200, 204, 206)
    assert d["fenetre_complete_couvre_tout"] is True


def test_plage_de_comptage_refusee(api, tmp_path, monkeypatch):
    """Si l'API refuse la plage 0-0, le comptage passe à 0-149."""
    rechercher = api.rechercher
    api.rechercher = lambda p: Reponse(400, {"message": "plage"}) if p.get("range") == "0-0" else rechercher(p)
    _, _, res = lancer(api, tmp_path)
    assert res["plage_de_comptage"] == "0-149"
    assert res["domaine"]["base"]["total"] == 56


def test_aucun_secret_et_token_refuse(api, tmp_path):
    _, _, _ = lancer(api, tmp_path)
    texte = (tmp_path / "verification_api.json").read_text(encoding="utf-8")
    assert ID not in texte and SECRET not in texte and "token-de-test" not in texte
    api.token = Reponse(401, {"error": "invalid_client"})
    (tmp_path / "verification_api.json").unlink()
    code, sortie, res = lancer(api, tmp_path)
    assert code == 1 and "❌" in sortie and res is None
