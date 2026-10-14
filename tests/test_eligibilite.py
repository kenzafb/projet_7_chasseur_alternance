"""Éligibilité décidée en Python (D94) : niveau, durée, début, alternance,
à partir des champs extraits par le modèle ; non précisé = jamais bloquant.
Cas de départ : comparaison humaine sur trois offres de stage (octobre 2026)."""

import json

import pytest

from france_travail.analyseur import analyser_offre, appliquer_archivage_auto, appliquer_analyse
from shared import eligibilite as el

# BUT2, 10 semaines de février à avril (le profil de la comparaison humaine)
BUT2 = {"prenom": "Alice", "formation": "BUT 2e année informatique", "date_debut": "2027-02-01",
        "date_fin": "2027-04-09", "duree_semaines": 10, "recherche": {"domaines": ["M18"]}}


def extraits(niveau="non_precise", duree=None, debut=None, alternance=False):
    return {"niveau_requis": niveau, "duree_mois": duree, "date_debut_offre": debut, "alternance_seulement": alternance}


def test_o1_orange_inéligible_pour_trois_raisons():
    raisons = el.raisons_ineligibilite(extraits("bac+5", 6, "janvier 2027"), BUT2, "stage")
    assert raisons == ["Bac+5 exigé, profil Bac+2", "6 mois demandés, 10 semaines disponibles",
                       "début en janvier 2027, stage possible du 1er février 2027 au 9 avril 2027"]


@pytest.mark.parametrize("valeurs, bloque", [
    (extraits("bac+5"), True),                    # O2 : Bac+5 exigé
    (extraits("bac+4"), True),                    # deux crans
    (extraits("bac+3"), False),                   # un cran : pas bloquant
    (extraits("non_precise"), False),
    (extraits(duree=3), False),                   # 13 semaines : moins de 10 + 4
    (extraits(duree=3.5), True),                  # 15,2 semaines
    (extraits(duree=None), False),
    (extraits(debut="mars 2027"), False),
    (extraits(debut="mai 2027"), True),
    (extraits(debut="01/2027"), True),
    (extraits(debut="28/01/2027"), False),        # quelques jours avant : toléré
    (extraits(debut="2027-01-15"), True),
    (extraits(debut="dès que possible"), False),
    (extraits(debut="janvier"), False),           # sans année : non précisé
    (extraits(alternance=True), True),
])
def test_regles_du_stage(valeurs, bloque):
    assert bool(el.raisons_ineligibilite(valeurs, BUT2, "stage")) is bloque


def test_durees_et_dates_seulement_en_stage():
    assert el.raisons_ineligibilite(extraits(duree=12, debut="janvier 2027"), BUT2, "job") == []
    assert el.raisons_ineligibilite(extraits(alternance=True), BUT2, "alternance") == []
    assert el.raisons_ineligibilite(extraits(alternance=True), BUT2, "job") == ["offre en alternance seulement"]


def test_profil_sans_dates_ni_niveau_rien_ne_bloque():
    assert el.raisons_ineligibilite(extraits("bac+5", 12, "janvier 2027"), {"prenom": "A"}, "stage") == []


@pytest.mark.parametrize("profil, crans, source", [
    ({"niveau_etudes": "Bac+2"}, 2, "niveau d'études"),
    ({"niveau_etudes": "Bac+3 en cours, Bac+2 obtenu"}, 3, "niveau d'études"),
    ({"niveau_etudes": "bac"}, 0, "niveau d'études"),
    ({"formation": "BUT1 GEA"}, 0, "formation"),
    ({"formation": "BUT 2e année"}, 2, "formation"),
    ({"formation": "2e année de BUT informatique"}, 2, "formation"),
    ({"formation": "BUT3"}, 3, "formation"),
    ({"formation": "Licence 3 économie"}, 3, "formation"),
    ({"formation": "Master 1"}, 4, "formation"),
    ({"formation": "M2 MIAGE"}, 5, "formation"),
    ({"niveau_vise": "Bac+3", "formation": "BUT2"}, 3, "niveau visé"),
    ({"niveau_etudes": "Bac+2", "formation": "Master 2"}, 2, "niveau d'études"),   # le champ prime
])
def test_niveau_du_profil(profil, crans, source):
    n = el.niveau_du_profil(profil)
    assert (n["crans"], n["source"], n["avertissement"]) == (crans, source, "")


