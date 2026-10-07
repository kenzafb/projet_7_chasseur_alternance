-- Schéma exact de l'ancienne base data/chasseur.db, lu en lecture seule
-- (sqlite3 "file:data/chasseur.db?mode=ro" .schema) le 2026-10-08.
CREATE TABLE users (
	id INTEGER NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	mot_de_passe_hash VARCHAR(255) NOT NULL, 
	cree_le DATETIME, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE TABLE candidatures (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	ref_offre VARCHAR(64), 
	titre VARCHAR(300), 
	entreprise VARCHAR(300), 
	lieu VARCHAR(200), 
	zone VARCHAR(100), 
	domaine VARCHAR(100), 
	lien TEXT, 
	source VARCHAR(100), 
	description TEXT, 
	score INTEGER, 
	verdict VARCHAR(50), 
	eligible BOOLEAN, 
	points_forts JSON, 
	points_faibles JSON, 
	resume_analyse TEXT, 
	lettre TEXT, 
	email_candidature VARCHAR(255), 
	objet_email VARCHAR(300), 
	statut VARCHAR(50), 
	date_trouvee VARCHAR(20), 
	date_candidature VARCHAR(20), 
	notes TEXT, raison_archivage VARCHAR(40) DEFAULT '', mode VARCHAR(20) DEFAULT 'alternance', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE INDEX ix_candidatures_ref_offre ON candidatures (ref_offre);
CREATE INDEX ix_candidatures_user_id ON candidatures (user_id);
CREATE TABLE entreprises (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	nom_commercial VARCHAR(300), 
	ville VARCHAR(150), 
	code_postal VARCHAR(10), 
	siren VARCHAR(20), 
	site_web TEXT, 
	secteur VARCHAR(200), 
	emails_trouves JSON, 
	telephones JSON, 
	contact_rh VARCHAR(200), 
	traite BOOLEAN, 
	mail_envoye BOOLEAN, 
	mail_envoye_le VARCHAR(30), 
	extra JSON, statut_suivi VARCHAR(30) DEFAULT 'envoye', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE INDEX ix_entreprises_user_id ON entreprises (user_id);
CREATE INDEX ix_entreprises_siren ON entreprises (siren);
CREATE TABLE profils (
                id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                mode VARCHAR(20) DEFAULT 'alternance',
                prenom VARCHAR(100),
                nom VARCHAR(100),
                email_contact VARCHAR(255),
                telephone VARCHAR(50),
                ville VARCHAR(150),
                linkedin VARCHAR(255),
                github VARCHAR(255),
                formation TEXT,
                experience TEXT,
                langues TEXT,
                disponibilite TEXT,
                paragraphe_perso TEXT,
                competences JSON,
                projets JSON,
                recherche JSON,
                lettre_type TEXT DEFAULT '',
                email_type TEXT DEFAULT '',
                pieces_jointes JSON DEFAULT '[]',
                niveau_vise TEXT DEFAULT '',
                formation_apporte TEXT DEFAULT '',
                criteres_eviter TEXT DEFAULT '', niveau_etudes TEXT DEFAULT '', duree_souhaitee TEXT DEFAULT '', dispo_horaires TEXT DEFAULT '', mobilite TEXT DEFAULT '', types_jobs_ok TEXT DEFAULT '', types_jobs_eviter TEXT DEFAULT '', localisation_pref TEXT DEFAULT '',
                PRIMARY KEY (id),
                UNIQUE (user_id, mode),
                FOREIGN KEY(user_id) REFERENCES users (id)
            );
