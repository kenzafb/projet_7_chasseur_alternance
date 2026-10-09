"""Import de l'historique des adresses contactées (scripts/importer_contacts_historiques.py) :
classement en trois groupes d'après l'ancienne base, import en mode alternance."""

import json
import sqlite3
from pathlib import Path

import pytest

import spontanees.envoyeur as envoyeur
from database.connexion import SessionLocal
from database.dedup_db import lire_emails_contactes
from database.entreprises_db import (ajouter_entreprises, lire_entreprises, lire_entreprises_envoyees,
                                     sauvegarder_enrichissement)
from database.models import EmailContacte
from scripts import importer_contacts_historiques as imp

DDL = Path(__file__).parent / "donnees" / "ancien_schema.sql"


@pytest.fixture
def ancienne_base(tmp_path):
    """Fausse ancienne base au schéma réel : une entreprise envoyée (deux
    adresses, dont une seulement destinataire), une non envoyée."""
    chemin = tmp_path / "ancienne.db"
    cx = sqlite3.connect(chemin)
    cx.executescript(DDL.read_text(encoding="utf-8"))
    cx.execute("INSERT INTO users (id, email, mot_de_passe_hash) VALUES (1, 'u1@test.fr', 'x')")
    lignes = [
        ("ACME", "111111111", ["RH@acme.fr"], 1, "2026-05-29 10:10",
         {"siret": "11111111100012", "mail_destinataires": ["jobs@acme.fr"]}),
        ("Beta", "222222222", ["contact@beta.fr"], 0, None, {"siret": "22222222200012"}),
    ]
    for nom, siren, emails, envoye, date, extra in lignes:
        cx.execute("INSERT INTO entreprises (user_id, nom_commercial, siren, emails_trouves, mail_envoye, "
                   "mail_envoye_le, extra) VALUES (1, ?, ?, ?, ?, ?, ?)",
                   (nom, siren, json.dumps(emails), envoye, date, json.dumps(extra)))
    cx.commit()
    cx.close()
    return chemin


@pytest.fixture
def historique(tmp_path):
    chemin = tmp_path / "emails_deja_envoyes.json"
    chemin.write_text(json.dumps(["rh@acme.fr", "Jobs@acme.fr ", "contact@beta.fr", "maman@perso.fr",
                                  "rh@acme.fr"]), encoding="utf-8")
    return chemin


def _sortie():
    lignes = []
    return lignes, lignes.append


