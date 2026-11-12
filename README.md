# Chasseur d'Alternance

Application web multi-utilisateurs qui automatise la recherche d'une alternance, d'un stage ou d'un job en Île-de-France. Elle rassemble les offres publiées (France Travail, La Bonne Alternance), constitue une liste d'entreprises ciblées pour des candidatures spontanées (base Sirene de l'INSEE, La Bonne Alternance), trouve leurs adresses de contact, envoie les candidatures depuis le compte mail de chaque utilisateur et suit les réponses. Chaque utilisateur a un profil par mode et ne voit que ses propres données.

> [!IMPORTANT]
> **L'IA tourne sur la machine**, avec [Ollama](https://ollama.com) et des modèles open source (Ministral 3 par défaut) : aucun fournisseur extérieur, aucune donnée envoyée ailleurs.
> Sur processeur, elle est lente (une à deux minutes par offre) : la recherche ajoute donc les offres sans les noter, et l'analyse vient ensuite, en différé.
> Sans IA (`ANALYSE_IA=false`, ou Ollama arrêté), tout le reste fonctionne : les offres restent « non analysées » et les emails douteux sont à valider à la main.

## Fonctionnalités

Trois modes, chacun à son URL (`/alternance`, `/job`, `/stage`) avec son profil, ses offres, ses candidatures spontanées et son suivi. Deux onglets ouverts dans deux modes ne se gênent pas.

### Offres

| Mode | France Travail | La Bonne Alternance |
|---|---|---|
| Alternance | contrats d'apprentissage et de professionnalisation | offres hors relais France Travail, filtrées par niveau de diplôme visé |
| Job | CDD, intérim, saisonnier ; thèmes « jobs d'été » et « sans diplôme ni expérience » en option | non |
| Stage | mot-clé « stage », offres en alternance écartées, intitulés filtrés par des règles (le stage doit être le poste, pas son objet) | non |

- Domaines du profil en codes de la nomenclature France Travail (14 grands domaines, 110 domaines), secteur de l'employeur et taille d'entreprise en option. Toutes les listes viennent des référentiels officiels, versionnés dans `docs/referentiels/`.
- Rien n'est tronqué en silence : au-delà du plafond de l'API France Travail (3150 offres par requête), la recherche est redécoupée par date de création ; La Bonne Alternance est interrogée autour de 19 centres d'Île-de-France, chaque cercle saturé étant redécoupé. Les logs donnent ce qui a été annoncé, récupéré et écarté.
- Offres dédoublonnées par utilisateur et par mode, archivage automatique par mots-clés (offres réservées à un public, écoles et CFA en alternance).
- **Analyse par l'IA locale, en différé.** La recherche ajoute les offres « non analysées » (30 par défaut), sans attendre l'IA. « Analyser les offres en attente » les fait noter une à une (note sur 10, éligibilité, points forts et faibles, catégorie métier), des plus récentes aux plus anciennes, 30 par lancement ou toute la file pour un lancement de nuit, avec la taille de la file et le temps pour la vider, la progression et le temps restant dans le bandeau, et un bouton d'arrêt. Les règles d'archivage par mots-clés passent avant l'IA. Une option du profil la lance après chaque recherche. Un prompt par mode (alternance, job, stage) ; une analyse archive les offres hors domaine ou inéligibles. Une réponse invalide est redemandée une fois, puis l'offre reste en attente : aucune note n'est jamais inventée.
- **Lettre de motivation** : la lettre type écrite dans le profil, avec des balises (`{entreprise}`, `{poste}`, `{date}`, `{contact_entreprise}`, `{portfolio}` remplacées en Python, `{paragraphe}` obligatoire). L'IA ne rédige que le paragraphe personnalisé, affiché et modifiable, régénérable, avant d'être inséré. Sans lettre type ou sans `{paragraphe}`, un message renvoie au profil.
- **J'ai postulé** sur une offre (date modifiable) : elle quitte la page Offres pour le tableau Candidatures, d'où elle peut être annulée.
- **La Bonne Alternance** : une offre LBA dont la page de candidature est connue porte « Postuler sur La Bonne Alternance » (nouvel onglet), à côté de « J'ai postulé ».

### Candidatures spontanées

- **Entreprises.** Sirene dans les trois modes : secteurs NAF déduits des domaines (secteurs « cœurs » toutes tailles, secteurs « transverses » pour les entreprises de 250 salariés et plus), ou secteurs choisis, ou case « tous les secteurs » ; filtres par taille (tranches INSEE) et par département. En alternance, s'y ajoutent les entreprises à fort potentiel d'embauche d'alternants repérées par La Bonne Alternance. Dédoublonnage par SIRET puis SIREN, source de chaque entreprise gardée et affichée. Bascule automatique vers la nomenclature NAF 2025 au 1er janvier 2027.
- **Emails.** Un scraper cherche le site de chaque entreprise et lit ses pages (adresses obfusquées comprises). Des règles, dans deux fichiers de données faciles à compléter, décident d'abord : adresses techniques, factices ou inutiles écartées (`shared/referentiels/emails_exclus.txt`, préfixes écartés) ; adresses de contact ou de recrutement validées d'office seulement sur le domaine du site, quand ce site correspond au nom de l'entreprise et n'est ni un annuaire, ni un hébergeur, ni un fournisseur générique (`shared/referentiels/validation_emails.txt`). Les autres sont douteuses : l'IA tranche en un appel par entreprise d'après le texte qui les entoure et désigne le meilleur contact ; sans elle, elles restent « non validées », jamais envoyées automatiquement. Chaque adresse affiche comment elle a été validée (règle, IA, à la main) ; une adresse écartée par l'IA reste visible et peut être validée quand même. Seules les adresses validées partent.
- **Envoi.** Chaque utilisateur envoie depuis son propre compte (Gmail avec un mot de passe d'application, ou tout serveur SMTP sur le port 465 ou 587), configuré dans Paramètres et vérifié par un test de connexion. Objet et message personnalisables avec des balises (`{prenom}`, `{date}`, `{portfolio}`, et en stage `{date_debut}`, `{duree_semaines}`...), pièces jointes, plafond de 50 mails par jour et par utilisateur, arrêt immédiat sur erreur de compte.
- **Mode test**, activé par défaut sur tout nouveau compte d'envoi : chaque candidature part vers l'adresse de l'utilisateur, le vrai destinataire indiqué dans l'objet, et rien n'est marqué comme envoyé. Un bandeau le signale.
- **Entreprises de La Bonne Alternance sans email** : quand LBA a un contact pour l'entreprise, « Postuler sur La Bonne Alternance » ouvre son formulaire, et « J'ai postulé » la fait entrer dans le suivi.
- Une adresse déjà contactée dans un mode n'est jamais réécrite dans ce mode ; une entreprise contactée dans un autre mode porte l'étiquette « déjà contactée en alternance le JJ/MM/AAAA », sans bloquer l'envoi.

### Suivi

Un tableau Candidatures par mode : offres postulées et entreprises contactées, avec la date, le statut (postulée ou envoyée, à relancer après 7 jours, réponse, entretien, refus) modifiable sur place, le lien et le contact. Statistiques par source (entreprises, emails trouvés, envois, réponses, entretiens). Limites réglables à chaque lancement (offres, nouvelles entreprises, sites scrapés, mails envoyés), bornées par le serveur, et logs des traitements en direct dans l'interface.

### Profil et compte

- **Copie de profil** : « Copier depuis un autre mode » reprend les sections qui ne dépendent pas du mode (identité, liens, formation, expérience, compétences, projets, lettre type, email, pièces jointes), avec un aperçu avant/après et une confirmation pour toute section déjà remplie.
- **Paramètres**, communs aux trois modes : email de connexion, mot de passe (les autres sessions sont alors fermées), compte d'envoi.
- **Mot de passe oublié** : l'administratrice donne un mot de passe temporaire (`scripts/reinitialiser_mot_de_passe.py`), à changer à la connexion suivante.

## Architecture technique

- **Backend** : Python 3.13, FastAPI, traitements longs dans des threads par utilisateur (une recherche et une étape de spontanées à la fois, arrêt possible).
- **Données** : SQLAlchemy 2, SQLite, schéma unique dans `database/models.py`, migrations Alembic (15 à ce jour, chacune testée en montée et en descente sans perte de lignes).
- **Authentification** : inscription sur code d'invitation, mots de passe hachés (argon2), session par cookie signé (`httponly`, `samesite`, `secure` en production) portant une empreinte du mot de passe (le changer ferme les autres sessions). Au plus 5 essais de connexion ratés en 15 minutes. Requêtes qui modifient des données refusées si elles viennent d'une autre page (en-tête Origin). Toutes les routes sauf connexion, inscription et mot de passe oublié exigent une session.
- **Isolation** : chaque table de données porte l'utilisateur (clé étrangère, suppression en cascade), chaque requête filtre sur l'utilisateur connecté, dédoublonnages, logs et traitements sont propres à chacun.
- **Secrets** : mots de passe SMTP chiffrés en base (Fernet, clé dans `.env`), jamais renvoyés au navigateur.
- **Sources externes** : API Offres d'emploi v2 de France Travail, API de La Bonne Alternance, API Sirene de l'INSEE. Tout ce qui dépend du comportement d'une API est réuni dans un fichier de paramètres par source, vérifié par un script lancé à la main (`scripts/verifier_*.py`).
- **IA** : API native d'Ollama par défaut (`/api/chat`, réflexion coupée par `think: false`, schéma JSON dans `format`), ou tout serveur au format compatible OpenAI (`IA_API=openai`). Un modèle par usage (analyse, lettre, extraction), un seul appel à la fois dans tout le processus, réponses validées par Pydantic (`shared/schemas_ia.py`) et bornées en Python. Test de démarrage de chaque modèle avant son premier usage ; serveur injoignable, schéma ou coupure de la réflexion refusés : pipeline arrêté avec un message clair, jamais de mode dégradé.
- **Interface** : templates Jinja2, JavaScript en modules ES sans framework, PDF générés par WeasyPrint. Les liens venus des API (offres, sites) ne sont gardés que s'ils sont en http(s).
- **Tests** : près de 1 200 tests automatisés (pytest), APIs externes et IA simulées, aucun appel réseau ni à Ollama, base temporaire migrée par Alembic ; chaque route de l'API essayée par un autre utilisateur (isolation) et avec des données limites.

```
main.py              application FastAPI : pages, routes /api, lancement des traitements
auth/                connexion, inscription, session, compte (Paramètres), contrôle de l'origine
database/            modèles SQLAlchemy et accès aux données
alembic/             migrations du schéma
france_travail/      offres : France Travail, La Bonne Alternance, analyse (en différé), lettre, PDF
spontanees/          candidatures spontanées : Sirene, scraper d'emails, envoi
shared/              configuration, client d'IA, modes, domaines, NAF, référentiels et règles
scripts/             vérification des API et de l'IA locale, imports et nettoyage, lancés à la main
templates/, static/  interface
tests/               suite pytest
docs/                décisions, spécification des sources, rapports de phase
```

## Installation de zéro (Fedora)

Prérequis : Python 3.13, les bibliothèques Pango et Cairo (WeasyPrint, pour les PDF), la police Carlito (lettres en PDF), Git ; Ollama pour l'IA (facultatif). Clés d'API à demander : France Travail (francetravail.io, application avec l'API « Offres d'emploi v2 »), La Bonne Alternance (api.apprentissage.beta.gouv.fr), INSEE Sirene (portail-api.insee.fr, API Sirene 3.11).

```bash
sudo dnf install -y python3.13 pango cairo git google-carlito-fonts
git clone <url-du-depot> chasseur_alternance
cd chasseur_alternance
python3.13 -m venv venv
venv/bin/pip install -r requirements.txt     # requirements-dev.txt en plus pour les tests et l'analyse du code
mkdir -p data                                # base SQLite et pièces jointes (hors dépôt)
cp .env.example .env
```

### Variables d'environnement (`.env`)

Toutes sont décrites dans `.env.example`, qui est complet. L'essentiel :

| Variable | Rôle |
|---|---|
| `SECRET_KEY` | **obligatoire**, 32 caractères au moins : `venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CLE_CHIFFREMENT` | chiffrement des mots de passe SMTP ; sans elle, l'envoi de mails est désactivé : `venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Ne plus la changer ensuite. |
| `DATABASE_URL` | chemin absolu, quatre barres obliques : `sqlite:////chemin/absolu/vers/chasseur_alternance/data/chasseur_v2.db` (vide : `DATA_DIR/chasseur_v2.db`) |
| `DATA_DIR`, `UPLOADS_DIR`, `LETTRES_PDF_DIR` | dossiers des données, pièces jointes et PDF de lettres (vides : `data/`, `data/uploads/`, `lettres_pdf/`) ; à sauvegarder avec la base |
| `CODE_INVITATION` | code à saisir sur `/register` (vide : inscriptions fermées) |
| `COOKIE_SECURE` | `true` derrière HTTPS, `false` en local |
| `FT_CLIENT_ID`, `FT_CLIENT_SECRET`, `LBA_API_KEY`, `INSEE_API_KEY` | identifiants des sources |
| `ANALYSE_IA`, `IA_*` | IA locale (section suivante) ; `ANALYSE_IA=false` pour travailler sans IA |
| `NOMENCLATURE_NAF` | vide (bascule NAF 2025 automatique le 1er janvier 2027) |
| `PLAFOND_ENVOIS_JOUR` | mails par utilisateur et par jour (50) |
| `FUSEAU_AFFICHAGE` | fuseau d'affichage des dates (`Europe/Paris`) |

**Police des lettres en PDF.** Carlito (paquet `google-carlito-fonts`), libre, aux mêmes métriques que Calibri, en 11 pt. Elle est prise sur le système par WeasyPrint et embarquée dans chaque PDF ; à défaut, Liberation Sans (`liberation-sans-fonts`). Aucun fichier de police n'est chargé par le PDF lui-même. En-tête de la lettre : nom, ville, téléphone et email ; un lien (portfolio...) s'écrit dans la lettre type, avec la balise `{portfolio}` par exemple.

### IA locale (Ollama)

```bash
curl -fsSL https://ollama.com/install.sh | sh     # installe aussi le service systemd « ollama »
ollama pull ministral-3:3b     # analyse des offres et validation des emails douteux
ollama pull ministral-3:8b     # lettres de motivation
```

Modèles par défaut : `ministral-3:3b` pour l'analyse et les emails, `ministral-3:8b` pour les lettres (`IA_MODELE_ANALYSE`, `IA_MODELE_LETTRE`, `IA_MODELE_EXTRACTION`). Les critères bloquants (niveau, durée, dates, alternance) sont vérifiés en Python : le modèle d'analyse ne fait que noter et recopier des informations de l'offre, ce qu'un petit modèle fait bien ; comparés à l'aveugle, les paragraphes de lettre du 8b sont nettement meilleurs. Mesures sur processeur, sans carte graphique : `ministral-3:8b` lit 27 tokens/s et écrit 7 tokens/s, soit une à deux minutes par offre ; `ministral-3:3b` lit 57 tokens/s et écrit 13 tokens/s. Avec une carte graphique intégrée AMD (Radeon 660M), `OLLAMA_IGPU_ENABLE=1` l'utilise : environ 30 s par offre. Sur une machine à peu de RAM (12 Go par exemple), n'autoriser qu'un modèle chargé à la fois :

```bash
sudo systemctl edit ollama         # ajouter, puis enregistrer :
#   [Service]
#   Environment="OLLAMA_MAX_LOADED_MODELS=1"
sudo systemctl restart ollama
```

Un autre serveur compatible OpenAI (llama.cpp, LM Studio, vLLM, un service en ligne avec `IA_API_KEY`) se choisit avec `IA_API=openai` et `IA_BASE_URL`.

### Lancement

Créer la base, et la mettre à jour après chaque `git pull` (sauvegarder `data/` avant toute migration) :

```bash
venv/bin/alembic upgrade head
venv/bin/uvicorn main:app --port 5002     # --reload pendant le développement
```

Ouvrir http://localhost:5002, créer un compte sur `/register` avec le code d'invitation, choisir un mode, remplir le profil, puis configurer le compte d'envoi (Paramètres, section Compte d'envoi) et le vérifier avec « Tester la connexion ». La documentation de l'API est sur http://localhost:5002/docs une fois connecté. En production derrière HTTPS : `COOKIE_SECURE=true`, et le proxy doit transmettre l'en-tête Host d'origine (contrôle de l'origine des requêtes).

Les pipelines existent aussi en ligne de commande, pour un utilisateur donné par son identifiant (`--user`, obligatoire) et un mode (`--mode`, `alternance` par défaut) : `venv/bin/python -m spontanees.fetch_entreprises`, `venv/bin/python -m spontanees.scraper_emails`, `venv/bin/python -m spontanees.envoyeur --limite 10 --test`.

### Tests et analyse du code

```bash
venv/bin/pip install -r requirements-dev.txt
systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q   # seul pytest est tué en cas d'emballement
venv/bin/ruff check .
venv/bin/vulture main.py auth database france_travail shared spontanees scripts
```

Chaque test est limité à 30 s. Sur une installation neuve, un test est sauté : il a besoin de l'ancienne base de la version mono-utilisateur, absente.

### Scripts (lancés à la main)

| Script | Rôle |
|---|---|
| `scripts/verifier_ia_locale.py` | test de démarrage des modèles, comparaison sur de vraies offres « non analysées » (lecture seule) ; `--modeles a,b`, `--lettre` |
| `scripts/verifier_france_travail.py` | points ouverts de l'API France Travail (paramètres, plafonds, mode stage) |
| `scripts/verifier_lba.py` | points ouverts de l'API La Bonne Alternance, pages de candidature à ouvrir |
| `scripts/verifier_sirene.py` | points ouverts de l'API Sirene, bascule NAF 2025 ; `--tous-secteurs` |
| `scripts/explorer_france_travail.py` | téléchargement des référentiels France Travail dans `docs/referentiels/` |
| `scripts/reinitialiser_mot_de_passe.py <email>` | mot de passe temporaire pour un utilisateur qui a oublié le sien |
| `scripts/nettoyer_emails_exclus.py` | règles d'adresses exclues appliquées aux données déjà en base (`--appliquer` pour écrire) |
| `scripts/importer_ancienne_base.py`, `scripts/importer_contacts_historiques.py` | reprise des données de la version mono-utilisateur (déjà faite) |

Les scripts `verifier_*` écrivent leur résultat daté dans `docs/referentiels/` et affichent les valeurs à reporter dans le fichier de paramètres de la source. La procédure de recette réelle est dans `docs/RECETTE.md`.

## Améliorations à venir

- **Téléphones et contact RH** des entreprises, que le scraper ne relève plus depuis le départ de l'IA en ligne.
- **Hébergement** pour un usage à plusieurs, avec un lien de réinitialisation du mot de passe par email (préparé dans `docs/DECISIONS.md`, D124).

## Documentation

Le dossier [`docs/`](docs/) contient le détail du projet :

- [`DECISIONS.md`](docs/DECISIONS.md) : toutes les décisions produit et techniques, leur raison et leur conséquence dans le code ;
- [`SPEC_SOURCES.md`](docs/SPEC_SOURCES.md) : spécification des sources (France Travail, La Bonne Alternance, Sirene) ;
- `PHASE_*_RAPPORT.md` : un rapport par phase de la refonte multi-utilisateurs (changements, tests, limites, points tranchés) ;
- [`RECETTE.md`](docs/RECETTE.md) : procédure de test réel de bout en bout ;
- [`ARCHITECTURE_ACTUELLE.md`](docs/ARCHITECTURE_ACTUELLE.md) : état des lieux de départ de la refonte ;
- `referentiels/` : référentiels officiels téléchargés et résultats des vérifications d'API, datés.
