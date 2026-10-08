# Chasseur d'Alternance

Application web (FastAPI) qui automatise une recherche d'alternance ou de job court en Île-de-France : collecte des offres France Travail et La Bonne Alternance, analyse de chaque offre par Mistral AI, génération de lettres de motivation, et pipeline de candidatures spontanées (entreprises INSEE Sirene, recherche des emails de contact, envoi SMTP). Comptes utilisateurs multiples, un profil par utilisateur et par mode (`alternance`, `job`), données en SQLite.

Projet en cours de refonte. L'état des lieux détaillé est dans `docs/ARCHITECTURE_ACTUELLE.md`, les rapports de phase dans `docs/PHASE_*_RAPPORT.md`.

## Structure

```
main.py              App FastAPI : pages, routes /api, threads des pipelines
auth/                Connexion, inscription, session
database/            SQLAlchemy : models.py (schéma, seule source de vérité), accès aux données
alembic/             Migrations du schéma (alembic upgrade head)
scripts/             importer_ancienne_base.py (comptes et profils de l'ancienne base)
france_travail/      Offres : scrapers FT et LBA, analyse Mistral, lettre, PDF
spontanees/          Candidatures spontanées : Sirene, scraping des emails, envoi
shared/              config.py (.env, chemins, géographie), ia.py (client Mistral),
                     modes.py, domaines.py, offres.py
templates/, static/  Interface (Jinja2, JS en modules ES)
archive/             Code désactivé (bot Telegram)
data/                Base SQLite, uploads, fichiers de dédup (gitignoré)
```

## Installation de zéro

Python 3.13 (venv de référence). WeasyPrint demande les bibliothèques système Pango et Cairo.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # puis remplir les clés
```

Dans `.env` :
- `SECRET_KEY` est obligatoire (32 caractères minimum, l'application refuse de démarrer sinon) : `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `DATABASE_URL` désigne la base. Pour un fichier SQLite, chemin absolu avec quatre barres obliques : `DATABASE_URL=sqlite:////home/moi/chasseur_alternance/data/chasseur_v2.db`. Vide ou absente : `data/chasseur.db`, l'ancienne base, que la nouvelle version ne sait pas lire.
- `CODE_INVITATION` ouvre l'inscription : sans lui, `/register` est fermé. `COOKIE_SECURE=true` en production derrière HTTPS.
- `CLE_CHIFFREMENT` chiffre les mots de passe SMTP des comptes d'envoi : `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Sans elle, l'application démarre mais l'envoi de mails est désactivé. La changer rend illisibles les mots de passe déjà enregistrés (chacun devra ressaisir le sien). `PLAFOND_ENVOIS_JOUR` (50 par défaut) borne les mails envoyés par utilisateur et par jour.

Puis créer la base (ou la mettre à jour après un `git pull`) :

```bash
alembic upgrade head
```

Le schéma est défini dans `database/models.py` ; après l'avoir modifié, générer une migration avec `alembic revision --autogenerate -m "..."`, la relire, puis `alembic upgrade head`. `alembic check` vérifie qu'aucune modification de `models.py` n'est oubliée. Alembic refuse de toucher une base qui a des tables sans avoir été créée par lui (l'ancienne base).

## Reprendre les comptes de l'ancienne base

L'ancienne `data/chasseur.db` (schéma d'avant Alembic) n'est pas migrée en place. Le script `scripts/importer_ancienne_base.py` copie dans une base neuve les comptes 1, 3 et 4 (même identifiant, même mot de passe) et tous leurs profils (alternance et job), sans candidatures, entreprises ni fichiers de dédoublonnage. La source est ouverte en lecture seule ; le script refuse si source et cible sont le même fichier ou si la cible contient déjà des comptes, et applique lui-même `alembic upgrade head` sur la cible.

```bash
# 1. Essai à blanc : affiche ce qui serait importé, n'écrit rien
python scripts/importer_ancienne_base.py --source data/chasseur.db --cible data/chasseur_v2.db --dry-run
# 2. Import réel
python scripts/importer_ancienne_base.py --source data/chasseur.db --cible data/chasseur_v2.db
# 3. Dans .env : DATABASE_URL=sqlite:////chemin/absolu/vers/data/chasseur_v2.db, puis relancer l'app
```

Les pièces jointes restent dans `data/uploads/` : seuls leurs chemins en base changent (relatifs à ce dossier). Le résumé final liste celles qui manquent ou n'ont pas d'extension.

## Lancement

Après `alembic upgrade head` :

```bash
uvicorn main:app --reload --port 5002
# ou : python main.py
```

Puis http://localhost:5002 (redirige vers `/login`, inscription sur `/register` avec le code d'invitation). Documentation de l'API, une fois connecté : http://localhost:5002/docs.

Chaque utilisateur envoie ses candidatures spontanées depuis son propre compte, configuré dans Profil, section Compte d'envoi (Gmail avec un mot de passe d'application, ou un autre serveur SMTP sur le port 465 ou 587), puis vérifié par « Tester la connexion ». Sans compte vérifié, l'envoi est refusé. L'envoi existe aussi en ligne de commande, avec le compte de l'utilisateur désigné :

```bash
python -m spontanees.envoyeur --user 1 --limite 10 --test
```

`--user` (identifiant du compte) est obligatoire pour les trois scripts : `spontanees.fetch_entreprises`, `spontanees.scraper_emails` et `spontanees.envoyeur`.

**Mode test.** Une case du compte d'envoi redirige toutes les candidatures spontanées vers l'adresse d'expédition de l'utilisateur, le vrai destinataire dans l'objet (`[TEST → rh@entreprise.fr] ...`) ; rien n'est enregistré comme contacté ni marqué envoyé. Un bandeau le signale sur la page Spontanées, et les logs du pipeline le répètent à chaque mail. `--test` en ligne de commande a le même effet pour un lancement.

**Limites par lancement**, réglées dans l'interface au moment de lancer, bornées par le serveur (`LIMITES_LANCEMENT` dans `shared/config.py`) : offres analysées par Mistral (30 par défaut, 200 au plus, France Travail et LBA ensemble), nouvelles entreprises récupérées (200, 5000), entreprises scrapées (20, 200), mails envoyés (10, 50).

Procédure de test réel de bout en bout : `docs/RECETTE.md`. Décisions prises hors du code : `docs/DECISIONS.md`.

## Tests

```bash
pip install -r requirements-dev.txt
systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q
```

Base SQLite temporaire créée par `alembic upgrade head`, réseau, Mistral et SMTP neutralisés, vrai `.env` ignoré. Le plafond mémoire fait que seul pytest est tué en cas d'emballement ; chaque test est en outre limité à 30 s (`pytest-timeout`, réglé dans `pytest.ini`). Les tests à threads passent par `en_parallele` (`tests/conftest.py`) : barrière, `join` et attentes ont tous un délai.

## Licence

MIT.
