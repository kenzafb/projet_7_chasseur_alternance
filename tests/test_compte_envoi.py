"""Compte d'envoi : chiffrement, routes, test de connexion, mail de test,
hôtes et ports refusés, mot de passe jamais exposé."""

import base64
import logging
import sqlite3

import pytest
from cryptography.fernet import Fernet

from database import compte_envoi_db
from shared import chiffrement, config, smtp

MDP = "abcd efgh ijkl mnop"          # tel que Google l'affiche
MDP_GMAIL = "abcdefghijklmnop"       # tel qu'il est envoyé au serveur
MDP_AUTRE = "S3cret-Autre-Serveur!"

GMAIL = {"preset": "gmail", "adresse": "ada@gmail.com", "nom_affiche": "Ada L", "mot_de_passe": MDP}
AUTRE = {"preset": "autre", "adresse": "ada@exemple.fr", "serveur": "smtp.exemple.fr", "port": 587,
         "chiffrement": "starttls", "identifiant": "ada", "mot_de_passe": MDP_AUTRE}


def _formes(mdp):
    """Le mot de passe sous les formes où il pourrait fuiter."""
    return [mdp, base64.b64encode(mdp.encode()).decode()]


def _sans_mot_de_passe(texte, *mdps):
    for mdp in mdps:
        for forme in _formes(mdp):
            assert forme not in texte, "mot de passe exposé"


@pytest.fixture
def ada(utilisateur):
    return utilisateur("ada@test.fr", prenom="Ada", nom="L")


# ─── Chiffrement ──────────────────────────────────────────────────────────────
def test_chiffrement_aller_retour(cle_chiffrement):
    jeton = chiffrement.chiffrer("mot de passé ✓")
    assert "mot de pass" not in jeton
    assert chiffrement.dechiffrer(jeton) == "mot de passé ✓"
    assert chiffrement.chiffrer("x") != chiffrement.chiffrer("x")   # sel aléatoire


def test_cle_changee_secret_illisible(cle_chiffrement, monkeypatch):
    jeton = chiffrement.chiffrer("secret")
    monkeypatch.setenv("CLE_CHIFFREMENT", Fernet.generate_key().decode())
    with pytest.raises(chiffrement.SecretIllisible) as e:
        chiffrement.dechiffrer(jeton)
    assert "saisis-le à nouveau" in str(e.value)


@pytest.mark.parametrize("cle", [None, "", "pas-une-cle-fernet", "x" * 44])
def test_sans_cle_valide_l_app_tourne_mais_les_mails_sont_desactives(ada, monkeypatch, cle):
    client, _ = ada
    if cle is None:
        monkeypatch.delenv("CLE_CHIFFREMENT", raising=False)
    else:
        monkeypatch.setenv("CLE_CHIFFREMENT", cle)
    assert client.get("/api/profil").status_code == 200   # l'app fonctionne

    r = client.get("/api/compte_envoi")
    assert r.status_code == 200
    assert r.json()["disponible"] is False and "CLE_CHIFFREMENT" in r.json()["raison"]
    for url, corps in [("/api/compte_envoi", GMAIL), ("/api/compte_envoi/tester", None),
                       ("/api/compte_envoi/mail_test", None)]:
        r = client.post(url, json=corps or {})
        assert r.status_code == 503, url
        assert "CLE_CHIFFREMENT" in r.json()["erreur"]
        if cle:
            assert cle not in r.text
    assert client.post("/api/compte_envoi/supprimer").status_code == 200


# ─── Enregistrement ───────────────────────────────────────────────────────────
def test_gmail_enregistre_chiffre_et_jamais_renvoye(ada, smtp_simule):
    client, user_id = ada
    r = client.post("/api/compte_envoi", json=GMAIL)
    assert r.status_code == 200, r.text
    c = r.json()["compte"]
    assert (c["serveur"], c["port"], c["chiffrement"], c["identifiant"]) == ("smtp.gmail.com", 465, "ssl", "ada@gmail.com")
    assert c["mot_de_passe_configure"] is True and c["verifie"] is False
    assert "mot_de_passe" not in c and "mot_de_passe_chiffre" not in c
    _sans_mot_de_passe(r.text + client.get("/api/compte_envoi").text, MDP, MDP_GMAIL)

    brut = sqlite3.connect(config.DATABASE_URL.removeprefix("sqlite:///")).execute(
        "SELECT mot_de_passe_chiffre FROM comptes_envoi").fetchone()[0]
    _sans_mot_de_passe(brut, MDP, MDP_GMAIL)
    # Espaces du mot de passe d'application retirés
    assert compte_envoi_db.compte_pour_envoi(user_id)["mot_de_passe"] == MDP_GMAIL


