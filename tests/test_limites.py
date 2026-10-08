"""Limites par lancement : valeurs par défaut, plafonds côté serveur, et
limites respectées par la recherche, le fetch, le scraper et l'envoi."""

import itertools
from types import SimpleNamespace

import pytest

import france_travail.analyseur
import france_travail.scraper as scraper
import main
import spontanees.envoyeur as envoyeur
import spontanees.fetch_entreprises as fetch
import spontanees.scraper_emails as scraper_emails
from database.candidatures_db import lire_candidatures
from database.dedup_db import lire_offres_vues
from database.entreprises_db import ajouter_entreprises, lire_entreprises
from shared import config
from tests.conftest import compte_verifie
from tests.test_envoyeur import attendre, entreprises

ANALYSE = ('{"score": 8, "eligible": true, "points_forts": [], "points_faibles": [], '
           '"domaine": "Informatique", "resume": "ok"}')


# ─── Règle commune ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("cle", sorted(config.LIMITES_LANCEMENT))
def test_defaut_et_plafond(cle):
    regle = config.LIMITES_LANCEMENT[cle]
    assert 1 <= regle["defaut"] <= regle["max"]
    assert config.limite_lancement(cle, None) == regle["defaut"]
    assert config.limite_lancement(cle, 0) == 1
    assert config.limite_lancement(cle, -7) == 1
    assert config.limite_lancement(cle, 10**9) == regle["max"]
    assert config.limite_lancement(cle, 1) == 1


def test_plafond_des_mails_inchange():
    assert config.LIMITES_LANCEMENT["mails"]["max"] == config.LIMITE_ENVOIS_PAR_LANCEMENT == 50