def test_classement_et_essai_a_blanc(ancienne_base, historique, utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    lignes, sortie = _sortie()
    r = imp.lancer(historique, ancienne_base, uid, dry_run=True, sortie=sortie)
    g = r["classement"]
    assert sorted(g["a"]) == ["jobs@acme.fr", "rh@acme.fr"]
    assert sorted(g["b"]) == ["contact@beta.fr"] and sorted(g["c"]) == ["maman@perso.fr"]
    texte = "\n".join(lignes)
    assert "(a) 2 adresses" in texte and "(b) 1 adresses" in texte and "(c) 1 adresses" in texte
    assert "rh@acme.fr  (ACME le 2026-05-29)" in texte and "rien n'est écrit" in texte
    # Rien d'écrit
    with SessionLocal() as db:
        assert db.query(EmailContacte).count() == 0


def test_import_groupe_a_par_defaut(ancienne_base, historique, utilisateur, smtp_simule):
    from tests.conftest import compte_verifie
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    compte_verifie(smtp_simule, uid, "alice@gmail.com")
    # Nouvelle base : ACME (même SIREN, autre SIRET), Beta, et une entreprise
    # dont l'adresse est dans l'historique sans être dans l'ancienne base
    ajouter_entreprises(uid, [{"siret": "11111111100099", "siren": "111111111", "nom": "ACME"},
                              {"siret": "22222222200012", "nom": "Beta"}, {"siret": "S3", "nom": "Perso"}])
    liste = lire_entreprises(uid)
    for e, emails in zip(liste, (["rh@acme.fr"], ["contact@beta.fr"], ["maman@perso.fr"])):
        e["emails_trouves"] = emails
    sauvegarder_enrichissement(uid, liste)
    ajouter_entreprises(uid, [{"siret": "11111111100099", "siren": "111111111"}], mode="job")

    lignes, sortie = _sortie()
    bilan = imp.lancer(historique, ancienne_base, uid, sortie=sortie)["bilan"]
    assert bilan == {"adresses": 2, "adresses_nouvelles": 2, "entreprises_marquees": 1,
                     "deja_envoyees": 0, "deja_historiques": 0}
    assert lire_emails_contactes(uid, "alternance") == {"rh@acme.fr", "jobs@acme.fr"}
    assert lire_emails_contactes(uid, "job") == set()
    acme, beta, perso = lire_entreprises(uid)
    assert acme["mail_envoye"] and acme["historique"] and acme["mail_envoye_le"] == "2026-05-29 10:10"
    assert acme["mail_destinataires"] == ["jobs@acme.fr", "rh@acme.fr"]
    assert not beta["mail_envoye"] and not perso["mail_envoye"]
    # Suivi d'alternance : notée historique, jamais « à relancer »
    suivi, = lire_entreprises_envoyees(uid)
    assert suivi["historique"] and suivi["statut_suivi"] == "envoye"
    # En job : étiquette seulement, l'envoi reste possible
    job, = lire_entreprises(uid, "job")
    assert job["contacts_autres_modes"] == [{"mode": "alternance", "date": "2026-05-29", "historique": True}]
    assert envoyeur.compter_a_envoyer(uid, "job") == 1
    # En alternance : plus jamais visée
    assert envoyeur.compter_a_envoyer(uid, "alternance") == 2   # Beta et Perso seulement

    # Relancer ne crée aucun doublon
    bilan = imp.lancer(historique, ancienne_base, uid, sortie=lambda m: None)["bilan"]
    assert bilan["adresses_nouvelles"] == 0 and bilan["entreprises_marquees"] == 0 and bilan["deja_historiques"] == 1
    with SessionLocal() as db:
        assert db.query(EmailContacte).count() == 2


def test_groupes_choisis_et_entreprise_deja_envoyee(ancienne_base, historique, utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    ajouter_entreprises(uid, [{"siret": "22222222200012", "nom": "Beta"}])
    liste = lire_entreprises(uid)
    liste[0].update(mail_envoye=True, mail_envoye_le="2026-10-01 09:00", mail_destinataires=["contact@beta.fr"])
    from database.entreprises_db import sauvegarder_entreprises
    sauvegarder_entreprises(uid, liste)
    bilan = imp.lancer(historique, ancienne_base, uid, groupes="b,c", sortie=lambda m: None)["bilan"]
    assert bilan["adresses"] == 2 and bilan["deja_envoyees"] == 1 and bilan["entreprises_marquees"] == 0
    beta, = lire_entreprises(uid)
    assert not beta["historique"] and beta["mail_envoye_le"] == "2026-10-01 09:00"   # pas touchée
    assert lire_emails_contactes(uid, "alternance") == {"contact@beta.fr", "maman@perso.fr"}
    with SessionLocal() as db:
        dates = {c.email: c.contacte_le for c in db.query(EmailContacte)}
    assert dates == {"contact@beta.fr": None, "maman@perso.fr": None}   # date inconnue hors groupe a


def test_refus(ancienne_base, historique, utilisateur, monkeypatch):
    with pytest.raises(imp.Refus, match="--user est obligatoire"):
        imp.lancer(historique, ancienne_base, sortie=lambda m: None)
    with pytest.raises(imp.Refus, match="groupes inconnus"):
        imp.lancer(historique, ancienne_base, 1, groupes="a,d", sortie=lambda m: None)
    with pytest.raises(imp.Refus, match="introuvable"):
        imp.lancer(historique, ancienne_base, 999, sortie=lambda m: None)
    # La cible ne peut pas être l'ancienne base
    monkeypatch.setattr(imp.config, "DATABASE_URL", f"sqlite:///{ancienne_base}")
    with pytest.raises(imp.Refus, match="ancienne base"):
        imp.lancer(historique, ancienne_base, dry_run=True, sortie=lambda m: None)
    assert imp.main(["--fichier", str(historique), "--source", str(ancienne_base), "--groupes", "z"]) == 1


def test_ancienne_base_ouverte_en_lecture_seule(ancienne_base, historique, utilisateur):
    avant = ancienne_base.read_bytes()
    _, uid = utilisateur("a@test.fr", prenom="Alice")
    imp.lancer(historique, ancienne_base, uid, groupes="a,b,c", sortie=lambda m: None)
    assert ancienne_base.read_bytes() == avant


@pytest.mark.parametrize("mode", ["job", "stage"])
def test_etiquette_sur_une_entreprise_recuperee_apres_l_import(ancienne_base, historique, utilisateur, mode,
                                                               monkeypatch):
    """Phase 6b, point 4 : une entreprise absente au moment de l'import,
    récupérée plus tard par Sirene dans un autre mode, porte l'étiquette
    « déjà contactée en alternance » dès qu'une de ses adresses scrapées
    est dans l'historique importé. L'envoi n'est pas bloqué."""
    import spontanees.fetch_entreprises as fetch
    from database.entreprises_db import calculer_stats
    from database.profil_db import sauvegarder_profil
    from tests.faux_sirene import FausseSirene, etablissement, siret_sirene
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    imp.lancer(historique, ancienne_base, uid, sortie=lambda m: None)           # groupe a, base vide
    assert lire_entreprises(uid, mode) == []

    monkeypatch.setenv("INSEE_API_KEY", "cle-insee")
    monkeypatch.setenv("NOMENCLATURE_NAF", "NAFRev2")
    monkeypatch.setattr(fetch.P, "PAUSE_S", 0)
    monkeypatch.setattr(fetch.requests, "get", FausseSirene([etablissement(7), etablissement(8)]).get)
    sauvegarder_profil(uid, {"recherche": {"domaines": ["M18"], "departements": ["75"]}}, mode=mode)
    fetch.main(uid, log_fn=lambda m: None, mode=mode)
    liste = lire_entreprises(uid, mode)
    assert [e["_extra"]["siret"] for e in liste] == [siret_sirene(7), siret_sirene(8)]
    assert all(e["contacts_autres_modes"] == [] for e in liste)                 # pas encore d'adresse
    # Le scraper trouve une adresse de l'historique (autre casse) pour la première
    liste[0]["emails_trouves"], liste[1]["emails_trouves"] = ["Jobs@ACME.fr"], ["contact@autre.fr"]
    sauvegarder_enrichissement(uid, liste)

    attendu = [{"mode": "alternance", "date": "2026-05-29", "historique": False}]
    premiere, seconde = lire_entreprises(uid, mode)
    assert premiere["contacts_autres_modes"] == attendu and seconde["contacts_autres_modes"] == []
    client.mode = mode
    prochaines = client.get("/api/spontanees/stats").json()["prochaines"]
    assert [p["contacts_autres_modes"] for p in prochaines] == [attendu, []]
    assert calculer_stats(uid, mode)["prochaines"][0]["contacts_autres_modes"] == attendu
    assert envoyeur.compter_a_envoyer(uid, mode) == 2                           # jamais bloquant
    assert lire_entreprises(uid, "alternance") == []