def test_mot_de_passe_requis_a_la_creation_puis_conserve(ada, smtp_simule):
    client, user_id = ada
    sans = {k: v for k, v in GMAIL.items() if k != "mot_de_passe"}
    assert client.post("/api/compte_envoi", json=sans).status_code == 400
    assert client.post("/api/compte_envoi", json={**sans, "mot_de_passe": ""}).status_code == 400
    assert client.post("/api/compte_envoi", json=GMAIL).status_code == 200
    # Modification sans mot de passe : l'ancien est gardé
    assert client.post("/api/compte_envoi", json={**sans, "nom_affiche": "Ada"}).status_code == 200
    assert compte_envoi_db.compte_pour_envoi(user_id)["mot_de_passe"] == MDP_GMAIL


def test_validation_422_ne_renvoie_pas_le_mot_de_passe(ada, smtp_simule):
    client, _ = ada
    for corps in [{**GMAIL, "champ_en_trop": MDP}, {**GMAIL, "preset": "outlook"},
                  {**AUTRE, "port": "pas-un-port"}, {**GMAIL, "mot_de_passe": {"x": MDP}}]:
        r = client.post("/api/compte_envoi", json=corps)
        assert r.status_code == 422
        _sans_mot_de_passe(r.text, MDP, MDP_AUTRE)


def test_adresse_invalide(ada, smtp_simule):
    client, _ = ada
    for adresse in ["", "pas-une-adresse", "a@b", "a b@c.fr", "x@y.fr\nBcc: z@w.fr"]:
        assert client.post("/api/compte_envoi", json={**GMAIL, "adresse": adresse}).status_code == 400


def test_chacun_son_compte(utilisateur, smtp_simule):
    client_a, _ = utilisateur("a@test.fr", prenom="A", nom="A")
    client_b, _ = utilisateur("b@test.fr", prenom="B", nom="B")
    client_a.post("/api/compte_envoi", json=GMAIL)
    assert client_b.get("/api/compte_envoi").json()["compte"] is None
    client_b.post("/api/compte_envoi/supprimer")
    assert client_a.get("/api/compte_envoi").json()["compte"]["adresse"] == "ada@gmail.com"


def test_suppression(ada, smtp_simule):
    client, user_id = ada
    client.post("/api/compte_envoi", json=GMAIL)
    assert client.post("/api/compte_envoi/supprimer").json()["ok"] is True
    assert client.get("/api/compte_envoi").json()["compte"] is None
    assert compte_envoi_db.compte_pour_envoi(user_id) is None


# ─── Test de connexion ────────────────────────────────────────────────────────
def test_connexion_reussie(ada, smtp_simule):
    client, _ = ada
    smtp_simule.comptes["ada@gmail.com"] = MDP_GMAIL
    client.post("/api/compte_envoi", json=GMAIL)
    r = client.post("/api/compte_envoi/tester").json()
    assert r["ok"] is True and r["compte"]["verifie"] is True and r["compte"]["verifie_le"]
    assert smtp_simule.connexions == [{"serveur": "smtp.gmail.com", "port": 465, "ip": "142.250.27.108",
                                       "tls": True, "identifiant": "ada@gmail.com"}]
    assert smtp_simule.messages == []   # aucun mail envoyé


def test_connexion_starttls_autre_serveur(ada, smtp_simule):
    client, _ = ada
    smtp_simule.comptes["ada"] = MDP_AUTRE
    client.post("/api/compte_envoi", json=AUTRE)
    assert client.post("/api/compte_envoi/tester").json()["ok"] is True
    assert smtp_simule.connexions[0] == {"serveur": "smtp.exemple.fr", "port": 587, "ip": "80.12.242.10",
                                         "tls": True, "identifiant": "ada"}


def test_mauvais_identifiants(ada, smtp_simule, capsys, caplog):
    client, _ = ada
    caplog.set_level(logging.DEBUG)
    smtp_simule.comptes["ada@gmail.com"] = "autre-mot-de-passe"
    client.post("/api/compte_envoi", json=GMAIL)
    r = client.post("/api/compte_envoi/tester")
    assert r.status_code == 200
    assert r.json()["ok"] is False and "Authentification refusée" in r.json()["message"]
    assert r.json()["compte"]["verifie"] is False
    sortie = capsys.readouterr()
    _sans_mot_de_passe(r.text + sortie.out + sortie.err + caplog.text, MDP, MDP_GMAIL)


