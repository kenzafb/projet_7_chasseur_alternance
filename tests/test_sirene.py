"""Recherche Sirene (phase 5d, SPEC_SOURCES section 4) : filtres de taille
et de département, plan des recherches, bascule NAF 2025, recherche
complète contre l'API simulée, pas de doublon avec LBA."""

import pytest

import spontanees.fetch_entreprises as fetch
from database.entreprises_db import ajouter_entreprises_lba, lire_entreprises
from database.profil_db import sauvegarder_profil
from shared.criteres import normaliser_recherche, options_du_profil
from shared.tailles import tranches_insee
from spontanees import parametres_sirene as P
from tests.faux_sirene import FausseSirene, etablissement, siret_sirene


class Journal(list):
    def __call__(self, msg):
        self.append(msg)

    def texte(self):
        return "\n".join(self)


def profil(domaines=("M18",), secteurs=(), tailles=(), inconnue=True, departements=()):
    return {"recherche": {"domaines": list(domaines), "secteurs": list(secteurs), "tailles_spontanees": list(tailles),
                          "taille_inconnue_spontanees": inconnue, "departements": list(departements)}}


TOUTES_SAUF_NN = "00 OR 01 OR 02 OR 03 OR 11 OR 12 OR 21 OR 22 OR 31 OR 32 OR 41 OR 42 OR 51 OR 52 OR 53"


def test_tranches_et_clauses():
    assert tranches_insee(["10_49", "moins_10"]) == ["00", "01", "02", "03", "11", "12"]
    assert tranches_insee(["sans_salarie"]) == ["NN"]
    assert " OR ".join(tranches_insee([])) == TOUTES_SAUF_NN                # rien de coché : tout sauf NN
    # Effectif inconnu : unités sans tranche (ABSENTS_PAR), plus « NN » (sans salarié, D55)
    assert fetch.filtre_tailles(["10_49"], False) == "trancheEffectifsUniteLegale:(11 OR 12)"
    assert fetch.filtre_tailles(["10_49"], True) == ("(trancheEffectifsUniteLegale:(11 OR 12) OR "
                                                     "-trancheEffectifsUniteLegale:*)")
    assert fetch.filtre_tailles([], False) == f"(trancheEffectifsUniteLegale:({TOUTES_SAUF_NN}) OR " \
                                              "-trancheEffectifsUniteLegale:*)"
    assert fetch.filtre_tailles(["sans_salarie"], False) == "trancheEffectifsUniteLegale:NN"
    assert fetch.filtre_grandes(["10_49"]) is None
    assert fetch.filtre_grandes(["5000_plus"]) == ("(trancheEffectifsUniteLegale:(52 OR 53) OR "
                                                   "categorieEntreprise:GE)")
    assert "categorieEntreprise:(ETI OR GE)" in fetch.filtre_grandes([])


def test_sans_syntaxe_d_absence(monkeypatch):
    monkeypatch.setattr(P, "ABSENTS_PAR", None)
    assert fetch.filtre_tailles(["10_49"], True) == "trancheEffectifsUniteLegale:(11 OR 12)"


def test_departements_dans_le_profil():
    assert normaliser_recherche({"departements": ["92", "75", "60", "75"]})["departements"] == ["75", "92"]
    assert [d["code"] for d in options_du_profil()["departements"]] == ["75", "77", "78", "91", "92", "93", "94", "95"]


def test_plan_des_recherches(monkeypatch):
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAFRev2")
    log = Journal()
    plan = fetch.plan_sirene(profil(tailles=["10_49"], departements=["75", "92"]), log)
    assert len(plan) == 1                                                 # 120 codes et 8 départements par requête
    assert "codePostalEtablissement:(75* OR 92*)" in plan[0][1] and "62.01Z OR 62.02A" in plan[0][1]
    assert "secteurs transverses non cherchés" in log.texte()
    plan = fetch.plan_sirene(profil(), Journal())
    assert [g for g, _ in plan] == ["cœurs", "transverses"]
    assert "codePostalEtablissement:(75* OR 77* OR 78* OR 91* OR 92* OR 93* OR 94* OR 95*)" in plan[0][1]
    assert f"trancheEffectifsUniteLegale:({TOUTES_SAUF_NN})" in plan[0][1]    # aucune taille : toutes sauf NN
    assert plan == fetch.plan_sirene(profil(), Journal())
    assert fetch.plan_sirene(profil(domaines=()), Journal()) == []
    # Paquets plus petits si l'API en acceptait moins
    monkeypatch.setattr(P, "NAF_PAR_REQUETE", 1)
    monkeypatch.setattr(P, "DEPARTEMENTS_PAR_REQUETE", 1)
    assert len(fetch.plan_sirene(profil(tailles=["10_49"], departements=["75", "92"]), Journal())) == 18 * 2


