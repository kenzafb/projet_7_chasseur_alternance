"""scripts/revalider_emails_en_base.py (D186) : examen en lecture seule,
écriture en une seule transaction à la fin ; un Ctrl+C pendant l'examen
n'écrit rien."""

import pytest

import scripts.revalider_emails_en_base as R
from database.connexion import SessionLocal
from database.entreprises_db import ajouter_entreprises
from database.models import Entreprise


@pytest.fixture
def entreprises(utilisateur, monkeypatch, tmp_path):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": f"S{i}", "nom": f"Ent {i}"} for i in range(3)])
    with SessionLocal() as db:
        for i, e in enumerate(db.query(Entreprise).order_by(Entreprise.id)):
            # Site déjà vérifié : pas de réseau ; l'adresse d'un autre domaine est écartée
            e.emails_trouves = [f"contact@ent{i}.fr", f"rh@autre{i}.fr"]
            e.extra = {**(e.extra or {}), "site_verifie": {"verifie": True, "domaine": f"ent{i}.fr"}}
        db.commit()
    monkeypatch.setattr(R, "ecrire_json", lambda nom, d: tmp_path / f"{nom}.json")
    return uid


def _adresses():
    with SessionLocal() as db:
        return [e.emails_trouves for e in db.query(Entreprise).order_by(Entreprise.id)]


def test_applique_tout_en_une_fois(entreprises):
    assert R.main(["--appliquer"]) == 0
    assert _adresses() == [["contact@ent0.fr"], ["contact@ent1.fr"], ["contact@ent2.fr"]]


def test_ctrl_c_pendant_l_examen_n_ecrit_rien(entreprises, monkeypatch, capsys):
    avant = _adresses()
    vraie, appels = R.revalider_une, []

    def interrompue(e, v):
        appels.append(e.id)
        if len(appels) == 2:
            raise KeyboardInterrupt
        return vraie(e, v)
    monkeypatch.setattr(R, "revalider_une", interrompue)
    assert R.main(["--appliquer"]) == 130
    assert _adresses() == avant
    assert "rien n'a été écrit" in capsys.readouterr().out


def test_entreprise_modifiee_entre_l_examen_et_l_ecriture_non_touchee(entreprises, monkeypatch):
    vrai_examen = R.examiner

    def examen_puis_modification(db, args):
        res = vrai_examen(db, args)
        with SessionLocal() as autre:      # l'application écrit pendant ce temps
            e = autre.query(Entreprise).order_by(Entreprise.id).first()
            e.emails_trouves = ["nouveau@ent0.fr"]
            autre.commit()
        return res
    monkeypatch.setattr(R, "examiner", examen_puis_modification)
    assert R.main(["--appliquer"]) == 0
    assert _adresses() == [["nouveau@ent0.fr"], ["contact@ent1.fr"], ["contact@ent2.fr"]]


def test_sans_appliquer_rien_n_est_ecrit(entreprises):
    avant = _adresses()
    assert R.main([]) == 0
    assert _adresses() == avant
