"""
Configuration commune des tests.

Isolation complète :
  - le vrai .env n'est pas lu (CHASSEUR_ENV_FILE pointe vers un fichier absent) ;
  - la base est un SQLite temporaire (DATABASE_URL) : schéma créé une fois
    par `alembic upgrade head` dans un modèle, recopié avant chaque test ;
  - Mistral, SMTP et tout accès réseau sont neutralisés : un appel non prévu
    fait échouer le test au lieu de partir sur Internet ;
  - PDF et pièces jointes écrits dans un dossier temporaire, jamais dans data/.

Ces variables doivent être posées AVANT tout import du projet : shared.config
lit l'environnement à l'import.
"""

import os
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

_TMP = Path(tempfile.mkdtemp(prefix="chasseur_tests_"))
os.environ["CHASSEUR_ENV_FILE"] = str(_TMP / "absent.env")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["SECRET_KEY"] = "cle-de-test-" + "x" * 40
os.environ["COOKIE_SECURE"] = "false"
os.environ["MISTRAL_API_KEY"] = "factice"
os.environ["MISTRAL_INTERVALLE_MIN_S"] = "0"   # pas d'attente entre appels simulés
for _var in ("CODE_INVITATION", "FT_CLIENT_ID", "FT_CLIENT_SECRET", "LBA_API_KEY",
             "INSEE_API_KEY", "CLE_CHIFFREMENT", "PLAFOND_ENVOIS_JOUR", "ANALYSE_IA"):
    os.environ.pop(_var, None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from shared import config  # noqa: E402

assert not str(config.DATABASE_URL).endswith("data/chasseur.db"), "les tests visent la vraie base"

import main  # noqa: E402
import shared.ia  # noqa: E402
from database.connexion import SessionLocal, engine  # noqa: E402
from database.models import User  # noqa: E402
from database.schema import migrer  # noqa: E402

CODE = "code-invitation-de-test"
MOT_DE_PASSE = "motdepasse-solide"


# ─── Barrières réseau ─────────────────────────────────────────────────────────
class _ReseauInterdit(Exception):
    pass


@pytest.fixture(autouse=True)
def pas_de_reseau(monkeypatch):
    """Toute connexion socket, résolution DNS ou connexion SMTP lève une
    erreur (le TestClient n'en ouvre pas)."""
    def refuser(*args, **kwargs):
        raise _ReseauInterdit("accès réseau interdit pendant les tests")
    monkeypatch.setattr(socket.socket, "connect", refuser)
    monkeypatch.setattr(socket, "create_connection", refuser)
    monkeypatch.setattr(socket, "getaddrinfo", refuser)
    monkeypatch.setattr("smtplib.SMTP", refuser)
    monkeypatch.setattr("smtplib.SMTP_SSL", refuser)


class FauxMistral:
    """Remplace le client Mistral : enregistre les appels, renvoie `reponse`."""

    def __init__(self):
        self.appels = []
        self.reponse = '{"contact_entreprise": "ACME\\n75010 Paris", "paragraphe_entreprise": "ACME, votre contexte me parle."}'
        self.chat = SimpleNamespace(complete=self._complete)

    def _complete(self, **kwargs):
        self.appels.append(kwargs)
        message = SimpleNamespace(content=self.reponse)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


@pytest.fixture(autouse=True)
def mistral(monkeypatch):
    faux = FauxMistral()
    monkeypatch.setattr(shared.ia, "client", faux)
    return faux


@pytest.fixture(autouse=True)
def dossiers_temporaires(monkeypatch, tmp_path):
    """PDF et pièces jointes dans tmp_path, jamais dans le projet."""
    monkeypatch.setattr(config, "LETTRES_PDF_DIR", tmp_path / "pdf")
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path / "uploads")


@pytest.fixture(autouse=True)
def pipelines_neufs(monkeypatch):
    """États, arrêts et logs des pipelines vides à chaque test."""
    from shared.pipelines import Pipelines
    monkeypatch.setattr(main, "pipelines", Pipelines())
    return main.pipelines


# ─── Envoi de mails simulé ────────────────────────────────────────────────────
class FauxDNS:
    """Remplace socket.getaddrinfo : noms connus -> adresses choisies par le test."""

    def __init__(self):
        self.noms = {"smtp.gmail.com": ["142.250.27.108"], "smtp.exemple.fr": ["80.12.242.10"]}

    def __call__(self, hote, port, *args, **kwargs):
        if hote not in self.noms:
            raise socket.gaierror(-2, "Name or service not known")
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))
                for ip in self.noms[hote]]


class FauxServeurSmtp:
    """Remplace la connexion de shared.smtp. Accepte les identifiants de
    `comptes` ({identifiant: mot de passe}), enregistre connexions et mails.
    Ses messages d'erreur contiennent volontairement le mot de passe reçu :
    l'application ne doit jamais les relayer."""

    def __init__(self):
        self.comptes = {}
        self.injoignable = False
        self.refuses = set()       # destinataires refusés
        self.connexions = []       # une entrée par login : serveur, port, ip, tls, identifiant
        self.messages = []         # (identifiant, from_addr, to_addrs, EmailMessage)

    def connexion(self, chiffrement):
        return _FausseConnexion(self, chiffrement)


