"""D218 : la campagne attend la connexion (démarrage, recherche, envoi,
message), essai toutes les 30 s, 30 min au plus, puis arrêt propre et
message au retour. Faux réseau piloté par la fausse horloge : coupé pendant
les intervalles de m.coupures ; rien de vrai ne part (conftest)."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

import spontanees.recherche_emails as se
import spontanees.site_officiel as S
from database import campagnes_db, compte_envoi_db
from database.entreprises_db import ajouter_entreprises, lire_entreprises
from shared import reseau, smtp
from shared.verrous import CAMPAGNE, Verrou
from spontanees import envoi
from tests.test_campagne import FausseHorloge, FauxTelegram, destinataires, entreprises, lancer, monde, une_fois  # noqa: F401

MODE = "stage"
MIN = timedelta(minutes=1)


class FauxNet:
    """Horloge et coupures : _joindre(url) répond hors des coupures ;
    sauf : cibles qui ne répondent jamais (site en panne, pas le réseau)."""

    def __init__(self, monkeypatch):
        self.horloge, self.coupures, self.sauf, self.essais = FausseHorloge(), [], set(), []
        monkeypatch.setattr(reseau, "_joindre", self.joindre)

    def coupe(self):
        return any(a <= self.horloge.t < b for a, b in self.coupures)

    def couper(self, minutes):
        self.coupures.append((self.horloge.t, self.horloge.t + minutes * MIN))

    def joindre(self, url):
        self.essais.append((self.horloge.t, url))
        return url not in self.sauf and not self.coupe()


@pytest.fixture
def net(monkeypatch):
    return FauxNet(monkeypatch)


def attente(net, journal, **kw):
    return reseau.Reseau(net.horloge, journal.append, **kw)


def journal_de(m) -> str:
    return campagnes_db.derniere(m.uid)["journal"]


# ─── shared/reseau.py ─────────────────────────────────────────────────────────
def test_connexion_presente_aucune_attente(net):
    journal = []
    assert attente(net, journal).attendre("démarrage")
    assert journal == [] and net.horloge.t.hour == 9 and net.horloge.t.minute == 0


def test_coupure_de_5_minutes_essai_toutes_les_30_s(net):
    journal, debut = [], net.horloge.t
    net.couper(5)
    r = attente(net, journal)
    assert r.attendre("démarrage")
    assert net.horloge.t - debut == 5 * MIN                         # repris au premier essai réussi
    essais = sorted({t for t, _ in net.essais})
    assert all(b - a == timedelta(seconds=30) for a, b in zip(essais, essais[1:], strict=False))
    assert "Pas d'accès internet (démarrage)" in journal[0] and "Connexion revenue après 5 min" in journal[-1]
    assert r.coupures == 1 and r.perdu_depuis is None


def test_toujours_coupe_abandon_apres_30_minutes(net):
    journal, debut = [], net.horloge.t
    net.couper(600)
    r = attente(net, journal)
    assert not r.attendre("recherche")
    assert net.horloge.t - debut == 30 * MIN and r.perdu_depuis == debut
    assert "Toujours pas d'accès internet après 30 min (recherche)" in journal[-1]
    # Déjà abandonné : plus aucune attente de 30 min
    assert not r.attendre("envoi") and net.horloge.t - debut == 30 * MIN


def test_arret_demande_pendant_l_attente(net):
    arret = []
    net.couper(600)
    r = reseau.Reseau(net.horloge, lambda m: arret.append(1) if "Pas d'accès" in m else None, arret=lambda: bool(arret))
    assert not r.attendre("démarrage") and r.perdu_depuis is None


def test_une_seule_cible_en_panne_n_est_pas_une_coupure(net):
    net.sauf = {"https://api.telegram.org"}
    assert reseau.en_ligne()
    net.sauf = set(reseau.CIBLES)
    assert not reseau.en_ligne()


# ─── Recherche web : une coupure n'est pas une panne du moteur ────────────────
class DDGSCoupe:
    """ddgs.DDGS : aucun moteur ne répond pendant une coupure, sinon acme.fr."""
    net = None
    appels = 0

    def __init__(self, **_):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def text(self, requete, region=None, backend=None, max_results=10):
        DDGSCoupe.appels += 1
        if DDGSCoupe.net.coupe():
            raise ConnectionError("réseau")
        return [{"href": "https://acme.fr", "title": "", "body": ""}]


@pytest.fixture
def moteurs(monkeypatch, net):
    DDGSCoupe.net, DDGSCoupe.appels = net, 0
    monkeypatch.setattr(se, "DDGS", DDGSCoupe)
    monkeypatch.setattr(se, "pause_ddg", lambda: None)
    journal = []
    monkeypatch.setattr(se, "journaliser", journal.append)
    se.reinitialiser_recherche()
    yield journal
    se.reinitialiser_recherche()
    monkeypatch.setattr(se, "_reseau", None)


def test_requete_reprise_au_retour_sans_compter_d_echec(moteurs, net, monkeypatch):
    erreurs = se.erreurs_ddg
    monkeypatch.setattr(se, "_reseau", attente(net, []))
    net.couper(3)
    assert [r["href"] for r in se._resultats_ddg("acme")] == ["https://acme.fr"]
    assert se.erreurs_ddg == erreurs and se._echecs_affilee == 0 and not se.recherche_arretee
    assert not any("Recherche web en échec" in ligne for ligne in moteurs)


def test_coupure_longue_n_arrete_pas_la_recherche_web(moteurs, net, monkeypatch):
    erreurs = se.erreurs_ddg
    monkeypatch.setattr(se, "_reseau", attente(net, []))
    net.couper(600)
    for _ in range(se.ECHECS_AVANT_ARRET + 1):
        assert se._resultats_ddg("x") == []
    assert se.erreurs_ddg == erreurs and not se.recherche_arretee


def test_sans_campagne_rien_ne_change(moteurs, net):
    """L'interface ne passe pas de reseau : un échec compte, comme avant (D187)."""
    erreurs = se.erreurs_ddg
    net.couper(600)
    assert se._resultats_ddg("x") == [] and se.erreurs_ddg == erreurs + 1


