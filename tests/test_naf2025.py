"""Bascule NAF 2025 (phase 8) : code NAF des entreprises dans les deux
nomenclatures (D112), migration 0014."""

import json
import sqlite3

import pytest
from alembic import command

import spontanees.fetch_entreprises as fetch
from database.entreprises_db import ajouter_entreprises, ajouter_entreprises_lba, lire_entreprises
from database.profil_db import sauvegarder_profil
from database.schema import config_alembic
from shared import naf
from spontanees import parametres_sirene as P
from tests.faux_sirene import FausseSirene, etablissement, siret_sirene


def _profil():
    return {"recherche": {"domaines": ["M18"], "tailles_spontanees": ["10_49"], "departements": ["75"],
                          "taille_inconnue_spontanees": False}}


@pytest.fixture
def sirene(monkeypatch):
    monkeypatch.setenv("INSEE_API_KEY", "cle-insee")
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAFRev2")
    monkeypatch.setattr(P, "PAUSE_S", 0)

    def brancher(fausse):
        monkeypatch.setattr(fetch.requests, "get", fausse.get)
        return fausse
    return brancher


def _par_siret(uid):
    return {e["_extra"]["siret"]: e for e in lire_entreprises(uid)}


# ─── Les deux codes ───────────────────────────────────────────────────────────
def test_deux_codes():
    assert naf.deux_codes("62.01Z") == {"naf_rev2": "62.01Z", "naf_2025": "62.10Y"}       # cible unique
    assert naf.deux_codes("6201Z") == {"naf_rev2": "62.01Z", "naf_2025": "62.10Y"}        # format LBA
    assert naf.deux_codes("68.31Z") == {"naf_rev2": "68.31Z", "naf_2025": ""}             # multiple : inconnu
    assert naf.deux_codes("68.31Z", "68.32H") == {"naf_rev2": "68.31Z", "naf_2025": "68.32H"}
    assert naf.deux_codes("62.10Y") == {"naf_rev2": "62.01Z", "naf_2025": "62.10Y"}       # une seule origine
    assert naf.deux_codes("62.10Y", "62.01Z") == {"naf_rev2": "62.01Z", "naf_2025": "62.10Y"}   # ordre indifférent
    assert naf.deux_codes("", None, "XX") == {"naf_rev2": "", "naf_2025": ""}


def test_extraire_infos_avant_et_apres_la_bascule():
    api = FausseSirene()
    etab = api._json(etablissement(1, naf="68.31Z", naf25="68.32H"))
    infos = fetch.extraire_infos(etab)
    assert (infos["code_naf"], infos["naf_rev2"], infos["naf_2025"]) == ("68.31Z", "68.31Z", "68.32H")
    # Après la bascule, la période peut porter le code NAF 2025 : classé quand même
    etab["periodesEtablissement"][0].update(activitePrincipaleEtablissement="68.32H",
                                            nomenclatureActivitePrincipaleEtablissement="NAF2025")
    etab.pop("activitePrincipaleNAF25Etablissement")
    etab["uniteLegale"]["activitePrincipaleUniteLegale"] = "68.32H"
    infos = fetch.extraire_infos(etab)
    assert (infos["naf_rev2"], infos["naf_2025"]) == ("", "68.32H")    # 68.32H a plusieurs origines


# ─── En base ──────────────────────────────────────────────────────────────────
def test_sirene_et_lba_enregistrent_les_deux_codes(utilisateur, sirene):
    from tests.faux_lba import entreprise
    import france_travail.scraper_lba as lba
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises_lba(uid, [lba.normaliser_entreprise(entreprise(9))])       # 6201Z
    sirene(FausseSirene([etablissement(1), etablissement(2, naf="68.31Z", naf25="68.32H")]))
    sauvegarder_profil(uid, {"recherche": {**_profil()["recherche"], "domaines": ["M18", "C15"]}})
    fetch.main(uid, log_fn=lambda m: None)
    ents = _par_siret(uid)
    assert (ents[siret_sirene(1)]["naf_rev2"], ents[siret_sirene(1)]["naf_2025"]) == ("62.01Z", "62.10Y")
    assert (ents[siret_sirene(2)]["naf_rev2"], ents[siret_sirene(2)]["naf_2025"]) == ("68.31Z", "68.32H")
    lba_e = next(e for e in ents.values() if e["sources"] == ["lba"])
    assert (lba_e["naf_rev2"], lba_e["naf_2025"]) == ("62.01Z", "62.10Y")


