"""Nom affiché d'une entreprise (D192) : dénomination de l'unité légale
d'abord, nom d'établissement ou enseigne ensuite (« PARIS HOTEL DE VILLE »,
établissement de la BRED, SIREN 552091795)."""

import spontanees.noms_entreprise as N
from database.connexion import SessionLocal
from database.entreprises_db import ajouter_entreprises, calculer_stats
from database.models import Entreprise


class Rep:
    status_code = 200

    def json(self):
        return {"results": [{"siren": "552091795", "sigle": "BRED", "nom_complet": "BRED BANQUE POPULAIRE (BRED)",
                             "nom_raison_sociale": "BRED BANQUE POPULAIRE", "siege": {"code_postal": "75012"}}]}


def test_denomination_lue_dans_l_annuaire(monkeypatch):
    monkeypatch.setattr(N.requests, "get", lambda *a, **k: Rep())
    e = {"siren": "552091795", "nom_commercial": "PARIS HOTEL DE VILLE", "sources": ["lba"],
         "_extra": {"autres_noms": ["BRED"]}}
    assert N.completer(e) == ["BRED"]                      # autres noms déjà connus : gardés
    assert e["denomination"] == "BRED BANQUE POPULAIRE"     # dénomination demandée quand même
    assert N.fiche_annuaire("552091795")["denomination"] == "BRED BANQUE POPULAIRE"


def test_denomination_sirene_sans_appel(monkeypatch):
    def interdit(*a, **k):
        raise AssertionError("annuaire appelé")
    monkeypatch.setattr(N.requests, "get", interdit)
    e = {"siren": "123456789", "sources": ["sirene"], "_extra": {"nom": "ACME SAS", "autres_noms": []}}
    N.completer(e)
    assert e["denomination"] == "ACME SAS"


def test_affichage_denomination_puis_etablissement(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": "55209179502456", "siren": "552091795", "nom": "PARIS HOTEL DE VILLE"},
                              {"siret": "12345678900011", "nom": "ACME SAS", "nom_commercial": "Acme Paris"},
                              {"siret": "98765432100011", "nom": "Solo SARL"}])
    with SessionLocal() as db:
        bred = db.query(Entreprise).filter(Entreprise.siren == "552091795").one()
        bred.sources = ["lba"]
        bred.extra = {**bred.extra, "denomination": "BRED BANQUE POPULAIRE"}
        db.commit()
    noms = {(e["nom"], e["nom_etablissement"]) for e in calculer_stats(uid, "alternance")["prochaines"]}
    assert noms == {("BRED BANQUE POPULAIRE", "PARIS HOTEL DE VILLE"), ("ACME SAS", "Acme Paris"), ("Solo SARL", "")}
