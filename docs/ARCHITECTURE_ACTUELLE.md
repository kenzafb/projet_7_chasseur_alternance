# Architecture actuelle : chasseur_alternance

Analyse en lecture seule, branche `refonte-multiuser`, commit `5b9a3ef`, arbre propre, 7 octobre 2026.
Convention : **[V]** = vérifié dans le code, la base ou les fichiers ; **[S]** = supposition non vérifiée.
Aucun secret n'est reproduit ici. Seuls les noms de variables d'environnement sont cités.

---

## 1. Arborescence commentée

```
chasseur_alternance/
├── main.py                     Point d'entrée ACTUEL : app FastAPI (uvicorn, port 5002), toutes les routes /api, threads de pipeline
├── app.py                      ANCIEN point d'entrée Flask (mono-utilisateur, lit les JSON). Mort mais toujours présent
├── telegram_bot.py             Bot Telegram : Gemini (Vertex AI) traduit le langage naturel en appels HTTP vers l'API locale
├── requirements.txt            Dépendances déclarées (obsolètes, cf. §9)
├── README.md                   Doc encore écrite pour la version Flask/JSON
├── .env / .env.example         Secrets (non lus ici) / modèle obsolète
├── .gitignore                  Exclut .env, data/, assets/, lettres_pdf/, shared/profil.py, venv...
│
├── auth/
│   ├── routes.py               /login, /logout, /register (formulaires HTML, session cookie)
│   └── securite.py             Hash mot de passe (PasswordHelper de fastapi-users), utilisateur_courant(), mode_courant()
│
├── database/
│   ├── connexion.py            Moteur SQLAlchemy, SQLite data/chasseur.db par défaut, SessionLocal
│   ├── models.py               4 tables : users, profils, candidatures, entreprises
│   ├── profil_db.py            CRUD profil par (user_id, mode) + pièces jointes
│   ├── candidatures_db.py      CRUD candidatures par (user_id, mode), mapping ref_offre <-> "id"
│   ├── entreprises_db.py       CRUD entreprises (spontanées) par user_id, stats, suivi
│   └── migration.py            Script one-shot : profil.py + JSON -> base, crée le compte user 1
│
├── france_travail/             Pipeline "offres" (malgré le nom, contient aussi LBA)
│   ├── main.py                 lancer_recherche() : FT -> analyse IA -> callback d'écriture ; + vieux helpers JSON
│   ├── scraper.py              API France Travail (OAuth2, pagination, filtre IDF), fichiers offres_vues_{mode}.json
│   ├── scraper_lba.py          API La Bonne Alternance (codes ROME, rayon 60 km autour de Paris)
│   ├── analyseur.py            Scoring Mistral (2 prompts : alternance / job), règles d'archivage auto
│   ├── generateur.py           Lettre de motivation : trame fixe + 2 blocs générés par Mistral
│   └── pdf_generator.py        Lettre -> PDF via WeasyPrint, dans lettres_pdf/
│
├── spontanees/                 Pipeline "candidatures spontanées"
│   ├── fetch_entreprises.py    API INSEE Sirene : entreprises par NAF x département -> table entreprises
│   ├── scraper_emails.py       Recherche du site (DuckDuckGo), scraping pages contact, extraction emails via Mistral
│   ├── envoyeur.py             Envoi SMTP Gmail avec pièces jointes, dédup, pauses aléatoires ; CLI + cron
│   ├── fetch_envoyes_gmail.py  One-shot IMAP : liste des destinataires déjà contactés -> emails_deja_envoyes.json
│   └── export_excel.py         Export Excel de suivi, lit encore le JSON (désynchronisé de la base)
│
├── shared/
│   ├── modes.py                Définition des modes "alternance" et "job" (sources, params FT, limite de lot)
│   ├── domaines.py             Domaines "maison" (informatique, immobilier) -> grand domaine FT, ROME LBA, NAF
│   ├── profil.py               Profil personnel historique (gitignoré), utilisé seulement par migration.py
│   └── profil.example.py       Modèle de profil.py
│
├── templates/
│   ├── base.html               Page SPA actuelle (FastAPI), bascule de mode, inclut les partials
│   ├── partials/*.html         offres, candidatures, spontanees, spontanees_suivi, profil (sections par mode)
│   ├── login.html / register.html  Pages d'auth
│   └── index.html              Ancienne page Flask (morte sous FastAPI)
│
├── static/
│   ├── js/                     Front actuel en modules ES : api.js, app.js, offres.js, candidatures.js, profil.js, spontanees.js, suivi.js
│   ├── css/                    base.css, components.css, pages.css
│   └── app.js                  Ancien front Flask monolithique (mort)
│
└── data/                       (gitignoré)
    ├── chasseur.db             Base SQLite réelle (4 users, 442 candidatures, 7858 entreprises)
    ├── chasseur.db.backup-avant-mode-profil   Sauvegarde avant ajout de la colonne mode
    ├── backup_avant_migration/ Copie des JSON + profil.py avant migration
    ├── candidatures.json       Ancien stockage des offres (290 entrées, figé)
    ├── entreprises_raw.json / entreprises_enrichies.json   Anciens stockages entreprises (identiques octet pour octet)
    ├── offres_vues.json        Ancien fichier de dédup FT (n'est plus lu)
    ├── offres_vues_alternance.json / offres_vues_job.json   Dédup FT actuelle (globale, pas par utilisateur)
    ├── emails_deja_envoyes.json  Dédup globale des destinataires (1085 adresses)
    ├── cron_envoi.log          Log de l'envoyeur lancé par cron
    └── uploads/user_1/         Pièces jointes du profil (CV, reco, plaquette)
```