def test_serveur_injoignable(ada, smtp_simule):
    client, _ = ada
    smtp_simule.comptes["ada@gmail.com"] = MDP_GMAIL
    client.post("/api/compte_envoi", json=GMAIL)
    assert client.post("/api/compte_envoi/tester").json()["ok"] is True
    smtp_simule.injoignable = True
    r = client.post("/api/compte_envoi/tester").json()
    assert r["ok"] is False and "injoignable" in r["message"]
    assert r["compte"]["verifie"] is True   # panne réseau : la vérification n'est pas perdue
    _sans_mot_de_passe(str(r), MDP, MDP_GMAIL)


def test_echec_d_authentification_retire_la_verification(ada, smtp_simule):
    client, _ = ada
    smtp_simule.comptes["ada@gmail.com"] = MDP_GMAIL
    client.post("/api/compte_envoi", json=GMAIL)
    client.post("/api/compte_envoi/tester")
    smtp_simule.comptes["ada@gmail.com"] = "revoque"
    assert client.post("/api/compte_envoi/tester").json()["compte"]["verifie"] is False


def test_modifier_la_connexion_retire_la_verification(ada, smtp_simule):
    client, _ = ada
    smtp_simule.comptes["ada@gmail.com"] = MDP_GMAIL
    client.post("/api/compte_envoi", json=GMAIL)
    client.post("/api/compte_envoi/tester")
    # Nom affiché seul : toujours vérifié
    r = client.post("/api/compte_envoi", json={"preset": "gmail", "adresse": "ada@gmail.com", "nom_affiche": "A. L."})
    assert r.json()["compte"]["verifie"] is True
    # Nouveau mot de passe : à revérifier
    r = client.post("/api/compte_envoi", json={**GMAIL, "mot_de_passe": "zzzz yyyy xxxx wwww"})
    assert r.json()["compte"]["verifie"] is False


def test_verification_d_une_configuration_modifiee_entre_temps(ada, smtp_simule, monkeypatch):
    """Le test réussi d'une ancienne configuration ne valide pas la nouvelle."""
    client, user_id = ada
    smtp_simule.comptes["ada@gmail.com"] = MDP_GMAIL
    client.post("/api/compte_envoi", json=GMAIL)
    vrai_test = smtp.tester_connexion

    def test_puis_modification(compte):
        vrai_test(compte)
        client.post("/api/compte_envoi", json={**GMAIL, "mot_de_passe": "nouveau mot de passe"})
    monkeypatch.setattr(smtp, "tester_connexion", test_puis_modification)
    client.post("/api/compte_envoi/tester")
    assert compte_envoi_db.lire_compte(user_id)["verifie"] is False


# ─── Mail de test ─────────────────────────────────────────────────────────────
def test_mail_de_test_vers_l_adresse_d_expedition_uniquement(ada, smtp_simule):
    """Décision D9 : comme le mode test, le mail de test part vers l'adresse
    d'expédition, plus vers l'adresse de connexion."""
    client, _ = ada
    smtp_simule.comptes["ada@gmail.com"] = MDP_GMAIL
    client.post("/api/compte_envoi", json=GMAIL)

    for autre in ["victime@exemple.fr", "ADA@test.fr.evil.com", "ada@test.fr, victime@exemple.fr",
                  "ada@test.fr"]:   # l'adresse de connexion non plus
        r = client.post("/api/compte_envoi/mail_test", json={"destinataire": autre})
        assert r.status_code == 400 and "adresse d'expédition" in r.json()["erreur"]
    assert smtp_simule.messages == []

    r = client.post("/api/compte_envoi/mail_test").json()   # défaut : adresse d'expédition
    assert r["ok"] is True and r["compte"]["verifie"] is True
    r = client.post("/api/compte_envoi/mail_test", json={"destinataire": "Ada@Gmail.com"}).json()
    assert r["ok"] is True
    envoyes = [(i, f, t) for i, f, t, _ in smtp_simule.messages]
    assert envoyes == [("ada@gmail.com", "ada@gmail.com", ["ada@gmail.com"])] * 2
    message = smtp_simule.messages[0][3]
    assert message["From"] == "Ada L <ada@gmail.com>"
    assert message["To"] == "ada@gmail.com"
    _sans_mot_de_passe(message.as_string(), MDP, MDP_GMAIL)


