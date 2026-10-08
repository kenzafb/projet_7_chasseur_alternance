"""
database/compte_envoi_db.py
===========================
Compte d'envoi (SMTP) de chaque utilisateur, et compteur quotidien de mails.

Le mot de passe est chiffré avant d'entrer en base (shared/chiffrement.py).
lire_compte() ne le renvoie jamais : seul compte_pour_envoi(), réservé à
l'envoi et au test de connexion, le déchiffre.
"""

from database.connexion import SessionLocal
from database.dates import JOUR_HEURE, en_texte, maintenant_affichage, maintenant_utc
from database.insertion import insert_du_dialecte
from database.models import CompteEnvoi, CompteurEnvoi
from shared.chiffrement import chiffrer, dechiffrer

# Changer l'un de ces champs (ou le mot de passe) oblige à revérifier le compte
_CHAMPS_CONNEXION = ("adresse", "serveur", "port", "chiffrement", "identifiant")


def _public(c: CompteEnvoi) -> dict:
    """Vue renvoyée au front : tout sauf le mot de passe."""
    return {
        "preset":      c.preset,
        "adresse":     c.adresse,
        "nom_affiche": c.nom_affiche or "",
        "serveur":     c.serveur,
        "port":        c.port,
        "chiffrement": c.chiffrement,
        "identifiant": c.identifiant,
        "mot_de_passe_configure": bool(c.mot_de_passe_chiffre),
        "verifie":     c.verifie_le is not None,
        "verifie_le":  en_texte(c.verifie_le, JOUR_HEURE),
        "mode_test":   bool(c.mode_test),
    }


def lire_compte(user_id: int) -> dict | None:
    """Compte de l'utilisateur sans mot de passe, ou None."""
    db = SessionLocal()
    try:
        c = db.query(CompteEnvoi).filter_by(user_id=user_id).first()
        return _public(c) if c else None
    finally:
        db.close()


def compte_pour_envoi(user_id: int) -> dict | None:
    """Compte avec le mot de passe déchiffré, pour se connecter au serveur.
    Ne jamais renvoyer ce dict au front ni l'écrire dans un log.
    "_version" permet de ne marquer vérifié que la configuration testée."""
    db = SessionLocal()
    try:
        c = db.query(CompteEnvoi).filter_by(user_id=user_id).first()
        if not c:
            return None
        compte = _public(c)
        compte["mot_de_passe"] = dechiffrer(c.mot_de_passe_chiffre)
        compte["_version"] = c.modifie_le
        return compte
    finally:
        db.close()


def enregistrer_compte(user_id: int, donnees: dict, mot_de_passe: str | None) -> dict:
    """Crée ou remplace le compte. `donnees` est déjà validé (shared/compte_envoi.py).
    mot_de_passe None : on garde celui en base (il doit exister).
    La vérification est perdue si un paramètre de connexion change."""
    db = SessionLocal()
    try:
        c = db.query(CompteEnvoi).filter_by(user_id=user_id).first()
        nouveau = c is None
        if nouveau:
            # Mode test activé à la création (décision D7) : rien ne part vers
            # une entreprise avant que l'utilisateur le décoche
            c = CompteEnvoi(user_id=user_id, mode_test=True)
            db.add(c)
        change = nouveau or mot_de_passe is not None or any(
            getattr(c, champ) != donnees[champ] for champ in _CHAMPS_CONNEXION)
        for champ in ("preset", "nom_affiche", *_CHAMPS_CONNEXION):
            setattr(c, champ, donnees[champ])
        if mot_de_passe is not None:
            c.mot_de_passe_chiffre = chiffrer(mot_de_passe)
        if change:
            c.verifie_le = None
        c.modifie_le = maintenant_utc()
        db.commit()
        return _public(c)
    finally:
        db.close()


def supprimer_compte(user_id: int) -> bool:
    db = SessionLocal()
    try:
        n = db.query(CompteEnvoi).filter_by(user_id=user_id).delete()
        db.commit()
        return n > 0
    finally:
        db.close()


def definir_mode_test(user_id: int, actif: bool) -> dict | None:
    """Active ou coupe le mode test (aucun effet sur la vérification).
    Retourne le compte public, ou None s'il n'existe pas."""
    db = SessionLocal()
    try:
        c = db.query(CompteEnvoi).filter_by(user_id=user_id).first()
        if not c:
            return None
        c.mode_test = bool(actif)
        db.commit()
        return _public(c)
    finally:
        db.close()


def marquer_verification(user_id: int, reussie: bool, version=None):
    """Connexion réussie : verifie_le = maintenant. Authentification refusée :
    verifie_le = NULL. Si `version` est donné, rien ne change quand le
    compte a été modifié depuis sa lecture (on ne valide que ce qu'on a testé)."""
    db = SessionLocal()
    try:
        q = db.query(CompteEnvoi).filter_by(user_id=user_id)
        if version is not None:
            q = q.filter(CompteEnvoi.modifie_le == version)
        q.update({"verifie_le": maintenant_utc() if reussie else None})
        db.commit()
    finally:
        db.close()


# ─── Plafond quotidien ────────────────────────────────────────────────────────
def _aujourdhui():
    return maintenant_affichage().date()


def envois_du_jour(user_id: int) -> int:
    db = SessionLocal()
    try:
        c = db.query(CompteurEnvoi).filter_by(user_id=user_id, jour=_aujourdhui()).first()
        return c.nombre if c else 0
    finally:
        db.close()


def reserver_envoi(user_id: int, plafond: int):
    """Compte un mail de plus pour aujourd'hui si le plafond le permet, en
    une seule requête (deux envois simultanés ne peuvent pas le dépasser).
    Retourne le jour réservé (à passer à liberer_envoi), ou None si le
    plafond est atteint."""
    if plafond <= 0:
        return None
    jour = _aujourdhui()
    db = SessionLocal()
    try:
        insert = insert_du_dialecte(db)
        requete = insert(CompteurEnvoi).values(user_id=user_id, jour=jour, nombre=1)
        requete = requete.on_conflict_do_update(
            index_elements=["user_id", "jour"],
            set_={"nombre": CompteurEnvoi.nombre + 1},
            where=CompteurEnvoi.nombre < plafond)
        reservee = (db.execute(requete).rowcount or 0) > 0
        db.commit()
        return jour if reservee else None
    finally:
        db.close()


def liberer_envoi(user_id: int, jour):
    """Rend une réservation : le mail n'est pas parti (refusé par le serveur)."""
    db = SessionLocal()
    try:
        (db.query(CompteurEnvoi)
           .filter(CompteurEnvoi.user_id == user_id, CompteurEnvoi.jour == jour,
                   CompteurEnvoi.nombre > 0)
           .update({"nombre": CompteurEnvoi.nombre - 1}))
        db.commit()
    finally:
        db.close()
