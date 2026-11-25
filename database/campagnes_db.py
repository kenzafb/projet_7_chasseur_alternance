"""
database/campagnes_db.py
========================
Campagnes automatiques (D213) : une ligne par lancement, avec son bilan par
mode et son journal, relus dans l'interface.
"""

from database.connexion import SessionLocal
from database.dates import JOUR_HEURE, en_texte, maintenant_affichage, maintenant_utc
from database.models import Campagne


def ouvrir(user_id: int) -> int:
    """Nouvelle campagne « en cours ». Celles restées en cours (processus tué)
    passent « interrompue » : l'appelant tient le verrou de la campagne."""
    db = SessionLocal()
    try:
        db.query(Campagne).filter_by(user_id=user_id, etat="en_cours").update(
            {"etat": "interrompue", "fin": maintenant_utc()})
        c = Campagne(user_id=user_id, debut=maintenant_utc(), etat="en_cours", bilan={}, journal="")
        db.add(c)
        db.commit()
        return c.id
    finally:
        db.close()


def noter(campagne_id: int, message: str):
    """Ajoute une ligne au journal, sans relire ce qui y est déjà."""
    ligne = f"{maintenant_affichage().strftime('%H:%M:%S')} {message}\n"
    db = SessionLocal()
    try:
        db.query(Campagne).filter_by(id=campagne_id).update(
            {Campagne.journal: Campagne.journal + ligne}, synchronize_session=False)
        db.commit()
    finally:
        db.close()


def enregistrer_bilan(campagne_id: int, bilan: dict, etat: str | None = None):
    """Bilan par mode ; etat : fin de la campagne."""
    valeurs = {"bilan": bilan}
    if etat:
        valeurs.update(etat=etat, fin=maintenant_utc())
    db = SessionLocal()
    try:
        db.query(Campagne).filter_by(id=campagne_id).update(valeurs)
        db.commit()
    finally:
        db.close()


def derniere(user_id: int) -> dict | None:
    db = SessionLocal()
    try:
        c = db.query(Campagne).filter_by(user_id=user_id).order_by(Campagne.id.desc()).first()
        return None if c is None else {
            "debut": en_texte(c.debut, JOUR_HEURE), "fin": en_texte(c.fin, JOUR_HEURE) if c.fin else "",
            "etat": c.etat, "bilan": c.bilan or {}, "journal": c.journal or ""}
    finally:
        db.close()