def test_mail_de_test_compte_dans_le_plafond(ada, smtp_simule, monkeypatch):
    client, user_id = ada
    monkeypatch.setattr(config, "PLAFOND_ENVOIS_JOUR", 2)
    smtp_simule.comptes["ada@gmail.com"] = MDP_GMAIL
    client.post("/api/compte_envoi", json=GMAIL)
    assert client.post("/api/compte_envoi/mail_test").json()["ok"] is True
    smtp_simule.injoignable = True
    assert client.post("/api/compte_envoi/mail_test").json()["ok"] is False   # rendu au compteur
    smtp_simule.injoignable = False
    assert client.post("/api/compte_envoi/mail_test").json()["ok"] is True
    r = client.post("/api/compte_envoi/mail_test")
    assert r.status_code == 400 and "Plafond" in r.json()["erreur"]
    assert compte_envoi_db.envois_du_jour(user_id) == 2
    assert len(smtp_simule.messages) == 2


def test_sans_compte(ada, smtp_simule):
    client, _ = ada
    for url in ("/api/compte_envoi/tester", "/api/compte_envoi/mail_test"):
        r = client.post(url, json={})
        assert r.status_code == 400 and "Aucun compte d'envoi" in r.json()["erreur"]


# ─── Hôtes et ports ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("hote", ["localhost", "LocalHost.", "mail.localhost", "127.0.0.1", "127.8.9.10",
                                  "10.1.2.3", "172.16.0.1", "192.168.1.10", "169.254.169.254", "0.0.0.0",
                                  "::1", "[::1]", "::ffff:127.0.0.1", "fe80::1", "fd00::1", "100.64.0.1",
                                  "224.0.0.1", "240.0.0.1"])
def test_hotes_interdits(ada, smtp_simule, hote):
    client, _ = ada
    r = client.post("/api/compte_envoi", json={**AUTRE, "serveur": hote})
    assert r.status_code == 400, hote
    assert client.get("/api/compte_envoi").json()["compte"] is None


@pytest.mark.parametrize("ips", [["10.0.0.5"], ["192.168.0.2"], ["127.0.0.1"], ["169.254.1.1"],
                                 ["::1"], ["80.12.242.10", "10.0.0.5"]])
def test_nom_qui_resout_vers_une_adresse_interdite(ada, smtp_simule, dns, ips):
    client, _ = ada
    dns.noms["interne.exemple.fr"] = ips
    r = client.post("/api/compte_envoi", json={**AUTRE, "serveur": "interne.exemple.fr"})
    assert r.status_code == 400 and "refusé" in r.json()["erreur"]


def test_serveur_introuvable_ou_nom_invalide(ada, smtp_simule):
    client, _ = ada
    for hote in ["inconnu.exemple.fr", "", "smtp exemple.fr", "smtp/../x"]:
        assert client.post("/api/compte_envoi", json={**AUTRE, "serveur": hote}).status_code == 400


@pytest.mark.parametrize("port", [25, 2525, 0, 80, 443, 993, -1, 70000])
def test_ports_hors_liste(ada, smtp_simule, port):
    client, _ = ada
    r = client.post("/api/compte_envoi", json={**AUTRE, "port": port, "chiffrement": None})
    assert r.status_code == 400 and "465" in r.json()["erreur"]


def test_port_et_chiffrement_coherents(ada, smtp_simule):
    client, _ = ada
    assert client.post("/api/compte_envoi", json={**AUTRE, "port": 465, "chiffrement": "starttls"}).status_code == 400
    r = client.post("/api/compte_envoi", json={**AUTRE, "port": 465, "chiffrement": None})
    assert r.status_code == 200 and r.json()["compte"]["chiffrement"] == "ssl"


def test_dns_qui_change_apres_l_enregistrement(ada, smtp_simule, dns):
    """Le serveur est revérifié à chaque connexion (rebinding DNS)."""
    client, _ = ada
    smtp_simule.comptes["ada"] = MDP_AUTRE
    client.post("/api/compte_envoi", json=AUTRE)
    dns.noms["smtp.exemple.fr"] = ["127.0.0.1"]
    r = client.post("/api/compte_envoi/tester").json()
    assert r["ok"] is False and "refusé" in r["message"]
    assert smtp_simule.connexions == []


def test_preset_gmail_ignore_un_serveur_fourni(ada, smtp_simule):
    client, _ = ada
    r = client.post("/api/compte_envoi", json={**GMAIL, "serveur": "127.0.0.1", "port": 25})
    assert r.status_code == 200 and r.json()["compte"]["serveur"] == "smtp.gmail.com"


