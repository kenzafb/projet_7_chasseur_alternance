"""
database/profil_db.py
=====================
Lecture du profil d'un utilisateur depuis la base, au format dict
(mêmes clés que l'ancien shared/profil.py PROFIL).
Permet à l'analyseur et au générateur de fonctionner pour n'importe
quel utilisateur.
"""

from database.connexion import SessionLocal
from database.models import Profil
from shared.criteres import normaliser_recherche
from shared.stage import duree_semaines, lire_date, verifier_periode


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
            # Mode stage : dates en AAAA-MM-JJ (vides si absentes), durée calculée
            "date_debut": p.date_debut.isoformat() if p.date_debut else "",
            "date_fin": p.date_fin.isoformat() if p.date_fin else "",
            "duree_semaines": duree_semaines(p.date_debut, p.date_fin),
            "etablissement": p.etablissement or "",
            "missions": p.missions or "",
            "portfolio": p.portfolio or "",
            "competences": p.competences or [],
            "projets": p.projets or [],
            "recherche": p.recherche or {},
            "lettre_type": p.lettre_type or "",
            "email_objet": p.email_objet or "",
            "email_type": p.email_type or "",
            "pieces_jointes": p.pieces_jointes or [],
        }
    finally:
        db.close()


def sauvegarder_profil(user_id: int, donnees: dict, mode: str = "alternance") -> bool:
    """
    Met à jour le profil d'un utilisateur depuis un dict de données
    (envoyé par le formulaire). Ne touche que les champs fournis.
    Date de stage illisible, fin avant le début, balise inconnue dans
    l'objet ou la trame du mail : ErreurUtilisateur (400), rien n'est écrit.
    """
    from shared.balises_mail import verifier_balises
    # Champs texte simples
    champs_texte = [
        "prenom", "nom", "email_contact", "telephone", "ville", "linkedin",
        "github", "formation", "experience", "langues", "disponibilite",
        "paragraphe_perso", "niveau_vise", "formation_apporte", "criteres_eviter",
        "niveau_etudes", "duree_souhaitee", "dispo_horaires", "mobilite",
        "types_jobs_ok", "types_jobs_eviter", "localisation_pref",
        "lettre_type", "email_objet", "email_type",
        "etablissement", "missions", "portfolio",
    ]
    # Champs structurés (listes/dicts stockés en JSON)
    champs_json = ["competences", "projets", "recherche"]

    dates = {champ: lire_date(donnees[champ], libelle) for champ, libelle in
             (("date_debut", "Date de début du stage"), ("date_fin", "Date de fin du stage")) if champ in donnees}
    for champ in ("email_objet", "email_type"):
        if champ in donnees:
            verifier_balises(donnees[champ] or "", mode)

    db = SessionLocal()
    try:
        p = db.query(Profil).filter_by(user_id=user_id, mode=mode).first()
        if not p:
            # Profil de ce mode pas encore créé → on le crée à la volée
            p = Profil(user_id=user_id, mode=mode)
            db.add(p)
        # Le formulaire envoie "email" (clé de lire_profil), la colonne est email_contact
        if "email" in donnees and "email_contact" not in donnees:
            donnees = {**donnees, "email_contact": donnees["email"]}
        if "recherche" in donnees:
            donnees = {**donnees, "recherche": normaliser_recherche(donnees["recherche"])}
        for champ in champs_texte:
            if champ in donnees:
                setattr(p, champ, donnees[champ] or "")
        for champ in champs_json:
            if champ in donnees:
                setattr(p, champ, donnees[champ])
        for champ, valeur in dates.items():
            setattr(p, champ, valeur)
        verifier_periode(p.date_debut, p.date_fin)   # avant l'écriture : rien n'est enregistré
        db.commit()
        return True
    finally:
        db.close()


def ajouter_piece_jointe(user_id: int, nom: str, chemin_fichier: str, mode: str = "alternance") -> list[str]:
    """Ajoute (ou remplace par nom) une pièce jointe dans le profil.
    Retourne les fichiers des pièces remplacées (à supprimer du disque s'ils
    ne sont plus référencés, cf. fichiers_references)."""
    db = SessionLocal()
    try:
        p = db.query(Profil).filter_by(user_id=user_id, mode=mode).first()
        if not p:
            p = Profil(user_id=user_id, mode=mode)
            db.add(p)
        pieces = list(p.pieces_jointes or [])
        # Remplace si une pièce du même nom existe déjà, sinon ajoute
        remplacees = [pj.get("fichier", "") for pj in pieces if pj.get("nom") == nom]
        pieces = [pj for pj in pieces if pj.get("nom") != nom]
        pieces.append({"nom": nom, "fichier": chemin_fichier})
        p.pieces_jointes = pieces
        db.commit()
        return [f for f in remplacees if f and f != chemin_fichier]
    finally:
        db.close()


def supprimer_piece_jointe(user_id: int, nom: str, mode: str = "alternance") -> list[str]:
    """Retire une pièce jointe du profil (par son nom). Retourne les fichiers
    retirés (à supprimer du disque s'ils ne sont plus référencés)."""
    db = SessionLocal()
    try:
        p = db.query(Profil).filter_by(user_id=user_id, mode=mode).first()
        if not p:
            return []
        pieces = p.pieces_jointes or []
        retirees = [pj.get("fichier", "") for pj in pieces if pj.get("nom") == nom]
        p.pieces_jointes = [pj for pj in pieces if pj.get("nom") != nom]
        db.commit()
        return [f for f in retirees if f]
    finally:
        db.close()


def fichiers_references(user_id: int) -> set[str]:
    """Fichiers de pièces jointes encore référencés par un profil de
    l'utilisateur, tous modes confondus (un même fichier peut servir aux deux)."""
    db = SessionLocal()
    try:
        profils = db.query(Profil).filter_by(user_id=user_id).all()
        return {pj.get("fichier", "") for p in profils for pj in (p.pieces_jointes or [])} - {""}
    finally:
        db.close()