# ─── Recherche d'emails : entreprise lue pendant une coupure ──────────────────
@pytest.fixture
def scraper(utilisateur, monkeypatch, net):
    """identifier : rien trouvé si la connexion est coupée, sinon acme.fr par le SIREN."""
    uid = utilisateur("a@test.fr", prenom="Alice")[1]
    ajouter_entreprises(uid, [{"siret": "S1", "siren": "123456781", "nom": "ACME"}], MODE)
    appels = []

    def identifier(e, *a, **k):
        appels.append(net.coupe())
        if net.coupe():
            return None, [{"url": "https://acme.fr", "detail": "accueil illisible"}]
        return S.Verification(url="https://acme.fr", source=S.DEVINE, verifie=True, preuve="siren", detail="SIREN"), []
    monkeypatch.setattr(se, "identifier", identifier)
    monkeypatch.setattr(se, "scraper_et_extraire", lambda v, nom, **k: {"emails": ["rh@acme.fr"], "douteux": []})
    monkeypatch.setattr(se, "completer_noms", lambda e: None)
    return SimpleNamespace(uid=uid, appels=appels)


def test_entreprise_refaite_au_retour_de_la_connexion(scraper, net):
    logs = []
    identifier_vrai = se.identifier

    def coupe_pendant_la_lecture(e, *a, **k):
        if not scraper.appels:
            net.couper(4)             # la connexion tombe pendant la première lecture
        return identifier_vrai(e, *a, **k)
    se.identifier = coupe_pendant_la_lecture
    se.main(scraper.uid, log_fn=logs.append, mode=MODE, reseau=attente(net, logs))
    e = lire_entreprises(scraper.uid, MODE)[0]
    assert scraper.appels == [True, False]
    assert e["traite"] and e["emails_trouves"] == ["rh@acme.fr"] and e["site_verifie"]["verifie"]
    assert any("Connexion coupée : entreprise remise en l'état" in ligne for ligne in logs)


def test_coupure_trop_longue_entreprise_laissee_a_faire(scraper, net):
    net.couper(600)
    se.main(scraper.uid, log_fn=lambda m: None, mode=MODE, reseau=attente(net, []))
    e = lire_entreprises(scraper.uid, MODE)[0]
    assert not e["traite"] and e["emails_trouves"] == [] and not e["_extra"].get("site_verifie")
    assert scraper.appels == [True]


