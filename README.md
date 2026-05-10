# Chasseur d'Alternance

Outil Python que j'ai développé pendant mon stage au Garage Numérique pour automatiser ma recherche d'alternance. Il interroge l'API France Travail, analyse chaque offre avec un LLM (Gemini via Google Cloud), génère des lettres de motivation personnalisées et envoie des candidatures spontanées par email.

> Construit par **Kenza Filali-Bouami** — DSP DevOps CNAM Paris, future étudiante DEUST IOSI en alternance (septembre 2026).

---

## Fonctionnalités

**Pipeline offres France Travail**
- Scraping automatique de l'API France Travail sur 23 requêtes ciblées (DevOps, Sys/Réseau, Support, Dev...)
- Analyse IA de chaque offre : score /10, éligibilité, points forts/faibles, verdict — via Gemini 2.5 Flash
- Génération de lettres de motivation personnalisées (template fixe + paragraphe IA) via Gemini 2.5 Pro
- Export PDF des lettres avec WeasyPrint
- Interface web de suivi : filtres, tri, statuts, sauvegarde auto

**Pipeline candidatures spontanées**
- Récupération des entreprises IT IDF via l'API Recherche Entreprises (codes NAF 62.*)
- Recherche des sites web via DuckDuckGo + validation du domaine
- Scraping des emails de contact (BeautifulSoup + Gemini pour filtrage intelligent)
- Génération de mails personnalisés (1-2 phrases IA par entreprise)
- Envoi SMTP Gmail avec CV et plaquette DEUST en pièces jointes
- Export Excel de suivi (3 feuilles : candidatures, stats, données brutes)

---

## Stack technique

| Composant | Technologie |
|---|---|
| Backend | Python 3.13, Flask |
| IA | Gemini 2.5 Flash / Pro via Vertex AI (Google Cloud) |
| Scraping offres | API France Travail OAuth2 |
| Scraping emails | DuckDuckGo (ddgs), BeautifulSoup4, Gemini |
| Données entreprises | API Recherche Entreprises (api.gouv.fr) |
| PDF | WeasyPrint |
| Excel | openpyxl |
| Envoi email | SMTP Gmail (App Password) |
| Frontend | HTML/CSS/JS vanilla (pas de framework) |

---

## Structure du projet

```
chasseur_alternance/
├── app.py                          # Serveur Flask — toutes les routes API
├── france_travail/
│   ├── scraper.py                  # Scraping API France Travail
│   ├── analyseur.py                # Analyse IA des offres (Gemini)
│   ├── generateur.py               # Génération des lettres (Gemini)
│   ├── pdf_generator.py            # Export PDF (WeasyPrint)
│   └── main.py                     # Orchestration recherche + sauvegarde
├── spontanees/
│   ├── fetch_entreprises.py        # Récupération entreprises IT IDF
│   ├── scraper_emails.py           # Scraping emails + Gemini
│   ├── generateur_mail.py          # Génération mails personnalisés
│   ├── envoyeur.py                 # Envoi SMTP Gmail
│   └── export_excel.py             # Export Excel de suivi
├── shared/
│   ├── profil.py                   # Profil candidat (gitignore)
│   └── profil.example.py           # Template profil à copier
├── templates/index.html            # Interface web
├── static/app.js                   # Logique frontend
├── assets/                         # CV + plaquette (gitignore)
├── data/                           # JSON générés (gitignore)
├── lettres_pdf/                    # PDF générés (gitignore)
├── .env                            # Variables d'environnement (gitignore)
├── .env.example                    # Template .env
└── requirements.txt
```

---

## Installation

### Prérequis

- Python 3.11+
- Un projet Google Cloud avec Vertex AI activé
- Un compte France Travail API (gratuit) : [francetravail.io](https://francetravail.io)
- Un App Password Gmail pour l'envoi SMTP

### Mise en place

```bash
# Cloner le projet
git clone https://github.com/kenzafb/chasseur-alternance
cd chasseur-alternance

# Créer et activer l'environnement virtuel
python -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer les variables d'environnement
cp .env.example .env
nano .env

# Configurer votre profil
cp shared/profil.example.py shared/profil.py
nano shared/profil.py
```

### Configuration `.env`

```bash
# Google Cloud / Vertex AI
GOOGLE_CLOUD_PROJECT=votre-projet-gcp
GCP_REGION=us-central1

# France Travail API
FT_CLIENT_ID=PAR_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FT_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Gmail SMTP
GMAIL_SENDER=votre.email@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# Debug scraper emails (true/false)
DEBUG_SCRAPER=false
```

---

## Utilisation

### Lancer l'interface web

```bash
python app.py
# → http://localhost:5002
```

L'interface permet de gérer tout le pipeline offres France Travail : recherche, analyse, lettre, PDF, statuts.

### Pipeline candidatures spontanées

Les 4 étapes sont accessibles depuis l'onglet **Spontanées** de l'interface, ou en ligne de commande :

```bash
# Étape 1 — Récupérer les entreprises IT IDF
python -m spontanees.fetch_entreprises

# Étape 2 — Scraper les emails de contact
python -m spontanees.scraper_emails

# Étape 3 — Générer les mails personnalisés
python -m spontanees.generateur_mail

# Étape 4 — Envoyer (--test pour envoyer à soi-même)
python -m spontanees.envoyeur --limite 10 --test

# Export Excel de suivi
python -m spontanees.export_excel
```

---

## Adapter à votre profil

Tout ce qui vous concerne est centralisé dans `shared/profil.py` :

- Informations personnelles (nom, email, téléphone, LinkedIn, GitHub)
- Formation et compétences techniques
- Projets GitHub
- Expérience professionnelle
- Mots-clés de recherche (titre des postes visés)

La lettre de motivation est un **template fixe** (`france_travail/generateur.py`) — seul le paragraphe de personnalisation est généré par l'IA. Modifiez le template pour l'adapter à votre parcours.

---

## Ce qui est exclu du dépôt (`.gitignore`)

| Fichier / dossier | Raison |
|---|---|
| `.env` | Clés API et credentials |
| `shared/profil.py` | Données personnelles |
| `assets/` | CV et documents personnels |
| `data/` | JSON générés (offres, entreprises) |
| `lettres_pdf/` | Lettres générées |

---

## Licence

MIT — libre d'utilisation, d'adaptation et de redistribution.
