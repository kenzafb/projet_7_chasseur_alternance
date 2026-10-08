"""Recherche France Travail (SPEC_SOURCES section 2) contre l'API simulée :
filtres par mode, découpage adaptatif au-delà de 3150 offres, dédoublonnage,
taille d'entreprise filtrée après récupération, options du profil."""

from datetime import datetime, timezone

import pytest

import france_travail.scraper as scraper
from database.dedup_db import lire_offres_vues
from france_travail import parametres_api
from shared.criteres import criteres_france_travail, normaliser_recherche
from tests.faux_france_travail import DEPTS, FausseAPI, Reponse, offre


@pytest.fixture
def api(monkeypatch):
    """API simulée branchée sur le scraper, sans pause ni token en cache."""
    fausse = FausseAPI()
    monkeypatch.setattr(scraper.requests, "get", fausse.get)
    monkeypatch.setattr(scraper.requests, "post", fausse.post)
    monkeypatch.setattr(scraper, "PAUSE_S", 0)
    monkeypatch.setattr(scraper, "_token_cache", {"token": None, "expire": 0})
    monkeypatch.setattr(scraper, "_maintenant", lambda: datetime(2026, 10, 8, tzinfo=timezone.utc))
    return fausse


class Journal(list):
    def __call__(self, msg):
        self.append(msg)

    def texte(self):
        return "\n".join(self)


def criteres(mode="alternance", **recherche):
    return criteres_france_travail({"recherche": recherche}, mode)


def recuperer(mode="alternance", **recherche):
    log = Journal()
    offres = scraper.recuperer_offres(criteres(mode, **recherche), log=log)
    return offres, log


# ─── Filtres par mode ─────────────────────────────────────────────────────────
def test_requetes_alternance_e2_et_fs_sans_qualification():
    reqs = scraper.requetes_initiales(**{k: criteres()[k] for k in ("filtres", "domaines")})
    assert reqs == [{"region": "11", "sort": "1", "natureContrat": "E2"},
                    {"region": "11", "sort": "1", "natureContrat": "FS"}]


def test_requetes_job_sans_qualification_ni_theme_par_defaut():
    reqs = scraper.requetes_initiales(**{k: criteres("job")[k] for k in ("filtres", "domaines")})
    assert [r["typeContrat"] for r in reqs] == ["CDD", "MIS", "SAI"]
    assert all("qualification" not in r and "theme" not in r and "natureContrat" not in r for r in reqs)


def test_requetes_avec_options_et_domaines(monkeypatch):
    c = criteres("job", domaines=["C", "M18"], themes=["13", "17"], secteurs=["62"])
    reqs = scraper.requetes_initiales(c["filtres"], c["domaines"])
    assert len(reqs) == 3 * 2 * 2          # 3 types, 2 thèmes, 2 groupes de domaine
    assert {r.get("grandDomaine") for r in reqs} == {"C", None}
    assert {r.get("domaine") for r in reqs} == {"M18", None}
    assert all(r["secteurActivite"] == "62" for r in reqs)
    # Valeurs multiples acceptées par l'API : regroupées
    monkeypatch.setitem(parametres_api.VALEURS_PAR_REQUETE, "typeContrat", 2)
    monkeypatch.setitem(parametres_api.VALEURS_PAR_REQUETE, "theme", None)
    reqs = scraper.requetes_initiales(c["filtres"], c["domaines"])
    assert sorted({r["typeContrat"] for r in reqs}) == ["CDD,MIS", "SAI"] and len(reqs) == 2 * 1 * 2
    assert {r["theme"] for r in reqs} == {"13,17"}


def test_grand_domaine_sans_parametre_remplace_par_ses_domaines(monkeypatch):
    monkeypatch.setattr(parametres_api, "PARAM_GRAND_DOMAINE", None)
    c = criteres(domaines=["C"])
    reqs = scraper.requetes_initiales(c["filtres"], c["domaines"])
    assert sorted({r["domaine"] for r in reqs}) == ["C11", "C12", "C13", "C14", "C15"]