class _FausseConnexion:
    ip_cible = None

    def __init__(self, serveur, chiffrement):
        self.serveur, self.chiffrement, self.tls = serveur, chiffrement, chiffrement == "ssl"
        self.identifiant = None

    def connect(self, hote, port):
        if self.serveur.injoignable:
            raise ConnectionRefusedError(111, "Connection refused")
        self.hote, self.port = hote, port
        return 220, b"pret"

    def ehlo(self):
        return 250, b"ok"

    def has_extn(self, nom):
        return nom == "starttls"

    def starttls(self, context=None):
        self.tls = True

    def login(self, identifiant, mot_de_passe):
        self.serveur.connexions.append({"serveur": self.hote, "port": self.port, "ip": self.ip_cible,
                                        "tls": self.tls, "identifiant": identifiant})
        if self.serveur.comptes.get(identifiant) != mot_de_passe:
            import smtplib
            raise smtplib.SMTPAuthenticationError(535, f"refuse {identifiant} {mot_de_passe}".encode())
        self.identifiant = identifiant

    def send_message(self, message, from_addr, to_addrs):
        import smtplib
        refuses = [a for a in to_addrs if a in self.serveur.refuses]
        if refuses and len(refuses) == len(to_addrs):
            raise smtplib.SMTPRecipientsRefused({a: (550, b"inconnu") for a in refuses})
        self.serveur.messages.append((self.identifiant, from_addr, list(to_addrs), message))
        return {a: (550, b"inconnu") for a in refuses}

    def quit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def cle_chiffrement(monkeypatch):
    from cryptography.fernet import Fernet
    cle = Fernet.generate_key().decode()
    monkeypatch.setenv("CLE_CHIFFREMENT", cle)
    return cle


@pytest.fixture
def dns(monkeypatch):
    faux = FauxDNS()
    monkeypatch.setattr(socket, "getaddrinfo", faux)
    return faux


@pytest.fixture
def smtp_simule(monkeypatch, cle_chiffrement, dns):
    """Clé de chiffrement posée, DNS et serveur SMTP simulés."""
    import shared.smtp
    serveur = FauxServeurSmtp()
    monkeypatch.setattr(shared.smtp, "_nouvelle_connexion", serveur.connexion)
    return serveur


def compte_verifie(serveur, user_id, adresse, mot_de_passe=None, mode_test=False):
    """Enregistre un compte d'envoi Gmail vérifié pour user_id, que le faux
    serveur `serveur` accepte, en envoi réel sauf mode_test=True (un compte
    neuf est créé en mode test). Retourne le mot de passe."""
    from database import compte_envoi_db
    mot_de_passe = mot_de_passe or f"mdp-de-{adresse}"
    compte_envoi_db.enregistrer_compte(user_id, {
        "preset": "gmail", "adresse": adresse, "nom_affiche": "", "serveur": "smtp.gmail.com",
        "port": 465, "chiffrement": "ssl", "identifiant": adresse}, mot_de_passe)
    compte_envoi_db.marquer_verification(user_id, True)
    compte_envoi_db.definir_mode_test(user_id, mode_test)
    serveur.comptes[adresse] = mot_de_passe
    return mot_de_passe


# ─── Threads de test ──────────────────────────────────────────────────────────
DELAI_THREADS = 10   # secondes : au-delà, un thread de test est considéré bloqué


def en_parallele(fonction, nombre, delai=DELAI_THREADS):
    """Lance `nombre` threads qui appellent fonction() au même moment
    (barrière avec délai), les attend avec un délai, et échoue si l'un d'eux
    ne s'est pas terminé. Threads démons : un thread bloqué n'empêche jamais
    pytest de s'arrêter. Retourne les exceptions levées dans les threads."""
    depart = threading.Barrier(nombre, timeout=delai)
    erreurs = []

    def cible():
        try:
            depart.wait()
            fonction()
        except Exception as e:
            erreurs.append(e)

    fils = [threading.Thread(target=cible, daemon=True) for _ in range(nombre)]
    for f in fils:
        f.start()
    fin = time.monotonic() + delai
    for f in fils:
        f.join(max(0.0, fin - time.monotonic()))
    bloques = [f.name for f in fils if f.is_alive()]
    assert not bloques, f"threads encore vivants après {delai} s : {bloques}"
    return erreurs


# ─── Base ─────────────────────────────────────────────────────────────────────
_FICHIER_BASE = _TMP / "test.db"
_MODELE_BASE = _TMP / "modele.db"


@pytest.fixture(scope="session")
def modele_base():
    """Base vide au schéma Alembic (upgrade head), créée une seule fois."""
    migrer(f"sqlite:///{_MODELE_BASE}")
    return _MODELE_BASE


@pytest.fixture(autouse=True)
def base(modele_base):
    """Base vide et fraîche pour chaque test : copie du modèle migré."""
    engine.dispose()
    shutil.copyfile(modele_base, _FICHIER_BASE)
    yield
    engine.dispose()


# ─── Clients ──────────────────────────────────────────────────────────────────
@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def code_invitation(monkeypatch):
    monkeypatch.setenv("CODE_INVITATION", CODE)
    return CODE


def inscrire(email, **profil):
    """Crée un compte via /register et renvoie (client connecté, user_id)."""
    c = TestClient(main.app)
    r = c.post("/register", data={"email": email, "mot_de_passe": MOT_DE_PASSE,
                                  "code_invitation": CODE, **profil},
               follow_redirects=False)
    assert r.status_code == 303, r.text
    db = SessionLocal()
    try:
        user_id = db.query(User).filter_by(email=email).one().id
    finally:
        db.close()
    return c, user_id


@pytest.fixture
def utilisateur(code_invitation):
    """Fabrique d'utilisateurs connectés : utilisateur("a@test.fr") -> (client, id)."""
    return inscrire