def test_entreprise_retrouvee_completee(utilisateur, sirene):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    # Enregistrée sans code NAF 2025 (correspondance multiple), puis retrouvée par Sirene
    ajouter_entreprises(uid, [{"siret": siret_sirene(2), "siren": siret_sirene(2)[:9], "code_naf": "68.31Z",
                               "nom": "Agence"}])
    assert _par_siret(uid)[siret_sirene(2)]["naf_2025"] == ""
    sirene(FausseSirene([etablissement(2, naf="68.31Z", naf25="68.32H")]))
    sauvegarder_profil(uid, {"recherche": {**_profil()["recherche"], "domaines": ["C15"]}})
    fetch.main(uid, log_fn=lambda m: None)
    assert _par_siret(uid)[siret_sirene(2)]["naf_2025"] == "68.32H"


# ─── Migration 0014 ───────────────────────────────────────────────────────────
def test_migration_0014_remplit_les_deux_codes(tmp_path):
    chemin = tmp_path / "v13.db"
    cfg = config_alembic(f"sqlite:///{chemin}")
    command.upgrade(cfg, "0013")
    cx = sqlite3.connect(chemin)
    cx.execute("INSERT INTO users (id, email, mot_de_passe_hash) VALUES (1, 'a@test.fr', 'x')")
    for secteur, extra in [("62.01Z", {"code_naf": "62.01Z"}), ("6201Z", {}), ("68.31Z", {}),
                           ("", {"code_naf": "64.19Z"}), ("", {}), ("62.10Y", {})]:
        cx.execute("INSERT INTO entreprises (user_id, secteur, extra) VALUES (1, ?, ?)", (secteur, json.dumps(extra)))
    cx.commit()
    cx.close()

    command.upgrade(cfg, "0014")
    cx = sqlite3.connect(chemin)
    assert cx.execute("SELECT naf_rev2, naf_2025 FROM entreprises ORDER BY id").fetchall() == [
        ("62.01Z", "62.10Y"), ("62.01Z", "62.10Y"), ("68.31Z", ""), ("64.19Z", "64.19Y"), ("", ""),
        ("62.01Z", "62.10Y")]
    assert cx.execute("SELECT secteur FROM entreprises WHERE id = 2").fetchone() == ("6201Z",)   # inchangé
    cx.close()

    command.downgrade(cfg, "0013")
    cx = sqlite3.connect(chemin)
    assert not {r[1] for r in cx.execute("PRAGMA table_info(entreprises)")} & {"naf_rev2", "naf_2025"}
    cx.close()


# ─── Repli de la variable NAF 2025 (D113) ─────────────────────────────────────
class Journal(list):
    def __call__(self, msg):
        self.append(msg)

    def texte(self):
        return "\n".join(self)


def test_avec_repli():
    q = ("etablissementSiege:true AND activitePrincipaleNAF25UniteLegale:(62.10Y OR 62.20G) "
         "AND -activitePrincipaleNAF25UniteLegale:68.32G")
    assert fetch.avec_repli(q) == (q.replace("activitePrincipaleNAF25UniteLegale:", "activitePrincipaleUniteLegale:"),
                                   "activitePrincipaleUniteLegale")
    assert fetch.avec_repli("activitePrincipaleUniteLegale:62.01Z") is None    # NAF rév. 2 : pas de repli
    assert fetch.variable_naf_de(q) == "activitePrincipaleNAF25UniteLegale"


def test_variable_naf25_refusee_repli_sur_activite_principale(utilisateur, sirene, monkeypatch):
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAF2025")
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    # Après la bascule : activitePrincipaleUniteLegale porte les codes NAF 2025, NAF25 refusée (400)
    api = sirene(FausseSirene([etablissement(1, naf="62.10Y"), etablissement(2, naf="64.19Y", tranche="42",
                                                                             categorie="ETI")],
                              variable_naf25=None, nomenclature="NAF2025"))
    sauvegarder_profil(uid, {"recherche": {**_profil()["recherche"], "tailles_spontanees": ["10_49", "250_4999"]}})
    log = Journal()
    fetch.main(uid, log_fn=log)
    assert sorted(_par_siret(uid)) == [siret_sirene(1), siret_sirene(2)]          # cœur et transverse
    texte = log.texte()
    assert "variable activitePrincipaleNAF25UniteLegale" in texte                 # plan
    assert texte.count("Sirene refuse activitePrincipaleNAF25UniteLegale") == 1   # un seul essai refusé
    assert "variable activitePrincipaleUniteLegale acceptée" in texte
    assert "variable NAF : activitePrincipaleUniteLegale" in texte                # bilan
    assert "recherche abandonnée" not in texte
    refusees = [r["q"] for r in api.recherches if "NAF25" in r["q"]]
    assert len(refusees) == 1
    e = _par_siret(uid)[siret_sirene(1)]
    assert (e["naf_rev2"], e["naf_2025"]) == ("62.01Z", "62.10Y")                 # code de la période en NAF 2025


