"""
database/models.py
==================
Schéma de la base, seule source de vérité : les migrations Alembic
(dossier alembic/) sont générées à partir de ce fichier, et `alembic check`
vérifie qu'elles le reflètent exactement.

Toutes les données sont rattachées à un utilisateur via user_id, avec
suppression en cascade : supprimer un user supprime ses profils,
candidatures, entreprises, offres vues, emails contactés, compte d'envoi
et compteurs d'envoi.

Dates : colonnes DateTime(timezone=True), valeurs en UTC. SQLite ne stocke
pas le fuseau et relit des dates naïves : database/dates.py les considère
comme UTC. Les structures (listes, objets) sont en colonnes JSON.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Date,
    ForeignKey, DateTime, JSON, UniqueConstraint, Index, MetaData, false, text,
)
from sqlalchemy.orm import relationship, declarative_base

# Noms de contraintes explicites : indispensables aux migrations SQLite
# (mode batch d'Alembic) et stables d'un SGBD à l'autre.
CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=CONVENTION))


def maintenant_utc() -> datetime:
    return datetime.now(timezone.utc)


def _user_id():
    """Clé étrangère vers users, supprimée avec l'utilisateur."""
    return Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def _relation_vers_user(retour: str):
    return relationship("User", back_populates=retour)


def _relation_depuis_user(classe: str):
    # passive_deletes : la base supprime les lignes (ON DELETE CASCADE)
    return relationship(classe, back_populates="user",
                        cascade="all, delete-orphan", passive_deletes=True)


# ─── Utilisateur (identité de connexion) ──────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id                = Column(Integer, primary_key=True)
    email             = Column(String(255), unique=True, nullable=False, index=True)
    mot_de_passe_hash = Column(String(255), nullable=False)
    cree_le           = Column(DateTime(timezone=True), default=maintenant_utc)

    # Liens vers les données de l'utilisateur (un profil par mode)
    profils          = _relation_depuis_user("Profil")
    candidatures     = _relation_depuis_user("Candidature")
    entreprises      = _relation_depuis_user("Entreprise")
    offres_vues      = _relation_depuis_user("OffreVue")
    emails_contactes = _relation_depuis_user("EmailContacte")
    compte_envoi     = relationship("CompteEnvoi", back_populates="user", uselist=False,
                                    cascade="all, delete-orphan", passive_deletes=True)
    compteurs_envoi  = _relation_depuis_user("CompteurEnvoi")


# ─── Profil (un par utilisateur et par mode) ──────────────────────────────────
class Profil(Base):
    __tablename__ = "profils"
    __table_args__ = (UniqueConstraint("user_id", "mode"),)

    id      = Column(Integer, primary_key=True)
    user_id = _user_id()
    mode    = Column(String(20), nullable=False, default="alternance", server_default="alternance")   # alternance | job

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
    niveau_vise       = Column(Text, default="")   # diplôme préparé par le contrat (ex. "Bac+2")
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
    email_objet      = Column(String(300), default="")   # objet du mail de candidature spontanée
    email_type       = Column(Text, default="")   # trame d'email pour candidatures spontanées
    # [{"nom": "...", "fichier": "user_1/cv.pdf"}, ...] : chemin relatif à UPLOADS_DIR
    pieces_jointes   = Column(JSON, default=list)

    # Structures → stockées en JSON
    competences = Column(JSON, default=list)   # ["Linux...", "Python...", ...]
    projets     = Column(JSON, default=list)   # [{"nom":..., "url":..., "description":...}]
    recherche   = Column(JSON, default=dict)   # {"titre_poste":[...], "localisation":..., ...}

    user = _relation_vers_user("profils")


# ─── Candidature (offres FT / LBA analysées) ──────────────────────────────────
class Candidature(Base):
    __tablename__ = "candidatures"
    __table_args__ = (
        UniqueConstraint("user_id", "mode", "ref_offre"),
        Index("ix_candidatures_user_id_mode", "user_id", "mode"),
    )

    id      = Column(Integer, primary_key=True)
    user_id = _user_id()
    mode    = Column(String(20), nullable=False, default="alternance", server_default="alternance")   # alternance | job

    # Identifiant métier (hash md5 de l'offre) pour la déduplication
    ref_offre = Column(String(64), nullable=False)

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
    raison_archivage  = Column(String(40), default="")   # note_basse, ecole_cfa, hors_domaine, stage, public_specifique, manuel

    # Dernière lettre PDF générée : chemin relatif à LETTRES_PDF_DIR
    # ("user_<id>/lettre_<hex>.pdf"), servie par /api/lettre_pdf/<ref_offre>
    lettre_pdf        = Column(String(255), default="")

    date_trouvee     = Column(DateTime(timezone=True))
    date_candidature = Column(DateTime(timezone=True))
    notes            = Column(Text, default="")

    user = _relation_vers_user("candidatures")


