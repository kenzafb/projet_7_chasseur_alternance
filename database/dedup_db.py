"""
database/dedup_db.py
====================
Dédoublonnage EN BASE, par utilisateur :
  - offres déjà vues par les recherches (table offres_vues, par mode) ;
  - adresses déjà contactées par les envois spontanés (table emails_contactes).

Remplace les anciens fichiers globaux data/offres_vues_{mode}.json et
data/emails_deja_envoyes.json, qui ne sont plus lus ni écrits. Une offre
vue par A reste proposée à B ; une adresse contactée par A ne bloque pas B.
"""

from database.connexion import SessionLocal
from database.insertion import inserer_ou_ignorer
from database.models import EmailContacte, OffreVue


def normaliser_email(adresse: str) -> str:
    return (adresse or "").strip().lower()


# ─── Offres vues ──────────────────────────────────────────────────────────────
def lire_offres_vues(user_id: int, mode: str) -> set[str]:
    """Références (ref_offre) des offres déjà vues par l'utilisateur dans ce mode."""
    db = SessionLocal()
    try:
        lignes = db.query(OffreVue.ref_offre).filter_by(user_id=user_id, mode=mode).all()
        return {ref for (ref,) in lignes}
    finally:
        db.close()


def marquer_offres_vues(user_id: int, mode: str, refs) -> int:
    """Marque des offres comme vues ; celles déjà marquées sont ignorées.
    Retourne le nombre de nouvelles lignes."""
    refs = sorted({r for r in refs if r})
    db = SessionLocal()
    try:
        n = inserer_ou_ignorer(
            db, OffreVue,
            [{"user_id": user_id, "mode": mode, "ref_offre": r} for r in refs],
            ["user_id", "mode", "ref_offre"])
        db.commit()
        return n
    finally:
        db.close()


# ─── Adresses contactées ──────────────────────────────────────────────────────
def lire_emails_contactes(user_id: int) -> set[str]:
    """Adresses déjà contactées par l'utilisateur (en minuscules)."""
    db = SessionLocal()
    try:
        lignes = db.query(EmailContacte.email).filter_by(user_id=user_id).all()
        return {email for (email,) in lignes}
    finally:
        db.close()


def ajouter_emails_contactes(user_id: int, adresses) -> int:
    """Enregistre des adresses contactées ; celles déjà connues sont ignorées.
    Retourne le nombre de nouvelles lignes."""
    adresses = sorted({normaliser_email(a) for a in adresses} - {""})
    db = SessionLocal()
    try:
        n = inserer_ou_ignorer(
            db, EmailContacte,
            [{"user_id": user_id, "email": a} for a in adresses],
            ["user_id", "email"])
        db.commit()
        return n
    finally:
        db.close()