def test_themes_seulement_en_mode_job():
    assert "theme" not in criteres("alternance", themes=["13"])["filtres"]
    assert criteres("job", themes=["13", "99"])["filtres"]["theme"] == ["13"]


def test_recuperation_simple_et_dedoublonnage(api):
    api.offres = [offre(1, nature="E2"), offre(2, nature="FS"), offre(3, nature="E1"),
                  offre(4, type_contrat="CDD", nature="E1", themes=("13", "17")),
                  offre(5, type_contrat="MIS", nature="E1", themes=("17",))]
    offres, _ = recuperer()
    assert sorted(o["id"] for o in offres) == ["FT1", "FT2"]
    offres, _ = recuperer("job", themes=["13", "17"])
    assert sorted(o["id"] for o in offres) == ["FT4", "FT5"]     # FT4 a les deux thèmes : une fois
    assert all("qualification" not in r for r in api.recherches)


def test_secteur_employeur(api):
    api.offres = [offre(1, secteur="62"), offre(2, secteur="68")]
    offres, _ = recuperer(secteurs=["68"])
    assert [o["id"] for o in offres] == ["FT2"]


# ─── Découpage ────────────────────────────────────────────────────────────────
def _plages_valides(api):
    for r in api.recherches:
        debut, fin = (int(x) for x in r["range"].split("-"))
        assert fin - debut + 1 <= 150 and debut <= 3000


def test_decoupage_par_departement(api):
    api.offres = [offre(n, dept=DEPTS[n % 8], jours=n % 50) for n in range(3313)]
    offres, log = recuperer()
    assert len(offres) == 3313
    _plages_valides(api)
    assert any("departement" in r for r in api.recherches)
    assert "⚠️" not in log.texte()
    assert "3313 offres distinctes" in log.texte()


def test_decoupage_jusqu_aux_domaines_puis_aux_dates(api):
    # Paris seul dépasse : grands domaines, puis domaines de M, puis fenêtres de dates pour M18
    api.offres = ([offre(n, dept="75", domaine="M18", jours=n % 200) for n in range(3400)]
                  + [offre(10000 + n, dept="75", domaine="M13") for n in range(100)]
                  + [offre(20000 + n, dept="92", domaine="C15") for n in range(50)])
    offres, log = recuperer()
    assert len(offres) == 3550
    _plages_valides(api)
    assert any(r.get("grandDomaine") == "M" for r in api.recherches)
    assert any(r.get("domaine") == "M18" and "minCreationDate" in r for r in api.recherches)
    assert "⚠️" not in log.texte()


def test_valeurs_multiples_eclatees_avant_les_dates(api, monkeypatch):
    monkeypatch.setitem(parametres_api.VALEURS_PAR_REQUETE, "natureContrat", 2)
    api.offres = [offre(n, dept="75", domaine="M18", nature="E2" if n % 2 else "FS", jours=n % 30)
                  for n in range(3300)]
    offres, log = recuperer(domaines=["M18"])
    assert len(offres) == 3300
    assert any(r.get("natureContrat") == "E2" for r in api.recherches)


def test_rien_tronque_en_silence(api):
    """Même date, même lieu, même domaine : plus aucun découpage possible."""
    api.offres = [offre(n, dept="75", domaine="M18") for n in range(3200)]
    for o in api.offres:
        o["dateCreation"] = "2026-09-30T08:00:00.000Z"
    offres, log = recuperer(domaines=["M18"])
    assert len(offres) == 3150
    assert "aucun découpage possible : 50 non récupérées" in log.texte()
    assert "50 non récupérées (plafond)" in log.texte()


def test_couverture_incomplete_signalee(api):
    """Offres rattachées à la région sans département : le découpage les perd, c'est dit."""
    api.offres = [offre(n, dept=DEPTS[n % 8]) for n in range(3200)] + [offre(9000 + n, dept="11") for n in range(10)]
    _, log = recuperer()
    assert "Découpage par département : 3200 offres retrouvées sur 3210" in log.texte()