def test_interface_reprend_defauts_et_plafonds(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = client.get("/").text
    for cle, regle in config.LIMITES_LANCEMENT.items():
        if cle == "sans_ia":   # même champ que « analyses », affiché quand ANALYSE_IA=false
            continue
        assert f'data-limite="{cle}" value="{regle["defaut"]}"' in page
        assert f'max="{regle["max"]}"' in page


# ─── Recherche d'offres ──────────────────────────────────────────────────────
def _brut_ft(i):
    return {"id": f"FT{i}", "intitule": f"Poste {i}", "lieuTravail": {"libelle": "75 - Paris 10e"},
            "entreprise": {"nom": "ACME"}, "dateCreation": "2026-10-01T08:00:00.000Z"}


def _lba(i):
    return {"id": f"LBA{i}", "titre": f"Alternance {i}", "entreprise": "LBA SA", "lieu": "75012 PARIS",
            "zone": "Paris", "source": "La Bonne Alternance", "lien": "", "description": "..."}


@pytest.fixture
def sources(monkeypatch, mistral):
    """France Travail et LBA simulés : nb_ft et nb_lba offres à chaque appel."""
    nombres = {"ft": 0, "lba": 0}
    monkeypatch.setattr(scraper, "recuperer_offres",
                        lambda criteres, log=print, **_: [_brut_ft(i) for i in range(nombres["ft"])])
    monkeypatch.setattr(main, "rechercher_lba", lambda profil, log=print: {"offres": [_lba(i) for i in range(nombres["lba"])], "entreprises": [], "requetes": 0})
    monkeypatch.setattr(france_travail.analyseur, "PAUSE_MISTRAL", 0)
    mistral.reponse = ANALYSE
    return nombres


def _rechercher(client, user_id, pipelines, **corps):
    r = client.post("/api/recherche", json=corps or None)
    assert r.status_code == 200, r.text
    attendre(lambda: not pipelines.etat("recherche", user_id)["en_cours"])
    return r.json()


def test_recherche_limite_france_travail_et_lba_ensemble(utilisateur, sources, mistral, pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    sources.update(ft=3, lba=10)
    assert _rechercher(client, user_id, pipelines_neufs, max_analyses=5)["max_analyses"] == 5
    assert len(mistral.appels) == 5
    refs = {c["id"] for c in lire_candidatures(user_id)}
    assert len(refs) == 5 and sorted(r for r in refs if r.startswith("LBA")) == ["LBA0", "LBA1"]
    assert "limite" in client.get("/api/logs").text.lower()


def test_offres_au_dela_de_la_limite_reproposees(utilisateur, sources, mistral, pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    sources.update(ft=10)
    _rechercher(client, user_id, pipelines_neufs, max_analyses=4)
    assert len(mistral.appels) == 4
    assert len(lire_offres_vues(user_id, "alternance")) == 4   # les 6 autres ne sont pas perdues
    assert len(lire_candidatures(user_id)) == 4
    _rechercher(client, user_id, pipelines_neufs, max_analyses=100)
    assert len(lire_candidatures(user_id)) == 10


def test_recherche_lba_ignoree_quand_france_travail_epuise_la_limite(utilisateur, sources, mistral,
                                                                     pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    sources.update(ft=6, lba=4)
    _rechercher(client, user_id, pipelines_neufs, max_analyses=6)
    assert len(mistral.appels) == 6
    assert "LBA ignorée" in client.get("/api/logs").text


def test_recherche_defaut_et_plafond_serveur(utilisateur, sources, pipelines_neufs, monkeypatch):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    assert _rechercher(client, user_id, pipelines_neufs)["max_analyses"] == 30
    assert _rechercher(client, user_id, pipelines_neufs, max_analyses=10**6)["max_analyses"] == 200
    assert client.post("/api/recherche", json={"max_analyses": 5, "autre": 1}).status_code == 422


def test_limite_du_mode_job_reste_un_plafond(utilisateur, sources, mistral, pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    client.post("/api/mode", json={"mode": "job"})
    client.post("/api/profil", json={"prenom": "Alice"})
    sources.update(ft=8)
    _rechercher(client, user_id, pipelines_neufs, max_analyses=3)
    assert len(mistral.appels) == 3


# ─── Fetch des entreprises ───────────────────────────────────────────────────
class FausseSirene:
    """API Sirene simulée : 3 établissements nouveaux par page, 2 pages par requête."""

    def __init__(self):
        self.numeros = itertools.count()
        self.appels = 0

    def get(self, url, headers=None, params=None, timeout=None):
        self.appels += 1
        etabs = []
        for _ in range(3):
            n = next(self.numeros)
            etabs.append({"siret": f"{n:014d}", "uniteLegale": {"denominationUniteLegale": f"Ent {n}",
                                                                  "siren": f"{n:09d}"},
                          "adresseEtablissement": {"codePostalEtablissement": "75010"},
                          "periodesEtablissement": [{"dateFin": None}]})
        suivant = None if params["curseur"] != "*" else "page2"
        donnees = {"header": {"total": 6, "curseurSuivant": suivant}, "etablissements": etabs}
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: donnees)


@pytest.fixture
def sirene(monkeypatch):
    faux = FausseSirene()
    monkeypatch.setattr(fetch, "INSEE_API_KEY", "factice")
    monkeypatch.setattr(fetch.requests, "get", faux.get)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    return faux


def test_fetch_s_arrete_a_la_limite(utilisateur, sirene):
    _, user_id = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(user_id, [{"siret": "DEJA1", "nom": "Ancienne"}])
    logs = []
    fetch.main(user_id, max_entreprises=5, log_fn=logs.append)
    assert len(lire_entreprises(user_id)) == 1 + 5   # les anciennes ne comptent pas
    assert sirene.appels == 2                         # plus aucune requête une fois la limite atteinte
    assert any("5 nouvelles entreprises ajoutées" in l for l in logs)


def test_fetch_sans_limite_parcourt_tout(utilisateur, sirene):
    _, user_id = utilisateur("a@test.fr", prenom="Alice")
    fetch.main(user_id)
    assert len(lire_entreprises(user_id)) == sirene.appels * 3 > 5


def test_route_fetch_borne_la_limite(utilisateur, monkeypatch, pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    recues = []
    monkeypatch.setattr(fetch, "main", lambda **kw: recues.append(kw["max_entreprises"]))
    for demande, attendu in ((None, 200), (12, 12), (10**6, 5000), (0, 1)):
        r = client.post("/api/spontanees/fetch", json={} if demande is None else {"max_entreprises": demande})
        assert r.json()["max_entreprises"] == attendu
        attendre(lambda: not pipelines_neufs.etat("spontanees", user_id)["en_cours"])
    assert recues == [200, 12, 5000, 1]


# ─── Scraper ─────────────────────────────────────────────────────────────────
def test_scraper_traite_au_plus_la_limite(utilisateur, monkeypatch):
    _, user_id = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(user_id, [{"siret": f"S{i}", "nom": f"Ent {i}"} for i in range(5)])
    monkeypatch.setattr(scraper_emails, "chercher_site", lambda e, url_exclue=None: ("https://ent.fr", "ddg"))
    monkeypatch.setattr(scraper_emails, "scraper_et_extraire", lambda url, nom, dirigeant=None, **_: {
        "emails": ["rh@ent.fr"], "telephones": [], "contact_rh": None, "url_finale": url, "fiable": True})
    scraper_emails.main(user_id, max_scrapees=2, log_fn=lambda m: None)
    assert sum(e["traite"] for e in lire_entreprises(user_id)) == 2
    scraper_emails.main(user_id, max_scrapees=2, log_fn=lambda m: None)
    assert sum(e["traite"] for e in lire_entreprises(user_id)) == 4


def test_route_scraper_borne_la_limite(utilisateur, monkeypatch, pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(user_id, [{"siret": f"S{i}", "nom": f"Ent {i}"} for i in range(250)])
    recues = []
    monkeypatch.setattr(scraper_emails, "main", lambda **kw: recues.append(kw["max_scrapees"]))
    for demande in (None, 7, 10**6):
        r = client.post("/api/spontanees/scraper", json={} if demande is None else {"max_scrapees": demande})
        assert r.status_code == 200
        attendre(lambda: not pipelines_neufs.etat("spontanees", user_id)["en_cours"])
    assert recues == [20, 7, 200]


# ─── Envoi ───────────────────────────────────────────────────────────────────
def test_route_envoi_borne_la_limite(utilisateur, smtp_simule, monkeypatch, pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    compte_verifie(smtp_simule, user_id, "alice@gmail.com")
    monkeypatch.setattr(envoyeur, "PAUSE_ENTRE_MAILS", (0, 0))
    entreprises(user_id, 60)
    recues = []
    monkeypatch.setattr(envoyeur, "main", lambda **kw: recues.append(kw["limite"]))
    for demande in (None, 3, 999):
        r = client.post("/api/spontanees/envoyer", json={} if demande is None else {"limite": demande})
        assert r.status_code == 200
        attendre(lambda: not pipelines_neufs.etat("spontanees", user_id)["en_cours"])
    assert recues == [10, 3, 50]


def test_envoi_respecte_la_limite(utilisateur, smtp_simule, monkeypatch):
    _, user_id = utilisateur("a@test.fr", prenom="Alice")
    compte_verifie(smtp_simule, user_id, "alice@gmail.com")
    monkeypatch.setattr(envoyeur, "PAUSE_ENTRE_MAILS", (0, 0))
    entreprises(user_id, 5)
    assert envoyeur.main(user_id, limite=2)["envoyes"] == 2
    assert len(smtp_simule.messages) == 2


# ─── Valeur appliquée affichée (décision D6) ─────────────────────────────────
def test_valeur_ramenee_journalisee(utilisateur, monkeypatch, pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(user_id, [{"siret": f"S{i}", "nom": f"Ent {i}"} for i in range(250)])
    monkeypatch.setattr(scraper_emails, "main", lambda **kw: None)
    r = client.post("/api/spontanees/scraper", json={"max_scrapees": 999})
    assert r.json()["max_scrapees"] == 200
    attendre(lambda: not pipelines_neufs.etat("spontanees", user_id)["en_cours"])
    assert "(demandé : 999, ramené à 200)" in client.get("/api/logs").text


def test_valeur_dans_les_bornes_sans_precision(utilisateur, monkeypatch, pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(user_id, [{"siret": f"S{i}", "nom": f"Ent {i}"} for i in range(10)])
    monkeypatch.setattr(scraper_emails, "main", lambda **kw: None)
    client.post("/api/spontanees/scraper", json={"max_scrapees": 7})
    attendre(lambda: not pipelines_neufs.etat("spontanees", user_id)["en_cours"])
    logs = client.get("/api/logs").text
    assert "au plus 7 entreprises" in logs and "ramené" not in logs


def test_front_affiche_la_valeur_appliquee_par_le_serveur():
    api = (config.STATIC_DIR / "js" / "api.js").read_text(encoding="utf-8")
    fonction = api[api.index("export function limite"):api.index("const LANCEMENTS")]
    assert "Math.min" not in fonction and "Math.max" not in fonction   # plus de bornage côté front
    assert "export function confirmerLancement" in api and "ramené à" in api
    for module in ("app.js", "spontanees.js"):
        assert "confirmerLancement(" in (config.STATIC_DIR / "js" / module).read_text(encoding="utf-8")
    assert "data-confirmation" in (config.TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")


# ─── Limites bornées par ce qui reste à traiter (phase 4b) ───────────────────
def test_scraper_borne_par_les_entreprises_a_traiter(utilisateur, monkeypatch, pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(user_id, [{"siret": f"S{i}", "nom": f"Ent {i}"} for i in range(5)])
    liste = lire_entreprises(user_id)
    liste[0]["traite"] = True                          # déjà traitée
    liste[1]["emails_trouves"] = ["rh@ent1.fr"]        # déjà des emails
    from database.entreprises_db import sauvegarder_enrichissement
    sauvegarder_enrichissement(user_id, liste)
    assert client.get("/api/spontanees/stats").json()["a_scraper"] == 3

    recues = []
    monkeypatch.setattr(scraper_emails, "main", lambda **kw: recues.append(kw["max_scrapees"]))
    r = client.post("/api/spontanees/scraper", json={"max_scrapees": 10})
    assert r.json()["max_scrapees"] == 3 and recues == [3]
    attendre(lambda: not pipelines_neufs.etat("spontanees", user_id)["en_cours"])
    assert "(demandé : 10, ramené à 3)" in client.get("/api/logs").text


def test_scraper_refuse_sans_entreprise_a_traiter(utilisateur, pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    r = client.post("/api/spontanees/scraper", json={"max_scrapees": 5})
    assert r.status_code == 400 and "Aucune entreprise à scraper" in r.json()["erreur"]
    assert pipelines_neufs.etat("spontanees", user_id)["en_cours"] is False


def test_envoi_borne_par_les_entreprises_a_contacter(utilisateur, smtp_simule, monkeypatch, pipelines_neufs):
    from database.dedup_db import ajouter_emails_contactes
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    compte_verifie(smtp_simule, user_id, "alice@gmail.com")
    entreprises(user_id, 4)                                        # rh0@ent0.fr ... rh3@ent3.fr
    ajouter_entreprises(user_id, [{"siret": "SANS", "nom": "Sans email"}])
    ajouter_emails_contactes(user_id, "alternance", ["rh0@ent0.fr"])   # déjà contactée dans ce mode
    liste = lire_entreprises(user_id)
    liste[1]["mail_envoye"] = True                                 # déjà envoyée
    from database.entreprises_db import sauvegarder_entreprises
    sauvegarder_entreprises(user_id, liste)
    assert client.get("/api/spontanees/stats").json()["a_envoyer"] == 2
    assert envoyeur.compter_a_envoyer(user_id, "job") == 3         # rh0 jamais contactée en job

    recues = []
    monkeypatch.setattr(envoyeur, "main", lambda **kw: recues.append(kw["limite"]))
    r = client.post("/api/spontanees/envoyer", json={"limite": 30})
    assert r.json()["limite"] == 2 and recues == [2]
    attendre(lambda: not pipelines_neufs.etat("spontanees", user_id)["en_cours"])
    assert "(demandé : 30, ramené à 2)" in client.get("/api/logs").text


def test_envoi_refuse_quand_rien_a_envoyer(utilisateur, smtp_simule, pipelines_neufs):
    client, user_id = utilisateur("a@test.fr", prenom="Alice")
    compte_verifie(smtp_simule, user_id, "alice@gmail.com")
    r = client.post("/api/spontanees/envoyer", json={"limite": 5})
    assert r.status_code == 400 and "Rien à envoyer" in r.json()["erreur"]
    assert smtp_simule.connexions == []


def test_front_affiche_le_maximum_disponible():
    page = (config.TEMPLATES_DIR / "partials" / "spontanees.html").read_text(encoding="utf-8")
    for cle in ("scrapees", "mails"):
        assert f'data-limite-max="{cle}"' in page
    js = (config.STATIC_DIR / "js" / "spontanees.js").read_text(encoding="utf-8")
    assert "stats?.a_scraper" in js and "stats?.a_envoyer" in js and "champ.max =" in js
