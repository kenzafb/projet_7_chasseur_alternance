# Chasseur d'Alternance

Pipeline automatisé de recherche et candidature en alternance DevOps/SysAdmin/Sécurité.
Développé par **Kenza FILALI-BOUAMI** — DEUST IOSI CNAM Paris, rentrée septembre 2026.

---

## Structure du projet

```
chasseur_alternance/
│
├── app.py                          ← Serveur Flask (interface web)
│
├── france_travail/                 ← Système A : offres France Travail
│   ├── scraper.py                  ← Récupère les offres via API France Travail
│   ├── analyseur.py                ← Score 1-10 par Gemini (Vertex AI)
│   ├── generateur.py               ← Génère la lettre de motivation (Gemini)
│   └── pdf_generator.py            ← Génère le PDF de la lettre
│
├── spontanees/                     ← Système B : candidatures spontanées
│   ├── fetch_entreprises.py        ← Récupère les entreprises IT IDF (API Sirene)
│   ├── scraper_emails.py           ← Trouve sites + emails (DuckDuckGo + Gemini)
│   ├── generateur_lettres.py       ← Génère les lettres personnalisées (Gemini)
│   ├── envoyeur.py                 ← Envoie les mails (SMTP Gmail)
│   └── export_excel.py             ← Export Excel du suivi
│
├── shared/
│   └── profil.py                   ← Profil Kenza (compétences, projets, critères)
│
├── data/                           ← Fichiers de données (non versionnés)
│   ├── entreprises_raw.json        ← Source brute Sirene (ne jamais modifier)
│   ├── entreprises_enrichies.json  ← Enrichi par scraper_emails.py
│   ├── candidatures.json           ← Offres FT analysées (interface web)
│   └── offres_vues.json            ← IDs offres déjà vues (anti-doublons)
│
├── assets/                         ← Fichiers fixes
│   ├── CV_Kenza_Filali-Bouami.pdf
│   └── lettre_template_KENZA.docx  ← Template avec balises {{...}}
│
├── lettres_pdf/                    ← Lettre PDF générée (1 seul fichier, écrasé)
│   └── Lettre_Kenza_Filali-Bouami.pdf
│
├── static/
│   └── app.js                      ← Frontend interface web
├── templates/
│   └── index.html                  ← Interface web
│
├── .env                            ← Variables d'environnement (non versionné)
├── .env.example                    ← Exemple de configuration
├── requirements.txt
└── prompt.md                       ← Contexte projet pour IAs
```

---

## ⚙Configuration `.env`

```env
# Vertex AI / GCP
GOOGLE_CLOUD_PROJECT=ton-projet-gcp
GCP_REGION=us-central1

# France Travail API
FT_CLIENT_ID=xxx
FT_CLIENT_SECRET=xxx

# Gmail SMTP
GMAIL_SENDER=ton@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

---

## Lancement

### Prérequis
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
gcloud auth application-default login  # pour Vertex AI
```

### Système A — Interface web France Travail
```bash
python app.py
# → http://localhost:5002
```
Depuis l'interface :
1. **Nouvelle recherche** — scrape les offres France Travail et les analyse
2. **Générer lettre** — génère une lettre personnalisée pour l'offre
3. **PDF** — génère le PDF dans `lettres_pdf/`
4. **Postuler FT** — ouvre l'offre + génère le PDF

### Système B — Candidatures spontanées (pipeline CLI)
```bash
# Étape 1 : récupérer les entreprises IT IDF
python spontanees/fetch_entreprises.py

# Étape 2 : trouver les emails (long, reprend automatiquement)
python spontanees/scraper_emails.py

# Étape 3 : générer les lettres personnalisées
python spontanees/generateur_lettres.py

# Étape 4 : envoyer les candidatures (50/jour)
python spontanees/envoyeur.py --limite 50

# Mode test (envoie tout à ton propre email)
python spontanees/envoyeur.py --test --limite 5

# Export Excel du suivi
python spontanees/export_excel.py
```

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Interface web | Flask + HTML/CSS/JS vanilla |
| IA scoring & génération | Gemini 2.5 Flash/Pro via Vertex AI |
| Scraping offres | API France Travail (OAuth2) |
| Scraping emails | DuckDuckGo (ddgs) + BeautifulSoup |
| Données entreprises | API Recherche Entreprises (Sirene) |
| Envoi mails | SMTP Gmail (mot de passe application) |
| Génération PDF | WeasyPrint |
| Génération DOCX | python-docx |
| Export Excel | openpyxl |

---

## Données

- **6576 entreprises IT** en IDF dans `entreprises_raw.json`
- Scoring des offres : 1-10 avec détection automatique inéligibles
- Archivage automatique des offres écoles/CFA
- Reprise automatique du scraper (champ `traite`)
- Limite 50 mails/jour avec pauses anti-spam (30-90s)

---

## Sécurité

Fichiers **non versionnés** (dans `.gitignore`) :
- `.env`
- `data/`
- `_archive/`

---

## Fichiers importants à ne jamais supprimer

- `data/entreprises_raw.json` — source brute des 6576 entreprises
- `data/entreprises_enrichies.json` — résultat du scraping (en cours)
- `data/candidatures.json` — toutes les offres analysées
- `assets/lettre_template_KENZA.docx` — template avec balises `{{...}}`
- `shared/profil.py` — cerveau du système
