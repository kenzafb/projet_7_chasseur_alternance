# Chasseur Alternance 🎯

Outil personnel d'automatisation de recherche d'alternance, construit avec Python, Flask et l'API Claude d'Anthropic.

## Ce que ça fait

- Scrape les offres d'alternance depuis l'API France Travail en Île-de-France
- Analyse chaque offre avec Claude Sonnet (scoring /10, éligibilité, points forts/faibles)
- Génère des lettres de motivation personnalisées et des emails de candidature
- Exporte les lettres en PDF avec mise en page professionnelle
- Envoie les candidatures par Gmail avec lettre PDF et CV en pièces jointes
- Interface web pour tout gérer : suivi des statuts, relances, entretiens

## Stack technique

- **Backend** : Python 3, Flask
- **IA** : API Anthropic (Claude Sonnet pour l'analyse et les lettres, Claude Haiku pour les emails)
- **Scraping** : API France Travail (OAuth2)
- **Email** : Gmail API (OAuth2)
- **PDF** : WeasyPrint
- **Frontend** : HTML/CSS/JS vanilla

## Structure du projet

```
chasseur_alternance/
├── app.py              # Serveur Flask + routes API
├── analyseur.py        # Analyse des offres avec Claude
├── generateur.py       # Génération lettres et emails
├── scraper.py          # Scraping France Travail
├── main.py             # Orchestrateur principal
├── connexion.py        # Authentification Gmail
├── envoi_gmail.py      # Envoi des candidatures
├── pdf_generator.py    # Export PDF des lettres
├── profil.py           # Profil candidat (compétences, projets...)
├── static/app.js       # Interface web
├── .env.example        # Variables d'environnement à configurer
└── requirements.txt    # Dépendances Python
```

## Installation

### Prérequis
- Python 3.10+
- Un compte Anthropic avec crédits API
- Un compte France Travail Recruteur (API gratuite)
- Un compte Google avec Gmail API activée

### 1. Cloner le repo

```bash
git clone https://github.com/kenzafb/chasseur-alternance.git
cd chasseur-alternance
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt --break-system-packages
```

### 3. Configurer les variables d'environnement

```bash
cp .env.example .env
nano .env
```

Remplis les valeurs :

```
ANTHROPIC_API_KEY=sk-ant-xxx
FT_CLIENT_ID=PAR_xxx
FT_CLIENT_SECRET=xxx
```

### 4. Configurer Gmail

- Va sur [console.cloud.google.com](https://console.cloud.google.com)
- Crée un projet, active l'API Gmail
- Crée des identifiants OAuth2 (Application de bureau)
- Télécharge le fichier et renomme-le `credentials.json`
- Place-le à la racine du projet

### 5. Configurer ton profil

Édite `profil.py` avec tes informations personnelles, compétences et projets.

### 6. Ajouter ton CV

Place ton CV PDF à la racine sous le nom `CV_Ton_Nom.pdf` et mets à jour la variable `CV_PATH` dans `envoi_gmail.py`.

### 7. Lancer l'application

```bash
python3 app.py
```

Ouvre [http://localhost:5002](http://localhost:5002)

## Utilisation

1. **Nouvelle recherche** → scrape les offres France Travail et les analyse automatiquement
2. **Analyser** → relance l'analyse IA sur une offre spécifique
3. **Générer lettre** → lettre de motivation personnalisée pour l'offre
4. **PDF** → télécharge la lettre en PDF prête à envoyer
5. **Postuler sur France Travail** → télécharge le PDF et ouvre la page de l'offre
6. **Générer email + Envoyer** → envoie la candidature complète par Gmail (lettre PDF + CV)

## Variables d'environnement

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Clé API Anthropic |
| `FT_CLIENT_ID` | Client ID France Travail |
| `FT_CLIENT_SECRET` | Secret France Travail |

## Projet réalisé dans le cadre

DSP DevOps — CNAM Paris (2025-2026)
Projet personnel — non affilié à France Travail ni à Anthropic
