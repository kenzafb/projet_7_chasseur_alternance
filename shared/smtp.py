"""
shared/smtp.py
==============
Connexion SMTP avec le compte d'envoi d'un utilisateur.

  - verifier_hote refuse un serveur qui résout vers une adresse locale,
    privée, de lien local ou réservée : le serveur de l'application ne doit
    pas servir à sonder son propre réseau ;
  - la connexion vise l'adresse IP vérifiée (aucune seconde résolution DNS
    qui pourrait répondre autre chose entre-temps) ; le nom d'hôte sert
    toujours à TLS (SNI et vérification du certificat) ;
  - toujours chiffré : SSL direct sur 465, STARTTLS exigé sur 587 ;
  - toute erreur devient ErreurSmtp, dont le message ne contient jamais le
    mot de passe (il est construit ici, pas recopié de l'exception).

Un « compte » est un dict : serveur, port, chiffrement ("ssl" ou
"starttls"), identifiant, mot_de_passe, adresse, nom_affiche.
"""

import base64
import ipaddress
import re
import smtplib
import socket
import ssl
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from shared.erreurs import ErreurUtilisateur

# Préréglage Gmail (mot de passe d'application). Aucun autre préréglage :
# seuls ceux dont on est certain qu'ils acceptent encore l'authentification
# par mot de passe sont proposés.
GMAIL = {"serveur": "smtp.gmail.com", "port": 465, "chiffrement": "ssl"}

# Seuls ports permis, et le chiffrement qui va avec
CHIFFREMENT_PAR_PORT = {465: "ssl", 587: "starttls"}

DELAI_S = 20   # délai de connexion et de réponse du serveur, en secondes

# Catégories d'ErreurSmtp
AUTH = "auth"         # identifiants refusés : le compte doit être revérifié
SERVEUR = "serveur"   # serveur injoignable, TLS, expéditeur refusé... : inutile d'insister
MESSAGE = "message"   # ce message-là est refusé (destinataire...) : on peut passer au suivant

_NOM_HOTE = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")


class HoteInterdit(ErreurUtilisateur):
    """Serveur SMTP refusé (adresse locale ou privée, introuvable...)."""


class ErreurSmtp(Exception):
    """Échec SMTP. Le message est sûr : il ne contient jamais le mot de passe."""

    def __init__(self, categorie: str, message: str):
        self.categorie = categorie
        super().__init__(message)


# ─── Serveur autorisé ? ───────────────────────────────────────────────────────
def _ip_interdite(ip) -> bool:
    if ip.version == 6 and ip.ipv4_mapped:   # ::ffff:127.0.0.1
        ip = ip.ipv4_mapped
    return (ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified or not ip.is_global)


def normaliser_hote(hote: str) -> str:
    return (hote or "").strip().lower().rstrip(".").removeprefix("[").removesuffix("]")