def test_plan_en_naf_2025(monkeypatch):
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAF2025")
    plan = fetch.plan_sirene(profil(), Journal())
    assert "activitePrincipaleNAF25UniteLegale:(62.10Y" in plan[0][1]
    monkeypatch.setitem(P.VARIABLE_NAF, "NAF2025", None)                  # variable inconnue : repli
    log = Journal()
    plan = fetch.plan_sirene(profil(), log)
    assert "62.01Z" in plan[0][1] and "recherche en NAF rév. 2" in log.texte()


# ─── Recherche complète contre l'API simulée ──────────────────────────────────
@pytest.fixture
def sirene(monkeypatch):
    monkeypatch.setenv("INSEE_API_KEY", "cle-insee")
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAFRev2")
    monkeypatch.setattr(P, "PAUSE_S", 0)

    def brancher(fausse):
        monkeypatch.setattr(fetch.requests, "get", fausse.get)
        return fausse
    return brancher


def _jeu():
    return [
        etablissement(1, tranche="12"),                     # cœur, 10 à 49 : gardé
        etablissement(2, tranche="NN"),                     # sans salarié (unité non employeuse)
        etablissement(3, tranche=None),                     # sans tranche : effectif inconnu
        etablissement(4, tranche="03"),                     # moins de 10
        etablissement(5, cp="92100"),                       # hors département choisi
        etablissement(6, siege=False),                      # pas le siège
        etablissement(7, actif=False),                      # cessée
        etablissement(8, naf="64.19Z", tranche="12"),       # transverse, petite : jamais
        etablissement(9, naf="64.19Z", tranche="42", categorie="ETI"),
        etablissement(10, naf="64.19Z", tranche="NN", categorie="GE"),
        etablissement(11, naf="68.32B", tranche="12"),      # support juridique : exclu
        etablissement(12, naf="68.31Z", tranche="12"),      # immobilier : autre domaine
    ]


def _sirets(uid):
    return sorted(int(e["_extra"]["siret"][:9]) for e in lire_entreprises(uid))


def test_recuperer_selon_le_profil(utilisateur, sirene):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    api = sirene(FausseSirene(_jeu()))
    sauvegarder_profil(uid, profil(tailles=["10_49"], departements=["75"]))
    logs = Journal()
    fetch.main(uid, log_fn=logs)
    assert _sirets(uid) == [1, 3]                                         # inconnu gardé, NN non (D55)
    assert "secteurs transverses non cherchés" in logs.texte()
    assert all("75*" in r["q"] and "92*" not in r["q"] for r in api.recherches)
    assert "Sirene : 2 nouvelles entreprises (2 cœurs)" in logs.texte()
    # « Sans salarié » cochée : NN gardé
    uid3 = utilisateur("c@test.fr", prenom="Carla")[1]
    sauvegarder_profil(uid3, profil(tailles=["sans_salarie", "10_49"], inconnue=False, departements=["75"]))
    fetch.main(uid3, log_fn=Journal())
    assert _sirets(uid3) == [1, 2]
    assert "1 requêtes en 0 min" in logs.texte()
    # Effectifs inconnus refusés
    sauvegarder_profil(uid, profil(tailles=["10_49"], inconnue=False, departements=["75"]))
    uid2 = utilisateur("b@test.fr", prenom="Bob")[1]
    sauvegarder_profil(uid2, profil(tailles=["10_49"], inconnue=False, departements=["75"]))
    fetch.main(uid2, log_fn=Journal())
    assert _sirets(uid2) == [1]


