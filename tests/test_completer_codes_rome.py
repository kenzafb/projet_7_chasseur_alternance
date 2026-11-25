"""scripts/completer_codes_rome.py (D208) : n'écrit que code_rome, lecture
seule par défaut, offre disparue laissée telle quelle."""

import importlib
import sys
from pathlib import Path

import pytest
import requests
from sqlalchemy import select, text

from database.connexion import SessionLocal, engine
from database.models import Base, Candidature
from offres import france_travail as ft
from shared.offres import generer_id

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
script = importlib.import_module("completer_codes_rome")
LIEN = "https://candidat.francetravail.fr/offres/recherche/detail/"


class Reponse:
    def __init__(self, statut, corps=None, entetes=None):
        self.status_code, self._corps, self.headers = statut, corps, entetes or {}

    def json(self):
        if self._corps is None:
            raise ValueError
        return self._corps


class API:
    """Offres par identifiant : code, statut HTTP ou exception."""

    def __init__(self, offres):
        self.offres, self.appels = offres, []

    def get(self, url, headers, timeout):
        ident = url.removeprefix(script.URL_DETAIL)
        self.appels.append(ident)
        r = self.offres[ident]
        if isinstance(r, list):
            r = r.pop(0)
        if isinstance(r, BaseException) or (isinstance(r, type) and issubclass(r, BaseException)):
            raise r
        return Reponse(r) if isinstance(r, int) else Reponse(200, {"id": ident, "romeCode": r, "intitule": "Autre"})


@pytest.fixture
def offres(utilisateur, monkeypatch):
    """Cinq offres à compléter, deux utilisateurs ; application arrêtée, jeton donné."""
    _, a = utilisateur("a@test.fr")
    _, b = utilisateur("b@test.fr")
    with SessionLocal() as db:
        def ajouter(uid, mode, ident, lien=None, **k):
            db.add(Candidature(**{"user_id": uid, "mode": mode, "ref_offre": generer_id(ident), "titre": f"T{ident}",
                               "lien": LIEN + ident if lien is None else lien, "source": "France Travail",
                               "description": "d", "score": 5, "statut": "gardee", **k}))
        ajouter(a, "stage", "1111111")
        ajouter(a, "job", "1111111")                                     # même offre, deux modes
        ajouter(b, "stage", "2222222")
        ajouter(a, "stage", "3333333")
        ajouter(a, "stage", "4444444", lien="https://partenaire.fr/offre")    # identifiant non lisible
        ajouter(a, "stage", "5555555", lien=LIEN + "1111111")                 # lien d'une autre offre
        ajouter(a, "stage", "6666666", code_rome="M1805")                     # déjà remplie
        ajouter(a, "alternance", "7777777", source="La Bonne Alternance")
        db.commit()
    monkeypatch.setattr(script, "application_lancee", lambda *x, **k: [])
    monkeypatch.setattr(ft, "get_token", lambda log=None: "jeton")
    monkeypatch.setattr(script.time, "sleep", lambda s: None)
    api = API({"1111111": "M1855", "2222222": "E1206", "3333333": 204})
    monkeypatch.setattr(script.requests, "get", api.get)
    return api


def photo(sans_code=False):
    with SessionLocal() as db:
        return {t.name: [tuple(v for c, v in x._mapping.items() if not (sans_code and c == "code_rome"))
                         for x in db.execute(select(t).order_by(t.c.id))] for t in Base.metadata.sorted_tables}


def codes():
    with SessionLocal() as db:
        return [c.code_rome for c in db.scalars(select(Candidature).order_by(Candidature.id))]


def test_lecture_seule_par_defaut(offres, capsys):
    avant = photo()
    assert script.main([]) == 0
    assert photo() == avant and offres.appels == ["1111111", "2222222", "3333333"]
    sortie = capsys.readouterr().out
    assert "6 offre(s) France Travail sans code métier" in sortie
    assert "3 à remplir, 1 qui n'existent plus, 0 sans code dans l'API, 2 sans identifiant lisible, 0 en erreur" in sortie
    assert "Lecture seule : rien n'est écrit" in sortie


def test_appliquer_n_ecrit_que_code_rome(offres):
    avant = photo(sans_code=True)
    assert script.main(["--appliquer"]) == 0
    assert codes() == ["M1855", "M1855", "E1206", "", "", "", "M1805", ""]
    assert photo(sans_code=True) == avant                  # titre, statut, note, autres tables : intacts
    offres.appels.clear()
    assert script.main(["--appliquer"]) == 0               # relancé : seulement ce qui reste vide
    assert offres.appels == ["3333333"]


@pytest.mark.parametrize("reponse", [500, requests.ConnectionError, "??"])
def test_erreur_laissee_vide(offres, reponse):
    offres.offres["2222222"] = reponse
    assert script.main(["--appliquer"]) == 0
    assert codes()[:3] == ["M1855", "M1855", ""]


def test_429_un_nouvel_essai(offres):
    offres.offres["2222222"] = [429, "E1206"]
    assert script.main(["--appliquer"]) == 0 and codes()[2] == "E1206"


def test_acces_refuse_rien_d_ecrit(offres, capsys):
    offres.offres["3333333"] = 401
    avant = photo()
    assert script.main(["--appliquer"]) == 1 and photo() == avant
    assert "401" in capsys.readouterr().out


def test_sans_jeton(offres, monkeypatch):
    monkeypatch.setattr(ft, "get_token", lambda log=None: None)
    assert script.main([]) == 1 and offres.appels == []


def test_application_lancee_avant_ou_pendant(offres, monkeypatch):
    avant = photo()
    monkeypatch.setattr(script, "application_lancee", lambda *x, **k: ["processus 42"])
    assert script.main(["--appliquer"]) == 1 and offres.appels == []
    assert script.main([]) == 0                            # lecture seule : permise
    etats = [[], ["processus 42"]]
    monkeypatch.setattr(script, "application_lancee", lambda *x, **k: etats.pop(0))
    assert script.main(["--appliquer"]) == 1 and photo() == avant


def test_interruption_rien_d_ecrit(offres):
    offres.offres["3333333"] = KeyboardInterrupt
    avant = photo()
    assert script.main(["--appliquer"]) == 130 and photo() == avant


def test_une_seule_transaction(offres):
    with engine.begin() as cx:
        cx.execute(text("CREATE TRIGGER bloque BEFORE UPDATE ON candidatures WHEN NEW.code_rome = 'E1206' "
                        "BEGIN SELECT RAISE(ABORT, 'non'); END"))
    with pytest.raises(Exception, match="non"):
        script.main(["--appliquer"])
    assert codes()[:3] == ["", "", ""]


def test_migration_manquante(offres, capsys):
    with engine.begin() as cx:
        cx.execute(text("ALTER TABLE candidatures DROP COLUMN code_rome"))
    assert script.main([]) == 1
    assert "alembic upgrade head" in capsys.readouterr().out