# ─── Entreprise (candidatures spontanées) ─────────────────────────────────────
class Entreprise(Base):
    __tablename__ = "entreprises"

    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mode    = Column(String(20), nullable=False, default="alternance", server_default="alternance")   # alternance | job

    nom_commercial = Column(String(300), default="")
    ville          = Column(String(150), default="")
    code_postal    = Column(String(10),  default="")
    siren          = Column(String(20),  index=True, default="")
    site_web       = Column(Text, default="")
    secteur        = Column(String(200), default="")
    # Sources qui ont trouvé l'entreprise : ["sirene"], ["lba"] (entreprise à
    # fort potentiel de La Bonne Alternance) ou les deux, dans l'ordre où
    # elles l'ont trouvée. Aucune priorité de l'une sur l'autre (D44).
    sources        = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))

    emails_trouves = Column(JSON, default=list)
    telephones     = Column(JSON, default=list)
    contact_rh     = Column(String(200), default="")

    traite         = Column(Boolean, default=False)
    mail_envoye    = Column(Boolean, default=False)
    mail_envoye_le = Column(DateTime(timezone=True))
    statut_suivi   = Column(String(30), default="envoye")   # envoye, reponse, entretien, refus, bounce ("à relancer" calculé via mail_envoye_le)
    extra          = Column(JSON, default=dict)   # champs FT/scraper non mappés (siret, dirigeant, mail_destinataires...)

    user = _relation_vers_user("entreprises")


# ─── Offres déjà vues (dédup des recherches, par utilisateur et par mode) ─────
class OffreVue(Base):
    __tablename__ = "offres_vues"
    __table_args__ = (UniqueConstraint("user_id", "mode", "ref_offre"),)

    id        = Column(Integer, primary_key=True)
    user_id   = _user_id()
    mode      = Column(String(20), nullable=False, default="alternance", server_default="alternance")
    ref_offre = Column(String(64), nullable=False)
    vue_le    = Column(DateTime(timezone=True), default=maintenant_utc)

    user = _relation_vers_user("offres_vues")


# ─── Emails déjà contactés (dédup des envois spontanés, par user et par mode) ─
class EmailContacte(Base):
    __tablename__ = "emails_contactes"
    __table_args__ = (UniqueConstraint("user_id", "mode", "email"),)

    id          = Column(Integer, primary_key=True)
    user_id     = _user_id()
    mode        = Column(String(20), nullable=False, default="alternance", server_default="alternance")
    email       = Column(String(255), nullable=False)
    contacte_le = Column(DateTime(timezone=True), default=maintenant_utc)

    user = _relation_vers_user("emails_contactes")


# ─── Compte d'envoi (SMTP de l'utilisateur, un seul par utilisateur) ──────────
class CompteEnvoi(Base):
    __tablename__ = "comptes_envoi"

    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    adresse      = Column(String(255), nullable=False)        # adresse d'expédition (From)
    nom_affiche  = Column(String(150), default="")            # nom affiché devant l'adresse
    preset       = Column(String(20), nullable=False)         # gmail | autre
    serveur      = Column(String(255), nullable=False)        # hôte SMTP
    port         = Column(Integer, nullable=False)            # 465 | 587
    chiffrement  = Column(String(10), nullable=False)         # ssl | starttls
    identifiant  = Column(String(255), nullable=False)
    # Chiffré par Fernet (shared/chiffrement.py, clé CLE_CHIFFREMENT) ;
    # jamais renvoyé par l'API ni écrit dans un log
    mot_de_passe_chiffre = Column(Text, nullable=False)
    # Mode test : chaque candidature spontanée part vers l'adresse d'expédition,
    # le vrai destinataire dans l'objet ; rien n'est enregistré comme contacté.
    # Vrai à la création d'un compte (compte_envoi_db), faux pour les comptes
    # antérieurs à la migration 0006
    mode_test    = Column(Boolean, nullable=False, default=False, server_default=false())
    # Dernière connexion et authentification réussies ; remis à NULL quand
    # les paramètres de connexion changent ou que l'authentification échoue
    verifie_le   = Column(DateTime(timezone=True))
    modifie_le   = Column(DateTime(timezone=True), default=maintenant_utc)

    user = relationship("User", back_populates="compte_envoi")


# ─── Mails envoyés par utilisateur et par jour (plafond quotidien) ────────────
class CompteurEnvoi(Base):
    __tablename__ = "compteurs_envoi"
    __table_args__ = (UniqueConstraint("user_id", "jour"),)

    id      = Column(Integer, primary_key=True)
    user_id = _user_id()
    jour    = Column(Date, nullable=False)   # jour calendaire dans FUSEAU_AFFICHAGE
    nombre  = Column(Integer, nullable=False, default=0)

    user = _relation_vers_user("compteurs_envoi")