def test_repli_refuse_aussi_recherche_abandonnee(utilisateur, sirene, monkeypatch):
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAF2025")
    monkeypatch.setitem(P.VARIABLE_NAF_REPLI, "NAF2025", "activiteInexistante")
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    sirene(FausseSirene([etablissement(1, naf="62.10Y")], variable_naf25=None))
    sauvegarder_profil(uid, _profil())
    log = Journal()
    fetch.main(uid, log_fn=log)
    assert lire_entreprises(uid) == [] and "recherche abandonnée" in log.texte()


def test_naf_rev2_sans_repli(utilisateur, sirene):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    sirene(FausseSirene([etablissement(1)]))
    sauvegarder_profil(uid, _profil())
    log = Journal()
    fetch.main(uid, log_fn=log)
    assert "refuse" not in log.texte() and "variable NAF : activitePrincipaleUniteLegale" in log.texte()


# ─── Variable NAF 2025 acceptée mais vide (D116) ──────────────────────────────
def _grandes():
    return {"recherche": {**_profil()["recherche"], "tailles_spontanees": ["10_49", "250_4999"]}}


def test_variable_naf25_vide_repli_utilise(utilisateur, sirene, monkeypatch):
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAF2025")
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    api = sirene(FausseSirene([etablissement(1, naf="62.10Y"),
                               etablissement(2, naf="64.19Y", tranche="42", categorie="ETI")],
                              naf25_vide=True, nomenclature="NAF2025"))
    sauvegarder_profil(uid, _grandes())
    log = Journal()
    fetch.main(uid, log_fn=log)
    assert sorted(_par_siret(uid)) == [siret_sirene(1), siret_sirene(2)]
    texte = log.texte()
    assert texte.count("variable NAF25 vide, repli utilisé") == 1
    assert "variable NAF : activitePrincipaleUniteLegale" in texte and "abandonnée" not in texte
    assert len([r for r in api.recherches if "NAF25" in r["q"]]) == 1           # essayée une fois


def test_variable_naf25_vide_et_repli_vide_zero_sans_erreur(utilisateur, sirene, monkeypatch):
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAF2025")
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    # Aucune entreprise du domaine : 0 avec les deux variables
    api = sirene(FausseSirene([etablissement(1, naf="01.11Y")], naf25_vide=True))
    sauvegarder_profil(uid, _profil())
    log = Journal()
    fetch.main(uid, log_fn=log)
    texte = log.texte()
    assert lire_entreprises(uid) == [] and "en erreur" not in texte and "abandonnée" not in texte
    assert "ni avec activitePrincipaleUniteLegale (repli essayé)" in texte
    assert "repli utilisé" not in texte
    naf25 = [r for r in api.recherches if "NAF25" in r["q"]]
    repli = [r for r in api.recherches if "activitePrincipaleUniteLegale:" in r["q"]]
    assert len(naf25) == len(repli) >= 1                                       # un repli par recherche nulle


def test_variable_naf25_remplie_pas_de_repli_sur_un_zero(utilisateur, sirene, monkeypatch):
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAF2025")
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    # Cœurs trouvés (variable remplie), transverses à 0 : pas de repli
    api = sirene(FausseSirene([etablissement(1, naf="62.01Z", naf25="62.10Y")]))
    sauvegarder_profil(uid, _grandes())
    log = Journal()
    fetch.main(uid, log_fn=log)
    assert sorted(_par_siret(uid)) == [siret_sirene(1)]
    assert not [r for r in api.recherches if "activitePrincipaleUniteLegale:" in r["q"]]
    assert "repli" not in log.texte()
