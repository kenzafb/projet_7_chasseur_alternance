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
from database.models import Candidature


# Colonnes simples de la table (hors id technique, user_id, et ref_offre)
_CHAMPS = [
    "titre", "entreprise", "lieu", "zone", "domaine", "lien", "source",
    "description", "score", "verdict", "eligible", "points_forts",
    "points_faibles", "resume_analyse", "lettre", "email_candidature",
    "objet_email", "statut", "raison_archivage", "date_trouvee", "date_candidature", "notes",
]


def _vers_dict(c: Candidature) -> dict:
    """Transforme une ligne de base en dict au format de l'ancien JSON."""
    d = {champ: getattr(c, champ) for champ in _CHAMPS}
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


def remplacer_candidatures(user_id: int, candidatures: list[dict], mode: str = "alternance"):
    """
    Écrit la liste complète des candidatures d'un utilisateur.
    Stratégie simple et sûre : on met à jour l'existant par ref_offre,
    on insère les nouvelles. (On ne supprime rien automatiquement.)
    """
    db = SessionLocal()
    try:
        existantes = {
            c.ref_offre: c
            for c in db.query(Candidature).filter_by(user_id=user_id, mode=mode).all()
        }
        for offre in candidatures:
            ref = offre.get("id", "")
            c = existantes.get(ref)
            if c is None:
                c = Candidature(user_id=user_id, ref_offre=ref, mode=mode)
                db.add(c)
            for champ in _CHAMPS:
                if champ in offre:
                    setattr(c, champ, offre[champ])
        db.commit()
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
                setattr(c, champ, valeur)
        db.commit()
        return True
    finally:
        db.close()

def ajouter_candidature(user_id: int, offre: dict, mode: str = "alternance") -> bool:
    """
    Ajoute UNE candidature en base si elle n'existe pas déjà (par ref_offre).
    Utilisé par la recherche FT pour sauvegarder au fur et à mesure de l'analyse.
    Retourne True si ajoutée, False si déjà présente.
    """
    ref = offre.get("id", "")
    db = SessionLocal()
    try:
        existe = (db.query(Candidature)
                    .filter_by(user_id=user_id, ref_offre=ref, mode=mode)
                    .first())
        if existe:
            return False
        c = Candidature(user_id=user_id, ref_offre=ref, mode=mode)
        for champ in _CHAMPS:
            if champ in offre:
                setattr(c, champ, offre[champ])
        c.statut = offre.get("statut", "nouveau")
        db.add(c)
        db.commit()
        return True
    finally:
        db.close()