Dossiers ignorés et présents : `assets/` (anciens PDF codés en dur), `lettres_pdf/`, `venv/` (Python 3.13).

---

## 2. Point d'entrée et flux principal

**Lancement [V]** : `uvicorn main:app --reload --port 5002` (ou `python main.py`). Le bot se lance à part : `python telegram_bot.py`. L'envoyeur peut aussi tourner en CLI (`python -m spontanees.envoyeur --limite 50 --user 1`) ; une ligne cron existe mais est **commentée** [V].

**Requête HTTP [V]** : `SessionMiddleware` (cookie signé, 14 jours) ; chaque route appelle `utilisateur_courant(request)` qui relit `users` en base, puis `mode_courant(request)` qui lit `session["mode"]` (défaut `alternance`). Pas de `Depends`, la vérification est copiée dans chaque route.

**Flux A : recherche d'offres (`POST /api/recherche`) [V]**
1. Capture `user_id`, `mode`, profil du mode, puis lance un thread.
2. `france_travail.main.lancer_recherche` -> `scraper.chercher_offres` : token OAuth2 FT, requêtes `offres/search` région 11 (IDF) avec `natureContrat=E2` (alternance) ou `typeContrat=CDD,MIS,SAI&qualification=0` (job), par grand domaine en alternance ou tous domaines en job, pagination jusqu'à 3000, filtre départements IDF, id = md5 de l'id FT, exclusion des ids présents dans `offres_vues_{mode}.json`.
3. `analyseur.analyser_offres` : un appel Mistral par offre, pause 10 s, règles d'archivage auto, callback `ajouter_candidature(user_id, offre, mode)` qui écrit en base au fil de l'eau.
4. Si le mode a la source `lba` (alternance seulement) : `scraper_lba.chercher_offres_lba(romes)`, dédup contre la base, analyse Mistral **en ligne dans main.py** (copie des règles d'archivage), écriture en base.
5. Le front interroge `GET /api/statut_recherche` puis `GET /api/candidatures`.

**Flux B : traitement d'une offre [V]** : `POST /api/analyser` (ré-analyse), `/api/generer_lettre` (Mistral + trame), `/api/sauvegarder`, `/api/maj_statut`, `/api/archiver`, `/api/offre/archivage`, `/api/telecharger_pdf` (génère un PDF côté serveur et renvoie seulement son chemin, affiché par `alert()`).

**Flux C : candidatures spontanées [V]** (un seul pipeline à la fois, état global `etat_spontanees`, `_stop_event` partagé)
1. `POST /api/spontanees/fetch` -> `fetch_entreprises.main` : INSEE Sirene, requête Lucene (siège actif, au moins 10 salariés, NAF du domaine du profil, départements 75/92/93/94), insertion en base dédupliquée par SIRET.
2. `POST /api/spontanees/scraper` -> `scraper_emails.main` : pour chaque entreprise non traitée, recherche du site par DuckDuckGo, scraping de pages contact/carrières/sitemap, extraction emails par regex + Mistral, sauvegarde en base tous les 5.
3. `POST /api/spontanees/envoyer` -> `envoyeur.main` : un même mail (trame `email_type` du profil ou trame codée en dur) + pièces jointes du profil, via SMTP Gmail, limite plafonnée à 50, pause 30 à 90 s, dédup sur `emails_deja_envoyes.json` + `mail_destinataires`.
4. Suivi : `GET /api/spontanees/suivi` (statut `a_relancer` calculé après 7 jours), `POST /api/spontanees/suivi/statut`, `GET /api/spontanees/stats`.

**Flux D : profil [V]** : `GET/POST /api/profil`, `/api/profil/upload` (PDF, 5 Mo max, dans `data/uploads/user_{id}/`), `/api/profil/piece`, `/api/profil/piece/supprimer`, `/api/domaines`, `GET/POST /api/mode`.

---

## 3. Stockage des données

### Base SQLite `data/chasseur.db` (SQLAlchemy 2.0, pas d'Alembic)
Schéma réel lu dans `sqlite_master` [V]. Il diffère du modèle Python : les colonnes ajoutées après coup l'ont été par `ALTER TABLE` ou par une recréation manuelle de `profils` ; aucun script de ces migrations n'est dans le dépôt [V].

| Table | Champs | Contraintes / remarques |
|---|---|---|
| `users` | id, email (unique, index), mot_de_passe_hash (argon2/bcrypt via pwdlib), cree_le | 4 lignes |
| `profils` | id, user_id, mode, prenom, nom, email_contact, telephone, ville, linkedin, github, formation, experience, langues, disponibilite, paragraphe_perso, competences (JSON liste), projets (JSON liste de {nom,url,description}), recherche (JSON dict : titre_poste, localisation, type_contrat, disponibilite, domaines...), lettre_type, email_type, pieces_jointes (JSON liste de {nom,fichier}), niveau_vise, formation_apporte, criteres_eviter, niveau_etudes, duree_souhaitee, dispo_horaires, mobilite, types_jobs_ok, types_jobs_eviter, localisation_pref | UNIQUE(user_id, mode). 5 lignes : user 1 alternance + job, users 2, 3, 4 alternance |
| `candidatures` | id, user_id, mode, ref_offre (md5), titre, entreprise, lieu, zone, domaine, lien, source, description, score, verdict, eligible, points_forts (JSON), points_faibles (JSON), resume_analyse, lettre, email_candidature, objet_email, statut, raison_archivage, date_trouvee, date_candidature, notes | Pas de contrainte d'unicité (user_id, mode, ref_offre) ; dédup applicative. Index modèle sur `mode` absent en base. 442 lignes : user 1 alternance 319, user 1 job 63, user 3 alternance 60 |
| `entreprises` | id, user_id, nom_commercial, ville, code_postal, siren, site_web, secteur (= code NAF), emails_trouves (JSON), telephones (JSON), contact_rh, traite, mail_envoye, mail_envoye_le (str "AAAA-MM-JJ HH:MM"), statut_suivi, extra (JSON : siret, nom, code_naf, adresse, departement, taille, categorie, dirigeant, telephone, mail_destinataires, mail_note...) | **Pas de colonne mode.** 7858 lignes : user 1 6860 (418 envoyés), user 3 998 |

Valeurs de `statut` candidature observées : nouveau, en_cours, envoye, archive (le code accepte aussi reponse, entretien, refus). `raison_archivage` : note_basse, ecole_cfa, hors_it, stage, public_specifique, manuel. `statut_suivi` : envoye, a_relancer (calculé), reponse, entretien, refus, bounce.

Dates stockées en chaînes, JSON en colonnes JSON SQLite.

### Fichiers encore utilisés [V]
- `data/offres_vues_alternance.json`, `data/offres_vues_job.json` : listes d'ids md5 (495 et 113). **Globales à tous les utilisateurs.**
- `data/emails_deja_envoyes.json` : liste d'adresses (1085). **Globale.**
- `data/uploads/user_{id}/*.pdf` : pièces jointes, chemins stockés en relatif dans `profils.pieces_jointes`.
- `lettres_pdf/Lettre_{prenom}_{nom}.pdf` : un seul fichier par nom, écrasé à chaque génération.

### Fichiers hérités, plus lus par la version FastAPI [V]
`candidatures.json` (liste de dicts : id, titre, entreprise, lieu, zone, domaine, lien, source, description, date_trouvee, score, verdict, eligible, points_forts, points_faibles, resume_analyse, lettre, email_candidature, statut, date_candidature, notes), `entreprises_raw.json` et `entreprises_enrichies.json` (identiques, 6860 dicts : nom, nom_commercial, siret, siren, code_naf, adresse, ville, code_postal, departement, site_web, taille, categorie, ca, dirigeant, traite, emails_trouves, telephones, telephone, contact_rh, url_scrapee, source_recherche, tentatives_site, mail_envoye, mail_envoye_le, mail_destinataires, mail_note), `offres_vues.json`. Ils restent lus par `app.py` (Flask) et `export_excel.py`.

---

## 4. Intégrations externes

| Service | Usage | Où | Config |
|---|---|---|---|
| **France Travail** Offres d'emploi v2 | OAuth2 client_credentials, scope `api_offresdemploiv2 o2dsoffre`, `GET /offres/search` | `france_travail/scraper.py` (`get_token`, `_paginer`) | FT_CLIENT_ID, FT_CLIENT_SECRET |
| **La Bonne Alternance** | `GET api.apprentissage.beta.gouv.fr/api/job/v1/search` (romes par lots de 20, lat/lng Paris, rayon 60, exclut le partenaire France Travail) | `france_travail/scraper_lba.py` | LBA_API_KEY (Bearer) |
| **INSEE Sirene 3.11** | `GET /api-sirene/3.11/siret`, pagination par curseur | `spontanees/fetch_entreprises.py` | INSEE_API_KEY (en-tête `X-INSEE-Api-Key-Integration`) |
| **Mistral AI**, modèle `mistral-large-latest` | Scoring des offres (JSON mode, retry 429), lettre (temp 0.6), extraction des contacts des pages web | `analyseur.py`, `generateur.py`, `scraper_emails.py` (3 clients instanciés séparément) | MISTRAL_API_KEY |
| **Google Gemini** `gemini-2.5-pro` via Vertex AI (`google-genai`, région `us-central1` codée en dur) | Compréhension d'intention du bot Telegram uniquement | `telegram_bot.py` | GOOGLE_CLOUD_PROJECT (absent du `.env` actuel [V] ; dépend peut-être d'une config gcloud par défaut [S]) |
| **DuckDuckGo** (lib `ddgs`) | Recherche du site web des entreprises | `scraper_emails.py` | aucune |
| Sites des entreprises | `requests` + BeautifulSoup, pages contact et sitemap | `scraper_emails.py` | DEBUG_SCRAPER |
| **Gmail SMTP** `smtp.gmail.com:465` SSL | Envoi des candidatures spontanées | `spontanees/envoyeur.py` | GMAIL_SENDER, GMAIL_APP_PASSWORD (un seul compte pour tout le monde) |
| **Gmail IMAP** `imap.gmail.com:993` | Lecture des destinataires du dossier Envoyés | `spontanees/fetch_envoyes_gmail.py` | idem |
| **Telegram** (`python-telegram-bot` 22, polling) | Pilotage à distance, filtre sur un seul user id Telegram | `telegram_bot.py` | TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_ID, FLASK_BASE_URL (défaut localhost:5002) |
| WeasyPrint | PDF de lettre | `pdf_generator.py` | aucune |

