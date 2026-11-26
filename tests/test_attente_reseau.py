"""D218, D219 : la campagne attend la connexion (démarrage, recherche,
envoi, message), essai toutes les 30 s, jusqu'à l'heure butoir (13:00), 30 min
au moins ; revenue avant, elle part ou reprend, message à l'appui ; sinon
arrêt propre et message au retour. Faux réseau piloté par la fausse horloge : coupé pendant
les intervalles de m.coupures ; rien de vrai ne part (conftest)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import spontanees.recherche_emails as se
import spontanees.site_officiel as S
from database import campagnes_db, compte_envoi_db
from database.entreprises_db import ajouter_entreprises, lire_entreprises
from shared import extinction, reseau, smtp
from shared.verrous import CAMPAGNE, Verrou
from spontanees import envoi
from tests.test_campagne import PARIS, FausseHorloge, actions, FauxTelegram, destinataires, entreprises, lancer, monde, une_fois  # noqa: F401

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
    assert "Pas d'accès internet (démarrage)" in journal[0] and "jusqu'à 13:00" in journal[0]
    assert "Connexion revenue à 09:05 après 5 min" in journal[-1]
    assert r.coupures == 1 and r.perdu_depuis is None


def test_toujours_coupe_abandon_a_l_heure_butoir(net):
    journal, debut = [], net.horloge.t
    net.couper(600)
    r = attente(net, journal)
    assert not r.attendre("recherche")
    assert net.horloge.t == debut.replace(hour=13) and r.perdu_depuis == debut and r.fin_attente == net.horloge.t
    assert "Toujours pas d'accès internet à 13:00 (recherche), coupure depuis 09:00" in journal[-1]
    # Déjà abandonné : plus aucune attente
    assert not r.attendre("envoi") and net.horloge.t == debut.replace(hour=13)


def test_heure_butoir_reglable(net):
    net.couper(600)
    r = attente(net, [], heure_butoir="10:15")
    assert not r.attendre("démarrage") and net.horloge.t == net.horloge.t.replace(hour=10, minute=15)


@pytest.mark.parametrize("heure, minute, abandon", [(12, 50, (13, 20)), (14, 0, (14, 30))])
def test_coupure_peu_avant_ou_apres_la_butoir_attendue_30_min(net, heure, minute, abandon):
    """Un trou de 30 s à 14:00 n'arrête pas la campagne : 30 min au moins."""
    net.horloge.t = net.horloge.t.replace(hour=heure, minute=minute)
    net.couper(600)
    r = attente(net, [])
    r.fixer_butoir(net.horloge.t)
    assert not r.attendre("envoi") and (net.horloge.t.hour, net.horloge.t.minute) == abandon


def test_heure_butoir_du_env(monkeypatch):
    from spontanees.campagne import reglages_env
    assert reglages_env().heure_butoir == "13:00"
    monkeypatch.setenv("CAMPAGNE_HEURE_BUTOIR", "11:30")
    assert reglages_env().heure_butoir == "11:30"
    monkeypatch.setenv("CAMPAGNE_HEURE_BUTOIR", "midi")
    with pytest.raises(Exception, match="CAMPAGNE_HEURE_BUTOIR"):
        reglages_env()


def test_retour_avant_la_butoir_prevenu(net):
    retours = []
    net.couper(90)
    r = attente(net, [], au_retour=lambda *a: retours.append(a))
    assert r.attendre("envoi")
    assert retours == [(net.horloge.t - 90 * MIN, net.horloge.t, "envoi")]


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
    assert monde.telegram.messages[0] == "🌐 Connexion revenue à 09:10, campagne lancée (coupure depuis 09:00)."
    assert monde.telegram.messages[1].startswith("▶️ Campagne commencée")
    j = journal_de(monde)
    assert "Pas d'accès internet (démarrage)" in j and "Connexion revenue à 09:10 après 10 min" in j


@pytest.fixture
def prochaine_7h(monkeypatch):
    """Minuteur du lundi au vendredi à 07:00 : la prochaine est vendredi 27/11."""
    monkeypatch.setattr(extinction, "prochain_lancement", lambda: datetime(2026, 11, 27, 7, 0, tzinfo=PARIS))


def a_sept_heures(monde):
    monde.horloge.t = monde.horloge.t.replace(hour=7)
    return monde.horloge.t


def test_demarrage_sans_connexion_retour_a_9h_campagne_lancee(monde, prochaine_7h):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    debut = a_sept_heures(monde)
    monde.coupures.append((debut, debut.replace(hour=9)))
    b = lancer(monde, une_fois("Envoyer"))
    assert b["stage"]["envoyes"] == 3 and monde.scrapees == ["Ent0", "Ent1", "Ent2"]
    assert monde.telegram.messages[0] == "🌐 Connexion revenue à 09:00, campagne lancée (coupure depuis 07:00)."
    assert monde.telegram.messages[1].startswith("▶️ Campagne commencée")
    assert campagnes_db.derniere(monde.uid)["etat"] == "terminee"
    assert "Connexion revenue à 09:00 après 2 h 00 : reprise (démarrage)" in journal_de(monde)


