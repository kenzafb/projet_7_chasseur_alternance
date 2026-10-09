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
    assert res["multiples"]["natureContrat=E2,FS"]["max"] == 1
    assert "première valeur" in res["multiples"]["natureContrat=E2,FS"]["verdict"]
    assert res["propositions"]["VALEURS_PAR_REQUETE"]["natureContrat"] == 1
    assert res["propositions"]["VALEURS_PAR_REQUETE"]["typeContrat"] == 3


def test_liste_refusee(api, tmp_path):
    api.multiples, api.multiples_refuses = set(), True
    _, _, res = lancer(api, tmp_path)
    assert res["multiples"]["typeContrat=CDD,MIS,SAI"]["refuse"] is True
    assert res["propositions"]["VALEURS_PAR_REQUETE"]["typeContrat"] == 1


def test_tranche_effectif(api, tmp_path):
    _, sortie, res = lancer(api, tmp_path)
    t = res["tranche_effectif"]
    assert t["champ_propose"] == "trancheEffectifEtab"
    champ = t["champs"]["trancheEffectifEtab"]
    assert champ["presence"] < champ["sur"]                 # absent de certaines offres
    assert champ["non_reconnues"] == []                     # NN : sans salarié (D55)
    assert res["propositions"]["CHAMP_TRANCHE_EFFECTIF"] == "trancheEffectifEtab"
    assert "trancheEffectifEtab : présent dans" in sortie


def test_secteur_limite_a_deux_valeurs(api, tmp_path):
    """Liste de cinq refusée (« 2 chaînes séparées par des virgules ») :
    l'essai à exactement deux valeurs tranche."""
    api.max_valeurs = {"secteurActivite": 2}
    _, sortie, res = lancer(api, tmp_path)
    assert res["multiples"]["secteurActivite=62,68,86,47,41"]["refuse"] is True
    deux = res["multiples"]["secteurActivite=62,68"]
    assert deux["max"] == 2 and "acceptée" in deux["verdict"]
    assert res["propositions"]["VALEURS_PAR_REQUETE"]["secteurActivite"] == 2
    assert "secteurActivite=62,68 : acceptée" in sortie


def test_liste_comparee_a_ses_seules_valeurs(api, tmp_path):
    """Régression : l'essai à deux valeurs était comparé aux totaux des
    cinq, et jugé « incohérent » (1289 = 614 + 675 le 8 octobre 2026)."""
    api.max_valeurs = {"secteurActivite": 2}
    _, _, res = lancer(api, tmp_path)
    essai = res["multiples"]["secteurActivite=62,68,86,47,41"]["essai_deux_valeurs"]
    assert essai["max"] == 2 and set(essai["liste"]["params"]["secteurActivite"].split(",")) == {"62", "68"}


def test_decoupage(api, tmp_path):
    _, sortie, res = lancer(api, tmp_path)
    d = res["decoupage"]
    assert d["departement=75"]["total"] == 7
    assert d["fenetre_7_jours"]["statut"] in (200, 204, 206)
    assert d["fenetre_complete_couvre_tout"] is True
    assert d["fenetre_complete"]["total"] == d["total_sans_dates"]["total"] == 56
    assert d["moities_moins_complete"] == 0


def test_decalage_de_fuseau_visible(api, tmp_path):
    """L'API lit les dates en heure de Paris : la fin « maintenant » perd
    les dernières heures, la fin avec marge retrouve tout."""
    from datetime import datetime, timedelta, timezone
    recentes = [offre(900 + n) for n in range(5)]
    for n, o in enumerate(recentes):
        o["dateCreation"] = (datetime.now(timezone.utc) - timedelta(minutes=10 + n)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")
    api.offres += recentes
    api.decalage_heures = 2
    _, sortie, res = lancer(api, tmp_path)
    d = res["decoupage"]
    assert d["fenetre_fin_maintenant"]["total"] == 56
    assert d["fenetre_fin_plus_3h"]["total"] == d["fenetre_complete"]["total"] == 61
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


# ─── 5. Stages (phase 6b) ─────────────────────────────────────────────────────
def _offres_de_stage():
    """Trois stages, une offre qui parle de stage dans sa seule description,
    une alternance ; « stagiaire » seul ne contient pas « stage »."""
    o = [offre(500, nature="E1", type_contrat="CDD", titre="Stage développeur web H/F"),
         offre(501, nature="E1", type_contrat="CDI", titre="Stage comptable"),
         offre(502, nature="E1", type_contrat="CDD", titre="STAGE assistant RH"),
         offre(503, nature="E1", type_contrat="CDI", titre="Technicien support"),
         offre(504, nature="E2", type_contrat="CDD", titre="Apprenti logistique, ancien stage accepté"),
         offre(505, nature="E1", type_contrat="CDI", titre="Stagiaire juriste")]
    o[3]["description"] = "Possibilité d'embauche après un stage de fin d'études."
    return o


def test_essai_stage(api, tmp_path):
    api.offres += _offres_de_stage()
    code, sortie, res = lancer(api, tmp_path)
    assert code == 0 and "decoupage" in res and "stage" not in res        # fichier à part
    st = json.loads((tmp_path / "verification_stage.json").read_text(encoding="utf-8"))
    assert st["recherche"]["motsCles"] == "stage"
    assert st["total"]["total"] == 5
    types = st["repartition"]["typeContrat"]
    assert {c: n for c, n in types["totaux"].items() if n} == {"CDD": 3, "CDI": 2} and types["somme"] == 5
    natures = st["repartition"]["natureContrat"]
    assert {c: n for c, n in natures["totaux"].items() if n} == {"E1": 4, "E2": 1}
    ech = st["echantillon"]
    assert ech["offres_lues"] == 5 and ech["intitule_avec_stage"] == 4 and ech["alternance"] == 1
    assert "Stagiaire juriste" not in ech["exemples"]
    assert ech["typeContrat"] == {"CDD": 3, "CDI": 2}
    assert "Stage développeur web H/F" in ech["exemples"] and len(ech["exemples"]) == 5
    assert "motsCles=stage : 5 offres en Île-de-France" in sortie
    assert "    - Stage comptable" in sortie and "CDD Contrat à durée déterminée 3" in sortie


def test_essai_stage_seul(api, tmp_path):
    api.offres += _offres_de_stage() + [offre(600 + n, titre=f"Stage {n}") for n in range(30)]
    sorties = []
    assert vf.main(session=api, sortie=tmp_path, pause=0, afficher=sorties.append, seulement_stage=True) == 0
    assert not (tmp_path / "verification_api.json").exists()
    st = json.loads((tmp_path / "verification_stage.json").read_text(encoding="utf-8"))
    assert st["total"]["total"] == 35 and len(st["echantillon"]["exemples"]) == vf.EXEMPLES_STAGE
    # Seulement des recherches avec motsCles, une par code des référentiels plus le total et l'échantillon
    assert all(p.get("motsCles") == "stage" for p in api.recherches)
    assert len(api.recherches) == 2 + 12 + 19
