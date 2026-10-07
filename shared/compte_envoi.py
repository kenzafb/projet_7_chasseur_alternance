"""
shared/compte_envoi.py
======================
Règles du compte d'envoi de chaque utilisateur : validation de la
configuration saisie, test de connexion, mail de test, et garde-fou appelé
avant tout envoi (compte configuré, vérifié, clé de chiffrement présente).

Aucun message produit ici ne contient le mot de passe.
"""

import re

from database import compte_envoi_db
from shared import config, smtp
from shared.chiffrement import ChiffrementIndisponible, raison_indisponible
from shared.erreurs import ErreurUtilisateur

_ADRESSE = re.compile(r"^[^@\s<>\"',;()\[\]]+@[^@\s<>\"',;()\[\]]+\.[^@\s<>\"',;()\[\]]+$")
LONGUEUR_MAX_MOT_DE_PASSE = 512

OBJET_MAIL_TEST = "Test du compte d'envoi"
CORPS_MAIL_TEST = (
    "Bonjour,\n\n"
    "Ce mail de test a été envoyé par le Chasseur avec ton compte d'envoi.\n"
    "Si tu le reçois, les candidatures spontanées partiront bien de cette adresse.\n")


class CompteEnvoiRequis(ErreurUtilisateur):
    """Pas de compte, ou compte jamais vérifié : refus avant tout envoi."""


def exiger_chiffrement():
    """Lève ChiffrementIndisponible (503) si CLE_CHIFFREMENT manque ou est invalide."""
    raison = raison_indisponible()
    if raison:
        raise ChiffrementIndisponible(raison)


def adresse_valide(adresse: str) -> bool:
    return len(adresse) <= 255 and bool(_ADRESSE.match(adresse))


def preparer(corps: dict, compte_existe: bool) -> tuple[dict, str | None]:
    """Valide et normalise la configuration envoyée par le front.
    Retourne (champs à enregistrer, mot de passe ou None pour garder l'actuel).
    Lève ErreurUtilisateur (400) avec un message lisible."""
    adresse = (corps.get("adresse") or "").strip()
    if not adresse_valide(adresse):
        raise ErreurUtilisateur("Adresse d'expédition invalide.")
    nom_affiche = " ".join((corps.get("nom_affiche") or "").split())[:150]
    mot_de_passe = corps.get("mot_de_passe") or None

    if corps.get("preset") == "gmail":
        champs = {**smtp.GMAIL, "identifiant": adresse}
        if mot_de_passe:
            # Google affiche le mot de passe d'application en 4 groupes de 4 lettres
            mot_de_passe = "".join(mot_de_passe.split()) or None
    else:
        port = corps.get("port")
        if port not in smtp.CHIFFREMENT_PAR_PORT:
            raise ErreurUtilisateur("Port refusé : seuls 465 (SSL) et 587 (STARTTLS) sont permis.")
        chiffrement = corps.get("chiffrement") or smtp.CHIFFREMENT_PAR_PORT[port]
        if chiffrement != smtp.CHIFFREMENT_PAR_PORT[port]:
            raise ErreurUtilisateur("Le port 465 s'utilise avec SSL, le port 587 avec STARTTLS.")
        serveur = smtp.normaliser_hote(corps.get("serveur"))
        smtp.verifier_hote(serveur)   # HoteInterdit (400) : local, privé, réservé, introuvable
        identifiant = (corps.get("identifiant") or "").strip() or adresse
        if len(identifiant) > 255:
            raise ErreurUtilisateur("Identifiant trop long.")
        champs = {"serveur": serveur, "port": port, "chiffrement": chiffrement,
                  "identifiant": identifiant}

    if mot_de_passe is None and not compte_existe:
        raise ErreurUtilisateur("Mot de passe requis pour configurer le compte d'envoi.")
    if mot_de_passe and len(mot_de_passe) > LONGUEUR_MAX_MOT_DE_PASSE:
        raise ErreurUtilisateur("Mot de passe trop long.")
    return {"preset": "gmail" if corps.get("preset") == "gmail" else "autre",
            "adresse": adresse, "nom_affiche": nom_affiche, **champs}, mot_de_passe


def _compte_complet(user_id: int) -> dict:
    exiger_chiffrement()
    compte = compte_envoi_db.compte_pour_envoi(user_id)
    if not compte:
        raise CompteEnvoiRequis(
            "Aucun compte d'envoi configuré : renseigne-le dans Profil, section "
            "Compte d'envoi, puis teste la connexion.")
    return compte


def exiger_compte_verifie(user_id: int) -> dict:
    """Compte complet (mot de passe déchiffré) d'un utilisateur prêt à envoyer.
    Lève ChiffrementIndisponible (503) ou CompteEnvoiRequis (400)."""
    compte = _compte_complet(user_id)
    if not compte["verifie"]:
        raise CompteEnvoiRequis(
            "Compte d'envoi non vérifié : lance « Tester la connexion » dans Profil, "
            "section Compte d'envoi, avant d'envoyer.")
    return compte


def _noter_echec(user_id: int, compte: dict, erreur: smtp.ErreurSmtp):
    """Identifiants refusés : le compte n'est plus considéré comme vérifié."""
    if erreur.categorie == smtp.AUTH:
        compte_envoi_db.marquer_verification(user_id, False)


def tester(user_id: int) -> dict:
    """Connexion et authentification puis déconnexion, aucun mail envoyé.
    Retourne {ok, message, compte} ; un échec SMTP n'est pas une exception."""
    compte = _compte_complet(user_id)
    try:
        smtp.tester_connexion(compte)
    except smtp.ErreurSmtp as e:
        _noter_echec(user_id, compte, e)
        return {"ok": False, "message": str(e), "compte": compte_envoi_db.lire_compte(user_id)}
    compte_envoi_db.marquer_verification(user_id, True, version=compte["_version"])
    return {"ok": True, "message": "Connexion réussie : le compte d'envoi est vérifié.",
            "compte": compte_envoi_db.lire_compte(user_id)}


def envoyer_mail_test(user_id: int, adresse_utilisateur: str, destinataire: str | None) -> dict:
    """Mail de test vers l'utilisateur lui-même : son adresse de connexion ou
    l'adresse d'expédition du compte, rien d'autre. Compte dans le plafond."""
    compte = _compte_complet(user_id)
    siennes = {a.strip().lower() for a in (adresse_utilisateur, compte["adresse"]) if a}
    dest = (destinataire or adresse_utilisateur or "").strip().lower()
    if dest not in siennes:
        raise ErreurUtilisateur(
            "Le mail de test ne peut partir que vers ta propre adresse "
            "(adresse de connexion ou adresse d'expédition).")
    jour = compte_envoi_db.reserver_envoi(user_id, config.PLAFOND_ENVOIS_JOUR)
    if jour is None:
        raise ErreurUtilisateur(
            f"Plafond de {config.PLAFOND_ENVOIS_JOUR} mails par jour atteint : réessaie demain.")
    message = smtp.construire_message(compte, [dest], OBJET_MAIL_TEST, CORPS_MAIL_TEST)
    try:
        smtp.envoyer_message(compte, message, [dest])
    except smtp.ErreurSmtp as e:
        compte_envoi_db.liberer_envoi(user_id, jour)
        _noter_echec(user_id, compte, e)
        return {"ok": False, "message": str(e), "compte": compte_envoi_db.lire_compte(user_id)}
    compte_envoi_db.marquer_verification(user_id, True, version=compte["_version"])
    return {"ok": True, "message": f"Mail de test envoyé à {dest}.",
            "compte": compte_envoi_db.lire_compte(user_id)}
