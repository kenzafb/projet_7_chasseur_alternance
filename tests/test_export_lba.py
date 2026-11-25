"""Entreprises à fort potentiel tirées de l'export LBA (D163) : lecture en
flux, seules les entreprises d'IDF gardées, filtre du profil, rafraîchi au
plus une fois par semaine, ancien fichier gardé si l'export échoue."""

import json
from datetime import datetime, timedelta, timezone

import pytest
import requests

from offres import export_lba as X
from tests.faux_lba import entreprise, offre, siret_lba


def _recruteur(n, rome="M1805", cp="75012", taille="20-49"):
    e = entreprise(n, rome=rome, cp=cp, taille=taille)
    e["identifier"]["partner_label"] = "recruteurs_lba"
    e["offer"] = {"title": "recruteurs_lba", "rome_codes": [rome], "description": "recruteurs_lba"}
    return e


EXPORT = [offre(1), _recruteur(1), _recruteur(2, cp="22100"), _recruteur(3, rome="K2111"),
          _recruteur(4, taille="0-0"), _recruteur(5, cp="93200")]


class Flux:
    def __init__(self, texte, bloc=7):
        self.octets, self.bloc = texte.encode("utf-8"), bloc

    def iter_content(self, taille):
        for i in range(0, len(self.octets), self.bloc):   # coupe aussi au milieu d'un caractère
            yield self.octets[i:i + self.bloc]

    def raise_for_status(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Reponse:
    def __init__(self, statut, corps):
        self.status_code, self._corps, self.text = statut, corps, json.dumps(corps)

    def json(self):
        return self._corps


@pytest.fixture
def export(monkeypatch):
    # FICHIER et META : dans tmp_path (conftest, dossiers_temporaires)
    monkeypatch.setenv("LBA_API_KEY", "cle")
    etat = {"appels": 0, "panne": False, "objets": EXPORT}

    def get(url, headers=None, timeout=None, stream=False, **_):
        if url == X.P.URL_EXPORT:
            etat["appels"] += 1
            if etat["panne"]:
                raise requests.ConnectionError("injoignable")
            return Reponse(200, {"url": "https://s3.example/export.json", "lastUpdate": "2026-11-22T02:02:02.000Z"})
        return Flux(json.dumps(etat["objets"], ensure_ascii=False, indent=2))
    monkeypatch.setattr(X.requests, "get", get)
    return etat


def _profil(**recherche):
    return {"recherche": {"domaines": ["M18"], **recherche}}


def test_lecture_en_flux_par_petits_morceaux():
    objets = [{"a": i, "t": "é" * (i % 5)} for i in range(200)]
    texte = json.dumps(objets, ensure_ascii=False)
    assert list(X.objets_en_flux(X.morceaux_http(Flux(texte, bloc=3)))) == objets
    assert list(X.objets_en_flux(iter(["[", "]"]))) == []


def test_seules_les_entreprises_d_idf_gardees(export):
    logs = []
    assert X.preparer(logs.append)
    m = X.meta()
    assert (m["objets_lus"], m["recruteurs"], m["recruteurs_idf"]) == (6, 5, 4)    # Côtes-d'Armor écartée, offre ignorée
    assert m["export_du"].startswith("2026-11-22")
    assert sorted(e["siret"] for e in X.recruteurs()) == sorted(siret_lba(n) for n in (1, 3, 4, 5))


def test_filtre_du_profil(export):
    X.preparer()
    garder = X.lba.filtre_entreprise(_profil(departements=["75"]))
    codes = X.codes_metiers(X.domaines_du_profil(_profil()))
    # Code métier hors M18 (3), sans salarié (4, « 0-0 » exclu par défaut), autre département (5)
    assert [e["siret"] for e in X.recruteurs(codes, garder)] == [siret_lba(1)]
    assert "romes" not in next(X.recruteurs(codes, garder))


def test_rafraichi_au_plus_une_fois_par_semaine(export, monkeypatch):
    X.preparer()
    X.preparer()
    assert export["appels"] == 1
    m = X.meta()
    m["le"] = (datetime.now(timezone.utc) - timedelta(days=X.FRAICHEUR_JOURS, minutes=1)).isoformat()
    X.META.write_text(json.dumps(m))
    export["objets"] = EXPORT + [_recruteur(6)]
    X.preparer()
    assert export["appels"] == 2 and X.meta()["recruteurs_idf"] == 5


def test_export_injoignable_ancien_fichier_garde(export):
    X.preparer()
    m = X.meta()
    m["le"] = "2020-01-01T00:00:00+00:00"
    X.META.write_text(json.dumps(m))
    export["panne"] = True
    logs = []
    assert X.preparer(logs.append) and "export du 2026-11-22" in logs[-1]
    assert len(list(X.recruteurs())) == 4


def test_sans_cle_ni_fichier(export, monkeypatch):
    monkeypatch.delenv("LBA_API_KEY")
    logs = []
    assert X.entreprises_pour_profil(_profil(), logs.append) is None and "LBA_API_KEY" in logs[0]


def test_etape_trouver_des_entreprises_lit_l_export(export, utilisateur, monkeypatch):
    import spontanees.recuperation as fetch
    from database.entreprises_db import lire_entreprises
    from database.profil_db import sauvegarder_profil
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    sauvegarder_profil(uid, _profil())
    monkeypatch.setattr(fetch, "_cle", lambda: "")              # Sirene non interrogé
    monkeypatch.setattr(X.lba, "rechercher_pour_profil", lambda *a, **k: pytest.fail("plus de recherche"))
    logs = []
    fetch.main(uid, max_entreprises=10, log_fn=logs.append)
    ents = lire_entreprises(uid)
    assert sorted(e["_extra"]["siret"] for e in ents) == sorted(siret_lba(n) for n in (1, 5))
    assert all(e["sources"] == ["lba"] for e in ents)
    assert any("2 nouvelles entreprises à fort potentiel" in m for m in logs)
