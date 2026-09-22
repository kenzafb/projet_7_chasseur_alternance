"""
database/models.py
==================
Définition des 4 tables de l'app, en SQLAlchemy.
Tout ce qui était "Kenza en dur" ou "fichier JSON global" devient
une ligne rattachée à un utilisateur via user_id.

Les structures (listes, objets) sont stockées en JSON dans une colonne,
ce que SQLite gère nativement.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float,
    ForeignKey, DateTime, JSON, UniqueConstraint,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


# ─── Utilisateur (identité de connexion) ──────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id                = Column(Integer, primary_key=True)
    email             = Column(String(255), unique=True, nullable=False, index=True)
    mot_de_passe_hash = Column(String(255), nullable=False)
    cree_le           = Column(DateTime, default=datetime.utcnow)

    # Liens vers les données de l'utilisateur
    profil       = relationship("Profil", back_populates="user", uselist=False,
                                cascade="all, delete-orphan")
    candidatures = relationship("Candidature", back_populates="user",
                                cascade="all, delete-orphan")
    entreprises  = relationship("Entreprise", back_populates="user",
                                cascade="all, delete-orphan")


# ─── Profil (un par utilisateur — l'ancien profil.py) ─────────────────────────
class Profil(Base):
    __tablename__ = "profils"
    __table_args__ = (UniqueConstraint("user_id", "mode", name="uq_profil_user_mode"),)

    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    mode    = Column(String(20), default="alternance", index=True)   # alternance | job

    # Champs simples
    prenom           = Column(String(100), default="")
    nom              = Column(String(100), default="")
    email_contact    = Column(String(255), default="")
    telephone        = Column(String(50),  default="")
    ville            = Column(String(150), default="")
    linkedin         = Column(String(255), default="")
    github           = Column(String(255), default="")

    # Champs texte long
    formation        = Column(Text, default="")
    experience       = Column(Text, default="")
    langues          = Column(Text, default="")
    disponibilite    = Column(Text, default="")
    paragraphe_perso = Column(Text, default="")
    niveau_vise       = Column(Text, default="")   # diplôme préparé par le contrat (ex. "Bac+2 DEUST Info")
    formation_apporte = Column(Text, default="")   # compétences que la formation va apporter
    criteres_eviter   = Column(Text, default="")   # ce que la personne préfère éviter
    # Champs spécifiques au mode JOB
    niveau_etudes     = Column(Text, default="")   # niveau/diplôme déjà obtenu
    duree_souhaitee   = Column(Text, default="")   # ex. "1 à 2,5 mois"
    dispo_horaires    = Column(Text, default="")   # ex. "soir, week-end OK"
    mobilite          = Column(Text, default="")   # permis, zones accessibles
    types_jobs_ok     = Column(Text, default="")   # types de jobs acceptés
    types_jobs_eviter = Column(Text, default="")   # types de jobs refusés
    localisation_pref = Column(Text, default="")   # localisation préférée (job, optionnel)

    lettre_type      = Column(Text, default="")   # trame de lettre de motivation (l'IA ne fait que le paragraphe entreprise)
    email_type       = Column(Text, default="")   # trame d'email pour candidatures spontanées
    pieces_jointes   = Column(JSON, default=list)   # [{"nom": "...", "fichier": "chemin.pdf"}, ...]

    # Structures → stockées en JSON
    competences = Column(JSON, default=list)   # ["Linux...", "Python...", ...]
    projets     = Column(JSON, default=list)   # [{"nom":..., "url":..., "description":...}]
    recherche   = Column(JSON, default=dict)   # {"titre_poste":[...], "localisation":..., ...}

    user = relationship("User", back_populates="profil")


# ─── Candidature (l'ancien candidatures.json) ─────────────────────────────────
class Candidature(Base):
    __tablename__ = "candidatures"

    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mode    = Column(String(20), default="alternance", index=True)   # alternance | job

    # Identifiant métier (le hash md5 actuel) pour la déduplication
    ref_offre = Column(String(64), index=True)

    titre          = Column(String(300), default="")
    entreprise     = Column(String(300), default="")
    lieu           = Column(String(200), default="")
    zone           = Column(String(100), default="")
    domaine        = Column(String(100), default="")
    lien           = Column(Text, default="")
    source         = Column(String(100), default="")
    description    = Column(Text, default="")

    score          = Column(Integer, default=0)
    verdict        = Column(String(50), default="")
    eligible       = Column(Boolean, default=True)
    points_forts   = Column(JSON, default=list)
    points_faibles = Column(JSON, default=list)
    resume_analyse = Column(Text, default="")

    lettre            = Column(Text, default="")
    email_candidature = Column(String(255), default="")
    objet_email       = Column(String(300), default="")
    statut            = Column(String(50), default="nouveau")
    raison_archivage  = Column(String(40), default="")   # note_basse, ecole_cfa, hors_it, stage, public_specifique, manuel

    date_trouvee     = Column(String(20), default="")
    date_candidature = Column(String(20), default="")
    notes            = Column(Text, default="")
    user = relationship("User", back_populates="candidatures")


# ─── Entreprise (l'ancien entreprises_enrichies.json — spontanées) ────────────
class Entreprise(Base):
    __tablename__ = "entreprises"

    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    nom_commercial = Column(String(300), default="")
    ville          = Column(String(150), default="")
    code_postal    = Column(String(10),  default="")
    siren          = Column(String(20),  index=True, default="")
    site_web       = Column(Text, default="")
    secteur        = Column(String(200), default="")

    emails_trouves = Column(JSON, default=list)
    telephones     = Column(JSON, default=list)
    contact_rh     = Column(String(200), default="")

    traite         = Column(Boolean, default=False)
    mail_envoye    = Column(Boolean, default=False)
    mail_envoye_le = Column(String(30), default="")
    statut_suivi   = Column(String(30), default="envoye")   # envoye, reponse, entretien, refus, bounce ("à relancer" calculé via mail_envoye_le)
    extra          = Column(JSON, default=dict)   # champs FT/scraper non mappés (siret, dirigeant, mail_destinataires...)
    user = relationship("User", back_populates="entreprises")
