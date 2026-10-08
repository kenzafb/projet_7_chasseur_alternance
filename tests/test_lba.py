"""Recherche La Bonne Alternance (phase 5c, SPEC_SOURCES section 3) contre
l'API simulée : codes métiers, recherche sans code, niveau filtré après
récupération, taille des entreprises, centres et redécoupage des cercles
au plafond, offres France Travail exclues."""

import math

import pytest

import france_travail.scraper_lba as lba
from shared.config import LBA_CENTRES
from shared.niveaux import niveau_europeen
from shared.tailles import taille_depuis_tranche
from tests.faux_lba import FausseLBA, distance_km, entreprise, offre

PARIS = (48.8566, 2.3522)


class Journal(list):
    def __call__(self, msg):
        self.append(msg)

    def texte(self):
        return "\n".join(self)


@pytest.fixture
def api(monkeypatch):
    """Branche une API LBA simulée sur le scraper, sans pause."""
    monkeypatch.setenv("LBA_API_KEY", "cle-de-test")
    monkeypatch.setattr(lba, "PAUSE_S", 0)

    def brancher(fausse):
        fausse.codes_max = 100                     # vérifié le 9 octobre 2026
        monkeypatch.setattr(lba.requests, "get", fausse.get)
        return fausse
    return brancher


def profil(domaines=("M18",), niveau="", tailles=(), inconnue=True):
    return {"niveau_vise": niveau,
            "recherche": {"domaines": list(domaines), "tailles": list(tailles), "taille_inconnue": inconnue}}