@pytest.mark.parametrize("profil", [{}, {"formation": "École d'ingénieurs"}, {"formation": "BUT2 puis Master 1"},
                                    {"formation": "BTS"}])
def test_niveau_inconnu_ou_ambigu_avertissement(profil):
    n = el.niveau_du_profil(profil)
    assert n["crans"] is None and "niveau d'études actuel" in n["avertissement"]


# ─── Dans l'analyse ──────────────────────────────────────────────────────────
def reponse(score, **champs):
    base = {"score": score, "eligible": True, "points_forts": ["a"], "points_faibles": ["b"], "domaine": "Dev",
            "resume": "ok", "niveau_requis": "non_precise", "duree_mois": None, "date_debut_offre": None,
            "alternance_seulement": False}
    return json.dumps({**base, **champs})


def test_analyse_plafonnee_avec_la_raison(ia):
    ia.reponse = reponse(9, niveau_requis="bac+5", duree_mois=6, date_debut_offre="janvier 2027")
    a = analyser_offre({"titre": "Stage ingénieur", "description": "..."}, BUT2, mode="stage")
    assert (a["score"], a["eligible"], a["verdict"]) == (3, False, "ineligible")
    assert a["raison_ineligibilite"].startswith("Bac+5 exigé, profil Bac+2 ; 6 mois demandés")
    assert a["points_faibles"][0] == "Inéligible : Bac+5 exigé, profil Bac+2" and a["points_faibles"][-1] == "b"
    offre = {"titre": "Stage ingénieur", "description": "..."}
    appliquer_analyse(offre, a, mode="stage", verbeux=False)
    assert (offre["statut"], offre["raison_archivage"]) == ("archive", "ineligible")


def test_information_non_precisee_jamais_bloquante(ia):
    ia.reponse = reponse(9)
    a = analyser_offre({"titre": "Stage", "description": "..."}, BUT2, mode="stage")
    assert (a["score"], a["eligible"], a["raison_ineligibilite"]) == (9, True, "")


def test_score_bas_mais_eligible_pas_archive():
    offre = {"titre": "Dev", "description": "...", "eligible": True, "score": 2}
    appliquer_archivage_auto(offre, {}, mode="job", verbeux=False)
    assert "statut" not in offre


def test_avertissement_dans_le_profil(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    client.mode = "stage"
    client.post("/api/profil", json={"prenom": "Alice", "formation": "École d'ingénieurs"})
    assert "niveau d'études actuel" in client.get("/api/profil").json()["niveau_profil"]["avertissement"]
    client.post("/api/profil", json={"niveau_etudes": "Bac+2 en cours"})
    assert client.get("/api/profil").json()["niveau_profil"] == {
        "crans": 2, "libelle": "Bac+2", "source": "niveau d'études", "avertissement": ""}
    page = client.get("/stage").text
    assert page.count('data-profil="niveau_etudes"') == 3 and page.count("data-niveau-avert") == 3


def test_archive_ineligible_motif_filtre_et_retour(utilisateur, ia):
    from database.candidatures_db import ajouter_candidature, lire_candidature
    from france_travail.analyseur import marquer_non_analysee
    from shared import config
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    client.mode = "stage"
    client.post("/api/profil", json={**{k: v for k, v in BUT2.items() if k != "duree_semaines"}})
    ajouter_candidature(uid, marquer_non_analysee({"id": "O1", "titre": "Stage ingénieur", "description": "..."},
                                                  mode="stage"), mode="stage")
    ia.reponse = reponse(8, niveau_requis="bac+5")
    assert client.post("/api/analyser", json={"id": "O1"}).status_code == 200
    o = lire_candidature(uid, "O1", mode="stage")
    assert (o["statut"], o["raison_archivage"], o["score"]) == ("archive", "ineligible", 3)
    assert o["points_faibles"][0] == "Inéligible : Bac+5 exigé, profil Bac+2"
    # Remise dans les offres actives
    assert client.post("/api/offre/archivage", json={"id": "O1", "desarchiver": True}).json()["ok"]
    assert lire_candidature(uid, "O1", mode="stage")["statut"] == "nouveau"
    assert client.post("/api/offre/archivage", json={"id": "O1", "raison": "ineligible"}).status_code == 200
    page = client.get("/stage").text
    assert 'data-filter="ineligible">Inéligible<' in page
    js = (config.STATIC_DIR / "js" / "offres.js").read_text(encoding="utf-8")
    assert "Remettre dans les offres actives" in js and "motifIneligible" in js
