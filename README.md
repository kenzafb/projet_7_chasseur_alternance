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
- **Analyse par l'IA locale, en différé.** La recherche ajoute les offres « non analysées », sans attendre l'IA. « Analyser les offres en attente » les fait noter une à une (note sur 10, éligibilité, points forts et faibles, catégorie métier), des plus récentes aux plus anciennes, avec une limite par lancement, la progression et le temps restant dans le bandeau, et un bouton d'arrêt. Une option du profil la lance après chaque recherche. Un prompt par mode (alternance, job, stage) ; une analyse archive les offres hors domaine ou inéligibles. Une réponse invalide est redemandée une fois, puis l'offre reste en attente : aucune note n'est jamais inventée.
- **Lettre de motivation** : la trame du profil (ou celle du mode), dont l'IA rédige seulement le bloc destinataire et un paragraphe sur l'entreprise, à la demande.

### Candidatures spontanées

- **Entreprises.** Sirene dans les trois modes : secteurs NAF déduits des domaines (secteurs « cœurs » toutes tailles, secteurs « transverses » pour les entreprises de 250 salariés et plus), ou secteurs choisis, ou case « tous les secteurs » ; filtres par taille (tranches INSEE) et par département. En alternance, s'y ajoutent les entreprises à fort potentiel d'embauche d'alternants repérées par La Bonne Alternance. Dédoublonnage par SIRET puis SIREN, source de chaque entreprise gardée et affichée. Bascule automatique vers la nomenclature NAF 2025 au 1er janvier 2027.
- **Emails.** Un scraper cherche le site de chaque entreprise et lit ses pages (adresses obfusquées comprises). Des règles, dans deux fichiers de données faciles à compléter, décident d'abord : adresses techniques, factices ou inutiles écartées (`shared/referentiels/emails_exclus.txt`, préfixes écartés), adresses de contact ou de recrutement du domaine du site validées (`shared/referentiels/validation_emails.txt`). Les autres sont douteuses : l'IA tranche d'après le texte qui les entoure ; sans elle, elles restent « non validées », jamais envoyées automatiquement, à valider à la main.
- **Envoi.** Chaque utilisateur envoie depuis son propre compte (Gmail avec un mot de passe d'application, ou tout serveur SMTP sur le port 465 ou 587), vérifié par un test de connexion. Objet et message personnalisables avec des balises (`{prenom}`, `{date}`, et en stage `{date_debut}`, `{duree_semaines}`...), pièces jointes, plafond de 50 mails par jour et par utilisateur, arrêt immédiat sur erreur de compte.
- **Mode test**, activé par défaut sur tout nouveau compte d'envoi : chaque candidature part vers l'adresse de l'utilisateur, le vrai destinataire indiqué dans l'objet, et rien n'est marqué comme envoyé. Un bandeau le signale.
- Une adresse déjà contactée dans un mode n'est jamais réécrite dans ce mode ; une entreprise contactée dans un autre mode porte l'étiquette « déjà contactée en alternance le JJ/MM/AAAA », sans bloquer l'envoi.

### Suivi

Statut par entreprise et par mode (envoyée, réponse, entretien, refus), statistiques par source (entreprises, emails trouvés, envois, réponses, entretiens), suivi des offres candidatées. Limites réglables à chaque lancement (offres, nouvelles entreprises, sites scrapés, mails envoyés), bornées par le serveur, et logs des traitements en direct dans l'interface.

## Architecture technique

- **Backend** : Python 3.13, FastAPI, traitements longs dans des threads par utilisateur (une recherche et une étape de spontanées à la fois, arrêt possible).
- **Données** : SQLAlchemy 2, SQLite, schéma unique dans `database/models.py`, migrations Alembic (13 à ce jour).
- **Authentification** : inscription sur code d'invitation, mots de passe hachés (argon2), session par cookie signé (`httponly`, `samesite`, `secure` en production). Toutes les routes sauf connexion et inscription exigent une session.
- **Isolation** : chaque table de données porte l'utilisateur (clé étrangère, suppression en cascade), chaque requête filtre sur l'utilisateur connecté, dédoublonnages, logs et traitements sont propres à chacun.
- **Secrets** : mots de passe SMTP chiffrés en base (Fernet, clé dans `.env`), jamais renvoyés au navigateur.
- **Sources externes** : API Offres d'emploi v2 de France Travail, API de La Bonne Alternance, API Sirene de l'INSEE. Tout ce qui dépend du comportement d'une API est réuni dans un fichier de paramètres par source, vérifié par un script lancé à la main (`scripts/verifier_*.py`).
- **IA** : tout serveur au format compatible OpenAI (`chat/completions`), Ollama sur la machine par défaut, un modèle par usage (analyse, lettre, extraction). Un seul appel à la fois dans tout le processus, réponses contraintes par un schéma JSON et validées par Pydantic (`shared/schemas_ia.py`), serveur injoignable signalé clairement et pipeline arrêté.
- **Interface** : templates Jinja2, JavaScript en modules ES sans framework, PDF générés par WeasyPrint.
- **Tests** : 856 tests automatisés (pytest), APIs externes et IA simulées, aucun appel réseau ni à Ollama, base temporaire migrée par Alembic.

```
main.py              application FastAPI : pages, routes /api, lancement des traitements
auth/                connexion, inscription, session
database/            modèles SQLAlchemy et accès aux données
alembic/             migrations du schéma
france_travail/      offres : France Travail, La Bonne Alternance, analyse (en différé), lettre, PDF
spontanees/          candidatures spontanées : Sirene, scraper d'emails, envoi
shared/              configuration, client d'IA, modes, domaines, NAF, référentiels et règles
scripts/             vérification des API et de l'IA locale, imports et nettoyage, lancés à la main
templates/, static/  interface
tests/               suite pytest
docs/                décisions, spécification des sources, rapports de phase
archive/             code désactivé (bot Telegram)
```

## Installation et lancement

Prérequis : Python 3.13 et les bibliothèques système Pango et Cairo (requises par WeasyPrint) ; Ollama pour l'IA (facultatif, voir plus bas). Clés d'API à demander : France Travail (francetravail.io), La Bonne Alternance, INSEE Sirene.

```bash
git clone <url-du-depot> chasseur_alternance
cd chasseur_alternance
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt        # requirements-dev.txt pour lancer les tests
mkdir -p data                          # base SQLite et fichiers envoyés (hors dépôt)
cp .env.example .env
```

Remplir `.env` en suivant les commentaires de `.env.example`. L'essentiel :

- `SECRET_KEY` (obligatoire, 32 caractères minimum) : `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- `CLE_CHIFFREMENT` (sans elle, l'envoi de mails est désactivé) : `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `DATABASE_URL` : chemin absolu, quatre barres obliques, par exemple `sqlite:////chemin/absolu/vers/chasseur_alternance/data/chasseur_v2.db`
- `CODE_INVITATION` : code à saisir sur `/register` (vide : inscriptions fermées)
- `ANALYSE_IA=true` et les variables `IA_*` de l'IA locale (section suivante) ; `false` pour travailler sans IA
- `FT_CLIENT_ID`, `FT_CLIENT_SECRET`, `LBA_API_KEY`, `INSEE_API_KEY` : identifiants des sources

### IA locale (Ollama)

Installer Ollama (Linux ; pour macOS et Windows, voir [ollama.com/download](https://ollama.com/download)), puis les deux modèles conseillés :

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull ministral-3:8b     # analyse des offres et lettres
ollama pull ministral-3:3b     # validation des emails douteux
```

Mesures sur processeur, sans carte graphique : `ministral-3:8b` lit 27 tokens/s et écrit 7 tokens/s, soit une à deux minutes par offre ; `ministral-3:3b` lit 57 tokens/s et écrit 13 tokens/s. Sur une machine à peu de RAM (12 Go par exemple), n'autoriser qu'un modèle chargé à la fois, sans quoi le passage de l'un à l'autre peut manquer de mémoire :

```bash
sudo systemctl edit ollama         # service installé par le script d'Ollama
# ajouter, puis enregistrer :
#   [Service]
#   Environment="OLLAMA_MAX_LOADED_MODELS=1"
sudo systemctl restart ollama
# ou, sans le service : OLLAMA_MAX_LOADED_MODELS=1 ollama serve
```

Vérifier l'installation et comparer des modèles sur de vraies offres « non analysées » de la base (lues en lecture seule, rien n'est écrit) :

```bash
venv/bin/python scripts/verifier_ia_locale.py
venv/bin/python scripts/verifier_ia_locale.py --modeles ministral-3:8b,ministral-3:3b,qwen3.5:9b
```

Le script affiche, pour chaque modèle, le temps par offre, si le JSON est valide, la note et le verdict proposés, et l'avis sur un email douteux. Un autre modèle se choisit dans `.env` (`IA_MODELE_ANALYSE`, `IA_MODELE_LETTRE`, `IA_MODELE_EXTRACTION`) ; un autre serveur compatible OpenAI (llama.cpp, LM Studio, vLLM, un service en ligne avec `IA_API_KEY`) avec `IA_BASE_URL`.

### Lancement

Créer la base (et la mettre à jour après chaque `git pull`), puis lancer :

```bash
alembic upgrade head
uvicorn main:app --reload --port 5002
```

Ouvrir http://localhost:5002, créer un compte sur `/register` avec le code d'invitation, choisir un mode, remplir le profil, puis configurer le compte d'envoi (Profil, section Compte d'envoi) et le vérifier avec « Tester la connexion ». La documentation de l'API est sur http://localhost:5002/docs une fois connecté. En production derrière HTTPS : `COOKIE_SECURE=true`.

Tests, sous plafond mémoire (seul pytest est tué en cas d'emballement ; chaque test est en outre limité à 30 s) :

```bash
pip install -r requirements-dev.txt
systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q
```

Sur une installation neuve, un test est sauté : il a besoin de l'ancienne base de la version mono-utilisateur, absente.

Les pipelines existent aussi en ligne de commande, pour un utilisateur donné par son identifiant (`--user`, obligatoire) et un mode (`--mode`, `alternance` par défaut) : `python -m spontanees.fetch_entreprises`, `python -m spontanees.scraper_emails`, `python -m spontanees.envoyeur --limite 10 --test`. La reprise des données de l'ancienne version (`scripts/importer_ancienne_base.py`, `scripts/importer_contacts_historiques.py`) et la procédure de recette réelle (`docs/RECETTE.md`) sont documentées dans `docs/`.

## Améliorations à venir

- **Téléphones et contact RH** des entreprises, que le scraper ne relève plus depuis le départ de l'IA en ligne.
- **Mot de passe oublié** et page Paramètres du compte.
- **Hébergement** pour un usage à plusieurs, en dehors d'une machine personnelle.
- **Refonte du bot Telegram** (aujourd'hui archivé) pour le multi-utilisateur.
- **Candidature directe via l'API de La Bonne Alternance**, qui transmet CV et lettre au recruteur sans passer par le scraper ni par le compte mail ; l'identifiant de candidature des entreprises est déjà conservé.

## Documentation

Le dossier [`docs/`](docs/) contient le détail du projet :

- [`DECISIONS.md`](docs/DECISIONS.md) : toutes les décisions produit et techniques, leur raison et leur conséquence dans le code ;
- [`SPEC_SOURCES.md`](docs/SPEC_SOURCES.md) : spécification des sources (France Travail, La Bonne Alternance, Sirene) ;
- `PHASE_*_RAPPORT.md` : un rapport par phase de la refonte multi-utilisateurs (changements, tests, limites, points tranchés) ;
- [`RECETTE.md`](docs/RECETTE.md) : procédure de test réel de bout en bout ;
- [`ARCHITECTURE_ACTUELLE.md`](docs/ARCHITECTURE_ACTUELLE.md) : état des lieux de départ de la refonte ;
- `referentiels/` : référentiels officiels téléchargés et résultats des vérifications d'API, datés.