# ─── Balayage complet ─────────────────────────────────────────────────────────
def test_mot_de_passe_absent_de_toute_reponse_log_et_erreur(ada, smtp_simule, capsys, caplog, pipelines_neufs):
    """Un même mot de passe suivi à travers tous les parcours, échecs compris."""
    import time
    from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
    caplog.set_level(logging.DEBUG)
    client, user_id = ada
    mdp = "Mdp-Unique-7f3a9c"
    textes = []

    def appel(methode, url, **kw):
        r = getattr(client, methode)(url, **kw)
        textes.append(r.text)
        return r

    appel("post", "/api/compte_envoi", json={**AUTRE, "mot_de_passe": mdp})
    appel("get", "/api/compte_envoi")
    appel("post", "/api/compte_envoi/tester")                    # identifiants refusés
    smtp_simule.comptes["ada"] = mdp
    appel("post", "/api/compte_envoi/tester")                    # réussi
    appel("post", "/api/compte_envoi", json={**AUTRE, "mot_de_passe": mdp, "port": 25})
    appel("post", "/api/compte_envoi", json={**AUTRE, "mot_de_passe": mdp, "serveur": "10.0.0.1"})
    appel("post", "/api/compte_envoi", json={**AUTRE, "mot_de_passe": mdp, "inconnu": 1})
    appel("post", "/api/compte_envoi/mail_test", json={"destinataire": "autre@x.fr"})
    smtp_simule.injoignable = True
    appel("post", "/api/compte_envoi/mail_test")                 # serveur injoignable
    appel("post", "/api/compte_envoi/tester")
    smtp_simule.injoignable = False

    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}])
    liste = lire_entreprises(user_id)
    liste[0]["emails_trouves"] = ["rh@acme.fr"]
    sauvegarder_enrichissement(user_id, liste)
    smtp_simule.comptes["ada"] = "change-cote-serveur"
    appel("post", "/api/spontanees/envoyer", json={"limite": 1})  # échec d'authentification en route
    fin = time.monotonic() + 5
    while pipelines_neufs.etat("spontanees", user_id)["en_cours"] and time.monotonic() < fin:
        time.sleep(0.01)
    appel("get", "/api/logs")
    appel("get", "/api/spontanees/statut")
    appel("get", "/api/compte_envoi")

    sortie = capsys.readouterr()
    tout = "\n".join(textes) + sortie.out + sortie.err + caplog.text
    assert "Authentification refusée" in tout and "injoignable" in tout   # les échecs ont bien eu lieu
    _sans_mot_de_passe(tout, mdp)


# ─── Vraie classe de connexion (sans réseau) ─────────────────────────────────
class _Coupe(Exception):
    pass


@pytest.mark.parametrize("chiffrement,port", [("ssl", 465), ("starttls", 587)])
def test_connexion_epinglee_sur_l_ip_verifiee(monkeypatch, dns, chiffrement, port):
    """La socket vise l'IP vérifiée (pas de seconde résolution) ; en SSL,
    le certificat est vérifié pour le nom d'hôte."""
    import socket
    import ssl
    ouvertures, verifications = [], []

    class FausseSocket:
        def makefile(self, *a, **k):
            raise _Coupe()

    class FauxServeurStarttls:
        """Socket qui répond comme un serveur proposant STARTTLS."""
        def __init__(self):
            self.reponses = [b"220 pret\r\n", b"250-smtp.exemple.fr\r\n250 STARTTLS\r\n",
                             b"220 go\r\n"]

        def makefile(self, *a, **k):
            import io
            return io.BytesIO(b"".join(self.reponses))

        def sendall(self, donnees):
            pass

        def close(self):
            pass

    def ouvrir(adresse, *args, **kwargs):
        ouvertures.append(adresse)
        return FausseSocket() if chiffrement == "ssl" else FauxServeurStarttls()

    def envelopper(self, sock, server_hostname=None, **kwargs):
        verifications.append((self.verify_mode, self.check_hostname, server_hostname))
        raise _Coupe()

    # conftest remplace smtplib.SMTP, que SMTP_SSL.__init__ appelle par son nom :
    # on remet la vraie classe, le réseau reste coupé par create_connection
    monkeypatch.setattr("smtplib.SMTP", smtp._SMTPEpingle.__mro__[2])
    monkeypatch.setattr(socket, "create_connection", ouvrir)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", envelopper)
    dns.noms["smtp.exemple.fr"] = ["80.12.242.10"]
    conn = smtp._nouvelle_connexion(chiffrement)
    conn.ip_cible = smtp.verifier_hote("smtp.exemple.fr")[0]
    with pytest.raises(_Coupe):
        conn.connect("smtp.exemple.fr", port)
        conn.ehlo()
        conn.starttls(context=ssl.create_default_context())
    assert ouvertures == [("80.12.242.10", port)]
    assert verifications == [(ssl.CERT_REQUIRED, True, "smtp.exemple.fr")]