def test_erreur_d_une_requete_n_arrete_pas_les_autres(api):
    api.offres = [offre(1, nature="E2"), offre(2, nature="FS")]
    rechercher = api.rechercher
    api.rechercher = lambda p: Reponse(500, {"message": "panne"}) if p.get("natureContrat") == "E2" else rechercher(p)
    offres, log = recuperer()
    assert [o["id"] for o in offres] == ["FT2"]
    assert "requête abandonnée" in log.texte() and "1 en erreur" in log.texte()


# ─── Taille d'entreprise, ordre, marquage ─────────────────────────────────────
def test_filtre_de_taille_apres_recuperation(api, utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    api.offres = [offre(1, tranche="10 à 19 salariés"), offre(2, tranche="1 ou 2 salariés"),
                  offre(3, tranche=None), offre(4, tranche="Non renseigné"), offre(5, tranche="32")]
    c = criteres(tailles=["10_49", "250_4999"], taille_inconnue=False)
    log = Journal()
    retenues = scraper.chercher_offres(uid, c, log=log)
    assert sorted(o["titre"] for o in retenues) == ["Offre 1", "Offre 5"]
    assert "3 offres écartées par la taille d'entreprise (dont 2 sans information)" in log.texte()
    # Les écartées ne sont pas marquées vues : elles reviennent si la taille change
    assert len(lire_offres_vues(uid, "alternance")) == 2
    c = criteres(tailles=["10_49"], taille_inconnue=True)
    assert sorted(o["titre"] for o in scraper.chercher_offres(uid, c, log=log)) == ["Offre 3", "Offre 4"]


def test_job_ecarte_l_alternance_et_trie_par_date(api, utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    api.offres = [offre(1, nature="E1", type_contrat="CDD", jours=5),
                  offre(2, nature="E2", type_contrat="CDD", jours=1),
                  offre(3, nature="E1", type_contrat="MIS", jours=0),
                  offre(4, nature="E1", type_contrat="SAI", jours=9)]
    retenues = scraper.chercher_offres(uid, criteres("job"), mode="job", limite_lot=2, marquer=False)
    assert [o["titre"] for o in retenues] == ["Offre 3", "Offre 1"]


# ─── Profil ───────────────────────────────────────────────────────────────────
def test_normalisation_des_options():
    assert normaliser_recherche({"secteurs": ["62", "62", "00", 68], "tailles": ["10_49", "x"],
                                 "taille_inconnue": "non", "themes": ["17", "01"], "autre": 1}) == {
        "secteurs": ["62", "68"], "tailles": ["10_49"], "taille_inconnue": True, "themes": ["17"], "autre": 1}
    assert normaliser_recherche({"taille_inconnue": False})["taille_inconnue"] is False
    c = criteres()
    assert (c["tailles"], c["taille_inconnue"], c["domaines"]) == ([], True, [])


def test_options_et_profil_par_l_api(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    options = client.get("/api/criteres_options").json()
    assert len(options["secteurs"]) == 88 and options["secteurs"][0] == {
        "code": "01", "libelle": "Culture et production animale, chasse et services annexes"}
    assert [t["cle"] for t in options["tailles"]][0] == "moins_10"
    assert "alternant" in options["tailles"][0]["avertissement"]
    assert options["themes"] == [{"code": "13", "libelle": "Métiers saisonniers, de vacances / Jobs d'été"},
                                 {"code": "17", "libelle": "Métiers accessibles sans diplôme et sans expérience"}]
    r = client.post("/api/profil", json={"recherche": {"secteurs": ["62"], "tailles": ["50_249"],
                                                       "taille_inconnue": False}})
    assert r.json()["ok"] is True
    rech = client.get("/api/profil").json()["recherche"]
    assert (rech["secteurs"], rech["tailles"], rech["taille_inconnue"]) == (["62"], ["50_249"], False)