Les commentaires parlent encore de "Gemini" dans `generateur.py` alors que l'appel est Mistral [V].

---

## 5. Gestion des utilisateurs

### Ce qui existe et fonctionne [V]
- Comptes : inscription ouverte à tous (`/register`, mot de passe 6 caractères min), connexion, déconnexion, session cookie signée par SECRET_KEY.
- Isolation en base : profils, candidatures et entreprises filtrés par `user_id` dans toutes les fonctions de `database/*`.
- Profil multi-mode : un profil par (user, mode), créé à la volée.
- Uploads rangés par `data/uploads/user_{id}`.
- Les pipelines reçoivent `user_id` en paramètre.

### À moitié fait [V]
- **Pas de dépendance FastAPI** : vérification de session copiée dans ~25 routes ; aucune protection CSRF.
- **Routes non authentifiées** : `/api/logs`, `/api/statut_recherche`, `/api/spontanees/statut`, `/api/spontanees/stop`. N'importe qui peut lire les logs (noms d'entreprises, adresses destinataires) ou stopper le pipeline d'un autre.
- **États globaux en mémoire** : `etat_recherche`, `etat_spontanees`, `_stop_event`, `_logs` sont partagés. Un seul utilisateur peut lancer une recherche ou un pipeline à la fois, les autres voient sa progression et ses logs.
- **Entreprises sans mode** : la table n'a pas de colonne `mode`, `fetch_entreprises` et `envoyeur` lisent toujours le profil `alternance` (main.py ne passe pas le mode).
- **Relation `User.profil` en `uselist=False`** alors qu'il y a désormais plusieurs profils par user.
- **migration.py** n'est pas à jour (ne connaît ni `mode` ni les nouveaux champs) ; les migrations de schéma faites ensuite ne sont pas versionnées.
- **Bot Telegram non adapté** : il appelle l'API sans cookie de session, donc `stats`, `fetch`, `scraper`, `envoyer` renvoient 401 ; seuls `logs`, `statut` et `stop` passent (parce qu'ils sont non protégés). Son prompt parle de "Kenza" et de "fichiers JSON locaux".
- **Pas d'onboarding** : le commentaire de `auth/routes.py` le mentionne, rien n'est implémenté [V] ; le front affiche un bandeau de bienvenue sur `?bienvenue=1` [V].