def autour(n, cote_km=6.0, centre=PARIS):
    """n points en grille dans un carré de cote_km autour de centre."""
    cote = math.ceil(math.sqrt(n))
    lat0, lon0 = centre
    for i in range(n):
        x, y = (i % cote) / cote - 0.5, (i // cote) / cote - 0.5
        yield (lat0 + y * cote_km / 111.32, lon0 + x * cote_km / (111.32 * math.cos(math.radians(lat0))))


# ─── Niveau visé, tailles ─────────────────────────────────────────────────────
@pytest.mark.parametrize("texte, niveau", [
    ("Bac+2", 5), ("BTS SIO", 5), ("bac + 3", 6), ("Licence pro (Bac+3)", 6), ("BUT informatique", 6),
    ("Bachelor", 6), ("Bac+4", 6), ("Master 2", 7), ("Bac+5", 7), ("Diplôme d'ingénieur", 7),
    ("Bac pro", 4), ("CAP cuisine", 3), ("Titre RNCP niveau 6", 6), ("Bac+2 à Bac+3", 5),
    ("", None), ("je ne sais pas", None), (None, None),
])
def test_niveau_europeen(texte, niveau):
    assert niveau_europeen(texte) == niveau


def test_tailles_au_format_lba():
    assert taille_depuis_tranche("0-0") == taille_depuis_tranche("6-9") == "moins_10"
    assert taille_depuis_tranche("10-19") == "10_49"
    assert taille_depuis_tranche("50-99") == "50_249"
    assert taille_depuis_tranche("10000+") == "5000_plus"


# ─── Géographie ───────────────────────────────────────────────────────────────
def test_sept_sous_cercles_recouvrent_le_cercle():
    cercle = ("Paris", 48.8566, 2.3522, 8)
    sous = lba.sous_cercles(cercle)
    assert len(sous) == 7 and all(c[3] == 4 for c in sous)
    for i in range(36):
        for f in (0.2, 0.5, 0.8, 0.99):
            a, d = math.radians(10 * i), 8 * f
            p = (48.8566 + d * math.sin(a) / 111.32, 2.3522 + d * math.cos(a) / (111.32 * math.cos(math.radians(48.8566))))
            assert min(distance_km(p, (c[1], c[2])) for c in sous) <= 4.01, (i, f)


@pytest.mark.parametrize("ville, point", [
    ("Château-Landon", (48.150, 2.700)), ("Provins", (48.560, 3.299)), ("La Ferté-Gaucher", (48.780, 3.310)),
    ("Lizy-sur-Ourcq", (49.020, 3.020)), ("Montereau", (48.385, 2.950)), ("Bray-sur-Seine", (48.415, 3.240)),
    ("Houdan", (48.790, 1.600)), ("Magny-en-Vexin", (49.155, 1.786)), ("Bonnières-sur-Seine", (49.035, 1.580)),
    ("Dourdan", (48.529, 2.011)), ("Méréville", (48.310, 2.080)), ("Beaumont-sur-Oise", (49.140, 2.290)),
    ("Luzarches", (49.110, 2.420)), ("Nangis", (48.555, 3.015)), ("Saclay", (48.730, 2.170)),
    ("Paris 16e", (48.852, 2.260)), ("Rozay-en-Brie", (48.680, 2.960)),
])
def test_centres_couvrent_l_ile_de_france(ville, point):
    assert any(distance_km(point, (lat, lon)) <= rayon for _, lat, lon, rayon in LBA_CENTRES), ville


# ─── Recherche ────────────────────────────────────────────────────────────────
def test_recherche_codes_niveau_taille_et_exclusions(api):
    offres = ([offre(i, niveau=6) for i in range(3)] + [offre(10 + i, niveau=5) for i in range(2)]
              + [offre(20 + i, niveau=None) for i in range(2)]
              + [offre(30 + i, partenaire="France Travail") for i in range(2)]
              + [offre(40, cp="60200")])                                   # Oise : hors IDF
    ents = [entreprise(1, taille="0-0"), entreprise(2, taille="50-99"), entreprise(3, taille="10-19")]
    fausse = api(FausseLBA(offres, ents, exclusion_ignoree=True))
    log = Journal()
    res = lba.rechercher_pour_profil(profil(niveau="Licence pro (Bac+3)", tailles=["50_249"]), log=log)
    assert sorted(o["titre"] for o in res["offres"]) == sorted(
        [f"Alternance {i}" for i in (0, 1, 2, 20, 21)])                  # niveau 6 ou sans niveau
    assert [e["siret"] for e in res["entreprises"]] == [f"9{2:013d}"]
    # Une requête par centre, les 96 codes M18 en un lot, jamais de niveau envoyé
    assert len(fausse.recherches) == len(LBA_CENTRES)
    assert all(len(r["romes"].split(",")) == 96 for r in fausse.recherches)
    assert not any("target_diploma_level" in r for r in fausse.recherches)
    t = log.texte()
    assert "2 offres relayées de France Travail écartées" in t
    assert "2 offres d'un autre niveau que le niveau 6 écartées" in t
    assert "2 entreprises écartées par la taille" in t
    assert f"en {len(LBA_CENTRES)} requêtes" in t


def test_profil_indifferent_cherche_sans_code(api):
    fausse = api(FausseLBA([offre(1)], [], sans_codes=True))
    log = Journal()
    res = lba.rechercher_pour_profil(profil(domaines=()), log=log)
    assert len(res["offres"]) == 1
    assert all("romes" not in r for r in fausse.recherches)
    assert "indifférent (recherche sans code métier)" in log.texte()
    assert lba.ignoree_pour_profil(profil(domaines=())) == ""


def test_niveau_non_renseigne_ou_non_reconnu_ne_filtre_rien(api):
    api(FausseLBA([offre(1, niveau=5), offre(2, niveau=7)]))
    for niveau, message in (("", "non renseigné"), ("quelque chose", "non reconnu")):
        log = Journal()
        assert len(lba.rechercher_pour_profil(profil(niveau=niveau), log=log)["offres"]) == 2
        assert message in log.texte()


def test_entreprise_normalisee(api):
    brut = entreprise(7, siret="123 456 789 00012", email="RH@Societe.fr")
    brut["apply"]["recipient_id"] = "partners_abc"
    e = lba.normaliser_entreprise(brut)
    assert e["siret"] == "12345678900012" and e["siren"] == "123456789"
    assert e["code_postal"] == "75012" and e["ville"] == "VILLE" and e["departement"] == "75"
    assert e["email"] == "rh@societe.fr" and e["candidature_id"] == "partners_abc"
    assert e["taille"] == "20-49" and e["code_naf"] == "6201Z"
    assert lba.normaliser_entreprise(entreprise(8, cp="60200")) is None


def test_entreprises_au_plafond_comptees_pendant_la_recherche_d_offres(api):
    ents = [entreprise(i, lieu=p) for i, p in enumerate(autour(400))]
    fausse = api(FausseLBA([], ents))
    log = Journal()
    res = lba.rechercher_pour_profil(profil(), log=log)
    assert len(fausse.recherches) == len(LBA_CENTRES)                    # pas de redécoupage
    assert len(res["entreprises"]) < 400
    assert "au plafond de 150 entreprises, non redécoupés pendant la recherche d'offres" in log.texte()


def test_cercles_au_plafond_redecoupes(api):
    ents = [entreprise(i, lieu=p) for i, p in enumerate(autour(400))]
    fausse = api(FausseLBA([], ents))
    log = Journal()
    res = lba.rechercher_pour_profil(profil(), log=log, redecouper_entreprises=True)
    assert len(res["entreprises"]) == 400                                # toutes retrouvées
    rayons = {float(r["radius"]) for r in fausse.recherches}
    assert {4.0, 5.0}.issubset(rayons)                                   # Paris 8 km, Clamart 10 km redécoupés
    assert "encore au plafond" not in log.texte()


def test_offres_au_plafond_redecoupees(api):
    offres = [offre(i, lieu=p) for i, p in enumerate(autour(300))]
    fausse = api(FausseLBA(offres, []))
    res = lba.rechercher_pour_profil(profil(), log=Journal())
    assert len(res["offres"]) == 300 and len(fausse.recherches) > len(LBA_CENTRES)


def test_cercle_encore_au_plafond_au_rayon_minimal(api):
    """200 entreprises au même point, même code : ni les cercles ni les codes
    ne les séparent, le cercle est signalé."""
    fausse = api(FausseLBA([], [entreprise(i) for i in range(200)]))
    log = Journal()
    res = lba.rechercher_pour_profil(profil(), log=log, redecouper_entreprises=True)
    assert len(res["entreprises"]) == 150 and res["au_plafond"] >= 1
    assert "encore au plafond de 150 au rayon minimal (1 km)" in log.texte()
    assert "Paris 1 km" in log.texte() and "[entreprises]" in log.texte()
    assert any(r.get("romes") == "M1805" for r in fausse.recherches)    # lot coupé jusqu'au code seul


def test_limite_de_requetes(api, monkeypatch):
    monkeypatch.setattr(lba, "LBA_REQUETES_MAX", 25)
    api(FausseLBA([], [entreprise(i, lieu=p) for i, p in enumerate(autour(400))]))
    log = Journal()
    res = lba.rechercher_pour_profil(profil(), log=log, redecouper_entreprises=True)
    assert res["requetes"] == 25 and "limite de 25 requêtes atteinte" in log.texte()


def test_objectif_de_nouvelles_entreprises(api):
    ents = [entreprise(i, lieu=p) for i, p in enumerate(autour(400))]
    fausse = api(FausseLBA([], ents))
    connus = frozenset(f"9{i:013d}" for i in range(400))
    log = Journal()
    lba.rechercher_pour_profil(profil(), log=log, redecouper_entreprises=True, objectif_entreprises=10,
                               connus=connus)
    assert "10 nouvelles entreprises atteintes" not in log.texte()       # toutes connues : on continue
    fausse.recherches.clear()
    log = Journal()
    lba.rechercher_pour_profil(profil(), log=log, redecouper_entreprises=True, objectif_entreprises=10)
    assert "10 nouvelles entreprises atteintes" in log.texte() and len(fausse.recherches) == 1


def test_cle_absente_ou_refusee(api, monkeypatch):
    api(FausseLBA([offre(1)]))
    monkeypatch.delenv("LBA_API_KEY")
    log = Journal()
    assert lba.rechercher_pour_profil(profil(), log=log) is None
    assert "LBA_API_KEY manquante" in log.texte()
    monkeypatch.setenv("LBA_API_KEY", " ")
    monkeypatch.setattr(lba.requests, "get", lambda *a, **k: type("R", (), {"status_code": 401, "text": ""})())
    log = Journal()
    assert lba.rechercher_pour_profil(profil(), log=log) is None
    assert "clé refusée (401)" in log.texte()


def test_erreur_d_une_requete_n_arrete_pas_les_autres(api, monkeypatch):
    fausse = api(FausseLBA([offre(1)]))
    appels = []

    def get(*a, **k):
        appels.append(1)
        if len(appels) == 1:
            raise lba.requests.ConnectionError()
        return fausse.get(*a, **k)
    monkeypatch.setattr(lba.requests, "get", get)
    log = Journal()
    res = lba.rechercher_pour_profil(profil(), log=log)
    assert len(res["offres"]) == 1 and "1 requêtes en erreur" in log.texte()
