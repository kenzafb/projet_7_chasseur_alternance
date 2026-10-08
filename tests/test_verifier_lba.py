"""scripts/verifier_lba.py contre l'API simulée : codes par requête, rayon,
niveau de diplôme, plafond, structure des entreprises, offres France
Travail, propositions, aucune donnée sensible écrite."""

import json

import pytest

from scripts import verifier_lba as vl
from tests.faux_lba import FausseLBA, Reponse, entreprise, offre

CLE = "cle-lba-tres-secrete"


def jeu(**options):
    offres = [offre(i, rome=f"M180{i % 10}", niveau=5 + i % 3) for i in range(200)]
    offres += [offre(1000 + i, partenaire="France Travail") for i in range(20)]
    offres += [offre(2000 + i, partenaire="Hellowork", rome="D1214") for i in range(30)]
    ents = [entreprise(i, rome="M1805", email="rh@societe.fr" if i % 2 else None) for i in range(170)]
    return FausseLBA(offres, ents, **options)


@pytest.fixture
def cle(monkeypatch):
    monkeypatch.setenv("LBA_API_KEY", CLE)


def lancer(api, tmp_path):
    sorties = []
    code = vl.main(session=api, sortie=tmp_path, pause=0, afficher=sorties.append)
    fichier = tmp_path / "verification_api.json"
    texte = fichier.read_text(encoding="utf-8") if fichier.exists() else ""
    return code, "\n".join(sorties), (json.loads(texte) if texte else None), texte


def test_valeurs_trouvees(cle, tmp_path):
    code, sortie, res, texte = lancer(jeu(), tmp_path)
    assert code == 0
    prop = res["propositions"]
    assert prop["CODES_PAR_REQUETE"] == 20
    assert prop["ACCEPTE_SANS_CODES"] is False
    assert prop["RAYON_MAX_KM"] == 200
    assert prop["PARAM_NIVEAU"] == "target_diploma_level"
    assert prop["VALEURS_NIVEAU"] == {"3": "3", "4": "4", "5": "5", "6": "6", "7": "7"}
    assert prop["PLAFOND_PAR_SOURCE"] == 150            # offres LBA et entreprises butent sur 150
    assert res["niveau"]["par_niveau"]["6"]["niveaux_lus_dans_les_offres"] == {"6": 60}   # M1800 hors des codes de référence
    assert res["france_travail"]["partenaires_france_travail"] == ["France Travail"]
    assert res["france_travail"]["exclusion_efficace"] is True
    assert "À reporter dans france_travail/parametres_lba.py" in sortie
    assert "CODES_PAR_REQUETE = 20   # inchangé" in sortie
    assert "RAYON_MAX_KM = 200   # actuel : 60" in sortie


def test_structure_des_entreprises_sans_donnees_sensibles(cle, tmp_path):
    code, sortie, res, texte = lancer(jeu(), tmp_path)
    ent = res["entreprises"]
    assert ent["champs_par_nom"]["siret"] == ["workplace.siret"]
    assert "apply.email" in ent["champs_par_nom"]["email"]
    assert "apply.recipient_id" in ent["champs_par_nom"]["candidature"]
    assert ent["chemins_de_parametres_lba"]["siret"]["presence"]["workplace.siret"] > 0
    # Ni clé, ni email complet, ni téléphone dans le fichier
    assert CLE not in texte and "rh@societe.fr" not in texte and "0102030405" not in texte
    assert "***@societe.fr" in texte


def test_autres_reponses_de_l_api(cle, tmp_path):
    api = jeu(param_niveau="diploma", codes_max=50, rayon_max=100, sans_codes=True, exclusion_ignoree=True)
    code, sortie, res, _ = lancer(api, tmp_path)
    prop = res["propositions"]
    assert prop["CODES_PAR_REQUETE"] == 50 and prop["RAYON_MAX_KM"] == 100
    assert prop["ACCEPTE_SANS_CODES"] is True
    assert prop["PARAM_NIVEAU"] == "diploma"
    assert res["france_travail"]["restantes_malgre_exclusion"] == {"France Travail": 20}
    assert "encore présentes malgré l'exclusion" in sortie


def test_niveau_introuvable_garde_la_valeur_actuelle(cle, tmp_path):
    code, sortie, res, _ = lancer(jeu(param_niveau="autre"), tmp_path)
    assert res["niveau"]["param"] is None
    assert res["propositions"]["PARAM_NIVEAU"] == vl.P.PARAM_NIVEAU
    assert "Aucun paramètre de niveau ne filtre" in sortie


def test_sans_cle_ou_cle_refusee(monkeypatch, tmp_path):
    monkeypatch.delenv("LBA_API_KEY", raising=False)
    code, sortie, res, _ = lancer(jeu(), tmp_path)
    assert code == 1 and "LBA_API_KEY absente" in sortie and res is None
    monkeypatch.setenv("LBA_API_KEY", CLE)
    api = jeu()
    api.get = lambda *a, **k: Reponse(401, {"error": f"clé {CLE} inconnue"})
    code, sortie, res, _ = lancer(api, tmp_path)
    assert code == 1 and "clé LBA refusée" in sortie and CLE not in sortie