def verifier_hote(hote: str) -> list[str]:
    """Adresses IP du serveur, toutes publiques. Lève HoteInterdit si le nom
    est invalide, introuvable, ou si l'une de ses adresses est locale,
    privée, de lien local ou réservée."""
    hote = normaliser_hote(hote)
    refus = f"Serveur SMTP refusé ({hote or 'vide'}) : adresse locale, privée ou réservée."
    if not hote or hote == "localhost" or hote.endswith(".localhost"):
        raise HoteInterdit(refus)
    try:
        litterale = ipaddress.ip_address(hote.split("%")[0])
    except ValueError:
        litterale = None
    if litterale is not None:
        if _ip_interdite(litterale):
            raise HoteInterdit(refus)
        return [str(litterale)]
    if not _NOM_HOTE.match(hote):
        raise HoteInterdit(f"Nom de serveur SMTP invalide : {hote}")
    try:
        infos = socket.getaddrinfo(hote, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        raise HoteInterdit(f"Serveur SMTP introuvable : {hote}") from None
    ips = list(dict.fromkeys(info[4][0] for info in infos))
    if not ips:
        raise HoteInterdit(f"Serveur SMTP introuvable : {hote}")
    for ip in ips:
        if _ip_interdite(ipaddress.ip_address(ip.split("%")[0])):
            raise HoteInterdit(refus)
    return ips


# ─── Connexion ────────────────────────────────────────────────────────────────
class _Epingle:
    """Ouvre la socket vers l'IP vérifiée ; self._host (nom d'hôte, posé par
    connect) reste celui que TLS vérifie."""
    ip_cible = None

    def _get_socket(self, host, port, timeout):
        return super()._get_socket(self.ip_cible or host, port, timeout)


class _SMTPEpingle(_Epingle, smtplib.SMTP):
    pass


class _SMTPSSLEpingle(_Epingle, smtplib.SMTP_SSL):
    pass


def _nouvelle_connexion(chiffrement: str):
    """Connexion SMTP non encore ouverte (remplacée par un faux dans les tests)."""
    if chiffrement == "ssl":
        return _SMTPSSLEpingle(timeout=DELAI_S, context=ssl.create_default_context())
    return _SMTPEpingle(timeout=DELAI_S)


def _sans_secret(texte, compte: dict) -> str:
    """Texte renvoyé par le serveur, nettoyé du mot de passe sous toutes ses
    formes vues sur le fil (en clair, base64 seul ou avec l'identifiant)."""
    if isinstance(texte, bytes):
        texte = texte.decode("utf-8", "replace")
    texte = str(texte or "")
    mdp = compte.get("mot_de_passe") or ""
    if mdp:
        ident = compte.get("identifiant") or ""
        for forme in (mdp,
                      base64.b64encode(mdp.encode()).decode(),
                      base64.b64encode(f"\0{ident}\0{mdp}".encode()).decode()):
            texte = texte.replace(forme, "***")
    return " ".join(texte.split())[:200]


def _executer(compte: dict, action=None):
    """Connexion, chiffrement, authentification, action(connexion) puis
    déconnexion. Toute erreur devient ErreurSmtp."""
    serveur, port = normaliser_hote(compte["serveur"]), int(compte["port"])
    ou = f"{serveur}:{port}"
    try:
        ips = verifier_hote(serveur)
    except HoteInterdit as e:
        raise ErreurSmtp(SERVEUR, str(e)) from None

    conn = _nouvelle_connexion(compte["chiffrement"])
    conn.ip_cible = ips[0]
    etape = "connexion"
    try:
        conn.connect(serveur, port)
        if compte["chiffrement"] == "starttls":
            conn.ehlo()
            if not conn.has_extn("starttls"):
                raise ErreurSmtp(SERVEUR, f"Le serveur {ou} ne propose pas STARTTLS : connexion "
                                          "abandonnée pour ne pas envoyer le mot de passe en clair.")
            conn.starttls(context=ssl.create_default_context())
            conn.ehlo()
        etape = "authentification"
        conn.login(compte["identifiant"], compte["mot_de_passe"])
        etape = "envoi"
        return action(conn) if action else None
    except ErreurSmtp:
        raise
    except smtplib.SMTPAuthenticationError:
        raise ErreurSmtp(AUTH, f"Authentification refusée par {serveur} : identifiant ou mot de passe "
                               "incorrect. Pour Gmail, il faut un mot de passe d'application "
                               "(validation en deux étapes activée).") from None
    except smtplib.SMTPRecipientsRefused as e:
        refusees = ", ".join(sorted(e.recipients))
        raise ErreurSmtp(MESSAGE, f"Adresse(s) refusée(s) par le serveur : {refusees}") from None
    except smtplib.SMTPSenderRefused as e:
        raise ErreurSmtp(SERVEUR, f"Le serveur refuse l'expéditeur (code {e.smtp_code}) : vérifie "
                                  "l'adresse d'expédition, ou le quota d'envoi du compte est atteint.") from None
    except smtplib.SMTPNotSupportedError:
        raise ErreurSmtp(SERVEUR, f"Le serveur {ou} n'accepte pas l'authentification "
                                  "par mot de passe.") from None
    except smtplib.SMTPResponseException as e:
        if etape == "envoi":
            raise ErreurSmtp(MESSAGE, f"Message refusé par le serveur (code {e.smtp_code}) : "
                                      f"{_sans_secret(e.smtp_error, compte)}") from None
        raise ErreurSmtp(SERVEUR, f"Réponse inattendue de {ou} pendant l'étape {etape} "
                                  f"(code {e.smtp_code}).") from None
    except ssl.SSLError:
        raise ErreurSmtp(SERVEUR, f"Échec de la connexion chiffrée avec {ou} (certificat refusé "
                                  "ou chiffrement inadapté au port).") from None
    except Exception as e:   # OSError, délai dépassé, connexion coupée...
        raise ErreurSmtp(SERVEUR, f"Serveur {ou} injoignable ou connexion interrompue pendant "
                                  f"l'étape {etape} ({type(e).__name__}).") from None
    finally:
        try:
            conn.quit()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass


def tester_connexion(compte: dict) -> None:
    """Connexion et authentification puis déconnexion, sans rien envoyer."""
    _executer(compte)


def envoyer_message(compte: dict, message: EmailMessage, destinataires: list[str]) -> dict:
    """Envoie `message` ; retourne les destinataires refusés quand d'autres
    ont été acceptés ({adresse: (code, texte)}), sinon {}."""
    return _executer(compte, lambda conn: conn.send_message(
        message, from_addr=compte["adresse"], to_addrs=destinataires)) or {}


# ─── Message ──────────────────────────────────────────────────────────────────
def _une_ligne(texte: str) -> str:
    """Pas de retour à la ligne dans un en-tête (injection d'en-têtes)."""
    return " ".join((texte or "").split())


def construire_message(compte: dict, destinataires: list[str], objet: str, corps: str,
                       pieces=()) -> EmailMessage:
    """Mail texte, expédié par le compte ; pieces : [(nom_fichier, octets PDF)]."""
    adresse = compte["adresse"]
    msg = EmailMessage()
    msg["From"] = Address(display_name=_une_ligne(compte.get("nom_affiche")), addr_spec=adresse)
    msg["To"] = ", ".join(destinataires)
    msg["Subject"] = _une_ligne(objet)
    msg["Date"] = formatdate(usegmt=True)
    msg["Message-ID"] = make_msgid(domain=adresse.rsplit("@", 1)[-1])   # domaine explicite : pas de DNS
    msg.set_content(corps)
    for nom, contenu in pieces:
        msg.add_attachment(contenu, maintype="application", subtype="pdf", filename=nom)
    return msg