### Ce qui suppose encore un utilisateur unique [V]
- **Compte Gmail unique** : tous les utilisateurs enverraient leurs candidatures depuis la même adresse (GMAIL_SENDER), et `fetch_envoyes_gmail.py` ne lit que cette boîte.
- **Dédup globale** : `emails_deja_envoyes.json` (adresses contactées par l'user 1 bloquent les autres) et `offres_vues_{mode}.json` (une offre vue par un utilisateur n'est jamais proposée aux suivants : un nouvel inscrit ne reçoit que les offres publiées après coup).
- **`user_id=1` par défaut** : `envoyeur.main`, `scraper_emails.main`, `fetch_entreprises.main`, CLI `--user 1`, cron.
- **Fallback vers l'user 1** : `analyser_offre(profil=None)` -> `lire_profil(1)` ; `generer_pdf_lettre` fait `profil or lire_profil(1)`, donc un profil vide (`{}`) imprime les coordonnées de l'user 1 sur la lettre d'un autre.
- **Chemins absolus `/home/kenza/...`** : `fetch_entreprises.py` (FICHIER_RAW, FICHIER_SORTIE), `scraper_emails.py` (FICHIER_ENTREE, FICHIER_SORTIE), `envoyeur.py` (FICHIER_JSON, FICHIER_EMAILS_ENVOYES, CV_PATH, PLAQUETTE_PATH, RECO_PATH), `fetch_envoyes_gmail.py` (FICHIER_SORTIE), ligne cron.
- **Contenus codés en dur** : objet de mail "Candidature spontanée en alternance", trame de mail "rentrée 2026", trame de lettre "Objet : Candidature en alternance" (aussi en mode job si l'utilisateur n'a pas de `lettre_type`), "Paris, le" sur le PDF, prompt de lettre au féminin ("la candidate"), exemple "Garage Numérique" et "Linux et Docker", prompt job qui décrit les préférences d'une personne précise (jobs calmes, surveillance, gardiennage), liste d'écoles/CFA, mots-clés BOETH/MAAZI.
- **Géographie figée sur l'Île-de-France** : région FT `11`, départements IDF, coordonnées Paris pour LBA, départements Sirene 75/92/93/94 ; le champ `recherche.localisation` du profil n'est utilisé que dans le prompt.
- **Domaines** : seulement `informatique` et `immobilier`, avec `informatique` comme défaut silencieux.

