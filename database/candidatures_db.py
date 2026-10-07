"""
database/candidatures_db.py
===========================
Couche d'accès aux candidatures EN BASE, par utilisateur.

Remplace charger_candidatures() / sauvegarder_candidatures() qui lisaient
le fichier JSON global. Même format de sortie (liste de dicts avec les mêmes
clés que l'ancien JSON) → le reste du code n'a pas à changer.

Mapping important : en base la clé métier s'appelle ref_offre ; côté app
elle est attendue sous le nom "id" (les routes font c["id"] == body.id).
"""

from database.connexion import SessionLocal
from database.dates import JOUR, en_texte, vers_utc
from database.insertion import inserer_ou_ignorer
from database.models import Candidature


# Colonnes simples de la table (hors id technique, user_id, et ref_offre)
_CHAMPS = [
    "titre", "entreprise", "lieu", "zone", "domaine", "lien", "source",
    "description", "score", "verdict", "eligible", "points_forts",
    "points_faibles", "resume_analyse", "lettre", "email_candidature",
    "objet_email", "statut", "raison_archivage", "date_trouvee", "date_candidature", "notes",
]
# Colonnes DateTime, échangées avec l'app sous forme "AAAA-MM-JJ"
_DATES = {"date_trouvee", "date_candidature"}


def _ecrire(c: Candidature, champ: str, valeur):
    setattr(c, champ, vers_utc(valeur) if champ in _DATES else valeur)


def _vers_dict(c: Candidature) -> dict:
    """Transforme une ligne de base en dict au format de l'ancien JSON."""
    d = {champ: getattr(c, champ) for champ in _CHAMPS}
    for champ in _DATES:
        d[champ] = en_texte(d[champ], JOUR)
    d["id"] = c.ref_offre          # la clé "id" attendue par l'app = ref_offre
    return d


def lire_candidatures(user_id: int, mode: str = "alternance") -> list[dict]:
    """Retourne toutes les candidatures d'un utilisateur pour un mode donné."""
    db = SessionLocal()
    try:
        lignes = (db.query(Candidature)
                    .filter_by(user_id=user_id, mode=mode)
                    .order_by(Candidature.score.desc())
                    .all())
        return [_vers_dict(c) for c in lignes]
    finally:
        db.close()


def lire_candidature(user_id: int, ref_offre: str, mode: str = "alternance") -> dict | None:
    """Retourne une candidature précise (par son id/ref_offre), ou None."""
    db = SessionLocal()
    try:
        c = db.query(Candidature).filter_by(user_id=user_id, ref_offre=ref_offre, mode=mode).first()
        return _vers_dict(c) if c else None
    finally:
        db.close()


def modifier_candidature(user_id: int, ref_offre: str, modifs: dict, mode: str = "alternance") -> bool:
    """
    Met à jour les champs d'une candidature précise.
    modifs = {"statut": "envoye", "lettre": "...", ...}
    Retourne True si trouvée et modifiée, False sinon.
    """
    db = SessionLocal()
    try:
        c = db.query(Candidature).filter_by(user_id=user_id, ref_offre=ref_offre, mode=mode).first()
        if not c:
            return False
        for champ, valeur in modifs.items():
            if champ in _CHAMPS:
                _ecrire(c, champ, valeur)
        db.commit()
        return True
    finally:
        db.close()

def ajouter_candidature(user_id: int, offre: dict, mode: str = "alternance") -> bool:
    """
    Ajoute UNE candidature en base si elle n'existe pas déjà (par ref_offre).
    Utilisé par la recherche pour sauvegarder au fur et à mesure de l'analyse.
    Idempotent : un doublon (même deux insertions simultanées) est ignoré.
    Retourne True si ajoutée, False si déjà présente.
    """
    ligne = {"user_id": user_id, "mode": mode, "ref_offre": offre.get("id", "")}
    for champ in _CHAMPS:
        if champ in offre:
            ligne[champ] = vers_utc(offre[champ]) if champ in _DATES else offre[champ]
    ligne["statut"] = offre.get("statut", "nouveau")
    db = SessionLocal()
    try:
        n = inserer_ou_ignorer(db, Candidature, [ligne], ["user_id", "mode", "ref_offre"])
        db.commit()
        return n == 1
    finally:
        db.close()


def lire_lettre_pdf(user_id: int, ref_offre: str, mode: str = "alternance") -> str:
    """Chemin relatif de la dernière lettre PDF de cette candidature ("" si aucune).
    Filtré par user_id : c'est la vérification du propriétaire."""
    db = SessionLocal()
    try:
        c = db.query(Candidature).filter_by(user_id=user_id, ref_offre=ref_offre, mode=mode).first()
        return (c.lettre_pdf or "") if c else ""
    finally:
        db.close()


def enregistrer_lettre_pdf(user_id: int, ref_offre: str, fichier: str, mode: str = "alternance") -> str | None:
    """Enregistre le PDF de la candidature. Retourne le chemin du PDF qu'il
    remplace ("" si aucun), ou None si la candidature n'existe pas."""
    db = SessionLocal()
    try:
        c = db.query(Candidature).filter_by(user_id=user_id, ref_offre=ref_offre, mode=mode).first()
        if not c:
            return None
        ancien = c.lettre_pdf or ""
        c.lettre_pdf = fichier
        db.commit()
        return ancien
    finally:
        db.close()
