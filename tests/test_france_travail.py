"""Recherche France Travail (SPEC_SOURCES section 2) contre l'API simulée :
filtres par mode, découpage adaptatif au-delà de 3150 offres, dédoublonnage,
taille d'entreprise filtrée après récupération, options du profil."""

from datetime import datetime, timedelta, timezone

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
def test_requetes_alternance_e2_et_fs_sans_qualification(monkeypatch):
    reqs = scraper.requetes_initiales(**{k: criteres()[k] for k in ("filtres", "domaines")})
    assert reqs == [{"region": "11", "sort": "1", "natureContrat": "E2,FS"}]   # liste acceptée (vérifié)
    monkeypatch.setitem(parametres_api.VALEURS_PAR_REQUETE, "natureContrat", 1)
    reqs = scraper.requetes_initiales(**{k: criteres()[k] for k in ("filtres", "domaines")})
    assert reqs == [{"region": "11", "sort": "1", "natureContrat": "E2"},
                    {"region": "11", "sort": "1", "natureContrat": "FS"}]


def test_requetes_job_sans_qualification_ni_theme_par_defaut():
    reqs = scraper.requetes_initiales(**{k: criteres("job")[k] for k in ("filtres", "domaines")})
    assert [r["typeContrat"] for r in reqs] == ["CDD,MIS,SAI"]
    assert all("qualification" not in r and "theme" not in r and "natureContrat" not in r for r in reqs)


def test_requetes_avec_options_et_domaines(monkeypatch):
    c = criteres("job", domaines=["C", "M18"], themes=["13", "17"], secteurs=["62"])
    reqs = scraper.requetes_initiales(c["filtres"], c["domaines"])
    assert len(reqs) == 1 * 2 * 2          # types en une liste, 2 thèmes (liste refusée), 2 groupes de domaine
    assert {r.get("grandDomaine") for r in reqs} == {"C", None}
    assert {r.get("domaine") for r in reqs} == {"M18", None}
    assert all(r["secteurActivite"] == "62" and r["typeContrat"] == "CDD,MIS,SAI" for r in reqs)
    # Paquets de la taille acceptée par l'API
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


def _sans_decoupage_geo_ni_domaine(api):
    for r in api.recherches:
        assert not {"departement", "grandDomaine", "domaine"} & set(r), r


def test_decoupage_par_dates_seulement_retrouve_tout(api):
    """Offres sans département ni domaine comprises : le découpage par
    département ou domaine les perdait (vérification du 8 octobre 2026)."""
    api.offres = ([offre(n, dept=DEPTS[n % 8], domaine="M18" if n % 3 else "J11", jours=n % 50)
                   for n in range(3313)]
                  + [offre(5000 + n, dept="11", domaine="", jours=n % 5) for n in range(40)])
    offres, log = recuperer()
    assert len(offres) == 3353
    _plages_valides(api)
    _sans_decoupage_geo_ni_domaine(api)
    assert any("minCreationDate" in r for r in api.recherches)
    assert "3353 annoncées par l'API, 3353 récupérées, écart 0" in log.texte()
    assert "⚠️" not in log.texte()


def test_pas_de_bilan_sans_decoupage(api):
    api.offres = [offre(n) for n in range(10)]
    _, log = recuperer()
    assert "annoncées par l'API" not in log.texte()


def test_marge_de_fuseau(api, monkeypatch):
    """L'API lit les dates en heure de Paris : sans marge, les dernières
    heures d'offres manquent ; avec la marge, l'union retrouve le total."""
    api.decalage_heures = 2
    maintenant = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(scraper, "_maintenant", lambda: maintenant)
    api.offres = [offre(n, jours=n % 40) for n in range(3300)]
    for n, o in enumerate(api.offres[:60]):          # publiées dans la dernière heure
        o["dateCreation"] = (maintenant - timedelta(minutes=n % 59)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    offres, log = recuperer()
    assert len(offres) == 3300 and "écart 0" in log.texte()
    monkeypatch.setattr(parametres_api, "MARGE_FIN_FENETRE_HEURES", 0)
    limite = (maintenant - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    perdues = sum(1 for o in api.offres if o["dateCreation"][:19] > limite)
    assert perdues >= 60
    offres, log = recuperer()
    assert len(offres) == 3300 - perdues
    assert f"3300 annoncées par l'API, {3300 - perdues} récupérées, écart {perdues}" in log.texte()


def test_bornes_communes_dedoublonnees(api):
    """Deux moitiés partagent leur borne : une offre publiée pile à cette
    seconde est lue deux fois et comptée une seule."""
    api.offres = [offre(n, jours=n % 60) for n in range(3300)]
    offres, log = recuperer()
    assert len(offres) == len({o["id"] for o in offres}) == 3300


def test_rien_tronque_en_silence(api):
    """Même heure de publication : plus aucun découpage possible."""
    api.offres = [offre(n, dept="75", domaine="M18") for n in range(3200)]
    for o in api.offres:
        o["dateCreation"] = "2026-09-30T08:00:00.000Z"
    offres, log = recuperer(domaines=["M18"])
    assert len(offres) == 3150
    assert "découpage impossible : 50 non récupérées" in log.texte()
    assert "3200 annoncées par l'API, 3150 récupérées, écart 50" in log.texte()
    assert "50 non récupérées (plafond)" in log.texte()
    # Découpé jusqu'à l'heure, pas plus fin
    fenetres = [(r["minCreationDate"], r["maxCreationDate"]) for r in api.recherches if "minCreationDate" in r]
    plus_courte = min(scraper._date(b) - scraper._date(a) for a, b in fenetres)
    assert timedelta(minutes=30) < plus_courte <= timedelta(hours=1)


def test_erreur_d_une_requete_n_arrete_pas_les_autres(api, monkeypatch):
    monkeypatch.setitem(parametres_api.VALEURS_PAR_REQUETE, "natureContrat", 1)
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


def test_dates_ignorees_tronque_avec_message(api):
    api.params_reconnus -= {"grandDomaine", "domaine", "minCreationDate", "maxCreationDate"}
    api.offres = [offre(n, dept="75", domaine="M18", jours=n % 100) for n in range(3300)]
    offres, log = recuperer(domaines=["M18"])
    assert len(offres) == 3150
    assert "Découpage par date sans effet" in log.texte()
    assert "150 non récupérées" in log.texte()
    assert len(api.recherches) < 100


def test_secteurs_par_paquets_de_deux(api):
    """secteurActivite accepte deux valeurs par requête (vérifié le 8 octobre 2026)."""
    c = criteres(secteurs=["62", "68", "86"])
    assert sorted(r["secteurActivite"] for r in scraper.requetes_initiales(c["filtres"], c["domaines"])) == [
        "62,68", "86"]
    api.max_valeurs = {"secteurActivite": 2}
    api.offres = [offre(1, secteur="62"), offre(2, secteur="68"), offre(3, secteur="86"), offre(4, secteur="47")]
    offres, log = recuperer(secteurs=["62", "68", "86"])
    assert sorted(o["id"] for o in offres) == ["FT1", "FT2", "FT3"] and "⚠️" not in log.texte()