def test_toutes_tailles_et_transverses(utilisateur, sirene):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    sirene(FausseSirene(_jeu()))
    sauvegarder_profil(uid, profil(departements=["75"]))
    logs = Journal()
    fetch.main(uid, log_fn=logs)
    # Toutes les tailles sauf « sans salarié » : 1, 3, 4 ; transverses : 9 (tranche), 10 (catégorie GE)
    assert _sirets(uid) == [1, 3, 4, 9, 10]
    assert "2 transverses" in logs.texte()


def test_pas_de_doublon_avec_lba_et_trace_des_deux_sources(utilisateur, sirene):
    from tests.faux_lba import entreprise
    import france_travail.scraper_lba as lba
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises_lba(uid, [lba.normaliser_entreprise(entreprise(1, siret=siret_sirene(1)))])
    sirene(FausseSirene(_jeu()))
    sauvegarder_profil(uid, profil(tailles=["10_49"], departements=["75"]))
    logs = Journal()
    fetch.main(uid, log_fn=logs)
    ents = lire_entreprises(uid)
    assert _sirets(uid) == [1, 3]
    assert next(e for e in ents if e["_extra"]["siret"] == siret_sirene(1))["sources"] == ["lba", "sirene"]
    assert "1 déjà en base retrouvées" in logs.texte()


def test_meme_siren_autre_etablissement_pas_de_doublon(utilisateur, sirene):
    """D59 : LBA donne un établissement secondaire (autre SIRET, même SIREN)
    que Sirene retrouve par son siège : une seule entreprise, deux sources."""
    from tests.faux_lba import entreprise
    import france_travail.scraper_lba as lba
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    secondaire = f"{1:09d}00099"
    ajouter_entreprises_lba(uid, [lba.normaliser_entreprise(entreprise(1, siret=secondaire))])
    sirene(FausseSirene(_jeu()))
    sauvegarder_profil(uid, profil(tailles=["10_49"], departements=["75"]))
    logs = Journal()
    fetch.main(uid, log_fn=logs)
    ents = lire_entreprises(uid)
    assert sorted(e["_extra"]["siret"] for e in ents) == sorted([secondaire, siret_sirene(3)])
    assert next(e for e in ents if e["_extra"]["siret"] == secondaire)["sources"] == ["lba", "sirene"]
    assert "1 déjà en base retrouvées" in logs.texte()
    # Et dans l'autre sens : LBA retrouve un siège Sirene par le SIREN
    b = ajouter_entreprises_lba(uid, [lba.normaliser_entreprise(entreprise(9, siret=f"{3:09d}00077"))])
    assert b["ajoutees"] == 0 and b["deux_sources"] == 1


def test_pagination_par_curseur_et_limite(utilisateur, sirene, monkeypatch):
    monkeypatch.setattr(P, "PAR_PAGE", 2)
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    api = sirene(FausseSirene([etablissement(i) for i in range(1, 8)]))
    sauvegarder_profil(uid, profil(departements=["75"]))
    fetch.main(uid, log_fn=Journal())
    assert _sirets(uid) == list(range(1, 8))
    curseurs = [r["curseur"] for r in api.recherches if "62.01Z" in r["q"]]
    assert curseurs == ["*", "c2", "c4", "c6"]
    _, uid2 = utilisateur("b@test.fr", prenom="Bob")
    sauvegarder_profil(uid2, profil(departements=["75"]))
    fetch.main(uid2, max_entreprises=3, log_fn=Journal())
    assert len(_sirets(uid2)) == 3


def test_rien_a_chercher_ou_cle_absente(utilisateur, sirene, monkeypatch):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    api = sirene(FausseSirene(_jeu()))
    sauvegarder_profil(uid, profil(domaines=()))
    logs = Journal()
    fetch.main(uid, log_fn=logs)
    assert api.recherches == [] and "Aucun domaine ni secteur choisi" in logs.texte()
    monkeypatch.delenv("INSEE_API_KEY")
    sauvegarder_profil(uid, profil())
    logs = Journal()
    fetch.main(uid, log_fn=logs)
    assert api.recherches == [] and "INSEE_API_KEY manquante" in logs.texte()


