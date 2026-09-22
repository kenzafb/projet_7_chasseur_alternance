"""
database/profil_db.py
=====================
Lecture du profil d'un utilisateur depuis la base, au format dict
(mêmes clés que l'ancien shared/profil.py PROFIL).
Permet à l'analyseur et au générateur de fonctionner pour n'importe
quel utilisateur, pas seulement Kenza.
"""

from database.connexion import SessionLocal
from database.models import Profil


def lire_profil(user_id: int, mode: str = "alternance") -> dict:
    """Retourne le profil de l'utilisateur (pour un mode) sous forme de dict."""
    db = SessionLocal()
    try:
        p = db.query(Profil).filter_by(user_id=user_id, mode=mode).first()
        if not p:
            return {}
        return {
            "prenom": p.prenom or "",
            "nom": p.nom or "",
            "email": p.email_contact or "",
            "telephone": p.telephone or "",
            "ville": p.ville or "",
            "linkedin": p.linkedin or "",
            "github": p.github or "",
            "formation": p.formation or "",
            "experience": p.experience or "",
            "langues": p.langues or "",
            "disponibilite": p.disponibilite or "",
            "paragraphe_perso": p.paragraphe_perso or "",
            "niveau_vise": p.niveau_vise or "",
            "formation_apporte": p.formation_apporte or "",
            "criteres_eviter": p.criteres_eviter or "",
            "niveau_etudes": p.niveau_etudes or "",
            "duree_souhaitee": p.duree_souhaitee or "",
            "dispo_horaires": p.dispo_horaires or "",
            "mobilite": p.mobilite or "",
            "types_jobs_ok": p.types_jobs_ok or "",
            "types_jobs_eviter": p.types_jobs_eviter or "",
            "localisation_pref": p.localisation_pref or "",
            "competences": p.competences or [],
            "projets": p.projets or [],
            "recherche": p.recherche or {},
            "lettre_type": p.lettre_type or "",
            "email_type": p.email_type or "",
            "pieces_jointes": p.pieces_jointes or [],
        }
    finally:
        db.close()


def sauvegarder_profil(user_id: int, donnees: dict, mode: str = "alternance") -> bool:
    """
    Met à jour le profil d'un utilisateur depuis un dict de données
    (envoyé par le formulaire). Ne touche que les champs fournis.
    """
    # Champs texte simples
    champs_texte = [
        "prenom", "nom", "email_contact", "telephone", "ville", "linkedin",
        "github", "formation", "experience", "langues", "disponibilite",
        "paragraphe_perso", "niveau_vise", "formation_apporte", "criteres_eviter",
        "niveau_etudes", "duree_souhaitee", "dispo_horaires", "mobilite",
        "types_jobs_ok", "types_jobs_eviter", "localisation_pref",
        "lettre_type", "email_type",
    ]
    # Champs structurés (listes/dicts stockés en JSON)
    champs_json = ["competences", "projets", "recherche"]

    db = SessionLocal()
    try:
        p = db.query(Profil).filter_by(user_id=user_id, mode=mode).first()
        if not p:
            # Profil de ce mode pas encore créé → on le crée à la volée
            p = Profil(user_id=user_id, mode=mode)
            db.add(p)
        for champ in champs_texte:
            if champ in donnees:
                setattr(p, champ, donnees[champ] or "")
        for champ in champs_json:
            if champ in donnees:
                setattr(p, champ, donnees[champ])
        db.commit()
        return True
    finally:
        db.close()


def ajouter_piece_jointe(user_id: int, nom: str, chemin_fichier: str, mode: str = "alternance") -> bool:
    """Ajoute (ou remplace par nom) une pièce jointe dans le profil."""
    db = SessionLocal()
    try:
        p = db.query(Profil).filter_by(user_id=user_id, mode=mode).first()
        if not p:
            p = Profil(user_id=user_id, mode=mode)
            db.add(p)
        pieces = list(p.pieces_jointes or [])
        # Remplace si une pièce du même nom existe déjà, sinon ajoute
        pieces = [pj for pj in pieces if pj.get("nom") != nom]
        pieces.append({"nom": nom, "fichier": chemin_fichier})
        p.pieces_jointes = pieces
        db.commit()
        return True
    finally:
        db.close()


def supprimer_piece_jointe(user_id: int, nom: str, mode: str = "alternance") -> bool:
    """Retire une pièce jointe du profil (par son nom)."""
    db = SessionLocal()
    try:
        p = db.query(Profil).filter_by(user_id=user_id, mode=mode).first()
        if not p:
            return False
        p.pieces_jointes = [pj for pj in (p.pieces_jointes or []) if pj.get("nom") != nom]
        db.commit()
        return True
    finally:
        db.close()