---

## 6. Les modes

Définis dans `shared/modes.py` : `alternance` (défaut) et `job`. **Il n'existe pas de mode `stage`** [V] : en alternance, une offre dont le titre contient "stage" est archivée automatiquement avec la raison `stage`, et le front a un filtre "Stage" sur cette raison.

| | Alternance | Job (CDD, intérim, saisonnier) |
|---|---|---|
| Sources | FT (`natureContrat=E2`) + LBA | FT seulement (`typeContrat=CDD,MIS,SAI`, `qualification=0`), offres `alternance=true` exclues |
| Filtre domaine | Oui (grand domaine FT, ROME LBA) | Non, tous domaines |
| Volume | jusqu'à 3000 offres FT, toutes analysées | lots de 100 par run, le reste aux runs suivants |
| Prompt d'analyse | Recruteur alternance, niveau visé, formation | Recruteur jobs courts, pénibilité, durée, localisation |
| Archivage auto | public spécifique, école/CFA, hors domaine, stage, note basse | note basse seulement |
| Lettre | paragraphe orienté compétences | paragraphe orienté qualités humaines |
| Profil | sections `alternance` + `commun` | sections `job` + `commun` (niveau_etudes, duree_souhaitee, dispo_horaires, mobilite, types_jobs_ok/eviter, localisation_pref) |
| Candidatures spontanées | Oui | Non adaptées (entreprises sans mode, mail "alternance") |

**Fonctionne [V, par lecture]** : recherche FT dans les deux modes, analyse alternance, analyse job pendant la recherche, lettre dans les deux modes, profils séparés, bascule de mode par session, titres adaptés dans le front. La base contient 63 candidatures job pour l'user 1, signe que le mode a tourné [V].

