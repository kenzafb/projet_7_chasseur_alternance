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
from shared.erreurs import ErreurUtilisateur
from shared.stage import duree_semaines, lire_date, verifier_periode


def lire_profil(user_id: int, mode: str = "alternance") -> dict:
    """Retourne le profil de l'utilisateur (pour un mode) sous forme de dict."""
    db = SessionLocal()
    try:
        p = db.query(Profil).filter_by(user_id=user_id, mode=mode).first()
        return profil_vers_dict(p) if p else {}
    finally:
        db.close()


def profil_vers_dict(p: Profil) -> dict:
    """Une ligne de profils -> dict (format de lire_profil), avec le niveau
    d'études retenu pour l'éligibilité (niveau_profil, shared/eligibilite.py)."""
    from shared.eligibilite import niveau_du_profil
    d = _profil_vers_dict(p)
    d["niveau_profil"] = niveau_du_profil(d)
    d["manques_ia"] = manques_ia(d)
    return d


def manques_ia(profil: dict) -> list[str]:
    """Champs vides dont l'IA a besoin pour juger les offres et écrire les
    lettres, dans tous les modes (avertissement du profil)."""
    champs = (("compétences", bool(profil.get("competences"))),
              ("projets", any((x.get("nom") or x.get("description")) for x in profil.get("projets") or [])),
              ("expérience", bool((profil.get("experience") or "").strip())))
    return [libelle for libelle, rempli in champs if not rempli]


def _profil_vers_dict(p: Profil) -> dict:
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
        "analyse_auto": bool(p.analyse_auto),
        "competences": p.competences or [],
        "projets": p.projets or [],
        "recherche": p.recherche or {},
        "lettre_type": p.lettre_type or "",
        "email_objet": p.email_objet or "",
        "email_type": p.email_type or "",
        "pieces_jointes": p.pieces_jointes or [],
    }


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
        if "analyse_auto" in donnees:
            p.analyse_auto = donnees["analyse_auto"] in (True, "true", "1", 1, "on")
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


# Clé de lire_profil -> colonne de profils (copie entre modes, D117)
_COLONNE = {"email": "email_contact"}


def copier_sections(user_id: int, source: str, cible: str, sections, ecraser=()) -> dict:
    """Copie des sections du profil du mode source vers le mode cible du
    même utilisateur (shared.copie_profil), en une transaction. Refus
    (ErreurUtilisateur, rien n'est écrit) : section non copiable, copie
    impossible (balise de l'email), section remplie et différente dans le
    mode cible sans être dans ecraser. Pièces jointes : les références aux
    fichiers sont partagées, pas les fichiers dupliqués (D118). Retourne
    {copiees, fichiers_retires} : fichiers que le mode cible ne référence
    plus (à supprimer du disque s'ils ne servent plus à aucun mode)."""
    import copy
    from shared.copie_profil import apercu
    sections = list(dict.fromkeys(sections or []))
    if not sections:
        raise ErreurUtilisateur("Coche au moins une section à copier.")
    db = SessionLocal()
    try:
        # Les deux profils lus par user_id : jamais celui d'un autre utilisateur
        p_source = db.query(Profil).filter_by(user_id=user_id, mode=source).first()
        if not p_source:
            raise ErreurUtilisateur(f"Aucun profil enregistré en mode {source}.")
        p_cible = db.query(Profil).filter_by(user_id=user_id, mode=cible).first()
        d_cible = _profil_vers_dict(p_cible) if p_cible else {}
        plan = apercu(_profil_vers_dict(p_source), d_cible, sections, source, cible)
        if erreurs := [s for s in plan if s["erreur"]]:
            raise ErreurUtilisateur(f"{erreurs[0]['libelle']} : {erreurs[0]['erreur']}")
        a_confirmer = [s["libelle"] for s in plan if s["a_confirmer"] and s["cle"] not in set(ecraser or ())]
        if a_confirmer:
            raise ErreurUtilisateur("Déjà rempli dans ce mode, confirme l'écrasement : " + ", ".join(a_confirmer) + ".")
        if not p_cible:
            p_cible = Profil(user_id=user_id, mode=cible)
            db.add(p_cible)
        retires = []
        for s in plan:
            for ligne in s["champs"]:
                champ = ligne["champ"]
                if champ == "pieces_jointes":
                    gardes = {pj.get("fichier") for pj in ligne["copie"]}
                    retires += [pj.get("fichier", "") for pj in ligne["actuel"] if pj.get("fichier") not in gardes]
                setattr(p_cible, _COLONNE.get(champ, champ), copy.deepcopy(ligne["copie"]))
        db.commit()
        return {"copiees": [s["cle"] for s in plan], "fichiers_retires": [f for f in retires if f]}
    finally:
        db.close()