def test_demarrage_sans_connexion_retour_a_14h_trop_tard(monde, prochaine_7h, monkeypatch):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    debut = a_sept_heures(monde)
    monde.coupures.append((debut, debut.replace(hour=14)))
    verrou_libre = []
    vrai_envoyer = FauxTelegram.envoyer

    def envoyer(self, texte, boutons=None):
        v = Verrou(CAMPAGNE)
        verrou_libre.append(v.prendre())
        v.liberer()
        return vrai_envoyer(self, texte, boutons)
    monkeypatch.setattr(FauxTelegram, "envoyer", envoyer)
    b = lancer(monde, une_fois("Envoyer"), fin="veille")
    assert b == {} and monde.scrapees == [] and monde.recherches == [] and monde.smtp.messages == []
    assert actions(monde) == []                                  # ni veille ni extinction
    derniere = campagnes_db.derniere(monde.uid)
    assert derniere["etat"] == "arretee"
    assert "Toujours pas d'accès internet à 13:00 (démarrage), coupure depuis 07:00" in derniere["journal"]
    assert "arrêtée avant de commencer" in derniere["journal"]
    # Un seul message, dès le retour de la connexion (14:00)
    assert len(monde.telegram.messages) == 1, monde.telegram.messages
    m = monde.telegram.messages[0].splitlines()
    assert m[0] == ("🌐 Connexion revenue à 14:00, trop tard pour aujourd'hui, "
                    "prochaine campagne vendredi 27/11 à 07:00.")
    assert "arrêtée à 13:00 : pas d'accès internet depuis 07:00" in m[1] and m[2] == "Rien n'a été cherché ni envoyé."
    assert verrou_libre[-1]          # une autre campagne pouvait partir pendant l'attente du message


def test_message_au_retour_abandonne_avant_la_prochaine_campagne(monde, prochaine_7h):
    debut = a_sept_heures(monde)
    monde.coupures.append((debut, debut + timedelta(days=2)))
    lancer(monde, une_fois("Envoyer"))
    assert monde.telegram.messages == []
    assert monde.horloge.t <= datetime(2026, 11, 27, 6, 50, tzinfo=PARIS)
    assert "connexion toujours absente" in journal_de(monde)


def test_coupure_a_10h_retour_a_11h_reprise_la_ou_elle_en_etait(monde, prochaine_7h):
    """Veille réglée : jamais pendant l'attente, seulement à la fin, après le retour."""
    ajouter_entreprises(monde.uid, entreprises(10), MODE)
    monde.horloge.t = monde.horloge.t.replace(hour=9, minute=58)
    dix = monde.horloge.t.replace(hour=10, minute=0)
    monde.coupures.append((dix, dix.replace(hour=11)))
    vues = {}

    def avec_email(nom):
        vues[nom] = monde.horloge.t
        return nom in ("Ent5", "Ent6", "Ent7")
    monde.avec_email = avec_email
    b = lancer(monde, validation="auto", fin="veille")
    assert b["stage"]["envoyes"] == 3 and b["stage"]["raison"] == "cible atteinte"
    assert all(vues[f"Ent{i}"] < dix + 5 * MIN for i in range(5))           # premier lot
    assert all(vues[f"Ent{i}"] > dix.replace(hour=11) for i in range(5, 8))  # repris au retour
    assert monde.scrapees == [f"Ent{i}" for i in range(10)]                  # rien refait, rien sauté
    msgs = monde.telegram.messages
    # Coupure vue à 10:03, à la fin du premier lot (limite connue de D218)
    retour = msgs.index("🌐 Connexion revenue à 11:00, campagne reprise (coupure depuis 10:03).")
    veille = next(i for i, t in enumerate(msgs) if t.startswith("🔌 Mise en veille dans 2 minutes"))
    assert retour < veille and len(actions(monde)) == 1
    assert campagnes_db.derniere(monde.uid)["etat"] == "terminee"
    assert "en panne" not in journal_de(monde)


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


def test_coupure_pendant_l_envoi_au_dela_de_la_butoir(monde, monkeypatch, prochaine_7h):
    """Coupée à 12:5x : attendue 30 min (au-delà de 13:00), puis arrêt, message au retour."""
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    monde.horloge.t = monde.horloge.t.replace(hour=12, minute=45)
    vrai = envoi.envoyer_mail

    def envoyer_mail(compte, dest, *a, **k):
        if dest == ["rh@ent1.fr"] and not monde.coupures:
            monde.coupures.append((monde.horloge.t, monde.horloge.t + 50 * MIN))
        if monde.coupe():
            raise smtp.ErreurSmtp(smtp.SERVEUR, "Serveur smtp.gmail.com:465 injoignable (OSError).")
        return vrai(compte, dest, *a, **k)
    monkeypatch.setattr(envoi, "envoyer_mail", envoyer_mail)
    b = lancer(monde, une_fois("Envoyer"), fin="veille")
    assert destinataires(monde) == [["rh@ent0.fr"]] and compte_envoi_db.envois_du_jour(monde.uid) == 1
    assert "pas d'accès internet" in b["stage"]["erreur"]
    assert campagnes_db.derniere(monde.uid)["etat"] == "arretee" and actions(monde) == []
    coupure = monde.coupures[0][0]
    assert coupure.hour == 12 and monde.horloge.t >= coupure + 50 * MIN
    dernier = monde.telegram.messages[-1]
    assert dernier.startswith(f"🌐 Connexion revenue à {monde.coupures[0][1]:%H:%M}, trop tard pour aujourd'hui, "
                              "prochaine campagne vendredi 27/11 à 07:00.")
    assert f"arrêtée à {coupure + 30 * MIN:%H:%M}" in dernier
    assert "stage" in dernier                                     # résumé de ce qui a été fait


def test_panne_de_telegram_seule_n_est_pas_une_coupure(monde):
    """Internet présent, Telegram en panne : aucune attente (D213 : journalisé, la campagne continue)."""
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    debut = monde.horloge.t
    b = lancer(monde, lambda t: setattr(t, "panne", True) or [], validation="auto")
    assert b["stage"]["envoyes"] == 3 and "Pas d'accès internet" not in journal_de(monde)
    assert monde.telegram.messages == [] and monde.horloge.t - debut < 30 * MIN