**Incomplet ou cassé [V]** : ré-analyse manuelle en mode job (cf. §8, bug 2) ; spontanées réservées de fait à l'alternance ; la dédup `offres_vues` du mode alternance est écrasée lors d'un run job (cf. §8, bug 1) ; trame de lettre par défaut "alternance" en mode job.

---

## 7. Historique git

Le dépôt n'a que **8 commits** au total (pas 20) [V] :

| Commit | Date | Contenu |
|---|---|---|
| bc7e6de | 2026-03-18 | Commit initial v1.0 : Flask, scripts à plat |
| 28fed6f | 2026-03-18 | Sidebar, filtres, tri, date FT |
| 825e955 | 2026-04-06 | Candidatures spontanées, réorganisation en paquets `france_travail/`, `spontanees/`, `shared/` |
| 29336da | 2026-05-10 | "Finalisation", suppression de `generateur_lettres.py`, ajout de `generateur_mail.py`, `profil.example.py` |
| ee1ef26, 353433a | 2026-05-10 | Retouches README |
| 81f5a2e | 2026-05-11 | UI spontanées, bouton arrêt, "projet finalisé" |
| **5b9a3ef** | **2026-09-22** | **"Version FastAPI multi-utilisateurs"** : 48 fichiers, +7326/-1031 |

**Pas de commit "WIP"** au sens littéral [V]. Le travail multi-utilisateur est entièrement contenu dans `5b9a3ef`, un commit massif qui mélange : passage Flask -> FastAPI (`main.py`), auth (`auth/`), couche base (`database/`), migration, LBA (`scraper_lba.py`), modes et domaines (`shared/modes.py`, `shared/domaines.py`), nouveau front modulaire (`static/js`, `static/css`, `templates/base.html` + partials), bot Telegram, sync Gmail, suppression de `generateur_mail.py`.

État des branches [V] : `main`, `origin/main` et `refonte-multiuser` pointent **tous sur 5b9a3ef**. Le travail "abandonné" est donc déjà sur `main` et poussé. Aucun stash, aucun fichier modifié.

Indices de l'abandon en cours de route [V] : `app.py`, `static/app.js`, `templates/index.html` laissés en place ; commentaire de `entreprises_db.py` qui dit encore "lecture seule, le JSON reste la source d'écriture" alors que les écritures sont faites ; README et `.env.example` non mis à jour ; `requirements.txt` non mis à jour ; ligne cron commentée ; le dernier envoi en log a eu lieu sur l'ancien JSON ou la base, impossible à dater depuis le log [S].

---

## 8. Bugs, incohérences, code mort ou dupliqué

### Bugs confirmés par lecture
1. **Écrasement de la dédup alternance en mode job** : `france_travail/main.py:70` appelle `sauvegarder_offres_vues(offres_vues)` sans `mode`, donc écrit dans `offres_vues_alternance.json` l'ensemble chargé pour le mode courant. En mode job, la liste alternance est remplacée par celle du job ; au run alternance suivant, les offres déjà vues sont ré-analysées par Mistral (coût, temps ; pas de doublon en base grâce à `ajouter_candidature`). Le fichier a déjà été sauvegardé correctement dans `chercher_offres`, cet appel est en plus redondant.
2. **Ré-analyse en mode job avec le prompt alternance** : `main.py:359` (`/api/analyser`) appelle `analyser_offre(offre, profil)` sans `mode`.
3. **Archivage LBA "hors domaine" jamais déclenché** : `main.py:308` teste `domaine == "Hors IT"` alors que l'analyseur renvoie `"Hors domaine"`.
4. **Analyse LBA sans pause** : la boucle de `main.py` n'a pas le `time.sleep(PAUSE_MISTRAL)` d'`analyser_offres`, risque de 429 (le retry atténue).
5. **Le scraper perd ses résultats de site** : `sauvegarder_enrichissement` ne persiste ni `site_web`, ni `url_scrapee`, ni `source_recherche`, ni `tentatives_site`. Le site trouvé par DuckDuckGo est perdu ; le compteur de retry repart à zéro.
6. **PDF** : fichier unique `lettres_pdf/Lettre_{prenom}_{nom}.pdf` écrasé à chaque fois, chemin serveur renvoyé au navigateur sans téléchargement possible, fallback sur le profil de l'user 1, `p['prenom']` etc. lève `KeyError` si un champ manque.
7. **Trame de lettre utilisateur** : `template.format(...)` hors du `try` ; une accolade dans `lettre_type` fait planter la route en 500.
8. **Nom de pièce jointe tronqué** : `_nom_fichier_sur` coupe à 80 caractères, extension `.pdf` comprise (fichier réel dans `data/uploads/user_1/` sans extension) ; le nom est aussi dupliqué (`Programme_DEUST_IOSI_Programme_DEUST_IOSI.pdf`) [V sur disque, cause du doublement non trouvée dans le code actuel S].
9. **Pièces jointes partagées entre modes** : même dossier pour les deux modes ; supprimer une pièce dans un mode efface le fichier encore référencé par l'autre profil.
10. **`DATABASE_URL` du `.env` ignorée** : `database/connexion.py` lit l'env à l'import, avant le `load_dotenv()` de `main.py:48` (les autres modules qui appellent `load_dotenv` sont importés après `auth`). Sans impact aujourd'hui (variable absente du `.env`).
11. **Bot Telegram cassé** par l'auth (cf. §5).
12. **Deux fonctions nommées `api_spontanees_statut`** dans `main.py` (lignes 452 et 591) : les routes marchent, mais le nom est masqué.
13. **`calculer_stats`** : "5 dernières" = 5 dernières par ordre d'insertion, pas par date.
14. `contact_rh` normalisé différemment : texte lisible dans `migration.py`, `json.dumps` brut dans `sauvegarder_enrichissement`.

