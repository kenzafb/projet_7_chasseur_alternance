"""Correspondance domaine vers NAF (phase 5d, SPEC_SOURCES 4.1 et 4.3) :
codes NAF 2025 tirés de la table officielle de l'INSEE, cœurs et
transverses, exclusions, secteurs choisis, bascule au 1er janvier 2027."""

import csv
from datetime import date

from shared import config, naf


# ─── Correspondance ───────────────────────────────────────────────────────────
def _table_officielle():
    with open(naf.TABLE_INSEE, encoding="utf-8") as f:
        lignes = list(csv.DictReader(f))
    return {c: [l for l in lignes if l["naf_rev2"] == c] for c in {l["naf_rev2"] for l in lignes}}


def test_codes_naf_2025_tires_de_la_table_officielle():
    """Aucun code NAF 2025 inventé : chaque cible et chaque code retenu est
    dans la table de l'INSEE pour ce code rév. 2 ; les correspondances
    multiples (et elles seules) sont à valider, avec une note."""
    table = _table_officielle()
    doc = naf.correspondance()
    entrees = doc["exclusions"] + [e for g in doc["domaines"].values() for liste in g.values() for e in liste]
    assert len(entrees) == 3 + 18 + 6 + 8 + 3
    for e in entrees:
        officielles = {l["naf_2025"] for l in table[e["naf_rev2"]]}
        assert {c["code"] for c in e["naf_2025"]} == officielles, e["naf_rev2"]
        assert set(e["retenus_2025"]) <= officielles and e["retenus_2025"], e["naf_rev2"]
        multiple = any(l["type"] == "Multiple" for l in table[e["naf_rev2"]])
        assert e.get("a_valider", False) == multiple and (not multiple or e["note"]), e["naf_rev2"]


def test_coeurs_transverses_et_exclusions_en_nafrev2():
    c = naf.secteurs_sirene(["M18"], nomenclature="NAFRev2")
    assert len(c["coeurs"]) == 18 and c["coeurs"][0] == "62.01Z" and "95.11Z" in c["coeurs"]
    assert c["transverses"] == ["64.19Z", "65.11Z", "65.12Z", "70.10Z", "70.22Z", "71.12B"]
    assert c["secteurs"] == [] and not c["secteurs_requis"]
    c = naf.secteurs_sirene(["M18", "C15"], nomenclature="NAFRev2")
    assert len(c["coeurs"]) == 26 and len(c["transverses"]) == 6          # 64.19Z, 65.11Z, 65.12Z une fois
    assert not {"68.32B", "41.10D", "66.19A"} & set(c["coeurs"] + c["transverses"])


def test_codes_en_naf_2025():
    c = naf.secteurs_sirene(["M18", "C15"], nomenclature="NAF2025")
    assert "62.10Y" in c["coeurs"] and "63.10Y" in c["coeurs"]
    assert "60.20H" not in c["coeurs"] and "55.90Y" not in c["coeurs"]   # cibles multiples écartées
    assert c["coeurs"].count("58.29Y") == 1 and c["coeurs"].count("68.12Y") == 1
    assert "70.20Y" in c["transverses"]
    assert "68.32G" not in c["coeurs"]


def test_secteurs_choisis_pour_indifferent_et_domaine_sans_correspondance():
    c = naf.secteurs_sirene([], ["62"], "NAFRev2")
    assert c["secteurs_requis"] and c["secteurs"] == ["62.01Z", "62.02A", "62.02B", "62.03Z", "62.09Z"]
    assert c["coeurs"] == [] and c["transverses"] == []
    # Domaine couvert : les secteurs ne servent pas à Sirene (filtre France Travail seulement)
    assert naf.secteurs_sirene(["M18"], ["86"], "NAFRev2")["secteurs"] == []
    # Domaine sans correspondance : secteurs utilisés, en plus des cœurs des domaines couverts
    c = naf.secteurs_sirene(["J11", "C15"], ["86"], "NAFRev2")
    assert c["sans_correspondance"] == ["J11"] and c["secteurs"][0].startswith("86.") and len(c["coeurs"]) == 8
    # Grand domaine : M18 cherché, le reste de M par les secteurs
    c = naf.secteurs_sirene(["M"], [], "NAFRev2")
    assert len(c["coeurs"]) == 18 and c["sans_correspondance"] == ["M"]
    # Exclusions aussi pour une division entière, dans les deux nomenclatures
    assert "68.32B" not in naf.secteurs_sirene([], ["68"], "NAFRev2")["secteurs"]
    s2025 = naf.secteurs_sirene([], ["68"], "NAF2025")["secteurs"]
    assert "68.32G" not in s2025 and "68.31Y" in s2025
    # D57 : cible hors de la division gardée seulement si l'ancien code n'en a qu'une
    assert "55.90Y" not in s2025                                          # 68.20A : deux cibles
    assert "68.12Y" in naf.secteurs_sirene([], ["41"], "NAF2025")["secteurs"]   # 41.10A : une seule
    # Code déjà cœur : pas répété dans les secteurs
    c = naf.secteurs_sirene(["J11", "M18"], ["62"], "NAFRev2")
    assert c["secteurs"] == []


def test_avertissements():
    assert naf.avertissement_sirene(["M18"]) == ""
    assert "Aucun domaine ni secteur choisi" in naf.avertissement_sirene([])
    assert naf.avertissement_sirene([], ["62"]) == ""
    m = naf.avertissement_sirene(["J11"])
    assert "(J11)" in m and "choisis des secteurs" in m
    assert "cherchés par les secteurs" in naf.avertissement_sirene(["J11"], ["86"])


# ─── Nomenclature ─────────────────────────────────────────────────────────────
def test_bascule_naf_2025(monkeypatch):
    monkeypatch.delenv("NOMENCLATURE_NAF", raising=False)
    assert config.nomenclature_naf(date(2026, 12, 31)) == "NAFRev2"
    assert config.nomenclature_naf(date(2027, 1, 1)) == "NAF2025"
    monkeypatch.setenv("NOMENCLATURE_NAF", "naf2025")
    assert config.nomenclature_naf(date(2026, 10, 9)) == "NAF2025"
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAFRev2")
    assert config.nomenclature_naf(date(2027, 6, 1)) == "NAFRev2"
    monkeypatch.setenv("NOMENCLATURE_NAF", "autre")
    assert config.nomenclature_naf(date(2027, 6, 1)) == "NAF2025"