# ─── Campagne ─────────────────────────────────────────────────────────────────
def test_demarrage_attend_la_connexion(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    monde.coupures.append((monde.horloge.t, monde.horloge.t + 10 * MIN))
    b = lancer(monde, une_fois("Envoyer"))
    assert b["stage"]["envoyes"] == 3
    assert monde.telegram.messages[0].startswith("▶️ Campagne commencée")
    j = journal_de(monde)
    assert "Pas d'accès internet (démarrage)" in j and "Connexion revenue après 10 min" in j


def test_demarrage_sans_connexion_arret_puis_message_au_retour(monde, monkeypatch):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    debut = monde.horloge.t
    monde.coupures.append((debut, debut + 45 * MIN))
    verrou_libre = []
    vrai_envoyer = FauxTelegram.envoyer

    def envoyer(self, texte, boutons=None):
        v = Verrou(CAMPAGNE)
        verrou_libre.append(v.prendre())
        v.liberer()
        return vrai_envoyer(self, texte, boutons)
    monkeypatch.setattr(FauxTelegram, "envoyer", envoyer)
    b = lancer(monde, une_fois("Envoyer"))
    assert b == {} and monde.scrapees == [] and monde.smtp.messages == []
    derniere = campagnes_db.derniere(monde.uid)
    assert derniere["etat"] == "arretee"
    assert "Toujours pas d'accès internet après 30 min (démarrage)" in derniere["journal"]
    assert "arrêtée avant de commencer" in derniere["journal"]
    # Un seul message, dès le retour de la connexion (09:45)
    assert len(monde.telegram.messages) == 1, monde.telegram.messages
    m = monde.telegram.messages[0]
    assert "pas d'accès internet depuis 09:00" in m and "Connexion revenue à 09:45" in m and "Rien n'a été fait" in m
    assert "Connexion revenue à 09:45" in campagnes_db.derniere(monde.uid)["journal"]
    assert verrou_libre[-1]          # une autre campagne pouvait partir pendant l'attente du message


def test_coupure_pendant_la_recherche_pause_puis_reprise(monde):
    ajouter_entreprises(monde.uid, entreprises(6), MODE)

    def coupe_apres_ent1(nom):
        if nom == "Ent1":
            monde.coupures.append((monde.horloge.t, monde.horloge.t + 8 * MIN))
        return True
    monde.avec_email = coupe_apres_ent1
    b = lancer(monde, une_fois("Envoyer"))
    assert b["stage"]["raison"] == "cible atteinte" and b["stage"]["envoyes"] == 3
    j = journal_de(monde)
    assert "Pas d'accès internet" in j and "Connexion revenue" in j and "en panne" not in j
    assert monde.telegram.a_dit("recherche finie")           # message parti après la coupure


def test_coupure_pendant_l_envoi_meme_mail_repris(monde, monkeypatch):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    vrai = envoi.envoyer_mail
    envois = []

    def envoyer_mail(compte, dest, *a, **k):
        if len(envois) == 1 and not monde.coupures:
            monde.coupures.append((monde.horloge.t, monde.horloge.t + 5 * MIN))
        envois.append(dest)
        if monde.coupe():
            raise smtp.ErreurSmtp(smtp.SERVEUR, "Serveur smtp.gmail.com:465 injoignable (OSError).")
        return vrai(compte, dest, *a, **k)
    monkeypatch.setattr(envoi, "envoyer_mail", envoyer_mail)
    b = lancer(monde, une_fois("Envoyer"))
    assert b["stage"]["envoyes"] == 3 and b["stage"]["echecs"] == 0
    assert destinataires(monde) == [["rh@ent0.fr"], ["rh@ent1.fr"], ["rh@ent2.fr"]]       # aucun doublon
    assert compte_envoi_db.envois_du_jour(monde.uid) == 3
    assert "Pas d'accès internet (envoi)" in journal_de(monde)


def test_coupure_trop_longue_pendant_l_envoi(monde, monkeypatch):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    vrai = envoi.envoyer_mail

    def envoyer_mail(compte, dest, *a, **k):
        if dest == ["rh@ent1.fr"] and not monde.coupures:
            monde.coupures.append((monde.horloge.t, monde.horloge.t + 50 * MIN))
        if monde.coupe():
            raise smtp.ErreurSmtp(smtp.SERVEUR, "Serveur smtp.gmail.com:465 injoignable (OSError).")
        return vrai(compte, dest, *a, **k)
    monkeypatch.setattr(envoi, "envoyer_mail", envoyer_mail)
    b = lancer(monde, une_fois("Envoyer"))
    assert destinataires(monde) == [["rh@ent0.fr"]] and compte_envoi_db.envois_du_jour(monde.uid) == 1
    assert "pas d'accès internet" in b["stage"]["erreur"]
    assert campagnes_db.derniere(monde.uid)["etat"] == "arretee"
    assert "Connexion revenue à" in monde.telegram.messages[-1]
    assert "stage" in monde.telegram.messages[-1]                 # résumé de ce qui a été fait


def test_panne_de_telegram_seule_n_est_pas_une_coupure(monde):
    """Internet présent, Telegram en panne : aucune attente (D213 : journalisé, la campagne continue)."""
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    debut = monde.horloge.t
    b = lancer(monde, lambda t: setattr(t, "panne", True) or [], validation="auto")
    assert b["stage"]["envoyes"] == 3 and "Pas d'accès internet" not in journal_de(monde)
    assert monde.telegram.messages == [] and monde.horloge.t - debut < 30 * MIN