### Code mort ou désynchronisé
- `app.py`, `templates/index.html`, `static/app.js` : ancienne version Flask.
- `france_travail/main.py` : `charger_candidatures`, `sauvegarder_candidatures`, `ajouter_candidatures` (JSON) ; importés par `main.py` mais seule `lancer_recherche` sert, et `ajouter_candidatures` n'est appelé que si `on_offre` est absent.
- `main.py` : `FICHIER_ENRICHIES`, `FICHIER_RAW`, imports `json`, `lire_entreprises`.
- `fetch_entreprises.py` : `CODES_NAF`, `FICHIER_RAW`, `FICHIER_SORTIE`, `charger_base`, `sauvegarder`.
- `scraper_emails.py` : `FICHIER_ENTREE`, `FICHIER_SORTIE`.
- `envoyeur.py` : `FICHIER_JSON`, `CV_PATH`, `PLAQUETTE_PATH`, `RECO_PATH`, `LIMITE_PAR_RUN` utilisé seulement en CLI.
- `entreprises_db.calculer_stats` : champ `mail_generee` toujours 0.
- `export_excel.py` : lit le JSON figé, donc exporte des données périmées.
- `data/offres_vues.json`, `entreprises_raw.json` (copie exacte de `enrichies`), `candidatures.json`.
- README : décrit Flask, `generateur_mail.py` (supprimé), `python app.py`.

### Duplications
- `detecter_zone`, `generer_id`, `DEPTS_IDF` dans `scraper.py` et `scraper_lba.py`.
- Codes ROME IT (`ALL_CODES_ROME_IT`) et NAF (`CODES_NAF`) dupliqués avec `shared/domaines.py`.
- Règles d'archivage auto copiées entre `analyseur.analyser_offres` et `main.py` (déjà divergentes, cf. bug 3).
- Boucle retry Mistral copiée 3 fois ; 3 clients Mistral ; liste des mois en double (`generateur.py`, `pdf_generator.py`).
- Bloc "vérifier l'utilisateur" copié dans chaque route.