def test_erreur_d_une_recherche_n_arrete_pas_les_autres(utilisateur, sirene, monkeypatch):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    api = sirene(FausseSirene(_jeu()))
    appels = []

    def get(*a, **k):
        appels.append(1)
        if len(appels) == 1:                                    # cœurs en échec, transverses ensuite
            raise fetch.requests.ConnectionError()
        return api.get(*a, **k)
    monkeypatch.setattr(fetch.requests, "get", get)
    sauvegarder_profil(uid, profil(departements=["75"]))
    logs = Journal()
    fetch.main(uid, log_fn=logs)
    assert "recherche abandonnée (cœurs)" in logs.texte() and "1 en erreur" in logs.texte()
    assert _sirets(uid) == [9, 10]


# ─── Migration 0010 : ancien réglage pré-coché (D60) ──────────────────────────
def test_migration_0010_ancien_reglage(tmp_path):
    """D60, D63 : seules les tailles des spontanées sont pré-cochées ; celles
    des offres ne sont jamais touchées."""
    import json
    import sqlite3
    from alembic import command
    from database.schema import config_alembic
    chemin = tmp_path / "v9.db"
    cfg = config_alembic(f"sqlite:///{chemin}")
    command.upgrade(cfg, "0009")
    cx = sqlite3.connect(chemin)
    cx.execute("INSERT INTO users (id, email, mot_de_passe_hash) VALUES (1, 'a@test.fr', 'x'), (2, 'b@test.fr', 'x')")
    for user, mode, recherche in ((1, "alternance", {"domaines": ["M18"]}),
                                  (2, "alternance", {"tailles": ["moins_10"], "tailles_spontanees": ["50_249"],
                                                     "departements": []}),
                                  (1, "job", {})):
        cx.execute("INSERT INTO profils (user_id, mode, recherche) VALUES (?, ?, ?)", (user, mode, json.dumps(recherche)))
    cx.commit()
    cx.close()

    def lire():
        cx = sqlite3.connect(chemin)
        lignes = [json.loads(r) for (r,) in cx.execute("SELECT recherche FROM profils ORDER BY id")]
        cx.close()
        return lignes
    command.upgrade(cfg, "0010")
    lignes = lire()
    assert lignes[0] == {"domaines": ["M18"], "tailles_spontanees": ["10_49", "50_249", "250_4999", "5000_plus"],
                         "departements": ["75", "92", "93", "94"]}             # aucune taille d'offre ajoutée
    assert lignes[1] == {"tailles": ["moins_10"], "tailles_spontanees": ["50_249"],
                         "departements": ["75", "92", "93", "94"]}             # choix gardés
    assert lignes[2] == {}                                                # mode job : inchangé
    command.downgrade(cfg, "0009")
    lignes = lire()
    assert lignes[0] == {"domaines": ["M18"], "tailles_spontanees": [], "departements": []}
    assert lignes[1] == {"tailles": ["moins_10"], "tailles_spontanees": ["50_249"], "departements": []}


def test_tailles_des_offres_et_des_spontanees_separees(utilisateur, sirene):
    """D63 : les tailles des spontanées ne filtrent pas les offres, et
    inversement."""
    from shared.criteres import criteres_france_travail
    p = {"recherche": {"domaines": ["M18"], "tailles": ["5000_plus"], "taille_inconnue": False,
                       "tailles_spontanees": ["10_49"], "taille_inconnue_spontanees": False,
                       "departements": ["75"]}}
    c = criteres_france_travail(p, "alternance")
    assert c["tailles"] == ["5000_plus"] and c["taille_inconnue"] is False
    assert "trancheEffectifsUniteLegale:(11 OR 12)" in fetch.plan_sirene(p, Journal())[0][1]
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    sirene(FausseSirene(_jeu()))
    sauvegarder_profil(uid, p)
    fetch.main(uid, log_fn=Journal())
    assert _sirets(uid) == [1]
    assert normaliser_recherche({"tailles_spontanees": ["10_49", "x"], "taille_inconnue_spontanees": 0}) == {
        "tailles_spontanees": ["10_49"], "taille_inconnue_spontanees": True}
