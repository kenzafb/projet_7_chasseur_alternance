# Chasseur d'Alternance

Application web (FastAPI) qui automatise une recherche d'alternance ou de job court en Île-de-France : collecte des offres France Travail et La Bonne Alternance, analyse de chaque offre par Mistral AI, génération de lettres de motivation, et pipeline de candidatures spontanées (entreprises INSEE Sirene, recherche des emails de contact, envoi SMTP). Comptes utilisateurs multiples, un profil par utilisateur et par mode (`alternance`, `job`), données en SQLite.

Projet en cours de refonte. L'état des lieux détaillé est dans `ARCHITECTURE_ACTUELLE.md`, le ménage de la phase 0 dans `PHASE_0_RAPPORT.md`.

## Structure

```
main.py              App FastAPI : pages, routes /api, threads des pipelines
auth/                Connexion, inscription, session
database/            SQLAlchemy : modèles, accès profils / candidatures / entreprises
france_travail/      Offres : scrapers FT et LBA, analyse Mistral, lettre, PDF
spontanees/          Candidatures spontanées : Sirene, scraping des emails, envoi
shared/              config.py (.env, chemins, géographie), ia.py (client Mistral),
                     modes.py, domaines.py, offres.py
templates/, static/  Interface (Jinja2, JS en modules ES)
archive/             Code désactivé (bot Telegram)
data/                Base SQLite, uploads, fichiers de dédup (gitignoré)
```

## Installation

Python 3.13 (venv de référence). WeasyPrint demande les bibliothèques système Pango et Cairo.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # puis remplir les clés
```

La base `data/chasseur.db` doit exister. Pour une base neuve, `database.connexion.creer_tables()` crée les tables à partir de `database/models.py`.

## Lancement

```bash
uvicorn main:app --reload --port 5002
# ou : python main.py
```

Puis http://localhost:5002 (redirige vers `/login`, inscription sur `/register`). Documentation de l'API : http://localhost:5002/docs.

L'envoi des candidatures spontanées existe aussi en ligne de commande :

```bash
python -m spontanees.envoyeur --limite 10 --test --user 1
```

## Licence

MIT.
