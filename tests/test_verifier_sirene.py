"""scripts/verifier_sirene.py contre l'API Sirene simulée : tranches,
catégories, plusieurs codes NAF et départements, variable NAF 2025,
pagination, propositions, clé jamais écrite."""

import json

import pytest

from scripts import verifier_sirene as vs
from tests.faux_sirene import FausseSirene, Reponse, etablissement

CLE = "cle-insee-tres-secrete"


def jeu(**options):
    etabs, n = [], 0
    for cp in ("75011", "75015", "92100", "93200"):
        for naf, tranche, cat in (("62.01Z", "12", "PME"), ("62.01Z", "NN", "PME"), ("62.01Z", None, "PME"),
                                  ("62.02A", "11", "PME"), ("62.02A", "42", "ETI"), ("62.01Z", "53", "GE"),
                                  ("68.31Z", "01", "PME"), ("62.01Z", "03", None)):
            etabs.append(etablissement(n, naf=naf, cp=cp, tranche=tranche, categorie=cat))
            n += 1
    etabs.append(etablissement(999, cp="75001", siege=False))
    return FausseSirene(etabs, **options)


@pytest.fixture
def cle(monkeypatch):
    monkeypatch.setenv("INSEE_API_KEY", CLE)


def lancer(api, tmp_path):
    sorties = []
    code = vs.main(session=api, sortie=tmp_path, pause=0, afficher=sorties.append)
    fichier = tmp_path / "verification_api.json"
    texte = fichier.read_text(encoding="utf-8") if fichier.exists() else ""
    return code, "\n".join(sorties), (json.loads(texte) if texte else None), texte


def test_valeurs_trouvees(cle, tmp_path):
    code, sortie, res, texte = lancer(jeu(), tmp_path)
    assert code == 0 and CLE not in texte
    assert res["reference"]["total"] == 10                       # 75011 et 75015, 62.01Z, sièges
    t = res["tranches"]
    assert t["trancheEffectifsUniteLegale"]["ou_exact"] and t["trancheEffectifsUniteLegale"]["NN"] == 2
    assert t["lus"]["part_non_renseignes_unite_legale"] == 0.4  # NN et absent : 4 sur 10
    assert t["part_non_renseignes_requete"] == 0.4
    assert res["categories"]["unite_legale"]["seules"] == {"PME": 6, "ETI": 0, "GE": 2}
    assert res["categories"]["transverses_tranche_ou_categorie"]["total"] == 2
    assert res["naf_multiples"]["dix"]["ou_exact"] and res["naf_multiples"]["max_accepte"] == 250
    assert res["departements"]["ou_exact"]
    assert res["naf2025"]["variable_qui_filtre"] == "activitePrincipaleNAF25UniteLegale"
    assert res["naf2025"]["champs"]["uniteLegale.activitePrincipaleNAF25UniteLegale"]["presence"] == 10
    prop = res["propositions"]
    assert prop["NAF_PAR_REQUETE"] == 250 and prop["DEPARTEMENTS_PAR_REQUETE"] == 8
    assert prop["VARIABLE_NAF"]["NAF2025"] == "activitePrincipaleNAF25UniteLegale"
    assert prop["ABSENTS_PAR"] == "-trancheEffectifsUniteLegale:*"
    assert res["pagination"]["nombre_1001"]["total"] is None
    assert "À reporter dans spontanees/parametres_sirene.py" in sortie
    assert "NAF_PAR_REQUETE = 250   # actuel : 1" in sortie


def test_autres_reponses(cle, tmp_path):
    code, sortie, res, _ = lancer(jeu(variable_naf25=None, max_ou=40, absents_ok=False), tmp_path)
    prop = res["propositions"]
    assert prop["NAF_PAR_REQUETE"] == 30
    # Rien trouvé : la valeur actuelle de parametres_sirene.py est gardée
    assert res["naf2025"]["variable_qui_filtre"] is None
    assert prop["VARIABLE_NAF"] == vs.P.VARIABLE_NAF and prop["ABSENTS_PAR"] == vs.P.ABSENTS_PAR
    assert res["naf2025"]["variable_vue_dans_les_reponses"] is None
    assert "Aucune variable NAF 2025 essayée ne filtre" in sortie


def test_variable_vue_mais_non_essayee(cle, tmp_path):
    code, sortie, res, _ = lancer(jeu(variable_naf25="activitePrincipaleNaf2025Ul"), tmp_path)
    assert res["naf2025"]["variable_vue_dans_les_reponses"] == "activitePrincipaleNaf2025Ul"
    assert "vue dans les réponses : activitePrincipaleNaf2025Ul" in sortie


def test_sans_cle_ou_cle_refusee(monkeypatch, tmp_path):
    monkeypatch.delenv("INSEE_API_KEY", raising=False)
    code, sortie, res, _ = lancer(jeu(), tmp_path)
    assert code == 1 and "INSEE_API_KEY absente" in sortie
    monkeypatch.setenv("INSEE_API_KEY", CLE)
    api = jeu()
    api.get = lambda *a, **k: Reponse(403, {"header": {"message": CLE}})
    code, sortie, res, _ = lancer(api, tmp_path)
    assert code == 1 and "clé INSEE refusée (403)" in sortie and CLE not in sortie
