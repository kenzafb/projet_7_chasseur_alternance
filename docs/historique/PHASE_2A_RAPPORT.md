# Phase 2a : base neuve et versionnée, rapport

Branche `phase-2a-base`, créée depuis `refonte-multiuser` (aa7a73f), 8 octobre 2026. Non poussée, non fusionnée.
Règles suivies : `data/chasseur.db` seulement lue (sqlite3 `file:...?mode=ro`), aucune base créée dans `data/`, `.env` ni lu ni modifié (sa date, 00:22, précède la création de la branche, 00:32), aucun appel à FT, LBA, INSEE, Mistral ou SMTP. Seul accès réseau : `pip install alembic` dans `venv/`. Listing de `data/` (noms, tailles, dates) identique avant et après, aucun `__pycache__` dans `data/`.

## 1. Commits

| Commit | Thème |
|---|---|
| 4e8be8a | Schéma cible dans `models.py`, dates DateTime, conversions dans la couche d'accès (`database/dates.py`) |
| ff26ef8 | Alembic : `alembic.ini`, `env.py`, migration `0001`, `database/schema.migrer()`, `creer_tables()` supprimé, tests sur base migrée |
| ae2b6dc | `scripts/importer_ancienne_base.py`, pièces jointes relatives à `UPLOADS_DIR`, `database/migration.py` supprimé |
| 47b435e | Tests du schéma et du script d'import |
| a809a30 | Alembic refuse une base non gérée (l'ancienne) ; `DATABASE_URL=` vide vaut absente |
| e17dbfb | README |
| (dernier) | Ce rapport |

## 2. Schéma final

Source unique : `database/models.py`. Migration unique : `alembic/versions/0001_schema_initial.py` (autogénérée puis relue). Convention de nommage des contraintes (`pk_`, `fk_`, `uq_`, `ix_`) indispensable au mode batch SQLite. Toutes les dates en `DateTime(timezone=True)`, valeurs UTC ; défauts `datetime.now(timezone.utc)`. Toute clé `user_id` : `ForeignKey("users.id", ondelete="CASCADE")`, NOT NULL ; côté ORM `cascade="all, delete-orphan", passive_deletes=True`. `PRAGMA foreign_keys=ON` posé à chaque connexion SQLite par `database.connexion.creer_moteur()` (app, Alembic, script), sinon SQLite ignore la cascade.

| Table | Colonnes | Contraintes, index |
|---|---|---|
| `users` | id, email, mot_de_passe_hash, cree_le (DateTime) | `ix_users_email` UNIQUE. Relations en liste : `profils`, `candidatures`, `entreprises`, `offres_vues`, `emails_contactes` |
| `profils` | id, user_id, mode (NOT NULL, défaut `alternance` côté Python et serveur), prenom, nom, email_contact, telephone, ville, linkedin, github, formation, experience, langues, disponibilite, paragraphe_perso, niveau_vise, formation_apporte, criteres_eviter, niveau_etudes, duree_souhaitee, dispo_horaires, mobilite, types_jobs_ok, types_jobs_eviter, localisation_pref, lettre_type, email_type, pieces_jointes (JSON), competences (JSON), projets (JSON), recherche (JSON) | `uq_profils_user_id_mode` (user_id, mode). Index isolé sur mode retiré (absent de la vraie base, couvert par l'unique) |
| `candidatures` | id, user_id, mode (NOT NULL, défaut), ref_offre (NOT NULL), titre, entreprise, lieu, zone, domaine, lien, source, description, score, verdict, eligible, points_forts (JSON), points_faibles (JSON), resume_analyse, lettre, email_candidature, objet_email, statut, raison_archivage, date_trouvee (DateTime), date_candidature (DateTime), notes | `uq_candidatures_user_id_mode_ref_offre`, `ix_candidatures_user_id_mode`. Index isolés user_id et ref_offre retirés (redondants) |
| `entreprises` | id, user_id, **mode** (NOT NULL, défaut `alternance`, nouveau), nom_commercial, ville, code_postal, siren, site_web, secteur, emails_trouves (JSON), telephones (JSON), contact_rh, traite, mail_envoye, mail_envoye_le (DateTime), statut_suivi, extra (JSON) | `ix_entreprises_user_id`, `ix_entreprises_siren` |
| `offres_vues` (nouvelle) | id, user_id, mode (NOT NULL, défaut), ref_offre (NOT NULL), vue_le (DateTime, défaut maintenant) | `uq_offres_vues_user_id_mode_ref_offre`. Non branchée (2b) |
| `emails_contactes` (nouvelle) | id, user_id, email (NOT NULL), contacte_le (DateTime, défaut maintenant) | `uq_emails_contactes_user_id_email`. Non branchée (2b) |

Toutes les colonnes de la vraie base sont reprises (comparaison avec `sqlite_master` lu en lecture seule) ; aucune colonne du code n'en manque.

**Code adapté, et seulement là où le schéma l'impose**
- `database/dates.py` : `vers_utc` (chaîne ISO ou datetime naïf lu en heure locale, vide donne None) et `en_texte` (UTC relu, naïf sous SQLite, rendu en heure locale). `candidatures_db` convertit `date_trouvee` et `date_candidature` (format `AAAA-MM-JJ`), `entreprises_db` convertit `mail_envoye_le` (`AAAA-MM-JJ HH:MM`) : l'API et l'envoyeur échangent toujours les mêmes chaînes, aucun changement côté front ni scrapers. Le calcul « à relancer » compare des datetimes UTC au lieu de parser une chaîne.
- Relation `User.profil` (un seul) devenue `User.profils` : aucun code ne l'utilisait.
- Pièces jointes : `shared.config.chemin_piece_jointe(relatif)` résout sous `UPLOADS_DIR` et renvoie None si le chemin en sort. Utilisée par l'upload (stocke `user_N/fichier.pdf`), la suppression, le téléchargement (`main.py`) et l'envoyeur. Le dossier courant n'intervient plus.

## 3. Alembic

`alembic.ini` à la racine (`prepend_sys_path = %(here)s`, pas d'URL). `alembic/env.py` : URL = `config.attributes["database_url"]` si fourni (script, tests), sinon `DATABASE_URL` de `shared/config.py` ; `render_as_batch=True` ; moteur via `creer_moteur`. Garde-fou : une base qui a des tables sans `alembic_version` (l'ancienne `chasseur.db`) lève une erreur explicite sans être touchée. `database/schema.migrer(url)` équivaut à `alembic upgrade head` depuis Python. Vérifié en ligne de commande : `upgrade head` depuis un autre dossier avec `-c`, deuxième `upgrade head` sans effet, `alembic check` « No new upgrade operations detected », `alembic current` = `0001 (head)`. `alembic==1.20.0` ajouté à `requirements.txt` (Mako 1.4.3 tiré par dépendance, non épinglé).

## 4. Script d'import

`scripts/importer_ancienne_base.py --source <ancienne.db> --cible <fichier ou URL> [--dry-run]`. Ordre : source lue via `mode=ro` ; refus si source et cible sont le même fichier (`os.path.samefile`, liens symboliques compris) ; refus si la cible contient des users (comptage en lecture seule, sans créer le fichier) ; lecture des users 1, 3, 4 et de leurs profils (colonnes communes aux deux schémas, JSON décodé) ; conversion des pièces jointes (`data/uploads/user_1/x.pdf` devient `user_1/x.pdf`), contrôle d'existence sous `UPLOADS_DIR` et d'extension, fichiers jamais modifiés ; hors `--dry-run` : `upgrade head` sur la cible, nouveau contrôle « aucun user » dans la transaction, insertion des users (id, email, hash identiques, `cree_le` naïf relu comme UTC) puis des profils, en une transaction ; résumé. Les ids de profils ne sont pas conservés (renumérotés). Code retour 1 et message `REFUS : ...` sur la sortie d'erreur en cas de refus.

## 5. Essai à blanc sur la vraie base

`venv/bin/python scripts/importer_ancienne_base.py --source data/chasseur.db --cible data/chasseur_v2.db --dry-run`, code retour 0, `data/chasseur_v2.db` non créé, `data/chasseur.db` inchangé (date 22/09, taille 7061504) :

```
── ESSAI À BLANC (--dry-run) : rien n'a été écrit ──
Source : /home/kenza/Bureau/chasseur_alternance/data/chasseur.db (lecture seule)
Cible  : sqlite:////home/kenza/Bureau/chasseur_alternance/data/chasseur_v2.db

Users à importer : 3
  1  kenzafilbou@gmail.com
  3  tzeinab375@gmail.com
  4  aichafofana019@gmail.com

Profils à importer : 4
  user 1  alternance Kenza Filali-Bouami
  user 1  job        Kenza Filali-Bouami
  user 3  alternance Zeinab Toure
  user 4  alternance Aïcha Fofana

Pièces jointes trouvées : 5
  user 1 alternance : Lettre_Recommandation_Kenza_Filali-Bouami → user_1/Lettre_Recommandation_Kenza_Filali-Bouami_Lettre_Recommandation_Kenza_Filali-Bou
  user 1 alternance : Programme_DEUST_IOSI → user_1/Programme_DEUST_IOSI_Programme_DEUST_IOSI.pdf
  user 1 alternance : CV_Kenza_Filali-Bouami → user_1/CV_Kenza_Filali-Bouami.pdf
  user 1 job : CV Kenza Filali-Bouami → user_1/CV_Kenza_Filali-Bouami.pdf
  user 3 alternance : Alternance Assistante copropriété  → user_3/Alternance_Assistante_coproprie_te__.pdf
Pièces jointes manquantes : 0
Pièces jointes sans extension : 1
  user 1 alternance : Lettre_Recommandation_Kenza_Filali-Bouami → user_1/Lettre_Recommandation_Kenza_Filali-Bouami_Lettre_Recommandation_Kenza_Filali-Bou
(chemins relatifs à UPLOADS_DIR = /home/kenza/Bureau/chasseur_alternance/data/uploads)
```

À retenir : 3 users, 4 profils, 5 pièces jointes présentes, aucune manquante, une sans extension (la lettre de recommandation, nom tronqué à l'upload d'origine ; importée telle quelle, servie et jointe aux mails comme avant). `data/uploads/user_2/lettre.pdf` reste sur le disque, orphelin.

## 6. Tests

`pytest` : **87 passed** en 9 s (71 avant, tous toujours verts), aucun avertissement ; le filtre `utcnow` de `pytest.ini` est retiré, devenu inutile. `conftest.py` : la base de test est créée une fois par session par `upgrade head` dans un fichier modèle, recopiée avant chaque test ; `config.UPLOADS_DIR` redirigé vers `tmp_path`.

| Fichier | Couvre |
|---|---|
| `test_schema.py` (8) | `upgrade head` sur base vide puis `alembic check` sans différence, tables attendues ; `downgrade base` puis `upgrade` ; unicité (user_id, mode, ref_offre) avec même ref permise dans l'autre mode ; DELETE SQL direct d'un user qui vide profils, candidatures, entreprises ; `PRAGMA foreign_keys` actif ; mode par défaut des entreprises ; dates relues en texte et type DATETIME en base, statut `a_relancer` ; refus d'Alembic sur une base non gérée, laissée intacte |
| `test_import_ancienne_base.py` (8) | Fausse ancienne base dans `tmp_path` au DDL réel exact (`tests/donnees/ancien_schema.sql`, extrait en lecture seule de `data/chasseur.db` ; un test le recompare à la vraie base en lecture seule, ignoré si elle est absente), 4 users à hash argon2, profils alternance et job : user 2 exclu, ids et hashs identiques, profils des deux modes avec JSON et colonnes tardives, ni candidatures ni entreprises ; pièces trouvées, manquante, sans extension ; connexion avec l'ancien mot de passe sur la nouvelle base (et refus pour le user 2) ; pièce jointe importée servie par `/api/profil/piece` ; refus cible non vide (empreinte inchangée, CLI code 1) ; refus source = cible, y compris par lien symbolique ; `--dry-run` : cible absente non créée, cible existante et source inchangées octet pour octet ; import dans une cible neuve qui est migrée |

Autres vérifications : `compileall -q -x 'venv/|data/' .` sans erreur ; `uvicorn main:app --port 5099` sur une base temporaire migrée : `/login` 200, `/` 303, `/api/logs` 401.

## 7. Import réel : à lancer par l'humain

```bash
cd /home/kenza/Bureau/chasseur_alternance
source venv/bin/activate
pip install -r requirements.txt          # alembic (déjà présent dans venv/)
cp data/chasseur.db data/chasseur_avant_phase2.db   # sauvegarde, par prudence
python scripts/importer_ancienne_base.py --source data/chasseur.db --cible data/chasseur_v2.db --dry-run
python scripts/importer_ancienne_base.py --source data/chasseur.db --cible data/chasseur_v2.db
```

Ligne à mettre dans `.env` (puis relancer l'app) :

```
DATABASE_URL=sqlite:////home/kenza/Bureau/chasseur_alternance/data/chasseur_v2.db
```

Sans cette ligne, l'app vise toujours `data/chasseur.db`, que le nouveau code ne sait plus lire (dates en texte, pas de colonne `entreprises.mode`) ; `alembic upgrade head` refuserait alors de la toucher.

## 8. Points à valider

1. **Perte assumée des données de travail** : sur la nouvelle base, le user 1 repart sans ses 382 candidatures ni ses 6860 entreprises (418 mails envoyés), le user 3 sans ses 60 candidatures et 998 entreprises. Conforme à la consigne ; l'ancienne base reste lisible pour s'y référer.
2. **Dédoublonnage pendant l'intervalle 2a/2b** : `offres_vues` et `emails_contactes` sont vides et non branchées, donc le code continue de lire et d'écrire `data/offres_vues_{mode}.json` et `data/emails_deja_envoyes.json` (globaux). Les adresses déjà contactées restent donc protégées tant que ces fichiers existent ; ne pas les supprimer avant la 2b.
3. **Fuseau** : les chaînes de date reçues du code sont lues en heure locale du serveur et stockées en UTC ; une date seule (`date_trouvee`) devient minuit local. Si le serveur change de fuseau, l'affichage d'une date seule peut décaler d'un jour. Alternative : stocker ces deux colonnes en `Date`.
4. **Unicité stricte des candidatures** : deux offres de même `ref_offre` dans une même liste passée à `remplacer_candidatures`, ou deux insertions concurrentes via `ajouter_candidature`, lèvent désormais une `IntegrityError` au lieu de créer un doublon silencieux. À traiter en 2b (upsert ou capture de l'erreur).
5. `entreprises.mode` existe mais le code ne le renseigne ni ne le filtre : toutes les entreprises sont `alternance` jusqu'à la 2b.
6. Ids des users insérés explicitement : sans effet sous SQLite ; sur PostgreSQL il faudrait recaler la séquence (`setval`) après import.
7. Fichier sans extension (lettre de recommandation du user 1) : le renommer et mettre à jour le profil, ou le laisser (il fonctionne).
8. Noms de contraintes changés par la convention (`uq_profil_user_mode` devient `uq_profils_user_id_mode`) : sans effet sur le code.
9. Le DDL de référence des tests est figé dans `tests/donnees/ancien_schema.sql` (la vraie base est gitignorée) ; le garde-fou ne tourne que là où `data/chasseur.db` existe.
10. Ensuite : relire la branche, la fusionner dans `refonte-multiuser`, lancer l'import réel (section 7), pousser.