### Fragilités et sécurité
- Inscription ouverte + compte Gmail partagé = tout inscrit peut envoyer des mails depuis l'adresse du propriétaire.
- `SECRET_KEY` a une valeur de repli codée en dur ; cookie sans `https_only`.
- `etat_*` modifiés depuis des threads sans verrou ; threads `daemon` perdus au redémarrage d'uvicorn (`--reload` les tue à chaque modification de fichier).
- Les sessions SQLite sont ouvertes et fermées à chaque appel, les objets `User` détachés sont renvoyés (ça marche car seuls des attributs simples sont lus).
- `utilisateur_courant` refait une requête en base à chaque appel API (pas de cache de l'utilisateur dans la requête).

---

## 9. Dépendances et configuration

### `requirements.txt` déclaré [V]
flask 3.1.3, google-genai 1.70.0, google-auth 2.49.1, google-auth-httplib2 0.3.1, google-auth-oauthlib 1.3.1, requests 2.33.1, beautifulsoup4 4.14.3, ddgs 9.12.1, weasyprint 68.1, openpyxl 3.1.5, python-dotenv 1.2.2, mistralai (non épinglé).

### Réellement nécessaires mais absentes du fichier [V, présentes dans le venv]
fastapi 0.137.1, starlette 1.3.1, uvicorn 0.49.0, sqlalchemy 2.0.51, jinja2 3.1.6, python-multipart 0.0.32 (Form, UploadFile), itsdangerous 2.2.0 (SessionMiddleware), pydantic 2.12, fastapi-users 15.0.5 (utilisé uniquement pour `PasswordHelper`), pwdlib 0.3.0 + argon2-cffi + bcrypt, python-telegram-bot 22.7. `fastapi_users_db_sqlalchemy` installé mais inutilisé. `google-auth-oauthlib` et `google-auth-httplib2` semblent des restes de l'ancien envoi Gmail OAuth [S]. `flask` n'est utile qu'à `app.py`.

Note : `mistralai` 2.4.9 installé, import via `from mistralai.client import Mistral`.

Dépendances système de WeasyPrint (Pango, Cairo) requises [S, standard pour WeasyPrint].

### Variables d'environnement attendues par le code [V]
| Variable | Présente dans `.env` | Dans `.env.example` | Utilisée par |
|---|---|---|---|
| MISTRAL_API_KEY | oui | non | analyseur, generateur, scraper_emails |
| FT_CLIENT_ID, FT_CLIENT_SECRET | oui | oui | scraper.py |
| LBA_API_KEY | oui | non | scraper_lba.py |
| INSEE_API_KEY | oui | non | fetch_entreprises.py |
| GMAIL_SENDER, GMAIL_APP_PASSWORD | oui | oui | envoyeur, fetch_envoyes_gmail |
| DEBUG_SCRAPER | oui | oui | scraper_emails |
| TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_ID | oui | non | telegram_bot |
| SECRET_KEY | oui | non | main.py |
| GOOGLE_CLOUD_PROJECT | **non** | oui | telegram_bot |
| GCP_REGION | non | oui | inutilisée (région codée en dur) |
| FLASK_BASE_URL | non | non | telegram_bot (défaut localhost:5002) |
| DATABASE_URL | non | non | connexion.py (défaut SQLite, cf. bug 10) |

Fichiers de credentials : `.gitignore` prévoit `credentials.json` et `token_chasseur.json` (ancien OAuth Gmail), **absents** du disque [V].

---

## 10. Questions ouvertes

1. Qui sont les users 2, 3 et 4 en base (vrais utilisateurs, comptes de test) ? L'user 3 a 998 entreprises et 60 candidatures : faut-il conserver ces données lors de la refonte ?
2. Pour l'envoi en multi-utilisateur : chaque utilisateur branche-t-il son propre compte mail (SMTP perso, OAuth Gmail), ou l'application envoie-t-elle depuis une adresse commune ? Cela conditionne aussi la dédup `emails_deja_envoyes`.
3. La dédup des offres vues doit-elle devenir par utilisateur (logique produit) ou rester globale pour économiser les appels Mistral (analyse partagée, score par profil) ?
4. Le mode "stage" doit-il réutiliser FT (quel filtre ? FT n'a pas de type de contrat stage clair) et quelles autres sources ? Le code ne donne aucun indice.
5. Les candidatures spontanées doivent-elles exister en mode job et stage ? Si oui, faut-il un `mode` sur `entreprises` ou une table de liaison user/entreprise pour éviter de re-télécharger Sirene par utilisateur ?
6. Cible de déploiement : le commentaire de `connexion.py` évoque PostgreSQL sur Railway. Est-ce décidé ? Cela impose une vraie file de tâches (les threads + états en mémoire ne tiennent pas avec plusieurs workers).
7. La géographie doit-elle sortir de l'Île-de-France ?
8. Le bot Telegram doit-il devenir multi-utilisateur (association compte Telegram <-> user) ou rester un outil personnel ?
9. Pourquoi deux fournisseurs d'IA (Mistral pour le métier, Gemini Vertex pour le bot) ? Contrainte de coût, de quotas, ou historique ?
10. Le schéma réel de la base a été modifié à la main (`ALTER TABLE`, recréation de `profils`) : existe-t-il des scripts ou notes hors dépôt ? À défaut, la base de prod fait foi, pas `models.py`.
11. La ligne cron commentée signifie-t-elle que l'envoi automatique est suspendu volontairement (fin de la recherche d'alternance, réputation Gmail) ?
12. L'origine du doublement des noms de pièces jointes dans `data/uploads/user_1/` (copie manuelle, ancienne version du code ?) n'est pas visible dans le code actuel.
