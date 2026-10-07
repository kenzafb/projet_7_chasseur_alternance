"""Dates : stockées en UTC, affichées en heure de Paris, identiques quel que
soit le fuseau du processus (variable TZ)."""

import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from database import candidatures_db, entreprises_db
from database.connexion import SessionLocal, engine
from database.dates import (en_texte, instant_depuis_api, maintenant_affichage,
                            vers_utc, JOUR)
from database.models import User

FUSEAUX_PROCESSUS = ["UTC", "America/Los_Angeles", "Asia/Tokyo", "Pacific/Kiritimati", "Europe/Paris"]


@pytest.fixture
def fuseau_processus(monkeypatch):
    """Change le fuseau local du processus (TZ), comme un autre serveur."""
    def changer(nom):
        monkeypatch.setenv("TZ", nom)
        time.tzset()
    yield changer
    monkeypatch.undo()
    time.tzset()


def _user(email):
    db = SessionLocal()
    try:
        u = User(email=email, mot_de_passe_hash="x")
        db.add(u)
        db.commit()
        return u.id
    finally:
        db.close()


def _brut(sql):
    with engine.connect() as cx:
        return cx.execute(text(sql)).scalar_one()


@pytest.mark.parametrize("tz", FUSEAUX_PROCESSUS)
def test_resultat_independant_du_fuseau_du_processus(fuseau_processus, tz):
    fuseau_processus(tz)
    hiver = datetime(2026, 1, 15, 12)
    assert hiver.astimezone().utcoffset() == ZoneInfo(tz).utcoffset(hiver)   # le TZ a bien pris
    uid = _user("a@test.fr")

    # 29 mars 2026, 23h30 UTC = 30 mars 1h30 à Paris (passage à l'heure d'été la veille)
    candidatures_db.ajouter_candidature(uid, {"id": "r1", "date_trouvee": instant_depuis_api("2026-03-29T23:30:00.000Z")})
    # 25 octobre 2026, 0h30 UTC = 2h30 à Paris (jour du retour à l'heure d'hiver)
    candidatures_db.modifier_candidature(uid, "r1", {"date_candidature": datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)})
    c = candidatures_db.lire_candidature(uid, "r1")
    assert (c["date_trouvee"], c["date_candidature"]) == ("2026-03-30", "2026-10-25")
    assert _brut("SELECT date_trouvee FROM candidatures") == "2026-03-29 23:30:00.000000"

    # Texte sans fuseau : lu en heure de Paris, relu à l'identique
    entreprises_db.ajouter_entreprises(uid, [{"siret": "1"}])
    liste = entreprises_db.lire_entreprises(uid)
    liste[0].update(mail_envoye=True, mail_envoye_le="2026-01-15 09:30")
    entreprises_db.sauvegarder_entreprises(uid, liste)
    assert _brut("SELECT mail_envoye_le FROM entreprises") == "2026-01-15 08:30:00.000000"
    relue = entreprises_db.lire_entreprises(uid)
    assert relue[0]["mail_envoye_le"] == "2026-01-15 09:30"
    entreprises_db.sauvegarder_entreprises(uid, relue)   # relecture/réécriture : inchangé
    assert _brut("SELECT mail_envoye_le FROM entreprises") == "2026-01-15 08:30:00.000000"

    # Heure affichée : Paris, pas l'heure locale du processus
    assert maintenant_affichage().utcoffset() in (timedelta(hours=1), timedelta(hours=2))


def test_maj_statut_enregistre_l_instant(utilisateur, fuseau_processus):
    fuseau_processus("Pacific/Kiritimati")   # UTC+14 : la date locale du serveur est souvent « demain »
    client, uid = utilisateur("a@test.fr", prenom="A", nom="A")
    candidatures_db.ajouter_candidature(uid, {"id": "r1"})
    avant = datetime.now(timezone.utc)
    client.post("/api/maj_statut", json={"id": "r1", "statut": "envoye"})
    stocke = datetime.fromisoformat(_brut("SELECT date_candidature FROM candidatures")).replace(tzinfo=timezone.utc)
    assert avant - timedelta(seconds=1) <= stocke <= datetime.now(timezone.utc)
    assert candidatures_db.lire_candidature(uid, "r1")["date_candidature"] == en_texte(stocke, JOUR)


def test_date_seule_refusee_a_l_ecriture():
    with pytest.raises(ValueError, match="date seule"):
        vers_utc("2026-10-01")


@pytest.mark.parametrize("brut,attendu", [
    ("2026-10-01T08:00:00.000Z", datetime(2026, 10, 1, 8, tzinfo=timezone.utc)),
    ("2026-10-01T08:00:00", datetime(2026, 10, 1, 8, tzinfo=timezone.utc)),          # sans fuseau : UTC
    ("2026-10-01T10:00:00+02:00", datetime(2026, 10, 1, 8, tzinfo=timezone.utc)),
    ("2026-10-01", datetime(2026, 10, 1, 10, tzinfo=timezone.utc)),                   # midi à Paris
])
def test_horodatages_des_api(brut, attendu):
    assert instant_depuis_api(brut) == attendu


def test_horodatage_absent_ou_illisible_vaut_maintenant():
    for brut in (None, "", "pas une date"):
        assert abs(instant_depuis_api(brut) - datetime.now(timezone.utc)) < timedelta(seconds=5)


def test_suivi_trie_sur_l_instant():
    uid = _user("a@test.fr")
    entreprises_db.ajouter_entreprises(uid, [{"siret": "1", "nom": "Ancienne"}, {"siret": "2", "nom": "Récente"}])
    liste = entreprises_db.lire_entreprises(uid)
    # Nuit du retour à l'heure d'hiver : 2h30 (été) puis 2h10 (hiver), le texte trierait à l'envers
    liste[0].update(mail_envoye=True, mail_envoye_le=datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc))
    liste[1].update(mail_envoye=True, mail_envoye_le=datetime(2026, 10, 25, 1, 10, tzinfo=timezone.utc))
    entreprises_db.sauvegarder_entreprises(uid, liste)
    suivi = entreprises_db.lire_entreprises_envoyees(uid)
    assert [e["nom"] for e in suivi] == ["Récente", "Ancienne"]
    assert [e["mail_envoye_le"] for e in suivi] == ["2026-10-25 02:10", "2026-10-25 02:30"]
