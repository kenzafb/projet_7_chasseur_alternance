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
from tests.faux_sirene import FausseSirene, etablissement


class Journal(list):
    def __call__(self, msg):
        self.append(msg)

    def texte(self):
        return "\n".join(self)


def profil(domaines=("M18",), secteurs=(), tailles=(), inconnue=True, departements=()):
    return {"recherche": {"domaines": list(domaines), "secteurs": list(secteurs), "tailles": list(tailles),
                          "taille_inconnue": inconnue, "departements": list(departements)}}


def test_tranches_et_clauses():
    assert tranches_insee(["10_49", "moins_10"]) == ["00", "01", "02", "03", "11", "12"]
    assert tranches_insee([]) == []
    assert fetch.filtre_tailles([], True) is None
    assert fetch.filtre_tailles(["10_49"], False) == "trancheEffectifsUniteLegale:(11 OR 12)"
    assert fetch.filtre_tailles(["10_49"], True) == "trancheEffectifsUniteLegale:(11 OR 12 OR NN)"
    assert fetch.filtre_grandes(["10_49"]) is None
    assert fetch.filtre_grandes(["5000_plus"]) == ("(trancheEffectifsUniteLegale:(52 OR 53) OR "
                                                   "categorieEntreprise:GE)")
    assert "categorieEntreprise:(ETI OR GE)" in fetch.filtre_grandes([])


def test_absents_ajoutes_si_la_syntaxe_est_verifiee(monkeypatch):
    monkeypatch.setattr(P, "ABSENTS_PAR", "-trancheEffectifsUniteLegale:*")
    assert fetch.filtre_tailles(["10_49"], True) == ("(trancheEffectifsUniteLegale:(11 OR 12 OR NN) OR "
                                                     "-trancheEffectifsUniteLegale:*)")


def test_departements_dans_le_profil():
    assert normaliser_recherche({"departements": ["92", "75", "60", "75"]})["departements"] == ["75", "92"]
    assert [d["code"] for d in options_du_profil()["departements"]] == ["75", "77", "78", "91", "92", "93", "94", "95"]


def test_plan_des_recherches(monkeypatch):
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAFRev2")
    log = Journal()
    plan = fetch.plan_sirene(profil(tailles=["10_49"], departements=["75", "92"]), log)
    assert len(plan) == 18 * 2                                            # un code et un département par requête
    assert all("trancheEffectifsUniteLegale:(11 OR 12 OR NN)" in q for _, q in plan)
    assert "secteurs transverses non cherchés" in log.texte()
    monkeypatch.setattr(P, "NAF_PAR_REQUETE", 100)
    monkeypatch.setattr(P, "DEPARTEMENTS_PAR_REQUETE", 8)
    plan = fetch.plan_sirene(profil(), Journal())
    assert [g for g, _ in plan] == ["cœurs", "transverses"]
    assert "codePostalEtablissement:(75* OR 77* OR 78* OR 91* OR 92* OR 93* OR 94* OR 95*)" in plan[0][1]
    assert "trancheEffectif" not in plan[0][1]                            # aucune taille : toutes
    assert plan == fetch.plan_sirene(profil(), Journal())
    assert fetch.plan_sirene(profil(domaines=()), Journal()) == []


def test_plan_en_naf_2025(monkeypatch):
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAF2025")
    monkeypatch.setattr(P, "NAF_PAR_REQUETE", 100)
    monkeypatch.setattr(P, "DEPARTEMENTS_PAR_REQUETE", 8)
    log = Journal()
    plan = fetch.plan_sirene(profil(), log)                               # variable NAF 2025 inconnue
    assert "62.01Z" in plan[0][1] and "recherche en NAF rév. 2" in log.texte()
    monkeypatch.setitem(P.VARIABLE_NAF, "NAF2025", "activitePrincipaleNAF25UniteLegale")
    plan = fetch.plan_sirene(profil(), Journal())
    assert "activitePrincipaleNAF25UniteLegale:(62.10Y" in plan[0][1]


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
        etablissement(2, tranche="NN"),                     # effectif non renseigné
        etablissement(3, tranche=None),                     # sans tranche du tout
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
    return sorted(int(e["_extra"]["siret"]) for e in lire_entreprises(uid))


def test_recuperer_selon_le_profil(utilisateur, sirene):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    api = sirene(FausseSirene(_jeu()))
    sauvegarder_profil(uid, profil(tailles=["10_49"], departements=["75"]))
    logs = Journal()
    fetch.main(uid, log_fn=logs)
    assert _sirets(uid) == [1, 2]                                         # NN gardé, absent perdu (ABSENTS_PAR)
    assert "secteurs transverses non cherchés" in logs.texte()
    assert all("75*" in r["q"] and "92*" not in r["q"] for r in api.recherches)
    assert "Sirene : 2 nouvelles entreprises (2 cœurs)" in logs.texte()
    assert f"{len(api.recherches)} requêtes en 0 min" in logs.texte()
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
    # Plus de « au moins 10 salariés » : 1 à 4 ; transverses : 9 (tranche), 10 (catégorie GE)
    assert _sirets(uid) == [1, 2, 3, 4, 9, 10]
    assert "2 transverses" in logs.texte()


def test_pas_de_doublon_avec_lba_et_trace_des_deux_sources(utilisateur, sirene):
    from tests.faux_lba import entreprise
    import france_travail.scraper_lba as lba
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises_lba(uid, [lba.normaliser_entreprise(entreprise(1, siret=f"{1:014d}"))])
    sirene(FausseSirene(_jeu()))
    sauvegarder_profil(uid, profil(tailles=["10_49"], departements=["75"]))
    logs = Journal()
    fetch.main(uid, log_fn=logs)
    ents = lire_entreprises(uid)
    assert _sirets(uid) == [1, 2]
    assert next(e for e in ents if e["_extra"]["siret"] == f"{1:014d}")["sources"] == ["lba", "sirene"]
    assert "1 déjà en base retrouvées" in logs.texte()


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
        if len(appels) == 2:                                    # 62.02A ; 62.01Z est passé
            raise fetch.requests.ConnectionError()
        return api.get(*a, **k)
    monkeypatch.setattr(fetch.requests, "get", get)
    sauvegarder_profil(uid, profil(tailles=["10_49"], departements=["75"]))
    logs = Journal()
    fetch.main(uid, log_fn=logs)
    assert "recherche abandonnée (cœurs)" in logs.texte() and "1 en erreur" in logs.texte()
    assert _sirets(uid) == [1, 2]
