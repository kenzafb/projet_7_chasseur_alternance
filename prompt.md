# 🤖 PROMPT D'INTRODUCTION — CHASSEUR D'ALTERNANCE

Tu vas m'aider à travailler sur mon projet Python appelé **Chasseur d'Alternance**.
Ce fichier contient tout le contexte dont tu as besoin : mon profil, la structure du projet, et le contenu de tous les fichiers clés.

---

## 🎯 Qui je suis

**Kenza FILALI-BOUAMI**, étudiante au CNAM Paris.
- Formation actuelle : DSP DevOps (Bac+1), stage terminé au Garage Numérique (mars-avril 2026)
- Prochaine formation : DEUST IOSI parcours Technicien Développement, Sécurité et Exploitation (Bac+2), 2e année en alternance, démarrage septembre 2026
- Recherche : alternance DevOps / SysAdmin / Sécurité, IDF, septembre 2026
- Stack : Linux (Debian/Ubuntu/Arch), Docker, Bash, Python (FastAPI/Flask), Git, Node.js, HTML/CSS/JS, MySQL, TCP/IP/DNS/DHCP, CI/CD, IA/LLM
- Mail : kenzafilbou@gmail.com | GitHub : github.com/kenzafb

---

## 🗂 Ce qu'est le projet

Un pipeline Python complet en **deux systèmes distincts** :

### Système A — France Travail (interface web)
Scrape les offres d'alternance via l'API France Travail → les analyse avec Gemini (score 1-10, éligibilité) → permet de générer une lettre de motivation personnalisée et un PDF → pour postuler manuellement sur le site.

Fichiers : `france_travail/scraper.py` → `france_travail/analyseur.py` → `france_travail/generateur.py` → `france_travail/pdf_generator.py`
Piloté par `app.py` (Flask) + interface web (`templates/index.html` + `static/app.js`)
Données dans `data/candidatures.json`

### Système B — Candidatures spontanées (pipeline CLI)
Récupère les entreprises IT IDF via l'API Sirene → trouve leurs sites et emails via DuckDuckGo + BeautifulSoup + Gemini → génère des lettres personnalisées (template DOCX avec balises) → envoie par SMTP Gmail.

Fichiers : `spontanees/fetch_entreprises.py` → `spontanees/scraper_emails.py` → `spontanees/generateur_lettres.py` → `spontanees/envoyeur.py`
Données dans `data/entreprises_raw.json` et `data/entreprises_enrichies.json`

---

## 📁 Structure complète

```
chasseur_alternance/
├── app.py                          ← Flask, point d'entrée web
├── france_travail/
│   ├── scraper.py                  ← API France Travail
│   ├── analyseur.py                ← Scoring Gemini
│   ├── generateur.py               ← Génération lettre Gemini
│   └── pdf_generator.py            ← PDF WeasyPrint
├── spontanees/
│   ├── fetch_entreprises.py        ← API Sirene
│   ├── scraper_emails.py           ← DuckDuckGo + BS4 + Gemini
│   ├── generateur_lettres.py       ← Lettres DOCX Gemini
│   ├── envoyeur.py                 ← SMTP Gmail
│   └── export_excel.py             ← Export suivi openpyxl
├── shared/
│   └── profil.py                   ← Profil Kenza (cerveau du système)
├── data/                           ← JSON de données (non versionnés)
├── assets/                         ← CV PDF + template DOCX
├── lettres_pdf/                    ← 1 seul PDF généré, écrasé à chaque fois
├── static/app.js                   ← Frontend
└── templates/index.html            ← Interface web
```

---

## ⚙️ Stack technique

- **Python 3.13**, venv, Debian Linux
- **Gemini via Vertex AI** (google-genai SDK) — projet GCP, modèle `gemini-2.5-flash` / `gemini-2.5-pro` — authentification via `gcloud` ADC, PAS de clé API
- **France Travail API** — OAuth2 client credentials, variables `FT_CLIENT_ID` / `FT_CLIENT_SECRET`
- **DuckDuckGo** — lib `ddgs`, pauses anti-rate-limit intégrées
- **Gmail SMTP** — `smtplib` + mot de passe application (variable `GMAIL_APP_PASSWORD`)
- **python-docx** — génération lettres depuis template avec balises `{{NOM_ENTREPRISE}}` etc.
- **WeasyPrint** — génération PDF lettres France Travail

---

## 🔑 Points importants à retenir

- Gemini est sur **Vertex AI** (pas AI Studio) → pas de clé API, auth via `gcloud ADC`
- Le modèle s'appelle `"gemini-2.5-flash"` sans préfixe `models/` sur Vertex AI
- `shared/profil.py` est importé partout avec `from shared.profil import PROFIL`
- Le scraper reprend automatiquement grâce au champ `traite: true` dans le JSON
- Le PDF généré est toujours `lettres_pdf/Lettre_Kenza_Filali-Bouami.pdf` (écrasé à chaque fois)
- Les postes "Ingénieur" pour un poste occupé → inéligibles (score max 2)
- Les offres écoles/CFA → archivées automatiquement
- Pas d'envoi Gmail depuis l'interface web pour les offres France Travail (on postule directement sur le site)

---

## 🚀 Comment lancer

```bash
source venv/bin/activate

# Système A — interface web
python app.py  # → http://localhost:5002

# Système B — pipeline CLI
python spontanees/fetch_entreprises.py      # 1 fois
python spontanees/scraper_emails.py         # long, reprend auto
python spontanees/generateur_lettres.py     # relancer régulièrement
python spontanees/envoyeur.py --limite 50   # chaque jour
```

---

## 📋 Comment m'aider efficacement

- Si tu as besoin de voir un fichier, demande-moi de te l'envoyer avec `cat nom_fichier.py`
- Si tu me donnes du code à modifier, donne-moi la commande `sed` ou le fichier complet
- Les fichiers de données (`data/*.json`) sont volumineux, je t'enverrai juste les premières lignes si besoin
- Je travaille sur Debian Linux avec le venv activé

---

Le contenu détaillé de tous les fichiers suit ci-dessous.


--- FICHIER : app.py ---
from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
from france_travail.main import lancer_recherche, charger_candidatures, sauvegarder_candidatures
from france_travail.generateur import generer_lettre
from france_travail.analyseur import analyser_offre
from france_travail.pdf_generator import generer_pdf_lettre
from datetime import datetime
import threading
import os

load_dotenv()
app = Flask(__name__)

# État de la recherche en cours
etat_recherche = {"en_cours": False, "message": "Prêt"}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/candidatures")
def api_candidatures():
    return jsonify(charger_candidatures())

@app.route("/api/recherche", methods=["POST"])
def api_recherche():
    if etat_recherche["en_cours"]:
        return jsonify({"erreur": "Recherche déjà en cours"}), 400

    def lancer():
        etat_recherche["en_cours"] = True
        etat_recherche["message"] = "Recherche des offres..."
        try:
            lancer_recherche(analyser=True, max_analyse=999)
            etat_recherche["message"] = "Terminé !"
        except Exception as e:
            etat_recherche["message"] = f"Erreur : {e}"
        finally:
            etat_recherche["en_cours"] = False

    threading.Thread(target=lancer, daemon=True).start()
    return jsonify({"status": "démarré"})

@app.route("/api/statut_recherche")
def api_statut_recherche():
    return jsonify(etat_recherche)

@app.route("/api/generer_lettre", methods=["POST"])
def api_generer_lettre():
    data = request.get_json()
    offre_id = data.get("id")
    candidatures = charger_candidatures()
    offre = next((c for c in candidatures if c["id"] == offre_id), None)
    if not offre:
        return jsonify({"erreur": "Offre introuvable"}), 404
    lettre = generer_lettre(offre)
    for c in candidatures:
        if c["id"] == offre_id:
            c["lettre"] = lettre
            c["statut"] = "en_cours"
            break
    sauvegarder_candidatures(candidatures)
    return jsonify({"lettre": lettre})

@app.route("/api/analyser", methods=["POST"])
def api_analyser():
    data = request.get_json()
    offre_id = data.get("id")
    candidatures = charger_candidatures()
    offre = next((c for c in candidatures if c["id"] == offre_id), None)
    if not offre:
        return jsonify({"erreur": "Offre introuvable"}), 404
    analyse = analyser_offre(offre)
    for c in candidatures:
        if c["id"] == offre_id:
            c.update({
                "score": analyse.get("score", 5),
                "verdict": analyse.get("verdict", "moyen"),
                "eligible": analyse.get("eligible", True),
                "points_forts": analyse.get("points_forts", []),
                "points_faibles": analyse.get("points_faibles", []),
                "resume_analyse": analyse.get("resume", "")
            })
            break
    sauvegarder_candidatures(candidatures)
    return jsonify(analyse)

@app.route("/api/maj_statut", methods=["POST"])
def api_maj_statut():
    data = request.get_json()
    offre_id = data.get("id")
    statut = data.get("statut")
    candidatures = charger_candidatures()
    for c in candidatures:
        if c["id"] == offre_id:
            c["statut"] = statut
            if statut in ["envoye", "reponse", "entretien", "refus"]:
                if not c.get("date_candidature"):
                    c["date_candidature"] = datetime.now().strftime("%Y-%m-%d")
            break
    sauvegarder_candidatures(candidatures)
    return jsonify({"ok": True})

@app.route("/api/archiver", methods=["POST"])
def api_archiver():
    data = request.get_json()
    offre_id = data.get("id")
    cands = charger_candidatures()
    for c in cands:
        if c["id"] == offre_id:
            c["statut"] = "archive"
            break
    sauvegarder_candidatures(cands)
    return jsonify({"ok": True})

@app.route("/api/sauvegarder", methods=["POST"])
def api_sauvegarder():
    data = request.get_json()
    offre_id = data.get("id")
    candidatures = charger_candidatures()
    for c in candidatures:
        if c["id"] == offre_id:
            if "lettre" in data: c["lettre"] = data["lettre"]
            if "email_candidature" in data: c["email_candidature"] = data["email_candidature"]
            if "objet_email" in data: c["objet_email"] = data["objet_email"]
            break
    sauvegarder_candidatures(candidatures)
    return jsonify({"ok": True})

@app.route("/api/telecharger_pdf", methods=["POST"])
def api_telecharger_pdf():
    data = request.get_json()
    offre_id = data.get("id")
    cands = charger_candidatures()
    offre = next((c for c in cands if c["id"] == offre_id), None)
    if not offre: return jsonify({"erreur": "Non trouvé"}), 404
    lettre = data.get("lettre") or offre.get("lettre")
    if not lettre: return jsonify({"erreur": "Vide"}), 400
    chemin = generer_pdf_lettre(offre, lettre)
    return jsonify({"ok": True, "chemin": chemin})

if __name__ == "__main__":
    print("\n🚀 Chasseur Alternance démarré sur http://localhost:5002\n")
    app.run(debug=False, port=5002)



--- FICHIER : README.md ---
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



--- FICHIER : requirements.txt ---
# Web
flask==3.1.0

# Google / Vertex AI
google-genai
google-auth==2.49.1
google-auth-httplib2==0.3.0
google-auth-oauthlib==1.3.0
google-api-python-client==2.192.0

# Scraping
requests==2.32.3
beautifulsoup4==4.13.3
ddgs

# Documents
python-docx
weasyprint==68.1
openpyxl

# Utils
python-dotenv==1.2.2
anthropic==0.85.0



--- FICHIER : france_travail/analyseur.py ---
import time
import json
import re
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from shared.profil import PROFIL

load_dotenv()

client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location="us-central1"
)
MODELE = "gemini-2.5-flash"


def construire_contexte_profil():
    competences = ", ".join(PROFIL["competences"])
    projets = " | ".join([f"{p['nom']} : {p['description']}" for p in PROFIL["projets"]])
    return (
        "Candidate : Kenza Filali-Bouami, Paris 9e / Issy-les-Moulineaux, Navigo toutes zones IDF.\n"
        "\n"
        "NIVEAU : Bac+1 DSP DevOps CNAM (admin systemes, reseaux, scripting, dev web, algo, Java, BDD, Cloud, CMS).\n"
        "Integre DEUST IOSI Bac+2 en alternance septembre 2026.\n"
        "Programme DEUST : POO avancee, algo avancee, BDD relationnelles, dev web serveur, "
        "administration systeme/reseau, securite, gestion de projet, anglais professionnel.\n"
        "\n"
        f"COMPETENCES ACTUELLES : {competences}\n"
        "\n"
        f"PROJETS : {projets}\n"
        "\n"
        "EXPERIENCE : Stage technicienne au Garage Numerique (maintenance hardware/software, "
        "installation Linux Arch/Debian, support utilisateurs non-techniciens, dev web WordPress/HTML-CSS).\n"
        "\n"
        "DISPONIBILITE : alternance septembre 2026, IDF uniquement, 1 ou 2 ans."
    )


def analyser_offre(offre):
    contexte = construire_contexte_profil()

    prompt = (
        "Tu es un recruteur IT experimente. Evalue cette offre pour la candidate ci-dessous.\n"
        "Reponds UNIQUEMENT en JSON valide, sans backticks, sans texte autour.\n\n"
        f"=== PROFIL CANDIDATE ===\n{contexte}\n\n"
        f"=== OFFRE ===\n"
        f"Titre : {offre.get('titre', '')}\n"
        f"Entreprise : {offre.get('entreprise', '')}\n"
        f"Lieu : {offre.get('lieu', '')}\n"
        f"Description : {offre.get('description', '')}\n\n"
        "=== REGLES D'ELIGIBILITE ===\n"
        "INELIGIBLE (eligible:false, score max 2) si :\n"
        "- Le poste n'a aucun rapport avec l'informatique, le developpement, les systemes/reseaux, la data ou l'IA.\n"
        "- L'offre exige explicitement un niveau Master, Bac+4, Bac+5, ou mentionne 'cycle ingenieur' "
        "comme prerequis d'entree (pas comme diplome prepare).\n"
        "- L'offre exige 3+ ans d'experience professionnelle.
- Le poste n'a aucun rapport avec l'informatique technique : exclure les postes commerciaux, marketing, RH, finance, juridique, analyst metier non-technique, sales, business developer, meme si mentionne "IT" ou "data".\n"
        "\n"
        "REGLE STRICTE sur le mot 'Ingenieur' dans le titre ou la description :\n"
        "- Si 'Ingenieur' designe le POSTE OCCUPE (ex: 'Alternance Ingenieur DevOps', 'Ingenieur logiciel') "
        "et que l'offre n'est pas d'une ecole/CFA cherchant un etudiant → INELIGIBLE (score max 2).\n"
        "- Si l'offre est proposee par une ecole/CFA/organisme de formation (ISCOD, Scholia, IMC, "
        "MyDigitalSchool, Simplon, AFPA, etc.) pour PREPARER un diplome → ELIGIBLE, "
        "mais archiver automatiquement (statut: 'archive') car ces ecoles collectent les infos "
        "sans transmettre directement au recruteur.\n"
        "\n"
        "=== COMPETENCES A EVALUER ===\n"
        "Competences maitrisees maintenant : Linux, Bash, Python (Flask/FastAPI), Docker, Git, "
        "HTML/CSS/JS, TCP/IP/DNS/DHCP/SSH, Node.js, WordPress, C, virtualisation, IA/LLM, projets GitHub.\n"
        "Competences en cours (DSP) : algo, Java bases, HTML/CSS avance, BDD bases, scripting avance.\n"
        "Competences a venir (DEUST) : POO avancee, BDD relationnelles, dev serveur, securite reseau, "
        "admin systeme avancee, gestion projet.\n"
        "\n"
        "Pour les competences manquantes, distingue :\n"
        "- Competence absente mais dans le programme DEUST (Java, securite, BDD, POO) → point faible mineur, "
        "elle l'apprendra durant l'alternance.\n"
        "- Competence absente et hors programme (Azure, Kubernetes, .NET, COBOL, Mainframe) → point faible important.\n"
        "\n"
        "=== SCORING ===\n"
        "Ne jamais penaliser pour la date de debut ou disponibilite : ignorer ce critere.\n"
        "Localisation : toute l'IDF est acceptable. -1 point max pour grande couronne (77/78/91/95) "
        "si vraiment eloigne. Ne pas penaliser petite couronne (92/93/94).\n"
        "\n"
        "9-10 : alternance IT explicite Bac+2, competences principales matchent, Paris ou petite couronne.\n"
        "7-8  : bon match technique global, 1-2 lacunes dans des competences a venir au DEUST, "
        "ou grande couronne.\n"
        "5-6  : match partiel - competences importantes manquantes ET hors programme DEUST, "
        "ou techno tres specifique absente (.NET, Java avance).\n"
        "3-4  : peu de correspondance - poste trop specifique ou trop eloigne du profil.\n"
        "1-2  : ineligible (hors IT, niveau trop eleve, experience requise).\n"
        "\n"
        "PENALITE BAC+3 : si l'offre demande explicitement Bac+3/Licence ou superieur comme niveau "
        "MINIMUM d'entree, retire 4 points au score final (la candidate n'a pas encore Bac+2). "
        "Un score 9 avec penalite Bac+3 donne donc 5 maximum.\n"
        "\n"
        "Differencie bien les scores : ne mets pas tout a 8 ou 9.\n\n"
        "=== FORMAT DE REPONSE ===\n"
        '{"score": 7, "verdict": "bon", "eligible": true, '
        '"points_forts": ["max 3 points concrets lies a l\'offre"], '
        '"points_faibles": ["max 2 points, distinguer manquant-maintenant vs manquant-DEUST"], '
        '"resume": "max 12 mots factuels"}'
    )

    # Détection écoles/CFA → archivage automatique
    ECOLES_MOTS_CLES = [
        "iscod", "scholia", "imc alternance", "mydigitalschool", "simplon",
        "afpa", "cfa", "epitech", "openclassrooms", "studi", "ikigai",
        "la plateforme", "digital campus", "m2i", "doranco", "efficom",
        "ecole", "organisme de formation", "centre de formation"
    ]
    description_lower = offre.get("description", "").lower()
    entreprise_lower = offre.get("entreprise", "").lower()
    titre_lower = offre.get("titre", "").lower()
    est_ecole = any(
        mot in description_lower or mot in entreprise_lower or mot in titre_lower
        for mot in ECOLES_MOTS_CLES
    )

    try:
        response = client.models.generate_content(
            model=MODELE,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Tu es un recruteur IT. Tu reponds UNIQUEMENT en JSON valide sans backticks. "
                    "Tu ignores totalement la date de debut et la disponibilite dans ta notation."
                ),
                response_mime_type="application/json",
            )
        )
        texte = response.text
        texte = re.sub(r'```json\s*', '', texte)
        texte = re.sub(r'```\s*', '', texte)
        result = json.loads(texte)
        if "score" in result:
            result["score"] = max(1, min(10, int(result["score"])))
        if not result.get("eligible", True):
            result["score"] = min(result["score"], 2)
            result["verdict"] = "faible"
        if est_ecole:
            result["statut_auto"] = "archive"
            print(f"     → Archivée automatiquement (école/CFA détectée)")
        return result
    except Exception as e:
        print(f"  Erreur analyse : {e}")
        return {
            "score": 5, "verdict": "erreur", "eligible": True,
            "points_forts": [], "points_faibles": [], "resume": "Erreur analyse"
        }


def analyser_offres(offres, callback=None):
    offres_analysees = []
    for i, offre in enumerate(offres, 1):
        print(f"  [{i}/{len(offres)}] {offre['titre'][:50]}...")
        analyse = analyser_offre(offre)
        offre.update({
            "score": analyse.get("score", 5),
            "verdict": analyse.get("verdict", "moyen"),
            "eligible": analyse.get("eligible", True),
            "points_forts": analyse.get("points_forts", []),
            "points_faibles": analyse.get("points_faibles", []),
            "resume_analyse": analyse.get("resume", "")
        })
        if analyse.get("statut_auto") == "archive":
            offre["statut"] = "archive"
        eligible_str = "eligible" if offre["eligible"] else "INELIGIBLE"
        print(f"     Score : {offre['score']}/10 — {offre['verdict']} — {eligible_str}")
        offres_analysees.append(offre)
        if callback:
            callback(i, len(offres), offre)
        time.sleep(4)
    offres_analysees.sort(key=lambda x: x["score"], reverse=True)
    return offres_analysees



--- FICHIER : france_travail/generateur.py ---
import re
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from shared.profil import PROFIL

load_dotenv()

client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location="us-central1"
)
MODELE_LETTRE = "gemini-2.5-pro"
MODELE_EMAIL  = "gemini-2.5-flash"


def generer_lettre(offre):
    p = PROFIL
    projets = "\n".join([f"- {proj['nom']} ({proj['url']}) : {proj['description']}" for proj in p["projets"]])
    prompt = (
        "Redige une lettre de motivation professionnelle en francais pour ce poste.\n\n"
        f"CANDIDATE : {p['prenom']} {p['nom']} — {p['ville']} — {p['email']} — {p['github']}\n"
        f"Formation : Bac+1 DSP DevOps CNAM, integre DEUST IOSI Bac+2 en alternance septembre 2026\n"
        f"Competences : {', '.join(p['competences'])}\n"
        f"Experience : {p['experience'].strip()}\n"
        f"Projets :\n{projets}\n"
        f"Paragraphe personnel : {p['paragraphe_perso'].strip()}\n\n"
        f"OFFRE : {offre.get('titre', '')} — {offre.get('entreprise', '')} — {offre.get('lieu', '')}\n"
        f"Description : {offre.get('description', '')}\n\n"
        "Structure (2800 caracteres max, tenir sur une page A4) :\n"
        "1. 'Madame, Monsieur,' + accroche liee au poste ET a l entreprise\n"
        "2. Competences techniques en lien DIRECT avec l offre\n"
        "3. 1-2 projets GitHub les plus pertinents pour CE poste\n"
        "4. Motivation personnelle\n"
        "5. Disponibilite septembre 2026 + invitation entretien\n"
        f"6. '{p['prenom']} {p['nom']}'\n\n"
        "Contraintes : francais sans fautes, feminin, sans markdown, sans en-tete, sans 'Je me permets de'."
    )
    try:
        response = client.models.generate_content(
            model=MODELE_LETTRE,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=8000)
        )
        lettre = response.text.strip()
        return re.sub(r'\*\*(.*?)\*\*', r'\1', re.sub(r'#{1,6}\s', '', lettre))
    except Exception as e:
        print(f"  Erreur lettre : {e}")
        return "Erreur lors de la generation."


def generer_email(offre):
    p = PROFIL
    prompt = (
        f"Genere un email de candidature court en francais (4-5 lignes).\n\n"
        f"Candidature de : {p['prenom']} {p['nom']} (feminin)\n"
        f"Poste : {offre.get('titre', '')} chez {offre.get('entreprise', '')}\n"
        f"Contacts : {p['email']} | {p['telephone']} | {p['linkedin']}\n\n"
        "Format :\n"
        "Objet : [accrocheur]\n"
        "[ligne vide]\n"
        "[corps 4-5 lignes : mentionner lettre jointe, donner envie de lire]\n"
        "[coordonnees]\n\n"
        "Sans markdown, sans 'Je me permets de'."
    )
    try:
        response = client.models.generate_content(
            model=MODELE_EMAIL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=500)
        )
        email = response.text.strip()
        return re.sub(r'\*\*(.*?)\*\*', r'\1', email)
    except Exception as e:
        print(f"  Erreur email : {e}")
        return "Erreur lors de la generation."



--- FICHIER : france_travail/__init__.py ---



--- FICHIER : france_travail/main.py ---
import json
import os

from france_travail.scraper import chercher_offres, sauvegarder_offres_vues
from france_travail.analyseur import analyser_offres

FICHIER_CANDIDATURES = "data/candidatures.json"

def charger_candidatures():
    if os.path.exists(FICHIER_CANDIDATURES):
        with open(FICHIER_CANDIDATURES, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def sauvegarder_candidatures(candidatures):
    with open(FICHIER_CANDIDATURES, "w", encoding="utf-8") as f:
        json.dump(candidatures, f, ensure_ascii=False, indent=2)


def ajouter_candidatures(nouvelles_offres):
    candidatures = charger_candidatures()
    ids_existants = {c["id"] for c in candidatures}
    ajoutees = 0
    for offre in nouvelles_offres:
        if offre["id"] not in ids_existants:
            offre.setdefault("statut", "nouveau")
            offre.setdefault("lettre", "")
            offre.setdefault("email_candidature", "")
            offre.setdefault("date_candidature", "")
            offre.setdefault("notes", "")
            candidatures.append(offre)
            ajoutees += 1
    candidatures.sort(key=lambda x: x.get("score", 0), reverse=True)
    sauvegarder_candidatures(candidatures)
    return ajoutees


def lancer_recherche(analyser=True, max_analyse=999):
    print("\nRecherche des offres...")
    nouvelles_offres, offres_vues = chercher_offres()

    if not nouvelles_offres:
        print("Aucune nouvelle offre.")
        return []

    if analyser:
        # Callback : sauvegarde chaque offre dès qu'elle est analysée
        def sauvegarder_au_fur(index, total, offre_analysee):
            ajouter_candidatures([offre_analysee])

        analyser_offres(nouvelles_offres[:max_analyse], callback=sauvegarder_au_fur)
    else:
        ajouter_candidatures(nouvelles_offres)

    for offre in nouvelles_offres:
        offres_vues.add(offre["id"])
    sauvegarder_offres_vues(offres_vues)

    return nouvelles_offres



--- FICHIER : france_travail/pdf_generator.py ---
from weasyprint import HTML as WeasyHTML
from shared.profil import PROFIL
from datetime import datetime
import os

def generer_pdf_lettre(offre, lettre, dossier_output="lettres_pdf"):
    os.makedirs(dossier_output, exist_ok=True)
    p = PROFIL

    mois = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
    now = datetime.now()
    date_str = f"{now.day} {mois[now.month-1]} {now.year}"

    nom_entreprise = offre.get("entreprise", "Entreprise").replace(" ", "_").replace("/", "-")[:30]
    nom_fichier = "Lettre_Kenza_Filali-Bouami.pdf"
    chemin_pdf = os.path.join(dossier_output, nom_fichier)

    # Nom entreprise — si inconnu, on met "À l'attention du service recrutement"
    entreprise_brute = offre.get("entreprise", "")
    if not entreprise_brute or entreprise_brute.lower() in ["inconnue", "inconnu", "", "none"]:
        entreprise_affichee = "À l'attention du service recrutement"
        lieu_affiche = offre.get("lieu", "")
    else:
        entreprise_affichee = entreprise_brute
        lieu_affiche = offre.get("lieu", "")

    paragraphes = ""
    for para in lettre.strip().split("\n\n"):
        para = para.strip()
        if para:
            paragraphes += f"<p>{para.replace(chr(10), '<br>')}</p>\n"

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"/>
<style>
  @page {{ size: A4; margin: 2cm 2cm 2cm 2cm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Helvetica', 'Arial', sans-serif; font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; }}
  .entete {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid #ccc; }}
  .expediteur .nom {{ font-size: 12pt; font-weight: bold; margin-bottom: 4px; }}
  .expediteur .info {{ font-size: 8.5pt; color: #444; line-height: 1.6; }}
  .destinataire {{ text-align: right; }}
  .destinataire .entreprise {{ font-size: 10.5pt; font-weight: bold; margin-bottom: 4px; }}
  .destinataire .info {{ font-size: 8.5pt; color: #444; line-height: 1.6; }}
  .date-lieu {{ text-align: right; font-size: 9.5pt; color: #555; margin-bottom: 16px; }}
  .objet {{ font-size: 10pt; margin-bottom: 20px; }}
  .corps p {{ margin-bottom: 11px; text-align: justify; font-size: 10.5pt; }}
</style>
</head>
<body>
<div class="entete">
  <div class="expediteur">
    <div class="nom">{p['prenom']} {p['nom']}</div>
    <div class="info">{p['ville']} &bull; {p['telephone']} &bull; {p['email']}<br>{p['github']}</div>
  </div>
  <div class="destinataire">
    <div class="entreprise">{entreprise_affichee}</div>
    <div class="info">{lieu_affiche}</div>
  </div>
</div>
<div class="date-lieu">Paris, le {date_str}</div>
<div class="objet"><strong>Objet :</strong> Candidature — {offre.get('titre', 'Alternance')}</div>
<div class="corps">{paragraphes}</div>
</body>
</html>"""

    WeasyHTML(string=html).write_pdf(chemin_pdf)
    return chemin_pdf



--- FICHIER : france_travail/scraper.py ---
import requests
import json
import os
import time
import hashlib
from datetime import datetime
from dotenv import load_dotenv
from shared.profil import PROFIL

load_dotenv()

FICHIER_VUES = "data/offres_vues.json"

# Mapping requête → domaine (sans IA, sans token)
DOMAINES_MAP = {
    "devops": "DevOps",
    "infrastructure": "DevOps",
    "linux": "DevOps",
    "systemes": "Sys/Réseau",
    "réseaux": "Sys/Réseau",
    "reseau": "Sys/Réseau",
    "technicien": "Sys/Réseau",
    "administrateur": "Sys/Réseau",
    "helpdesk": "Support",
    "support": "Support",
    "développeur": "Développement",
    "developpeur": "Développement",
    "python": "Développement",
    "slam": "Développement",
    "web": "Développement",
    "data": "Data/IA",
    "ia": "Data/IA",
    "iosi": "Généraliste",
    "informatique": "Généraliste",
    "bts": "Généraliste",
    "but": "Généraliste",
}

def detecter_domaine(query):
    q = query.lower()
    for mot, domaine in DOMAINES_MAP.items():
        if mot in q:
            return domaine
    return "Autre"

def detecter_zone(lieu):
    if not lieu:
        return "Non précisé"
    if "75" in lieu or "paris" in lieu.lower():
        return "Paris"
    if any(x in lieu for x in ["92", "93", "94"]):
        return "Petite couronne"
    if any(x in lieu for x in ["77", "78", "91", "95"]):
        return "Grande couronne"
    return "IDF"

def charger_offres_vues():
    if os.path.exists(FICHIER_VUES):
        with open(FICHIER_VUES, "r") as f:
            return set(json.load(f))
    return set()

def sauvegarder_offres_vues(vues):
    with open(FICHIER_VUES, "w") as f:
        json.dump(list(vues), f)

def generer_id(texte):
    return hashlib.md5(texte.encode()).hexdigest()

_token_cache = {"token": None, "expire": 0}

def get_token():
    if time.time() < _token_cache["expire"]:
        return _token_cache["token"]
    r = requests.post(
        "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire",
        data={
            "grant_type": "client_credentials",
            "client_id": os.getenv("FT_CLIENT_ID"),
            "client_secret": os.getenv("FT_CLIENT_SECRET"),
            "scope": "api_offresdemploiv2 o2dsoffre"
        }
    )
    if r.status_code == 200:
        data = r.json()
        _token_cache["token"] = data["access_token"]
        _token_cache["expire"] = time.time() + data["expires_in"] - 60
        return _token_cache["token"]
    else:
        print(f"Erreur token France Travail : {r.status_code}")
        return None

def scraper_france_travail(query):
    offres = []
    token = get_token()
    if not token:
        return offres

    domaine = detecter_domaine(query)
    url = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
    params = {
        "motsCles": query + " alternance",
        "region": "11",
        "range": "0-14",
        "sort": "1",
    }
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code in [200, 206]:
            data = r.json()
            for offre in data.get("resultats", []):
                lien = offre.get("origineOffre", {}).get("urlOrigine", "")
                if not lien:
                    lien = f"https://candidat.francetravail.fr/offres/recherche/detail/{offre.get('id', '')}"
                lieu = offre.get("lieuTravail", {}).get("libelle", "Paris")
                offres.append({
                    "id": generer_id(offre.get("id", lien)),
                    "titre": offre.get("intitule", "Sans titre"),
                    "entreprise": offre.get("entreprise", {}).get("nom", "Inconnue"),
                    "lieu": lieu,
                    "zone": detecter_zone(lieu),
                    "domaine": domaine,
                    "lien": lien,
                    "source": "France Travail",
                    "description": offre.get("description", "")[:800],
                    "date_trouvee": offre.get("dateCreation", "")[:10] or datetime.now().strftime("%Y-%m-%d"),
                    "score": 0,
                    "lettre": "",
                    "statut": "nouveau"
                })
        else:
            print(f"  France Travail {r.status_code} pour '{query}'")
    except Exception as e:
        print(f"  Erreur France Travail ({query}) : {e}")

    return offres

def chercher_offres():
    print("Recherche des offres en cours...\n")
    offres_vues = charger_offres_vues()
    toutes_offres = []
    ids_session = set()
    queries = PROFIL["recherche"]["titre_poste"]

    for query in queries:
        print(f"  -> '{query}'")
        nouvelles = scraper_france_travail(query)
        for offre in nouvelles:
            if offre["id"] not in offres_vues and offre["id"] not in ids_session:
                if offre["titre"] and offre["titre"] != "Sans titre":
                    toutes_offres.append(offre)
                    ids_session.add(offre["id"])
        time.sleep(0.3)

    print(f"\n{len(toutes_offres)} nouvelles offres trouvees !\n")
    return toutes_offres, offres_vues

if __name__ == "__main__":
    offres, _ = chercher_offres()
    print(f"\n-- Apercu des 5 premieres --")
    for o in offres[:5]:
        print(f"\n[{o['source']}] {o['titre']}")
        print(f"  Domaine : {o['domaine']} | Zone : {o['zone']}")
        print(f"  Lieu : {o['lieu']}")



--- FICHIER : shared/__init__.py ---



--- FICHIER : shared/profil.py ---
# ─────────────────────────────────────────────
# PROFIL DE KENZA
# Ce fichier est le cerveau du chasseur.
# Toutes les décisions de l'IA (scoring,
# lettre de motivation, email) sont basées
# sur ces informations.
# ─────────────────────────────────────────────

PROFIL = {

    # ── Infos personnelles ──────────────────
    "prenom": "Kenza",
    "nom": "Filali-Bouami",
    "email": "kenzafilbou@gmail.com",
    "telephone": "07 50 87 21 76",
    "ville": "Paris 9e",
    "linkedin": "https://www.linkedin.com/in/kenza-filali-bouami/",
    "github": "https://github.com/kenzafb",

    # ── Formation ───────────────────────────
    "formation": """
- DSP DevOps (Bac +1) — Développement et exploitation de parcs informatiques, CNAM Paris (2025-2026, 60 ECTS)
- Candidate au DEUST IOSI parcours Technicien Développement, Sécurité et Exploitation (rentrée septembre 2026)
- Licence de Gestion L1, Université Paris 1 Panthéon-Sorbonne (2024-2025)
- Baccalauréat Général Mathématiques & SES, Lycée Maximilien Perret (2024)
""",

    # ── Compétences techniques ───────────────
    "competences": [
        "Linux Debian/Ubuntu/Arch Linux",
        "Administration systèmes et réseaux",
        "Bash scripting et automatisation",
        "Python (FastAPI, Flask, API REST)",
        "Docker et docker-compose",
        "Git et GitHub",
        "HTML5/CSS3 JavaScript",
        "TCP/IP DNS DHCP SSH",
        "Node.js",
        "WordPress CMS",
        "C algorithmique",
        "Intelligence artificielle (Ollama, LLM, API Anthropic)",
        "Virtualisation (VirtualBox VMware)",
    ],

    # ── Projets GitHub ───────────────────────
    "projets": [
        {
            "nom": "Grabber — Monitoring système",
            "url": "github.com/kenzafb/projet-grabber-devops",
            "description": "Script Bash d'audit système + API REST FastAPI + interface web responsive pour visualisation des métriques en temps réel"
        },
        {
            "nom": "Docker-Compose CLI Tool",
            "url": "github.com/kenzafb/projet_2_javascript",
            "description": "CLI Node.js pour automatiser la gestion de fichiers docker-compose.yml avec vérification d'images via l'API Docker Hub"
        },
        {
            "nom": "Chatbot IA local",
            "url": "github.com/kenzafb/projet_5_chatbot",
            "description": "Chatbot avec interface web Flask, mémoire de conversation, modèle Llama 3.1 tournant 100% en local via Ollama"
        },
        {
            "nom": "Email AI Assistant",
            "url": "github.com/kenzafb/email-ai-assistant",
            "description": "Assistant IA qui surveille Gmail, classe les emails et répond automatiquement. Interface web de validation, surveillance toutes les X minutes"
        },
        {
            "nom": "Auburn & Cream — Site vitrine",
            "url": "github.com/kenzafb/auburn-cream-coffee",
            "description": "Site multi-pages mobile-first HTML/CSS pur, conçu en équipe de 3"
        },
    ],

    # ── Expérience pro ───────────────────────
    "experience": """
- Stagiaire Technicienne au Garage Numérique (mars-avril 2026) : maintenance informatique, installation Linux,
  développement web (WordPress/HTML-CSS), relation public non-techniciens
- Téléenquêtrice chez Alyce (septembre 2025) : collecte structurée de données, outils numériques
- Enquêtrice terrain RATP chez Alyce (mai 2025) : protocoles rigoureux, autonomie
""",

    # ── Langues ──────────────────────────────
    "langues": "Français (natif), Anglais (B2), Espagnol (A2), Arabe (A1)",

    # ── Disponibilité ────────────────────────
    "disponibilite": "Disponible en alternance dès septembre 2026, Paris & Île-de-France. Niveau actuel : Bac+1 (DSP DevOps CNAM). Intègre un DEUST IOSI (Bac+2) en alternance à la rentrée septembre 2026.",

    # ── Paragraphe personnel ─────────────────
    # Utilisé comme base pour les lettres de motivation
    "paragraphe_perso": """
Passionnée d'informatique depuis l'enfance — des jeux vidéo aux premiers outils, l'envie de comprendre
comment les choses fonctionnent a toujours été là. C'est cette année, en formation DevOps au CNAM,
que j'ai découvert que ce monde était aussi le mien. Ce qui m'anime : voir le résultat concret de mon
travail, résoudre des problèmes qui ont un vrai impact, et apprendre quelque chose de nouveau chaque jour.
Je suis du genre à ne pas lâcher un bug avant de l'avoir compris, à chercher la solution propre plutôt
que le raccourci, et à perdre la notion du temps quand un projet m'absorbe vraiment. En alternance,
je cherche exactement ça : un environnement où je peux contribuer concrètement, progresser vite,
et ne jamais être dans la routine.
""",

    # ── Critères de recherche ────────────────
    "recherche": {
        "titre_poste": [
            "alternance devops",
            "alternance administrateur systèmes",
            "alternance technicien systèmes réseaux",
            "alternance développeur",
            "alternance support informatique",
            "alternance iosi",
            "alternance linux",
            "alternance infrastructure",
	    "alternance bts sio",
            "alternance bts sio sisr",
  	    "alternance bts sio slam",
 	    "alternance bts informatique",
   	    "alternance bts réseaux",
            "alternance but informatique",
            "alternance but réseaux télécommunications",
            "alternance technicien informatique",
            "alternance administrateur réseaux",
            "alternance helpdesk",
            "alternance support technique",
            "alternance technicien systèmes",
            "alternance cybersécurité",
            "alternance exploitation informatique",
            "alternance systèmes information",
            "alternance réseau sécurité",
        ],

        "localisation": "Paris Île-de-France",
        "type_contrat": "alternance",
        "disponibilite": "septembre 2026",
    }
}



--- FICHIER : spontanees/envoyeur.py ---
"""
envoyeur.py
===========
Pour chaque entreprise avec lettre_generee=true et mail_envoye=false,
génère le docx personnalisé, l'attache avec le CV et envoie le mail.

Lancement : python envoyeur.py
Lancement limité : python envoyeur.py --limite 10
"""

import json
import os
import io
import time
import random
import smtplib
import argparse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from dotenv import load_dotenv

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────

FICHIER_JSON  = "data/entreprises_enrichies.json"
CV_PATH       = "assets/CV_Kenza_Filali-Bouami.pdf"
TEMPLATE_PATH = "assets/lettre_template_KENZA.docx"

GMAIL_SENDER     = os.getenv("GMAIL_SENDER", "kenzafilbou@gmail.com")
GMAIL_PASSWORD   = os.getenv("GMAIL_APP_PASSWORD", "")

LIMITE_PAR_RUN   = 50          # max mails par lancement
PAUSE_ENTRE_MAILS = (30, 90)   # secondes (humain et anti-spam)
SAUVEGARDE_TOUS  = 10

# ─── Helpers JSON ─────────────────────────────────────────────────────────────

def charger_json():
    with open(FICHIER_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_json(data):
    with open(FICHIER_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Génération du DOCX personnalisé ─────────────────────────────────────────

def generer_docx(zones):
    """
    Charge le template, remplace les 4 balises {{...}} et retourne les bytes du docx.
    """
    doc = Document(TEMPLATE_PATH)

    remplacements = {
        "{{NOM_ENTREPRISE}}"        : zones.get("nom_entreprise", ""),
        "{{ADRESSE_ENTREPRISE}}"    : zones.get("adresse", ""),
        "{{DATE}}"                  : zones.get("date", ""),
        "{{OBJET_MAIL}}"            : zones.get("objet", ""),
        "{{PARAGRAPHE_PERSONNALISE}}": zones.get("paragraphe_personnalise", ""),
    }

    for para in doc.paragraphs:
        for balise, valeur in remplacements.items():
            if balise in para.text:
                # Remplacer en préservant le style du premier run
                for run in para.runs:
                    if balise in run.text:
                        run.text = run.text.replace(balise, valeur)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()

# ─── Construction du corps du mail ───────────────────────────────────────────

def corps_mail(zones):
    """Corps du mail court et professionnel."""
    nom_e = zones.get("nom_entreprise", "votre entreprise")
    return f"""\
Madame, Monsieur,

Je me permets de vous adresser ma candidature pour un contrat d'alternance \
en DevOps / SysAdmin / Sécurité à compter de septembre 2026, dans le cadre \
de ma 2ᵉ année de DEUST IOSI au CNAM Paris.

{zones.get("paragraphe_personnalise", "")}

Vous trouverez en pièce jointe mon curriculum vitae ainsi qu'une lettre de \
motivation détaillée.

Dans l'attente de votre retour, je reste disponible pour un entretien à votre \
convenance.

Cordialement,
Kenza FILALI-BOUAMI
07 50 87 21 76 | kenzafilbou@gmail.com | github.com/kenzafb
"""

# ─── Envoi du mail ────────────────────────────────────────────────────────────

def envoyer_mail(destinataire, sujet, corps, docx_bytes, nom_entreprise):
    """
    Envoie le mail avec le CV et la lettre en pièces jointes.
    Retourne True si succès, False sinon.
    """
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = destinataire
    msg["Subject"] = sujet

    # Corps texte
    msg.attach(MIMEText(corps, "plain", "utf-8"))

    # Pièce jointe 1 : CV PDF
    try:
        with open(CV_PATH, "rb") as f:
            cv_data = f.read()
        part_cv = MIMEBase("application", "pdf")
        part_cv.set_payload(cv_data)
        encoders.encode_base64(part_cv)
        part_cv.add_header(
            "Content-Disposition",
            "attachment",
            filename="CV_Kenza_Filali-Bouami.pdf"
        )
        msg.attach(part_cv)
    except FileNotFoundError:
        print(f"    [⚠️] CV introuvable : {CV_PATH}")
        return False

    # Pièce jointe 2 : Lettre DOCX
    nom_fichier = f"Lettre_Kenza_Filali-Bouami_{nom_entreprise[:30].replace(' ', '_')}.docx"
    part_lettre = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
    part_lettre.set_payload(docx_bytes)
    encoders.encode_base64(part_lettre)
    part_lettre.add_header(
        "Content-Disposition",
        "attachment",
        filename=nom_fichier
    )
    msg.attach(part_lettre)

    # Envoi SMTP Gmail
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, destinataire, msg.as_string())
        return True
    except Exception as e:
        print(f"    [❌] Erreur SMTP : {e}")
        return False

# ─── Pipeline principal ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limite", type=int, default=LIMITE_PAR_RUN,
                        help="Nombre maximum de mails à envoyer ce run")
    parser.add_argument("--test", action="store_true",
                        help="Mode test : envoie tout à kenzafilbou@gmail.com sans marquer mail_envoye")
    args = parser.parse_args()

    print("=" * 60)
    print("  Envoyeur — Chasseur d'Alternance")
    if args.test:
        print("  ⚠️  MODE TEST — tous les mails vont à", GMAIL_SENDER)
    print("=" * 60)

    if not GMAIL_PASSWORD:
        print("❌ GMAIL_APP_PASSWORD manquant dans .env")
        return

    entreprises = charger_json()

    a_envoyer = [
        e for e in entreprises
        if e.get("lettre_generee") and
           e.get("emails_trouves") and
           not e.get("mail_envoye")
    ]

    deja_envoyes = sum(1 for e in entreprises if e.get("mail_envoye"))
    print(f"[Queue] {len(a_envoyer)} à envoyer | {deja_envoyes} déjà envoyés")
    print(f"[Limite] {args.limite} mails ce run\n")

    if not a_envoyer:
        print("✅ Rien à envoyer.")
        return

    envoyes    = 0
    echecs     = 0
    traites    = 0

    for e in entreprises:
        if envoyes >= args.limite:
            print(f"\n⏹️  Limite de {args.limite} mails atteinte pour ce run.")
            break

        if not e.get("lettre_generee") or not e.get("emails_trouves") or e.get("mail_envoye"):
            continue

        nom       = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
        zones     = e.get("lettre_zones", {})
        emails    = e.get("emails_trouves", [])
        destinataire = GMAIL_SENDER if args.test else emails[0]

        idx = deja_envoyes + traites + 1
        total = deja_envoyes + len(a_envoyer)
        print(f"[{idx}/{total}] {nom}")
        print(f"  → {destinataire}")

        # Générer le docx
        try:
            docx_bytes = generer_docx(zones)
        except Exception as ex:
            print(f"  [❌] Erreur génération docx : {ex}")
            echecs += 1
            traites += 1
            continue

        # Corps et sujet du mail
        sujet = zones.get("objet", f"Candidature alternance DevOps – {nom}")
        corps = corps_mail(zones)

        # Envoi
        ok = envoyer_mail(destinataire, sujet, corps, docx_bytes, nom)

        if ok:
            print(f"  ✅ Envoyé")
            if not args.test:
                e["mail_envoye"]    = True
                e["mail_envoye_le"] = datetime.today().strftime("%Y-%m-%d %H:%M")
                e["mail_destinataire"] = destinataire
            envoyes += 1
        else:
            print(f"  ❌ Échec envoi")
            echecs += 1

        traites += 1

        # Sauvegarde intermédiaire
        if traites % SAUVEGARDE_TOUS == 0:
            sauvegarder_json(entreprises)
            print(f"\n  [💾 Sauvegarde — {envoyes} envoyés, {echecs} échecs]\n")

        # Pause anti-spam (sauf dernier)
        if envoyes < args.limite:
            pause = random.uniform(*PAUSE_ENTRE_MAILS)
            print(f"  ⏸️  Pause {pause:.0f}s...")
            time.sleep(pause)

    sauvegarder_json(entreprises)

    print("\n" + "=" * 60)
    print(f"  Envoyés  : {envoyes}")
    print(f"  Échecs   : {echecs}")
    print("=" * 60)
    if not args.test and envoyes > 0:
        print("\n→ Relance demain pour continuer le batch.")


if __name__ == "__main__":
    main()



--- FICHIER : spontanees/export_excel.py ---
"""
export_excel.py
===============
Génère un fichier Excel de suivi des candidatures spontanées
à partir de entreprises_enrichies.json.

Feuilles :
  - Candidatures  : tableau de suivi avec statuts, colonnes à remplir
  - Stats         : résumé automatique (formules Excel)
  - Source        : toutes les données brutes importées

Usage : python export_excel.py
"""

import json
import os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, GradientFill
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

FICHIER_ENTREE = "data/entreprises_enrichies.json"
FICHIER_SORTIE = f"candidatures_spontanees_{datetime.today().strftime('%Y%m')}.xlsx"

# ─── Couleurs ─────────────────────────────────────────────────────────────────
VIOLET_FONCE  = "4B3F72"
VIOLET_CLAIR  = "EDE9F7"
VERT          = "27AE60"
VERT_CLAIR    = "E8F8F0"
ORANGE        = "E67E22"
ORANGE_CLAIR  = "FEF0E0"
ROUGE         = "E74C3C"
ROUGE_CLAIR   = "FDEDEC"
GRIS_CLAIR    = "F5F5F5"
GRIS_TITRE    = "2C3E50"
BLANC         = "FFFFFF"
BLEU_CLAIR    = "EBF5FB"

STATUTS = ["À envoyer", "Envoyée", "Relancée", "Entretien", "Refus", "Sans réponse"]
COULEURS_STATUTS = {
    "À envoyer":   ("FFF3CD", "856404"),
    "Envoyée":     ("CCE5FF", "004085"),
    "Relancée":    ("D4EDDA", "155724"),
    "Entretien":   ("D1ECF1", "0C5460"),
    "Refus":       ("F8D7DA", "721C24"),
    "Sans réponse":("E2E3E5", "383D41"),
}

# ─── Styles helpers ───────────────────────────────────────────────────────────

def fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def font(bold=False, color="000000", size=11, italic=False):
    return Font(bold=bold, color=color, size=size, italic=italic, name="Arial")

def center():
    return Alignment(horizontal="center", vertical="center", wrap_text=True)

def left():
    return Alignment(horizontal="left", vertical="center", wrap_text=True)

def thin_border():
    s = Side(border_style="thin", color="CCCCCC")
    return Border(left=s, right=s, top=s, bottom=s)

def set_cell(ws, row, col, value, bold=False, bg=None, fg="000000",
             size=11, align="left", italic=False, border=True):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = Font(bold=bold, color=fg, size=size, italic=italic, name="Arial")
    cell.alignment = center() if align == "center" else left()
    if bg:
        cell.fill = fill(bg)
    if border:
        cell.border = thin_border()
    return cell


# ─── Feuille Candidatures ─────────────────────────────────────────────────────

def creer_feuille_candidatures(wb, entreprises):
    ws = wb.active
    ws.title = "Candidatures"
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A3"  # Figer les 2 premières lignes

    # Titre principal
    ws.merge_cells("A1:N1")
    titre = ws["A1"]
    titre.value = f"🎯 Suivi Candidatures Spontanées — Kenza | DEUST IOSI DevOps | Rentrée Sept. 2026"
    titre.font = Font(bold=True, color=BLANC, size=13, name="Arial")
    titre.fill = fill(VIOLET_FONCE)
    titre.alignment = center()
    ws.row_dimensions[1].height = 35

    # En-têtes
    colonnes = [
        ("N°",            5),
        ("Entreprise",    30),
        ("Ville",         14),
        ("Code NAF",      10),
        ("Taille",        10),
        ("Site Web",      28),
        ("Email Contact", 32),
        ("Statut",        14),
        ("Date Envoi",    13),
        ("Date Relance",  13),
        ("Réponse",       14),
        ("Contact RH",    20),
        ("Notes",         30),
        ("Lettre Gemini", 14),
    ]

    for col_idx, (nom, largeur) in enumerate(colonnes, 1):
        cell = ws.cell(row=2, column=col_idx, value=nom)
        cell.font = Font(bold=True, color=BLANC, size=10, name="Arial")
        cell.fill = fill(GRIS_TITRE)
        cell.alignment = center()
        cell.border = thin_border()
        ws.column_dimensions[get_column_letter(col_idx)].width = largeur

    ws.row_dimensions[2].height = 28

    # Validation liste déroulante Statut (colonne H = 8)
    dv = DataValidation(
        type="list",
        formula1=f'"{",".join(STATUTS)}"',
        allow_blank=True,
        showDropDown=False
    )
    dv.error = "Choisir un statut valide"
    dv.errorTitle = "Statut invalide"
    dv.prompt = "Choisir le statut de la candidature"
    ws.add_data_validation(dv)

    # Données
    ligne = 3
    avec_email = [e for e in entreprises if e.get("emails_trouves") or e.get("emails")]
    sans_email  = [e for e in entreprises if not e.get("emails_trouves") and not e.get("emails")]

    # On met d'abord celles avec email
    toutes = avec_email + sans_email

    for idx, e in enumerate(toutes, 1):
        emails = e.get("emails_trouves") or e.get("emails") or []
        email_principal = emails[0] if emails else ""

        bg_ligne = BLANC if idx % 2 == 0 else GRIS_CLAIR

        valeurs = [
            idx,
            e.get("nom", ""),
            e.get("ville", ""),
            e.get("code_naf", ""),
            e.get("tranche_effectif", ""),
            e.get("site_web") or e.get("url_scrapee") or "",
            email_principal,
            "À envoyer",  # Statut par défaut
            "",  # Date envoi
            "",  # Date relance
            "",  # Réponse
            "",  # Contact RH
            "",  # Notes
            "Non",  # Lettre Gemini
        ]

        for col_idx, val in enumerate(valeurs, 1):
            cell = ws.cell(row=ligne, column=col_idx, value=val)
            cell.font = Font(name="Arial", size=10, color="000000")
            cell.border = thin_border()
            cell.fill = fill(bg_ligne)
            cell.alignment = left()

            # URL cliquable
            if col_idx == 6 and val and val.startswith("http"):
                cell.hyperlink = val
                cell.font = Font(name="Arial", size=10, color="0563C1", underline="single")

            # Email cliquable
            if col_idx == 7 and val and "@" in val:
                cell.hyperlink = f"mailto:{val}"
                cell.font = Font(name="Arial", size=10, color="0563C1", underline="single")

            # Colonne Statut : liste déroulante
            if col_idx == 8:
                dv.add(cell)
                cell.alignment = center()

        ws.row_dimensions[ligne].height = 22
        ligne += 1

    # Mise en forme conditionnelle légère via note visuelle
    print(f"  [Excel] {ligne - 3} lignes entreprises ajoutées")
    return ligne


# ─── Feuille Stats ─────────────────────────────────────────────────────────────

def creer_feuille_stats(wb, nb_total):
    ws = wb.create_sheet("Stats")
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 22

    ws.merge_cells("A1:C1")
    t = ws["A1"]
    t.value = "📊 Tableau de Bord Candidatures"
    t.font = Font(bold=True, color=BLANC, size=13, name="Arial")
    t.fill = fill(VIOLET_FONCE)
    t.alignment = center()
    ws.row_dimensions[1].height = 32

    indicateurs = [
        ("Total entreprises",    f"=COUNTA(Candidatures!B3:B{2+nb_total})", VIOLET_CLAIR),
        ("À envoyer",            f'=COUNTIF(Candidatures!H3:H{2+nb_total},"À envoyer")', "FFF3CD"),
        ("Envoyées",             f'=COUNTIF(Candidatures!H3:H{2+nb_total},"Envoyée")', "CCE5FF"),
        ("Relancées",            f'=COUNTIF(Candidatures!H3:H{2+nb_total},"Relancée")', "D4EDDA"),
        ("Entretiens",           f'=COUNTIF(Candidatures!H3:H{2+nb_total},"Entretien")', "D1ECF1"),
        ("Refus",                f'=COUNTIF(Candidatures!H3:H{2+nb_total},"Refus")', ROUGE_CLAIR),
        ("Sans réponse",         f'=COUNTIF(Candidatures!H3:H{2+nb_total},"Sans réponse")', GRIS_CLAIR),
        ("Taux de réponse (%)",  f'=IF(COUNTIF(Candidatures!H3:H{2+nb_total},"Envoyée")=0,"—",ROUND((COUNTIF(Candidatures!H3:H{2+nb_total},"Entretien")+COUNTIF(Candidatures!H3:H{2+nb_total},"Refus"))*100/COUNTIF(Candidatures!H3:H{2+nb_total},"Envoyée"),1))', VERT_CLAIR),
    ]

    for row, (label, formule, bg) in enumerate(indicateurs, 3):
        set_cell(ws, row, 1, label, bold=True, bg=bg, size=11)
        cell_val = ws.cell(row=row, column=2, value=formule)
        cell_val.font = Font(bold=True, size=13, color=VIOLET_FONCE, name="Arial")
        cell_val.fill = fill(bg)
        cell_val.alignment = center()
        cell_val.border = thin_border()
        ws.row_dimensions[row].height = 26

    # Légende statuts
    ws.cell(row=13, column=1).value = "Légende des statuts"
    ws.cell(row=13, column=1).font = Font(bold=True, size=11, name="Arial")
    ws.row_dimensions[13].height = 22

    for r, (statut, (bg, fg)) in enumerate(COULEURS_STATUTS.items(), 14):
        c = ws.cell(row=r, column=1, value=f"  {statut}")
        c.fill = fill(bg)
        c.font = Font(color=fg, name="Arial", size=10)
        c.border = thin_border()
        c.alignment = left()
        ws.row_dimensions[r].height = 20


# ─── Feuille Source ───────────────────────────────────────────────────────────

def creer_feuille_source(wb, entreprises):
    ws = wb.create_sheet("Données brutes")
    ws.sheet_view.showGridLines = False

    headers = ["Nom", "SIRET", "SIREN", "Code NAF", "Libellé NAF",
               "Adresse", "Ville", "Dept", "Taille", "Site Web", "Emails trouvés", "Traité"]

    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = Font(bold=True, color=BLANC, size=10, name="Arial")
        c.fill = fill(GRIS_TITRE)
        c.alignment = center()
        c.border = thin_border()

    largeurs = [35, 16, 12, 10, 30, 35, 18, 8, 10, 35, 45, 8]
    for col, w in enumerate(largeurs, 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    for row, e in enumerate(entreprises, 2):
        emails = e.get("emails_trouves") or e.get("emails") or []
        valeurs = [
            e.get("nom", ""),
            e.get("siret", ""),
            e.get("siren", ""),
            e.get("code_naf", ""),
            e.get("libelle_naf", ""),
            e.get("adresse", ""),
            e.get("ville", ""),
            e.get("departement", ""),
            e.get("tranche_effectif", ""),
            e.get("site_web") or e.get("url_scrapee") or "",
            " | ".join(emails),
            "✅" if e.get("traite") else "⏳",
        ]
        bg = BLANC if row % 2 == 0 else GRIS_CLAIR
        for col, val in enumerate(valeurs, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.font = Font(name="Arial", size=9)
            c.fill = fill(bg)
            c.border = thin_border()
            c.alignment = left()
        ws.row_dimensions[row].height = 18


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Chasseur d'Alternance — Export Excel")
    print("=" * 55)

    # Charger les données (enrichies si dispo, sinon raw)
    fichier = FICHIER_ENTREE
    if not os.path.exists(fichier):
        fichier = "entreprises_raw.json"
    if not os.path.exists(fichier):
        print("[ERREUR] Aucun fichier JSON trouvé. Lance d'abord fetch_entreprises.py")
        return

    with open(fichier, "r", encoding="utf-8") as f:
        entreprises = json.load(f)

    print(f"[Chargement] {len(entreprises)} entreprises depuis {fichier}")

    # Trier : avec email d'abord, puis par ville
    entreprises.sort(key=lambda e: (
        0 if (e.get("emails_trouves") or e.get("emails")) else 1,
        e.get("ville", "")
    ))

    wb = Workbook()

    print("[Excel] Création feuille Candidatures...")
    nb = creer_feuille_candidatures(wb, entreprises)

    print("[Excel] Création feuille Stats...")
    creer_feuille_stats(wb, len(entreprises))

    print("[Excel] Création feuille Données brutes...")
    creer_feuille_source(wb, entreprises)

    # Sauvegarder
    output_path = FICHIER_SORTIE
    wb.save(output_path)

    avec_email = sum(1 for e in entreprises if e.get("emails_trouves") or e.get("emails"))
    print("\n" + "=" * 55)
    print(f"  Entreprises exportées : {len(entreprises)}")
    print(f"  Avec email            : {avec_email}")
    print(f"  Fichier Excel         : {FICHIER_SORTIE}")
    print("=" * 55)


if __name__ == "__main__":
    main()



--- FICHIER : spontanees/fetch_entreprises.py ---
"""
fetch_entreprises.py
====================
Récupère les entreprises IT (codes NAF 62.*) de Paris et petite couronne
via l'API Recherche d'Entreprises (gratuite, officielle, sans clé API).

Départements ciblés : 75 (Paris), 92 (Hauts-de-Seine), 93 (Seine-Saint-Denis), 94 (Val-de-Marne)
Résultat : entreprises_raw.json

Note : l'API ne fournit PAS de site web. Les sites seront trouvés par scraper_emails.py.
"""

import requests
import json
import time
import os

FICHIER_SORTIE = "data/entreprises_raw.json"

# Codes NAF informatique / ESN — format avec POINT (ex: 62.01Z)
CODES_NAF = [
    "62.01Z",  # Programmation informatique
    "62.02A",  # Conseil en systèmes et logiciels informatiques
    "62.02B",  # Tierce maintenance de systèmes
    "62.03Z",  # Gestion d'installations informatiques
    "62.09Z",  # Autres activités informatiques
    "63.11Z",  # Traitement de données, hébergement
]

# Paris + petite couronne
DEPARTEMENTS = ["75", "92", "93", "94"]

BASE_URL = "https://recherche-entreprises.api.gouv.fr/search"

# Correspondance code effectif → libellé lisible
TRANCHES_EFFECTIF = {
    "NN": "0", "00": "0", "01": "1-2", "02": "3-5", "03": "6-9",
    "11": "10-19", "12": "20-49", "21": "50-99", "22": "100-199",
    "31": "200-249", "32": "250-499", "41": "500-999", "42": "1000-1999",
    "51": "2000-4999", "52": "5000-9999", "53": "10000+",
}


def fetch_page(code_naf, departement, page=1, per_page=25):
    params = {
        "q": "informatique",
        "code_naf": code_naf,
        "departement": departement,
        "page": page,
        "per_page": per_page,
    }
    try:
        r = requests.get(BASE_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"    [ERREUR] NAF {code_naf} / Dept {departement} / page {page} : {e}")
        return None


def extraire_infos(unite):
    siege = unite.get("siege", {})
    matching = unite.get("matching_etablissements", [{}])
    etab = matching[0] if matching else {}

    # Nom commercial = souvent plus court, plus proche du domaine web
    nom_commercial = siege.get("nom_commercial") or etab.get("nom_commercial") or None

    # Taille lisible
    code_effectif = unite.get("tranche_effectif_salarie", "")
    taille = TRANCHES_EFFECTIF.get(code_effectif, code_effectif)

    # Chiffre d'affaires le plus récent
    finances = unite.get("finances") or {}
    ca = None
    if finances:
        annee_max = max(finances.keys())
        ca = finances[annee_max].get("ca")

    # Dirigeant principal (première personne physique)
    dirigeant = ""
    for d in (unite.get("dirigeants") or []):
        if d.get("type_dirigeant") == "personne physique":
            dirigeant = f"{d.get('prenoms', '')} {d.get('nom', '')}".strip()
            break

    return {
        "nom": unite.get("nom_complet", "").strip(),
        "nom_commercial": nom_commercial,
        "siret": siege.get("siret", ""),
        "siren": unite.get("siren", ""),
        "code_naf": unite.get("activite_principale", ""),
        "adresse": siege.get("adresse", ""),
        "ville": siege.get("libelle_commune", ""),
        "code_postal": siege.get("code_postal", ""),
        "departement": siege.get("departement", ""),
        "site_web": None,
        "taille": taille,
        "categorie": unite.get("categorie_entreprise", ""),
        "ca": ca,
        "dirigeant": dirigeant,
        "traite": False,
    }


def charger_existants():
    if os.path.exists(FICHIER_SORTIE):
        with open(FICHIER_SORTIE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {e["siret"]: e for e in data if e.get("siret")}
    return {}


def sauvegarder(entreprises_dict):
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(list(entreprises_dict.values()), f, ensure_ascii=False, indent=2)


def main():
    print("=" * 55)
    print("  Chasseur d'Alternance — Fetch Entreprises IT IDF")
    print("=" * 55)

    entreprises = charger_existants()
    if entreprises:
        print(f"[Reprise] {len(entreprises)} entreprises déjà en base.\n")

    total_nouvelles = 0
    pages_vides_consecutives = 0

    for dept in DEPARTEMENTS:
        for naf in CODES_NAF:
            print(f"\n[API] Dept {dept} | NAF {naf}")
            page = 1
            pages_vides_consecutives = 0

            while True:
                data = fetch_page(naf, dept, page=page)
                if not data:
                    break

                resultats = data.get("results", [])
                total_pages = data.get("total_pages", 1)

                if not resultats:
                    print(f"  Aucun résultat.")
                    break

                nouvelles_cette_page = 0
                for unite in resultats:
                    infos = extraire_infos(unite)
                    siret = infos["siret"]
                    if siret and siret not in entreprises:
                        entreprises[siret] = infos
                        total_nouvelles += 1
                        nouvelles_cette_page += 1

                print(f"  Page {page}/{total_pages} — +{nouvelles_cette_page} nouvelles | Total : {len(entreprises)}")

                if page >= total_pages:
                    break

                # Arrêt anticipé si 3 pages sans nouvelles
                if nouvelles_cette_page == 0:
                    pages_vides_consecutives += 1
                    if pages_vides_consecutives >= 3:
                        print(f"  → 3 pages sans nouvelles, passage au suivant.")
                        break
                else:
                    pages_vides_consecutives = 0

                # Sauvegarde toutes les 10 pages
                if page % 10 == 0:
                    sauvegarder(entreprises)

                page += 1
                time.sleep(0.3)

    sauvegarder(entreprises)

    # Résumé avec stats utiles
    avec_ca      = sum(1 for e in entreprises.values() if e.get("ca"))
    avec_dir     = sum(1 for e in entreprises.values() if e.get("dirigeant"))
    avec_nom_com = sum(1 for e in entreprises.values() if e.get("nom_commercial"))
    par_cat      = {}
    for e in entreprises.values():
        c = e.get("categorie") or "?"
        par_cat[c] = par_cat.get(c, 0) + 1

    print("\n" + "=" * 55)
    print(f"  Total entreprises     : {len(entreprises)}")
    print(f"  Nouvelles ce run      : {total_nouvelles}")
    print(f"  Avec nom commercial   : {avec_nom_com}")
    print(f"  Avec dirigeant        : {avec_dir}")
    print(f"  Avec CA               : {avec_ca}")
    print(f"  Par catégorie         : {par_cat}")
    print(f"  Fichier               : {FICHIER_SORTIE}")
    print("=" * 55)
    print("\n→ Lance maintenant : python scraper_emails.py")


if __name__ == "__main__":
    main()



--- FICHIER : spontanees/generateur_lettres.py ---
"""
generateur_lettres.py
=====================
Pour chaque entreprise avec un email dans entreprises_enrichies.json,
appelle Gemini (Vertex AI) pour générer les 4 zones personnalisées
de la lettre de motivation et sauvegarde le résultat dans le JSON.

Lancement : python generateur_lettres.py
"""


import json
import os
import time
import random
import re
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()


# ─── Config ───────────────────────────────────────────────────────────────────

FICHIER_JSON    = "data/entreprises_enrichies.json"
PROJET_GCP      = os.getenv("GOOGLE_CLOUD_PROJECT", "project-4fa72ea4-bd10-420c-988")
MODELE_GEMINI   = "gemini-2.5-flash"
PAUSE_GEMINI    = (4, 8)      # secondes entre chaque appel
SAUVEGARDE_TOUS = 20          # sauvegarde tous les N traitements

# ─── Profil Kenza (contexte fixe pour Gemini) ─────────────────────────────────

PROFIL_KENZA = """
Candidate : Kenza FILALI-BOUAMI
Formation : DSP DevOps (Bac+1) au CNAM Paris, actuellement en stage au Garage Numérique.
Prochaine formation : DEUST IOSI (Bac+2) au CNAM Paris, 2e année, démarrage septembre 2026 en alternance.
Disponibilité alternance : septembre 2026.
Compétences principales : Linux (Debian, Ubuntu, Arch), Docker/Docker-Compose, Bash scripting,
Python (FastAPI, API REST), Git/GitHub, CI/CD, administration système et réseau, sécurité informatique,
TCP/IP, DNS, DHCP, pare-feu, HTML/CSS/JavaScript, MySQL, WordPress.
Projets : Grabber (monitoring système FastAPI/Bash), outil CLI Docker-Compose (Node.js),
site Auburn & Cream (HTML/CSS pur, mobile-first).
Stage : Le Garage Numérique — maintenance matérielle/logicielle, configuration Linux,
développement web, support utilisateur.
Poste recherché : alternance DevOps / SysAdmin / Sécurité.
"""

# ─── Initialisation Gemini ────────────────────────────────────────────────────

gemini_client = genai.Client(
    vertexai=True,
    project=PROJET_GCP,
    location="us-central1"
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def date_du_jour():
    mois = ["janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    today = datetime.today()
    return f"{today.day} {mois[today.month - 1]} {today.year}"


def charger_json():
    with open(FICHIER_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def sauvegarder_json(data):
    with open(FICHIER_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def nettoyer_json_gemini(texte):
    """Nettoie les éventuels backticks markdown autour du JSON."""
    texte = re.sub(r'```json\s*', '', texte)
    texte = re.sub(r'```\s*', '', texte)
    return texte.strip()


# ─── Appel Gemini ─────────────────────────────────────────────────────────────

def generer_zones(entreprise):
    """
    Appelle Gemini pour générer les 4 zones personnalisées.
    Retourne un dict : {objet, adresse, paragraphe_personnalise} ou None si erreur.
    """
    nom         = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    ville       = entreprise.get("ville") or ""
    cp          = entreprise.get("code_postal") or ""
    site        = entreprise.get("site_web") or entreprise.get("url_scrapee") or ""
    emails      = entreprise.get("emails_trouves", [])
    telephone   = entreprise.get("telephone") or ""

    prompt = f"""
Tu aides une candidate (Kenza FILALI-BOUAMI) à personnaliser sa lettre de motivation
pour une candidature en alternance DevOps/SysAdmin/Sécurité.

PROFIL DE LA CANDIDATE :
{PROFIL_KENZA}

ENTREPRISE CIBLE :
- Nom : {nom}
- Ville : {ville} ({cp})
- Site web : {site if site else "inconnu"}

MISSION :
Génère exactement 3 éléments pour personnaliser la lettre :

1. OBJET : Une ligne d'objet percutante pour le mail/lettre (ex: "Candidature alternance DevOps – Septembre 2026")
   → Adapte-le au secteur/nom de l'entreprise si possible. Maximum 12 mots.

2. ADRESSE : L'adresse du destinataire à afficher sur la lettre.
   Format : "Nom de l'entreprise\\n{ville} ({cp})"
   → Si l'adresse exacte est inconnue, utilise juste le nom et la ville.

3. PARAGRAPHE_PERSONNALISE : UN seul paragraphe de 3 à 5 phrases maximum.
   → Montre que Kenza connaît ou s'intéresse à cette entreprise spécifiquement.
   → Explique pourquoi ses compétences (Linux, Docker, Python, sécurité) correspondent
     à ce que cette entreprise fait probablement (déduis-le du nom/secteur).
   → Ton professionnel, naturel, pas robotique. Pas de superlatifs excessifs.
   → Ne répète pas ce qui est déjà dans les autres paragraphes fixes de la lettre.
   → Ne mentionne PAS le CV (déjà dit dans la lettre).
   → Ne commence PAS par "Je" — commence par le nom de l'entreprise, "Votre", "C'est", etc.

IMPORTANT : Réponds UNIQUEMENT en JSON valide, sans backticks, sans texte autour :
{{"objet": "...", "adresse": "...", "paragraphe_personnalise": "..."}}
"""

    try:
        response = gemini_client.models.generate_content(
            model=MODELE_GEMINI,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Tu es un expert en rédaction de lettres de motivation professionnelles françaises. "
                    "Tu réponds UNIQUEMENT en JSON valide sans backticks ni texte autour."
                ),
                response_mime_type="application/json",
                temperature=0.7,
            )
        )
        texte = nettoyer_json_gemini(response.text)
        result = json.loads(texte)

        # Validation minimale
        if not all(k in result for k in ["objet", "adresse", "paragraphe_personnalise"]):
            print(f"    [⚠️] Gemini — réponse incomplète : {result}")
            return None

        return result

    except Exception as e:
        print(f"    [❌] Gemini erreur : {e}")
        return None


# ─── Pipeline principal ────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Générateur de lettres — Chasseur d'Alternance")
    print(f"  Modèle : {MODELE_GEMINI}  |  Projet : {PROJET_GCP}")
    print("=" * 60)

    entreprises = charger_json()

    # Filtrer : uniquement celles avec email ET pas encore de lettre générée
    a_traiter = [
        e for e in entreprises
        if e.get("emails_trouves") and not e.get("lettre_generee")
    ]
    deja_faites = sum(1 for e in entreprises if e.get("lettre_generee"))

    print(f"[Queue] {len(a_traiter)} à traiter | {deja_faites} déjà générées\n")

    if not a_traiter:
        print("✅ Toutes les lettres sont générées ! Lance : python envoyeur.py")
        return

    traites_ce_run = 0
    succes = 0
    erreurs = 0

    for e in entreprises:
        # Passer les entreprises sans email ou déjà traitées
        if not e.get("emails_trouves") or e.get("lettre_generee"):
            continue

        nom = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
        idx = deja_faites + traites_ce_run + 1
        total_avec_email = deja_faites + len(a_traiter)

        print(f"[{idx}/{total_avec_email}] {nom}")

        zones = generer_zones(e)

        if zones:
            e["lettre_zones"] = {
                "date"                  : date_du_jour(),
                "nom_entreprise"        : e.get("nom_commercial") or e.get("nom", ""),
                "adresse"               : zones["adresse"],
                "objet"                 : zones["objet"],
                "paragraphe_personnalise": zones["paragraphe_personnalise"],
            }
            e["lettre_generee"] = True
            print(f"  ✅ Objet : {zones['objet']}")
            succes += 1
        else:
            e["lettre_generee"] = False
            print(f"  ❌ Échec génération")
            erreurs += 1

        traites_ce_run += 1

        # Sauvegarde intermédiaire
        if traites_ce_run % SAUVEGARDE_TOUS == 0:
            sauvegarder_json(entreprises)
            print(f"\n  [💾 Sauvegarde — {idx}/{total_avec_email} | {succes} lettres générées]\n")

        # Pause anti-rate-limit
        time.sleep(random.uniform(*PAUSE_GEMINI))

    sauvegarder_json(entreprises)

    print("\n" + "=" * 60)
    print(f"  Lettres générées : {succes}")
    print(f"  Échecs           : {erreurs}")
    print(f"  Fichier          : {FICHIER_JSON}")
    print("=" * 60)
    print("\n→ Lance : python envoyeur.py")


if __name__ == "__main__":
    main()



--- FICHIER : spontanees/__init__.py ---



--- FICHIER : spontanees/scraper_emails.py ---
"""
scraper_emails.py v4
====================
CHANGELOG v4 :
  - Intégration Gemini (même config que analyseur.py) pour :
      1. Filtrer les faux positifs (favicon, mauvais domaine...)
      2. Extraire email + téléphone + nom du contact RH depuis le HTML
  - Gemini est appelé APRÈS le scraping BS4, seulement si des emails suspects
    sont trouvés OU si aucun email n'est trouvé mais qu'une page contact existe
  - Rate limit gratuit respecté : 1 appel Gemini max par entreprise + pause 4s

Installation : pip install ddgs beautifulsoup4 requests google-genai python-dotenv
"""

import json
import re
import time
import os
import random
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from ddgs.exceptions import RatelimitException
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ─── Gemini ───────────────────────────────────────────────────────────────────

gemini_client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location="us-central1"
)
MODELE_GEMINI = "gemini-2.5-flash"

# ─── Config ───────────────────────────────────────────────────────────────────

FICHIER_ENTREE  = "data/entreprises_raw.json"
FICHIER_SORTIE  = "data/entreprises_enrichies.json"
SAUVEGARDE_TOUS = 20

# ← Passe à False pour désactiver le debug une fois que tout tourne bien
DEBUG = True

PAUSE_DDG        = (3, 6)
PAUSE_LONGUE_N   = 15
PAUSE_LONGUE     = 45
PAUSE_RATELIMIT  = 90
PAUSE_GEMINI     = 5      # secondes entre chaque appel Gemini (limite gratuite)

# Taille max du HTML envoyé à Gemini (en caractères) — évite de dépasser le contexte
MAX_HTML_GEMINI  = 8000

PAGES_CONTACT = [
    "/contact", "/contacts", "/nous-contacter",
    "/recrutement", "/recrutements", "/rejoindre-nous",
    "/carrieres", "/carrières", "/careers",
    "/jobs", "/offres", "/nous-rejoindre",
    "/rh", "/equipe", "/about", "/a-propos",
]

PREFIXES_RH      = ["recrutement", "rh", "alternance", "stage", "emploi", "jobs", "career", "cv"]
PREFIXES_CONTACT = ["contact", "info", "accueil", "administration", "bonjour"]

DOMAINES_IGNORES = {
    "example.com", "test.com", "sentry.io", "github.com", "w3.org",
    "google.com", "linkedin.com", "facebook.com", "twitter.com",
    "societe.com", "pappers.fr", "infogreffe.fr", "verif.com",
}

DOMAINES_ANNUAIRES = {
    "societe.com", "pappers.fr", "infogreffe.fr", "verif.com",
    "manageo.fr", "sirene.fr", "annuaire-entreprises.data.gouv.fr",
    "kompass.com", "europages.fr", "linkedin.com", "viadeo.com",
    "leboncoin.fr", "indeed.fr", "welcometothejungle.com",
    "francetravail.fr", "pole-emploi.fr",
    "lefigaro.fr", "ameli.fr", "baidu.com",
    "ecdc.europa.eu", "rs-online.com", "skybet.com",
    "wikipedia.org", "wikimedia.org",
    "youtube.com", "instagram.com", "twitter.com", "facebook.com",
    "association.tel", "pages-jaunes.fr", "pagesjaunes.fr",
    "yelp.com", "tripadvisor.fr", "studyrama.com", "capital.fr",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

_compteur_ddg = 0


# ─── Debug helper ─────────────────────────────────────────────────────────────

def dbg(msg):
    if DEBUG:
        print(f"    [dbg] {msg}")


# ─── Utilitaires ──────────────────────────────────────────────────────────────

def pause_ddg():
    global _compteur_ddg
    _compteur_ddg += 1
    if _compteur_ddg % PAUSE_LONGUE_N == 0:
        print(f"\n  [⏸️  Pause {PAUSE_LONGUE}s — {_compteur_ddg} recherches DDG effectuées]")
        time.sleep(PAUSE_LONGUE)
    else:
        time.sleep(random.uniform(*PAUSE_DDG))


def extraire_domaine(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def est_email_valide(email):
    email = email.lower().strip()
    if re.search(r'@[\da-f]{4,}\.', email):
        return False
    if re.search(r'\.(png|jpg|jpeg|gif|svg|ico|webp|pdf|zip)$', email):
        return False
    if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
        return False
    domaine = email.split("@")[-1]
    if domaine in DOMAINES_IGNORES:
        return False
    if any(x in email for x in ["noreply", "no-reply", "donotreply", "bounce", "postmaster", "mailer"]):
        return False
    return True


def scorer_email(email):
    local = email.split("@")[0].lower()
    domaine = email.split("@")[-1].lower()
    # Emails perso : valides mais score très bas
    if domaine in {"gmail.com", "hotmail.com", "hotmail.fr", "yahoo.fr", "yahoo.com", "outlook.com"}:
        return 1
    for i, p in enumerate(PREFIXES_RH):
        if p in local:
            return 100 - i
    for i, p in enumerate(PREFIXES_CONTACT):
        if p in local:
            return 50 - i
    return 10


def extraire_emails_html(html, domaine_entreprise=None):
    emails_texte  = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html)
    emails_mailto = re.findall(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html)
    tous = list(set(e.lower() for e in emails_texte + emails_mailto))
    valides = [e for e in tous if est_email_valide(e)]
    if domaine_entreprise:
        meme   = [e for e in valides if e.split("@")[-1] == domaine_entreprise]
        autres = [e for e in valides if e.split("@")[-1] != domaine_entreprise]
        return meme + autres
    return valides


# ─── Gemini : extraction intelligente ────────────────────────────────────────

def gemini_extraire_contact(texte_page, nom_entreprise, emails_bruts):
    """
    Envoie le texte d'une page contact à Gemini.
    Retourne un dict : {email, telephone, contact_rh, fiable}
    """
    # Tronquer le texte pour ne pas exploser le contexte
    texte_tronque = texte_page[:MAX_HTML_GEMINI]

    emails_str = ", ".join(emails_bruts) if emails_bruts else "aucun trouvé par regex"

    prompt = (
        f"Tu analyses la page de contact/recrutement de l'entreprise '{nom_entreprise}'.\n\n"
        f"Emails détectés par regex (peuvent contenir des faux positifs) : {emails_str}\n\n"
        f"=== CONTENU DE LA PAGE ===\n{texte_tronque}\n\n"
        "=== MISSION ===\n"
        "1. Parmi les emails détectés, garde UNIQUEMENT les vrais emails de contact humains "
        "(recrutement, RH, contact général). Rejette les emails techniques (CDN, images, tracking...).\n"
        "2. Si tu trouves un email de recrutement/RH dans le texte que la regex a manqué, ajoute-le.\n"
        "3. Extrais le numéro de téléphone de l'entreprise si présent (format français de préférence).\n"
        "4. Extrais le nom du contact RH/recruteur si mentionné.\n\n"
        "Réponds UNIQUEMENT en JSON valide, sans backticks, sans texte autour :\n"
        '{"emails": ["contact@example.fr"], "telephone": "01 23 45 67 89", '
        '"contact_rh": "Marie Dupont", "fiable": true}\n\n'
        "Si aucun email valide trouvé : emails = []\n"
        "Si pas de téléphone : telephone = null\n"
        "Si pas de contact nommé : contact_rh = null\n"
        "fiable = false si la page ne semble pas être celle de cette entreprise."
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODELE_GEMINI,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Tu es un expert en extraction de données de contact. "
                    "Tu réponds UNIQUEMENT en JSON valide sans backticks."
                ),
                response_mime_type="application/json",
            )
        )
        texte = response.text
        texte = re.sub(r'```json\s*', '', texte)
        texte = re.sub(r'```\s*', '', texte)
        result = json.loads(texte)
        dbg(f"Gemini → {result}")
        time.sleep(PAUSE_GEMINI)  # respecter la limite gratuite
        return result
    except Exception as e:
        dbg(f"Gemini erreur : {e}")
        time.sleep(PAUSE_GEMINI)
        return {"emails": emails_bruts, "telephone": None, "contact_rh": None, "fiable": True}


# ─── Analyse du nom d'entreprise ──────────────────────────────────────────────

MOTS_IGNORES = {
    "sa", "sas", "sarl", "eurl", "sasu", "sci", "scop", "holding",
    "groupe", "group", "france", "services", "solutions", "technologies",
    "informatique", "info", "systemes", "systèmes", "consulting",
    "conseil", "tech", "digital", "numerique", "numérique",
    "de", "du", "la", "le", "les", "et", "en", "pour",
    "centre", "association", "societe", "société", "production",
}


def analyser_nom(nom):
    nom_clean = re.sub(r"[^a-z0-9\s]", " ", nom.lower())
    tous_mots = nom_clean.split()
    mots_longs  = [m for m in tous_mots if len(m) >= 4 and m not in MOTS_IGNORES]
    mots_courts = [m for m in tous_mots if 2 <= len(m) <= 3 and m not in MOTS_IGNORES]
    acronymes = re.findall(r'\b([A-Z]{2,6})\b', nom)
    acronyme = acronymes[0].lower() if acronymes else None
    if not acronyme and not mots_longs and mots_courts:
        acronyme = "".join(mots_courts)
    dbg(f"Analyse '{nom}' → mots={mots_longs}, acronyme={acronyme}, courts={mots_courts}")
    return {"mots": mots_longs, "acronyme": acronyme, "mots_courts": mots_courts}


def domaine_correspond(domaine, analyse):
    domaine_clean = re.sub(r"[^a-z0-9]", "", domaine.lower())
    for mot in analyse["mots"]:
        if mot in domaine_clean:
            return True, f"mot '{mot}' dans domaine"
    if analyse["acronyme"] and analyse["acronyme"] in domaine_clean:
        return True, f"acronyme '{analyse['acronyme']}' dans domaine"
    domaine_sans_tld = domaine_clean.rsplit(".", 1)[0] if "." in domaine_clean else domaine_clean
    for mot in analyse["mots_courts"]:
        if mot == domaine_sans_tld or domaine_sans_tld.startswith(mot):
            return True, f"mot court '{mot}' = début domaine"
    return False, "aucun mot du nom trouvé dans le domaine"


def est_url_valide(url, nom, analyse):
    domaine = extraire_domaine(url)
    if not domaine:
        return False, "URL invalide"
    for annuaire in DOMAINES_ANNUAIRES:
        if annuaire in domaine:
            return False, f"annuaire ({annuaire})"
    tld = domaine.rsplit(".", 1)[-1] if "." in domaine else ""
    if tld in {"cn", "ru", "ua", "in", "br", "mx"}:
        return False, f"TLD suspect ({tld})"
    return domaine_correspond(domaine, analyse)


# ─── Requêtes DDG ─────────────────────────────────────────────────────────────

def construire_requetes(entreprise, analyse):
    nom = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    ville = entreprise.get("ville") or ""
    cp = entreprise.get("code_postal") or ""
    dept = cp[:2] if cp else ""
    lieu = f"{ville} {dept}".strip()
    requetes = []
    if analyse["mots"]:
        mots_str = " ".join(analyse["mots"][:3])
        requetes.append(f'"{mots_str}" {lieu} site officiel')
    if analyse["acronyme"]:
        requetes.append(f'"{analyse["acronyme"]}" informatique {lieu} site officiel')
    nom_court = re.sub(r'\s*[\(\;].*', '', nom).strip()
    requetes.append(f'{nom_court} {lieu} recrutement contact')
    dbg(f"Requêtes : {requetes}")
    return requetes


def chercher_site_duckduckgo(entreprise):
    nom = entreprise.get("nom_commercial") or entreprise.get("nom", "")
    analyse = analyser_nom(nom)
    requetes = construire_requetes(entreprise, analyse)
    for i, requete in enumerate(requetes):
        dbg(f"Requête {i+1}/{len(requetes)} : {requete}")
        try:
            pause_ddg()
            with DDGS() as ddg:
                resultats = list(ddg.text(requete, max_results=5))
            dbg(f"  → {len(resultats)} résultats")
            for r in resultats:
                url = r.get("href", "")
                if not url:
                    continue
                valide, raison = est_url_valide(url, nom, analyse)
                dbg(f"  {'✅' if valide else '❌'} {extraire_domaine(url)} — {raison}")
                if valide:
                    return url
        except RatelimitException:
            print(f"  [⚠️  Rate limit DDG — attente {PAUSE_RATELIMIT}s...]")
            time.sleep(PAUSE_RATELIMIT)
            try:
                with DDGS() as ddg:
                    resultats = list(ddg.text(requete, max_results=5))
                for r in resultats:
                    url = r.get("href", "")
                    valide, _ = est_url_valide(url, nom, analyse)
                    if url and valide:
                        return url
            except Exception:
                pass
        except Exception as e:
            dbg(f"DDG erreur : {e}")
    return None


# ─── Scraping + Gemini ────────────────────────────────────────────────────────

def get_page(url, timeout=8):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code < 400 and "text/html" in r.headers.get("content-type", ""):
            return r.text, r.url
    except Exception:
        pass
    return None, None


def html_vers_texte(html):
    """Extrait le texte lisible d'une page HTML pour l'envoyer à Gemini."""
    soup = BeautifulSoup(html, "html.parser")
    # Supprimer scripts, styles, nav, footer qui polluent
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def trouver_liens_contact(soup, base_url):
    domaine_base = extraire_domaine(base_url)
    liens = set()
    mots_cles = ["contact", "recrutement", "carriere", "carrieres", "emploi",
                 "job", "jobs", "rejoindre", "rh", "about", "equipe", "team"]
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        texte = a.get_text(strip=True).lower()
        href_lower = href.lower()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if any(href_lower.endswith(ext) for ext in (".pdf", ".jpg", ".png", ".zip")):
            continue
        if any(m in href_lower for m in mots_cles) or any(m in texte for m in mots_cles):
            lien = urljoin(base_url, href)
            if extraire_domaine(lien) == domaine_base:
                liens.add(lien)
    return list(liens)[:6]


def scraper_et_extraire(url_site, nom_entreprise):
    """
    Scrape le site, collecte emails bruts avec BS4,
    puis appelle Gemini pour nettoyer et enrichir.
    Retourne : {emails, telephone, contact_rh, url_finale}
    """
    url_site = url_site.strip().rstrip("/")
    if not url_site.startswith("http"):
        url_site = "https://" + url_site

    domaine = extraire_domaine(url_site)
    tous_emails_bruts = []
    meilleur_texte_contact = ""  # texte de la page la plus pertinente pour Gemini

    html, url_finale = get_page(url_site)
    if not html:
        alt = url_site.replace("://www.", "://") if "://www." in url_site \
              else url_site.replace("://", "://www.")
        html, url_finale = get_page(alt)

    if not html:
        return {"emails": [], "telephone": None, "contact_rh": None, "url_finale": None}

    soup = BeautifulSoup(html, "html.parser")
    tous_emails_bruts.extend(extraire_emails_html(html, domaine))

    # Trouver les pages contact
    liens = trouver_liens_contact(soup, url_finale or url_site)
    for chemin in PAGES_CONTACT:
        liens.append(urljoin(url_finale or url_site, chemin))

    vus = {url_finale or url_site}
    pages_texte = [html_vers_texte(html)]  # page d'accueil en premier

    for lien in liens[:8]:
        if lien in vus:
            continue
        vus.add(lien)
        time.sleep(random.uniform(0.8, 2.0))
        html_page, _ = get_page(lien)
        if html_page:
            tous_emails_bruts.extend(extraire_emails_html(html_page, domaine))
            # Garder le texte des pages contact pour Gemini
            mots_contact = ["contact", "recrutement", "rh", "emploi", "carriere"]
            if any(m in lien.lower() for m in mots_contact):
                pages_texte.insert(0, html_vers_texte(html_page))  # priorité aux pages contact

    # Dédupliquer les emails bruts
    emails_bruts_uniques = list(set(tous_emails_bruts))
    dbg(f"Emails bruts BS4 : {emails_bruts_uniques}")

    # Texte à envoyer à Gemini : page contact en priorité, sinon accueil
    texte_pour_gemini = "\n\n---\n\n".join(pages_texte[:2])  # max 2 pages

    # Appel Gemini
    dbg("→ Appel Gemini pour extraction intelligente...")
    resultat_gemini = gemini_extraire_contact(texte_pour_gemini, nom_entreprise, emails_bruts_uniques)

    emails_finals = resultat_gemini.get("emails", [])
    # Validation finale : s'assurer que les emails Gemini passent quand même le filtre de base
    emails_finals = [e for e in emails_finals if est_email_valide(e)]
    emails_finals = sorted(emails_finals, key=scorer_email, reverse=True)[:5]

    return {
        "emails": emails_finals,
        "telephone": resultat_gemini.get("telephone"),
        "contact_rh": resultat_gemini.get("contact_rh"),
        "url_finale": url_finale,
        "fiable": resultat_gemini.get("fiable", True),
    }


# ─── Pipeline principal ───────────────────────────────────────────────────────

def charger_entreprises():
    fichier = FICHIER_SORTIE if os.path.exists(FICHIER_SORTIE) else FICHIER_ENTREE
    with open(fichier, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[Chargement] {fichier} → {len(data)} entreprises")
    return data


def sauvegarder(entreprises):
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(entreprises, f, ensure_ascii=False, indent=2)


def main():
    print("=" * 60)
    print("  Chasseur d'Alternance — Scraper Emails v4")
    print(f"  DEBUG = {DEBUG}  |  Gemini = {MODELE_GEMINI}")
    print("=" * 60)

    entreprises = charger_entreprises()
    a_traiter = [e for e in entreprises if not e.get("traite")]
    deja_faits = len(entreprises) - len(a_traiter)
    print(f"[Queue] {len(a_traiter)} à traiter | {deja_faits} déjà traités\n")

    if not a_traiter:
        print("✅ Tout traité ! Lance : python export_excel.py")
        return

    traites_ce_run = 0

    for i, e in enumerate(entreprises):
        if e.get("traite"):
            continue

        nom = (e.get("nom_commercial") or e.get("nom", "?"))[:50]
        idx = deja_faits + traites_ce_run + 1
        print(f"\n[{idx}/{len(entreprises)}] {nom}")

        # Étape 1 : trouver le site
        url = e.get("site_web")
        if not url:
            url = chercher_site_duckduckgo(e)
            if url:
                e["site_web"] = url
                print(f"  🌐 {url}")
            else:
                print(f"  ❌ Site introuvable")
                e["emails_trouves"] = []
                e["telephone"] = None
                e["contact_rh"] = None
                e["traite"] = True
                traites_ce_run += 1
                continue

        # Étape 2 : scraper + Gemini
        resultat = scraper_et_extraire(url, nom)

        # Ignorer si Gemini juge la page non fiable (mauvais site)
        if not resultat.get("fiable", True):
            print(f"  ⚠️  Page non fiable selon Gemini — site ignoré")
            e["site_web"] = None  # reset pour réessayer plus tard si besoin
            e["emails_trouves"] = []
            e["telephone"] = None
            e["contact_rh"] = None
            e["traite"] = True
            traites_ce_run += 1
            continue

        emails    = resultat["emails"]
        telephone = resultat.get("telephone")
        contact   = resultat.get("contact_rh")

        # Affichage résultat
        if emails:
            print(f"  ✅ {', '.join(emails[:3])}")
        else:
            print(f"  ⚠️  Aucun email")
        if telephone:
            print(f"  📞 {telephone}")
        if contact:
            print(f"  👤 {contact}")

        e["emails_trouves"] = emails
        e["telephone"]      = telephone
        e["contact_rh"]     = contact
        e["url_scrapee"]    = resultat.get("url_finale") or url
        e["traite"]         = True
        traites_ce_run += 1

        if traites_ce_run % SAUVEGARDE_TOUS == 0:
            sauvegarder(entreprises)
            avec = sum(1 for x in entreprises if x.get("emails_trouves"))
            print(f"\n  [💾 Sauvegarde — {idx}/{len(entreprises)} | {avec} avec email]\n")

    sauvegarder(entreprises)

    avec_email = sum(1 for e in entreprises if e.get("emails_trouves"))
    avec_tel   = sum(1 for e in entreprises if e.get("telephone"))
    avec_site  = sum(1 for e in entreprises if e.get("site_web"))
    print("\n" + "=" * 60)
    print(f"  Total          : {len(entreprises)}")
    print(f"  Avec site      : {avec_site}")
    print(f"  Avec emails    : {avec_email}")
    print(f"  Avec téléphone : {avec_tel}")
    print(f"  Fichier        : {FICHIER_SORTIE}")
    print("=" * 60)
    print("\n→ Lance : python export_excel.py")


if __name__ == "__main__":
    main()



--- FICHIER : static/app.js ---
var candidatures = [];
var timers = {};
var sectionActive = 'offres';
var filtres = {score:'tous', zone:'tous', domaine:'tous', source:'tous'};
var filtreCand = 'tous';
var triActif = 'score';
var sidebarOpen = false;

function formatDate(d) {
    if (!d) return '';
    var mois = ['jan','fév','mar','avr','mai','jun','jul','aoû','sep','oct','nov','déc'];
    var parts = d.split('-');
    if (parts.length < 3) return d;
    return parts[2] + ' ' + mois[parseInt(parts[1])-1] + ' ' + parts[0];
}

// ─── SIDEBAR ─────────────────────────────────
function toggleSidebar() {
    sidebarOpen = !sidebarOpen;
    var sb = document.getElementById('sidebar');
    if (sidebarOpen) {
        sb.classList.remove('closing');
        sb.classList.add('open');
        document.getElementById('toggle-btn').textContent = '✕';
    } else {
        sb.classList.remove('open');
        sb.classList.add('closing');
        document.getElementById('toggle-btn').textContent = '☰';
    }
}

// ─── PANELS FILTRES/TRI ──────────────────────
function togglePanel(id) {
    ['panel-filtres','panel-tri'].forEach(function(p) {
        if (p !== id) document.getElementById(p).classList.remove('open');
    });
    document.getElementById(id).classList.toggle('open');
}

document.addEventListener('click', function(e) {
    if (!e.target.closest('#panel-filtres') && !e.target.closest('#btn-filtres'))
        document.getElementById('panel-filtres').classList.remove('open');
    if (!e.target.closest('#panel-tri') && !e.target.closest('#btn-tri'))
        document.getElementById('panel-tri').classList.remove('open');
});

// ─── TRI ─────────────────────────────────────
function setTri(type) {
    triActif = type;
    document.getElementById('tri-check-score').style.color = type==='score' ? 'var(--accent)' : 'transparent';
    document.getElementById('tri-check-date').style.color = type==='date' ? 'var(--accent)' : 'transparent';
    document.getElementById('tri-label').textContent = type==='score' ? 'Note' : 'Date';
    document.getElementById('panel-tri').classList.remove('open');
    afficherOffres();
}

// ─── FILTRES ─────────────────────────────────
function setFiltre(type, val, btn) {
    filtres[type] = val;
    var parent = btn.parentElement;
    parent.querySelectorAll('.fsm').forEach(function(b) { b.classList.remove('actif','actif-zone','actif-domaine'); });
    var cls = type==='zone' ? 'actif-zone' : type==='domaine' ? 'actif-domaine' : 'actif';
    btn.classList.add(cls);
    var nb = Object.values(filtres).filter(function(v){return v!=='tous';}).length;
    var fc = document.getElementById('filtres-count');
    fc.textContent = nb; fc.style.display = nb > 0 ? 'inline' : 'none';
    document.getElementById('panel-filtres').classList.remove('open');
    afficherOffres();
}

function reinitialiserFiltres() {
    filtres = {score:'tous', zone:'tous', domaine:'tous', source:'tous'};
    document.querySelectorAll('.fsm').forEach(function(b) {
        b.classList.remove('actif','actif-zone','actif-domaine');
        if (b.textContent === 'Tous') b.classList.add('actif');
    });
    document.getElementById('filtres-count').style.display = 'none';
    document.getElementById('panel-filtres').classList.remove('open');
    afficherOffres();
}

function setFiltreCand(val, btn) {
    filtreCand = val;
    btn.closest('.toolbar-filtres').querySelectorAll('.btn').forEach(function(b) {
        b.style.borderColor = ''; b.style.color = '';
    });
    btn.style.borderColor = 'var(--accent)'; btn.style.color = 'var(--accent)';
    afficherCandidatures();
}

// ─── NAVIGATION ──────────────────────────────
function afficherSection(section) {
    sectionActive = section;
    ['offres','candidatures','spontanees','archive'].forEach(function(s) {
        var el = document.getElementById('section-'+s);
        if (el) el.style.display = s===section ? 'block' : 'none';
        var nav = document.getElementById('nav-'+s);
        if (nav) nav.classList.toggle('active', s===section);
    });
    var titres = {offres:'Offres', candidatures:'Candidatures', spontanees:'Spontanées', archive:'Archives'};
    document.getElementById('page-title').textContent = titres[section] || 'Offres';
    if (section==='offres') afficherOffres();
    if (section==='candidatures') afficherCandidatures();
    if (section==='archive') afficherArchives();
}

// ─── INIT ────────────────────────────────────
async function charger() {
    var r = await fetch('/api/candidatures');
    candidatures = await r.json();
    mettreAJourStats();
    construireFiltresDynamiques();
    afficherSection(sectionActive);
}

// ─── STATS ───────────────────────────────────
function mettreAJourStats() {
    var actives = candidatures.filter(function(c){return !['envoye','reponse','entretien','refus','rejete','archive'].includes(c.statut);});
    var env = candidatures.filter(function(c){return ['envoye','reponse','entretien','refus'].includes(c.statut);});
    var arch = candidatures.filter(function(c){return c.statut==='archive';});
    document.getElementById('s-total').textContent = candidatures.length;
    document.getElementById('s-top').textContent = candidatures.filter(function(c){return c.score>=7;}).length;
    document.getElementById('s-env').textContent = env.length;
    document.getElementById('s-entr').textContent = candidatures.filter(function(c){return c.statut==='entretien';}).length;
    document.getElementById('s-arch').textContent = arch.length;
    document.getElementById('badge-offres').textContent = actives.length;
    var bc = document.getElementById('badge-candidatures');
    if (bc) bc.textContent = env.length;
}

// ─── FILTRES DYNAMIQUES ──────────────────────
function construireFiltresDynamiques() {
    var zones = [...new Set(candidatures.map(function(c){return c.zone;}).filter(Boolean))].sort();
    var domaines = [...new Set(candidatures.map(function(c){return c.domaine;}).filter(Boolean))].sort();
    var sources = [...new Set(candidatures.map(function(c){return c.source;}).filter(Boolean))].sort();
    function build(elId, vals, type) {
        var el = document.getElementById(elId);
        if (!el) return;
        el.innerHTML = '<button class="fsm actif" onclick="setFiltre(\''+type+'\',\'tous\',this)">Tous</button>';
        vals.forEach(function(v) {
            el.innerHTML += '<button class="fsm" onclick="setFiltre(\''+type+'\',\''+v+'\',this)">'+v+'</button>';
        });
    }
    build('filtres-zone', zones, 'zone');
    build('filtres-domaine', domaines, 'domaine');
    build('filtres-source', sources, 'source');
}

// ─── AFFICHAGE OFFRES ────────────────────────
function afficherOffres() {
    var liste = candidatures.filter(function(c){
        return !['envoye','reponse','entretien','refus','archive'].includes(c.statut);
    });
    if (filtres.score==='haut') liste = liste.filter(function(c){return c.score>=8;});
    else if (filtres.score==='moyen') liste = liste.filter(function(c){return c.score>=5&&c.score<8;});
    else if (filtres.score==='bas') liste = liste.filter(function(c){return c.score<5;});
    if (filtres.zone!=='tous') liste = liste.filter(function(c){return c.zone===filtres.zone;});
    if (filtres.domaine!=='tous') liste = liste.filter(function(c){return c.domaine===filtres.domaine;});
    if (filtres.source!=='tous') liste = liste.filter(function(c){return c.source===filtres.source;});
    if (triActif==='date') liste.sort(function(a,b){return new Date(b.date_trouvee)-new Date(a.date_trouvee);});
    else liste.sort(function(a,b){return b.score-a.score;});
    var cnt = document.getElementById('offres-count');
    if (cnt) cnt.textContent = liste.length + ' offre' + (liste.length>1?'s':'');
    var el = document.getElementById('offres');
    if (liste.length===0) { el.innerHTML='<div class="empty"><div class="icon">🔍</div><p>Aucune offre.</p></div>'; return; }
    el.innerHTML = liste.map(construireOffre).join('');
}

// ─── AFFICHAGE ARCHIVES ──────────────────────
function afficherArchives() {
    var liste = candidatures.filter(function(c){return c.statut==='archive';});
    var el = document.getElementById('section-archive');
    if (!el) return;
    if (liste.length===0) {
        el.innerHTML = '<div class="empty"><div class="icon">🗑</div><p>Aucune offre archivée.</p></div>';
    } else {
        el.innerHTML = '<div class="offres">'+liste.map(construireOffre).join('')+'</div>';
    }
}

// ─── AFFICHAGE CANDIDATURES ──────────────────
function afficherCandidatures() {
    var liste = candidatures.filter(function(c){return ['envoye','reponse','entretien','refus'].includes(c.statut);});
    if (filtreCand!=='tous') liste = liste.filter(function(c){return c.statut===filtreCand;});
    liste.sort(function(a,b){return new Date(b.date_candidature||0)-new Date(a.date_candidature||0);});
    var grid = document.getElementById('cand-grid');
    if (!grid) return;
    if (liste.length===0) { grid.innerHTML='<div class="empty" style="grid-column:1/-1"><div class="icon">📬</div><p>Aucune candidature envoyée.</p></div>'; return; }
    var sl = {envoye:'Envoyée',reponse:'Réponse reçue',entretien:'Entretien',refus:'Refus'};
    grid.innerHTML = liste.map(function(o) {
        return '<div class="cc">'
            +'<div class="cc-titre">'+o.titre+'</div>'
            +'<div class="cc-meta">'+o.entreprise+' · '+o.lieu+'</div>'
            +'<span class="badge-statut badge-'+o.statut+'">'+(sl[o.statut]||o.statut)+'</span>'
            +(o.date_candidature?'<div class="cc-date">Envoyée le '+formatDate(o.date_candidature)+'</div>':'')
            +'<div class="cc-actions">'
            +'<a class="btn btn-secondary" style="font-size:.68rem;padding:4px 10px;text-decoration:none" href="'+o.lien+'" target="_blank">Voir l\'offre</a>'
            +'<select onchange="changerStatutCand(\''+o.id+'\',this.value)" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);padding:4px 8px;font-family:DM Mono,monospace;font-size:.68rem;outline:none">'
            +'<option value="envoye"'+(o.statut==='envoye'?' selected':'')+'>Envoyée</option>'
            +'<option value="reponse"'+(o.statut==='reponse'?' selected':'')+'>Réponse reçue</option>'
            +'<option value="entretien"'+(o.statut==='entretien'?' selected':'')+'>Entretien</option>'
            +'<option value="refus"'+(o.statut==='refus'?' selected':'')+'>Refus</option>'
            +'</select></div></div>';
    }).join('');
}

async function changerStatutCand(id, statut) {
    await fetch('/api/maj_statut',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,statut:statut})});
    var c = candidatures.find(function(c){return c.id===id;});
    if (c) c.statut = statut;
    mettreAJourStats(); afficherCandidatures();
    toast('Statut mis à jour !','ok');
}

// ─── CONSTRUCTION OFFRE ──────────────────────
function construireOffre(o) {
    var sc = o.score>=8?'haut':(o.score>=5?'moyen':'bas');
    var sl = {nouveau:'Nouvelle',en_cours:'En cours',rejete:'Rejetée',archive:'Archivée'};
    var pf = (o.points_forts||[]).map(function(p){return '<li>'+p+'</li>';}).join('');
    var pw = (o.points_faibles||[]).map(function(p){return '<li>'+p+'</li>';}).join('');
    var lt = (o.lettre||'').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    var da = o.resume_analyse && o.resume_analyse!=='Non analysée' && o.resume_analyse!=='Non analysee' && o.resume_analyse!=='Analyse echouee';
    var isArchive = o.statut==='archive';

    return '<div class="offre" id="offre-'+o.id+'">'
        +'<div class="offre-header" onclick="toggleOffre(\''+o.id+'\')">'
        +'<div class="offre-left">'
        +'<div class="offre-titre">'+o.titre+'</div>'
        +'<div class="offre-meta">'+o.entreprise+' · '+o.lieu
        +(o.zone?' <span class="mtag mzone">'+o.zone+'</span>':'')
        +(o.domaine?' <span class="mtag mdom">'+o.domaine+'</span>':'')
        +' <span class="mtag msrc">'+o.source+'</span>'
        +' · '+formatDate(o.date_trouvee)+'</div></div>'
        +'<div class="offre-right">'
        +'<span class="badge-statut badge-'+(o.statut||'nouveau')+'">'+(sl[o.statut]||'Nouvelle')+'</span>'
        +'<div class="score '+sc+'">'+o.score+'</div>'
        +(o.eligible===false?'<span style="color:#ff6584;font-size:.6rem;border:1px solid rgba(255,101,132,.4);padding:1px 5px;border-radius:20px;background:rgba(255,101,132,.1)">✕</span>':'')
        +'</div></div>'
        +'<div class="offre-body" id="body-'+o.id+'">'
        +'<div class="grid-2" style="margin-bottom:14px">'

        // Colonne gauche — Analyse IA
        +'<div><div class="sl">Analyse IA</div>'
        +'<div class="abox">'+(o.resume_analyse||'Non analysée')+'</div>'
        +(pf?'<ul class="points" style="margin-top:7px">'+pf+'</ul>':'')
        +(pw?'<ul class="points faibles" style="margin-top:3px">'+pw+'</ul>':'')
        +'<div style="margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
        +'<a class="lo" href="'+o.lien+'" target="_blank">Voir l\'offre →</a>'
        +(da?'<span style="font-size:.65rem;color:var(--muted)">✓ Analysée</span>'
            :'<button class="btn btn-secondary" style="font-size:.68rem;padding:4px 9px" onclick="analyser(\''+o.id+'\')">Analyser</button>')
        +(isArchive
            ?'<button class="btn btn-secondary" style="font-size:.68rem;padding:4px 9px;color:var(--accent)" onclick="desarchiver(\''+o.id+'\')">♻ Restaurer</button>'
            :'<button class="btn btn-secondary" style="font-size:.68rem;padding:4px 9px;color:var(--accent2)" onclick="archiver(\''+o.id+'\')">🗑 Archiver</button>')
        +'</div></div>'

        // Colonne droite — Statut uniquement
        +'<div><div class="sl">Statut</div>'
        +'<div style="display:flex;flex-direction:column;gap:6px">'
        +'<select id="statut-'+o.id+'" onchange="changerStatut(\''+o.id+'\')" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);padding:6px 10px;font-family:DM Mono,monospace;font-size:.74rem;outline:none">'
        +'<option value="nouveau"'+(o.statut==='nouveau'?' selected':'')+'>Nouvelle</option>'
        +'<option value="en_cours"'+(o.statut==='en_cours'?' selected':'')+'>En cours</option>'
        +'<option value="envoye"'+(o.statut==='envoye'?' selected':'')+'>Envoyée</option>'
        +'<option value="reponse"'+(o.statut==='reponse'?' selected':'')+'>Réponse reçue</option>'
        +'<option value="entretien"'+(o.statut==='entretien'?' selected':'')+'>Entretien</option>'
        +'<option value="refus"'+(o.statut==='refus'?' selected':'')+'>Refus</option>'
        +'<option value="rejete"'+(o.statut==='rejete'?' selected':'')+'>Rejetée</option>'
        +'</select>'
        +(o.date_candidature?'<span style="font-size:.65rem;color:var(--muted)">Postulée le '+formatDate(o.date_candidature)+'</span>':'')
        +'</div></div></div>'

        // Lettre
        +'<div style="margin-bottom:14px">'
        +'<div class="sl">Lettre <span style="font-size:.58rem;color:var(--muted)" id="statut-lettre-'+o.id+'"></span></div>'
        +'<textarea class="tl" id="lettre-'+o.id+'" oninput="sauvegardeAuto(\''+o.id+'\',\'lettre\')">'+lt+'</textarea>'
        +'<div class="actions">'
        +'<button class="btn btn-primary" style="font-size:.7rem" onclick="genererLettre(\''+o.id+'\')">Générer lettre</button>'
        +'<button class="btn btn-secondary" style="font-size:.7rem" onclick="telechargerPDF(\''+o.id+'\')">PDF</button>'
        +(o.source==='France Travail'?'<button class="btn btn-primary" style="font-size:.7rem;background:#e8301e;border-color:#e8301e" onclick="postulerFranceTravail(\''+o.id+'\',\''+o.lien+'\')">Postuler FT</button>':'')
        +'</div></div>'
        +'</div></div>';
}

// ─── TOGGLE OFFRE ────────────────────────────
function toggleOffre(id) {
    var b = document.getElementById('body-'+id);
    if (!b) return;
    var estOuverte = b.classList.contains('open');
    document.querySelectorAll('.offre-body').forEach(function(el){
        el.classList.remove('open');
    });
    if (!estOuverte) b.classList.add('open');
}

// ─── SAUVEGARDE AUTO ─────────────────────────
function sauvegardeAuto(id, type) {
    var key = id+type;
    clearTimeout(timers[key]);
    var ind = document.getElementById('statut-lettre-'+id);
    if (ind) ind.textContent = '...';
    timers[key] = setTimeout(async function() {
        var payload = {id:id};
        if (type==='lettre') {
            payload.lettre = document.getElementById('lettre-'+id).value;
            var c = candidatures.find(function(c){return c.id===id;});
            if (c) c.lettre = payload.lettre;
        }
        await fetch('/api/sauvegarder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        var c = candidatures.find(function(c){return c.id===id;});
        if (c && c.statut==='nouveau') {
            c.statut = 'en_cours';
            fetch('/api/maj_statut',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,statut:'en_cours'})});
            var sel = document.getElementById('statut-'+id); if (sel) sel.value='en_cours';
            var offEl = document.getElementById('offre-'+id);
            if (offEl) { var badge=offEl.querySelector('.badge-statut'); if(badge){badge.className='badge-statut badge-en_cours';badge.textContent='En cours';} }
        }
        if (ind) { ind.textContent='✓'; setTimeout(function(){if(ind)ind.textContent='';},2000); }
    }, 2000);
}

// ─── RECHERCHE ───────────────────────────────
async function lancerRecherche() {
    var btn=document.getElementById('btnRecherche'), st=document.getElementById('searchStatus');
    btn.disabled=true; st.textContent='Recherche...';
    await fetch('/api/recherche',{method:'POST'});
    var iv=setInterval(async function(){
        var r=await fetch('/api/statut_recherche'), s=await r.json();
        st.textContent=s.message||'En cours...';
        if(!s.en_cours){
            clearInterval(iv);
            btn.disabled=false;
            st.textContent='Prêt';
            await charger();
            toast('Recherche terminée — '+candidatures.length+' offres !','ok');
        }
    },3000);
}

// ─── GÉNÉRATION LETTRE ───────────────────────
async function genererLettre(id) {
    var btn=event.target; btn.disabled=true; btn.textContent='...';
    toast('Génération lettre...','ok');
    var r=await fetch('/api/generer_lettre',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
    var data=await r.json();
    if(data.lettre){
        document.getElementById('lettre-'+id).value=data.lettre;
        var c=candidatures.find(function(c){return c.id===id;}); if(c) c.lettre=data.lettre;
        var ind=document.getElementById('statut-lettre-'+id); if(ind) ind.textContent='✓';
        toast('Lettre générée !','ok');
    } else toast('Erreur génération','err');
    btn.disabled=false; btn.textContent='Générer lettre';
}

// ─── PDF ─────────────────────────────────────
async function telechargerPDF(id) {
    var lt = document.getElementById('lettre-'+id).value;
    if (!lt.trim()) { toast('Génère d\'abord une lettre !', 'err'); return; }
    var btn = event.target;
    btn.disabled = true;
    btn.textContent = '...';
    await fetch('/api/sauvegarder', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id, lettre: lt})
    });
    var r = await fetch('/api/telecharger_pdf', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id, lettre: lt})
    });
    var data = await r.json();
    if (data.ok) {
        btn.textContent = '✓ PDF prêt';
        btn.style.borderColor = 'var(--green)';
        btn.style.color = 'var(--green)';
        toast('✅ Lettre générée dans lettres_pdf/', 'ok');
        setTimeout(function() {
            btn.disabled = false;
            btn.textContent = 'PDF';
            btn.style.borderColor = '';
            btn.style.color = '';
        }, 3000);
    } else {
        toast('Erreur PDF', 'err');
        btn.disabled = false;
        btn.textContent = 'PDF';
    }
}

// ─── POSTULER FRANCE TRAVAIL ─────────────────
async function postulerFranceTravail(id, lien) {
    window.open(lien, '_blank');
    var lt = document.getElementById('lettre-'+id).value;
    if (!lt.trim()) {
        toast('Génération lettre...', 'ok');
        var r = await fetch('/api/generer_lettre', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: id})
        });
        var data = await r.json();
        if (data.lettre) {
            document.getElementById('lettre-'+id).value = data.lettre;
            var c = candidatures.find(function(c){return c.id===id;});
            if (c) c.lettre = data.lettre;
            lt = data.lettre;
        } else { toast('Erreur lettre', 'err'); return; }
    }
    await fetch('/api/sauvegarder', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id, lettre: lt})
    });
    var r2 = await fetch('/api/telecharger_pdf', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id, lettre: lt})
    });
    var data2 = await r2.json();
    if (data2.ok) {
        toast('✅ Lettre prête dans lettres_pdf/ — France Travail ouvert !', 'ok');
    } else {
        toast('Erreur génération lettre', 'err');
    }
    var c = candidatures.find(function(c){return c.id===id;});
    if (c && c.statut==='nouveau') {
        c.statut = 'en_cours';
        fetch('/api/maj_statut', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: id, statut: 'en_cours'})
        });
        mettreAJourStats();
    }
}

// ─── ANALYSER ────────────────────────────────
async function analyser(id) {
    toast('Analyse en cours...','ok');
    var r=await fetch('/api/analyser',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
    var data=await r.json();
    if(data.score){
        var c=candidatures.find(function(c){return c.id===id;});
        if(c){c.score=data.score;c.verdict=data.verdict;c.eligible=data.eligible;c.points_forts=data.points_forts;c.points_faibles=data.points_faibles;c.resume_analyse=data.resume;}
        afficherOffres();
        toast('Score : '+data.score+'/10','ok');
    }
}

// ─── STATUT ──────────────────────────────────
async function changerStatut(id) {
    var statut=document.getElementById('statut-'+id).value;
    await fetch('/api/maj_statut',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,statut:statut})});
    var c=candidatures.find(function(c){return c.id===id;}); if(c) c.statut=statut;
    mettreAJourStats();
    if(['envoye','reponse','entretien','refus','archive'].includes(statut)){
        afficherSection(sectionActive);
        toast('Déplacée !','ok');
    } else toast('Statut mis à jour !','ok');
}

// ─── ARCHIVER / RESTAURER ────────────────────
async function archiver(id) {
    await fetch('/api/archiver',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
    var c=candidatures.find(function(c){return c.id===id;}); if(c) c.statut='archive';
    mettreAJourStats(); afficherOffres();
    toast('Offre archivée','ok');
}

async function desarchiver(id) {
    await fetch('/api/maj_statut',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,statut:'nouveau'})});
    var c=candidatures.find(function(c){return c.id===id;}); if(c) c.statut='nouveau';
    mettreAJourStats(); afficherArchives();
    toast('Offre restaurée','ok');
}

// ─── TOAST ───────────────────────────────────
function toast(msg, type) {
    var t=document.createElement('div'); t.className='toast '+type; t.textContent=msg;
    document.body.appendChild(t); setTimeout(function(){t.remove();},3500);
}

charger();



--- FICHIER : templates/index.html ---
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Chasseur Alternance</title>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet"/>
  <style>
    :root{--bg:#0f0f14;--surface:#16161e;--border:#2a2a3a;--accent:#6c63ff;--accent2:#ff6584;--green:#4ade80;--yellow:#fbbf24;--text:#e8e8f0;--muted:#6b6b8a;--radius:6px;--sw:220px;--sc:52px}
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:var(--bg);color:var(--text);font-family:'DM Mono',monospace;min-height:100vh;display:flex}
    /* SIDEBAR — fermée par défaut, PAS de transition au chargement */
    .sidebar{width:var(--sc);min-height:100vh;background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;position:sticky;top:0;height:100vh;overflow:hidden}
    .sidebar.open{width:var(--sw);transition:width .25s}
    .sidebar.closing{width:var(--sc);transition:width .25s}
    .sidebar-top{padding:16px 12px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border);min-height:56px;gap:8px}
    .sidebar-logo{font-family:'Instrument Serif',serif;font-size:1.1rem;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;white-space:nowrap;overflow:hidden;max-width:0;opacity:0}
    .sidebar.open .sidebar-logo{max-width:200px;opacity:1;transition:opacity .2s .1s}
    .toggle-btn{background:none;border:none;color:var(--muted);cursor:pointer;font-size:1.1rem;padding:4px;flex-shrink:0;line-height:1}
    .toggle-btn:hover{color:var(--text)}
    .nav{flex:1;padding:12px 0}
    .nav-item{display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer;border-left:2px solid transparent;transition:all .15s;white-space:nowrap;overflow:hidden}
    .nav-item:hover{background:rgba(108,99,255,.08);color:var(--text)}
    .nav-item.active{border-left-color:var(--accent);color:var(--accent);background:rgba(108,99,255,.1)}
    .nav-icon{font-size:1rem;flex-shrink:0;width:20px;text-align:center}
    .nav-label,.nav-badge,.sidebar-stats{opacity:0;pointer-events:none}
    .sidebar.open .nav-label,.sidebar.open .nav-badge,.sidebar.open .sidebar-stats{opacity:1;pointer-events:auto;transition:opacity .2s .1s}
    .nav-label{font-size:.75rem;letter-spacing:.04em}
    .nav-badge{margin-left:auto;background:var(--accent);color:white;font-size:.58rem;padding:1px 5px;border-radius:10px;flex-shrink:0}
    .sidebar-stats{padding:12px;border-top:1px solid var(--border)}
    .stat-mini{display:flex;justify-content:space-between;font-size:.65rem;color:var(--muted);padding:3px 0}
    .stat-mini span:last-child{color:var(--text);font-weight:500}
    /* MAIN */
    .main{flex:1;min-width:0;display:flex;flex-direction:column}
    .topbar{padding:16px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;min-height:56px}
    .topbar-left{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
    .page-title{font-family:'Instrument Serif',serif;font-size:1.3rem;font-weight:400}
    .search-status{font-size:.72rem;color:var(--muted);padding:4px 10px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius)}
    .content{padding:20px 24px;flex:1}
    .btn{padding:7px 16px;border-radius:var(--radius);font-family:'DM Mono',monospace;font-size:.74rem;cursor:pointer;border:1px solid;transition:all .15s;letter-spacing:.04em}
    .btn-primary{background:var(--accent);color:white;border-color:var(--accent)}
    .btn-primary:hover{opacity:.85}
    .btn-secondary{background:transparent;color:var(--muted);border-color:var(--border)}
    .btn-secondary:hover{border-color:var(--accent);color:var(--accent)}
    .btn:disabled{opacity:.4;cursor:not-allowed}
    /* TOOLBAR */
    .toolbar-filtres{display:flex;gap:8px;margin-bottom:16px;align-items:center;flex-wrap:wrap}
    /* PANEL DROPDOWN */
    .panel-dropdown{display:none;position:absolute;top:calc(100% + 8px);left:0;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px;z-index:100;box-shadow:0 8px 32px rgba(0,0,0,.5);min-width:240px}
    .panel-dropdown.open{display:block}
    .panel-sec{font-size:.58rem;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;margin:12px 0 6px}
    .panel-sec:first-child{margin-top:0}
    .fg{display:flex;gap:5px;flex-wrap:wrap}
    .fsm{padding:3px 8px;border-radius:20px;font-size:.65rem;cursor:pointer;border:1px solid var(--border);background:transparent;color:var(--muted);transition:all .15s;font-family:'DM Mono',monospace}
    .fsm:hover,.fsm.actif{border-color:var(--accent);color:var(--accent);background:rgba(108,99,255,.1)}
    .fsm.actif-zone{border-color:var(--yellow);color:var(--yellow);background:rgba(251,191,36,.1)}
    .fsm.actif-domaine{border-color:var(--green);color:var(--green);background:rgba(74,222,128,.1)}
    .tri-opt{padding:8px 10px;border-radius:4px;cursor:pointer;font-size:.72rem;display:flex;align-items:center;gap:8px;transition:background .1s}
    .tri-opt:hover{background:rgba(108,99,255,.08)}
    /* OFFRES */
    .offres{display:flex;flex-direction:column;gap:10px}
    .offre{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;transition:border-color .2s}
    .offre:hover{border-color:rgba(108,99,255,.4)}
    .offre-header{padding:13px 16px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;gap:12px}
    .offre-left{display:flex;flex-direction:column;gap:3px;flex:1;min-width:0}
    .offre-titre{font-family:'Instrument Serif',serif;font-size:1rem;font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .offre-meta{font-size:.68rem;color:var(--muted);display:flex;gap:6px;flex-wrap:wrap;align-items:center}
    .mtag{padding:1px 6px;border-radius:3px;font-size:.6rem}
    .mzone{background:rgba(251,191,36,.1);color:var(--yellow);border:1px solid rgba(251,191,36,.2)}
    .mdom{background:rgba(74,222,128,.1);color:var(--green);border:1px solid rgba(74,222,128,.2)}
    .msrc{background:rgba(108,99,255,.1);color:var(--accent);border:1px solid rgba(108,99,255,.2)}
    .offre-right{display:flex;align-items:center;gap:8px;flex-shrink:0}
    .score{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.78rem;font-weight:500;flex-shrink:0}
    .score.haut{background:rgba(74,222,128,.15);color:var(--green);border:1px solid rgba(74,222,128,.3)}
    .score.moyen{background:rgba(251,191,36,.15);color:var(--yellow);border:1px solid rgba(251,191,36,.3)}
    .score.bas{background:rgba(255,101,132,.15);color:var(--accent2);border:1px solid rgba(255,101,132,.3)}
    .badge-statut{font-size:.6rem;padding:2px 7px;border-radius:20px;border:1px solid;white-space:nowrap}
    .badge-nouveau{color:var(--accent);border-color:rgba(108,99,255,.4);background:rgba(108,99,255,.1)}
    .badge-en_cours{color:var(--yellow);border-color:rgba(251,191,36,.4);background:rgba(251,191,36,.1)}
    .badge-envoye{color:var(--green);border-color:rgba(74,222,128,.4);background:rgba(74,222,128,.1)}
    .badge-rejete{color:var(--muted);border-color:var(--border)}
    .badge-reponse{color:#60a5fa;border-color:rgba(96,165,250,.4);background:rgba(96,165,250,.1)}
    .badge-entretien{color:#f472b6;border-color:rgba(244,114,182,.4);background:rgba(244,114,182,.1)}
    .badge-refus{color:var(--accent2);border-color:rgba(255,101,132,.4);background:rgba(255,101,132,.1)}
    .offre-body{display:none;padding:16px;border-top:1px solid var(--border)}
    .offre-body.open{display:block}
    .grid-2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    @media(max-width:750px){.grid-2{grid-template-columns:1fr}}
    .sl{font-size:.6rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:7px}
    .abox{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:11px;font-size:.76rem;line-height:1.6}
    .points{list-style:none;margin-top:5px}
    .points li{font-size:.73rem;color:var(--muted);padding:2px 0}
    .points li::before{content:"→ ";color:var(--accent)}
    .points.faibles li::before{color:var(--accent2)}
    .tl{width:100%;min-height:260px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:11px;font-family:'DM Mono',monospace;font-size:.74rem;line-height:1.7;color:var(--text);resize:vertical;outline:none;transition:border-color .2s}
    .tl:focus{border-color:var(--accent)}
    .actions{display:flex;gap:7px;margin-top:10px;flex-wrap:wrap}
    .lo{font-size:.7rem;color:var(--accent);text-decoration:none}
    .lo:hover{text-decoration:underline}
    .empty{text-align:center;padding:60px 20px;color:var(--muted);font-size:.82rem}
    .empty .icon{font-size:2.5rem;margin-bottom:12px}
    .toast{position:fixed;bottom:24px;right:24px;padding:11px 18px;border-radius:var(--radius);font-size:.76rem;font-family:'DM Mono',monospace;z-index:1000;border:1px solid;animation:tin .25s ease}
    .toast.ok{background:#0f2318;color:var(--green);border-color:rgba(74,222,128,.3)}
    .toast.err{background:#1f0f14;color:var(--accent2);border-color:rgba(255,101,132,.3)}
    @keyframes tin{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
    .is{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);padding:7px 11px;font-family:'DM Mono',monospace;font-size:.74rem;outline:none;margin-bottom:7px}
    .is:focus{border-color:var(--accent)}
    .cg{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
    .cc{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:14px}
    .cc-titre{font-family:'Instrument Serif',serif;font-size:.95rem;margin-bottom:4px}
    .cc-meta{font-size:.68rem;color:var(--muted);margin-bottom:10px}
    .cc-date{font-size:.65rem;color:var(--muted)}
    .cc-actions{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap}
    .cs{text-align:center;padding:80px 20px;color:var(--muted)}
    .cs .big{font-family:'Instrument Serif',serif;font-size:2rem;font-weight:400;margin-bottom:12px;color:var(--text)}
    .cs p{font-size:.8rem;line-height:1.7}
  </style>
</head>
<body>

<aside class="sidebar" id="sidebar">
  <div class="sidebar-top">
    <span class="sidebar-logo">Chasseur</span>
    <button class="toggle-btn" id="toggle-btn" onclick="toggleSidebar()">☰</button>
  </div>
  <nav class="nav">
    <div class="nav-item" id="nav-offres" onclick="afficherSection('offres')">
      <span class="nav-icon">🔍</span><span class="nav-label">Offres</span><span class="nav-badge" id="badge-offres">0</span>
    </div>
    <div class="nav-item" id="nav-candidatures" onclick="afficherSection('candidatures')">
      <span class="nav-icon">📬</span><span class="nav-label">Candidatures</span>
    </div>
    <div class="nav-item" id="nav-archive" onclick="afficherSection('archive')">
      <span class="nav-icon">🗑</span><span class="nav-label">Archives</span>
    </div>
    <div class="nav-item" id="nav-spontanees" onclick="afficherSection('spontanees')">
      <span class="nav-icon">⚡</span>
      <span class="nav-label">Spontanées</span>
    </div>
  </nav>
  <div class="sidebar-stats">
    <div class="stat-mini"><span>Total</span><span id="s-total">0</span></div>
    <div class="stat-mini"><span>Score 7+</span><span id="s-top">0</span></div>
    <div class="stat-mini"><span>Envoyées</span><span id="s-env">0</span></div>
    <div class="stat-mini"><span>Entretiens</span><span id="s-entr">0</span></div>
    <div class="stat-mini"><span>Archivées</span><span id="s-arch">0</span></div>
  </div>
</aside>

<div class="main">
  <div class="topbar">
    <div class="topbar-left">
      <span class="page-title" id="page-title">Offres</span>
      <div class="search-status" id="searchStatus">Prêt</div>
    </div>
    <button class="btn btn-primary" id="btnRecherche" onclick="lancerRecherche()">🔍 Nouvelle recherche</button>
  </div>

  <div class="content">

    <div id="section-offres">
      <div class="toolbar-filtres">
        <div style="position:relative">
          <button class="btn btn-secondary" id="btn-filtres" onclick="togglePanel('panel-filtres')">
            ⚙ Filtres <span id="filtres-count" style="display:none;background:var(--accent);color:white;font-size:.58rem;padding:1px 5px;border-radius:10px;margin-left:4px">0</span>
          </button>
          <div class="panel-dropdown" id="panel-filtres">
            <div class="panel-sec">Score</div>
            <div class="fg" id="filtres-score">
              <button class="fsm actif" onclick="setFiltre('score','tous',this)">Tous</button>
              <button class="fsm" onclick="setFiltre('score','haut',this)">8-10 ★</button>
              <button class="fsm" onclick="setFiltre('score','moyen',this)">5-7</button>
              <button class="fsm" onclick="setFiltre('score','bas',this)">&lt;5</button>
            </div>
            <div class="panel-sec">Zone</div>
            <div class="fg" id="filtres-zone"></div>
            <div class="panel-sec">Domaine</div>
            <div class="fg" id="filtres-domaine"></div>
            <div class="panel-sec">Source</div>
            <div class="fg" id="filtres-source"></div>
            <button onclick="reinitialiserFiltres()" style="margin-top:14px;font-size:.68rem;color:var(--accent2);background:none;border:none;cursor:pointer;font-family:DM Mono,monospace">✕ Réinitialiser</button>
          </div>
        </div>

        <div style="position:relative">
          <button class="btn btn-secondary" id="btn-tri" onclick="togglePanel('panel-tri')">
            ↕ Trier : <span id="tri-label">Note</span>
          </button>
          <div class="panel-dropdown" id="panel-tri">
            <div class="tri-opt" onclick="setTri('score',this)">
              <span id="tri-check-score" style="color:var(--accent)">✓</span> Note (meilleure en premier)
            </div>
            <div class="tri-opt" onclick="setTri('date',this)">
              <span id="tri-check-date" style="color:transparent">✓</span> Date (plus récente en premier)
            </div>
          </div>
        </div>

        <span id="offres-count" style="font-size:.68rem;color:var(--muted)"></span>
      </div>
      <div class="offres" id="offres"></div>
    </div>

    <div id="section-candidatures" style="display:none">
      <div class="toolbar-filtres">
        <button class="btn btn-secondary actif" onclick="setFiltreCand('tous',this)" style="border-color:var(--accent);color:var(--accent)">Toutes</button>
        <button class="btn btn-secondary" onclick="setFiltreCand('envoye',this)">Envoyées</button>
        <button class="btn btn-secondary" onclick="setFiltreCand('reponse',this)">Réponse</button>
        <button class="btn btn-secondary" onclick="setFiltreCand('entretien',this)">Entretien</button>
        <button class="btn btn-secondary" onclick="setFiltreCand('refus',this)">Refus</button>
      </div>
      <div class="cg" id="cand-grid"></div>
    </div>

    <div id="section-spontanees" style="display:none">
      <div class="cs">
        <div class="big">Candidatures spontanées</div>
        <p>Cibler des entreprises en IDF, récupérer leurs coordonnées<br>
        et envoyer des candidatures spontanées automatiquement.<br><br>
        <em style="color:var(--accent)">Bientôt disponible ✦</em></p>
      </div>
    </div>

    <div id="section-archive" style="display:none" class="offres">
    </div>

  </div>
</div>

<script src="/static/app.js"></script>
</body>
</html>



--- FICHIER : data/candidatures.json (100 premières lignes) ---
[
  {
    "id": "3bb8b8efe798e189b133d18e62808ef7",
    "titre": "Alternance Développeur·euse Java - Paris (H/F)",
    "entreprise": "Inconnue",
    "lieu": "75 - Paris 16e Arrondissement",
    "zone": "Paris",
    "domaine": "DevOps",
    "lien": "https://candidat.francetravail.fr/offres/recherche/detail/0498734",
    "source": "France Travail",
    "description": "Description :\nL'ISCOD, spécialiste de la formation en Digital Learning, recherche pour son entreprise partenaire, acteur majeur de la Tech en Europe, un(e) Développeur·euse Java en contrat d'apprentissage, pour préparer l'une de nos formations diplômantes reconnues par l'Etat de niveau 5 à niveau 7 (Bac+2, Bachelor/Bac+3 ou Mastère/Bac+5).\nChoisissez l'alternance nouvelle génération avec l'ISCOD !\n\nMissions :\nL'ESN assure une double mission dans le cadre de la gestion d'une partie du système d'information : maintenance corrective et évolutive et conduite de projets de développement.\nDans le cadre de votre alternance, vous êtes accueilli/e dans les locaux au sein d'une équipe de conception et développement et différentes responsabilités vous sont confiées :\nAnalyser fonctionnellement et/ou ",
    "date_trouvee": "2026-03-19",
    "score": 9,
    "lettre": "",
    "statut": "archive",
    "verdict": "excellent",
    "eligible": true,
    "points_forts": [
      "Solides bases en Java qui seront approfondies avec le programme DEUST",
      "Maîtrise avancée de Linux, Docker, Bash et Git, fondamentaux pour le développement",
      "Expérience en développement web et projets concrets démontrant l'autonomie et la capacité technique"
    ],
    "points_faibles": [
      "Java n'est pas encore le langage principal dominant (mais acquis via la formation)"
    ],
    "resume_analyse": "Excellent profil pour alternance Java, solides bases techniques, formation alignée.",
    "email_candidature": "",
    "date_candidature": "",
    "notes": ""
  },
  {
    "id": "e99b77aead220f97a3c44c184125f1d8",
    "titre": "Alternance Concepteur Développeur - Puteaux (F/H) (H/F)",
    "entreprise": "Inconnue",
    "lieu": "92 - Puteaux",
    "zone": "Petite couronne",
    "domaine": "DevOps",
    "lien": "https://candidat.francetravail.fr/offres/recherche/detail/0223017",
    "source": "France Travail",
    "description": "Au sein des équipes d'exploitation , vous interviendrez dans le cadre de la conception, mise en œuvre et exploitation d'une d'infrastructure de service.Concevoir, déployer, exploiter et optimiser nos solutions de Cloud privés,\nAutomatiser tout ce qui l'être : les déploiements, les tests, les mises à jour, la supervision, les backups .\nAnalyser et résoudre les anomalies liées à la performance et à la scalabilité des systèmes et de la solution de Cloud,\nAccompagner les développeurs dans l'automatisation du déploiement de leurs applications,\nDocumenter les solutions mises en œuvre,\nAssurer le RUN, le monitoring et la gestion des incidents,",
    "date_trouvee": "2026-03-13",
    "score": 9,
    "lettre": "Madame, Monsieur,\n\nVotre offre pour une alternance en tant que Concepteur Développeur au sein de vos équipes d’exploitation a immédiatement retenu mon attention. La perspective de contribuer à la conception, au déploiement et à l’optimisation d’infrastructures de services, avec un fort accent sur l'automatisation, correspond précisément à la voie que je souhaite suivre dans mon parcours DevOps.\n\nActuellement en Dilpôme de Spécialisation DevOps au Conservatoire National des Arts et Métiers, j’ai acquis des compétences directement applicables à vos missions. Je maîtrise l’administration de systèmes Linux (Debian, Ubuntu, Archlinux) et les fondamentaux réseaux (TCP/IP, DNS, DHCP). Mon aisance avec le scripting Bash et Python me permet de concevoir des outils d'automatisation performants. Je suis également familière avec la conteneurisation via Docker et docker-compose, un atout essentiel pour accompagner les développeurs dans le déploiement de leurs applications.\n\nMes projets personnels illustrent ma capacité à mettre ces compétences en pratique. J'ai par exemple développé \"Grabber\", un outil de monitoring système complet, combinant un script Bash d'audit, une API REST en FastAPI et une interface web pour la visualisation des métriques. J'ai également créé un CLI en Node.js pour automatiser la gestion des fichiers docker-compose, démontrant mon intérêt pour l'optimisation des flux de travail des développeurs, une mission clé de votre offre.\n\nPassionnée par la résolution de problèmes et animée par le désir de comprendre le fonctionnement des systèmes, je suis déterminée à transformer cette curiosité en expertise concrète. Je cherche un environnement dynamique où je pourrai non seulement appliquer mes acquis, mais aussi apprendre rapidement au contact de professionnels. L'idée de participer au RUN, d'analyser les anomalies de performance et de contribuer activement à la robustesse de vos solutions de cloud privé est particulièrement stimulante pour moi.\n\nDisponible pour débuter mon alternance en septembre 2026 dans le cadre de mon DEUST IOSI, je serais ravie d’échanger avec vous pour vous exposer plus en détail ma motivation et mes projets.\n\nDans cette attente, je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.\n\nKenza Filali-Bouami",
    "statut": "en_cours",
    "verdict": "bon",
    "eligible": true,
    "points_forts": [
      "Maîtrise de Linux, administration système/réseau, Python, Bash et Docker, essentiels pour le poste.",
      "Projets concrets d'automatisation et de monitoring, très alignés avec les missions d'exploitation et d'optimisation.",
      "Expérience en virtualisation et concepts Cloud, facilitant l'intégration aux solutions de Cloud privés."
    ],
    "points_faibles": [
      "Expérience directe avec des outils avancés de Cloud privé (orchestration, IaaS spécifiques) à acquérir.",
      "Connaissances en sécurité réseau et bases de données relationnelles encore en phase d'apprentissage (DEUST)."
    ],
    "resume_analyse": "Candidate Bac+1 solide en Linux, DevOps, automatisation, Python, Docker pour Cloud.",
    "email_candidature": "",
    "date_candidature": "",
    "notes": ""
  },
  {
    "id": "7290021d8b378bc4568460c6c6006a74",
    "titre": "Administrateur / Administratrice informatique (H/F)",
    "entreprise": "GROUPE IGF",
    "lieu": "92 - Hauts-de-Seine",
    "zone": "Petite couronne",
    "domaine": "Sys/Réseau",
    "lien": "https://candidat.francetravail.fr/offres/recherche/detail/8768473",
    "source": "France Travail",
    "description": "L'Administrateur de systèmes d'information (SI) joue un rôle crucial dans la gestion et la sécurité des infrastructures informatiques d'une entreprise. Gère et maintient les systèmes d'information et l'infrastructure réseau de l'entreprise Assure la sécurité des données et des accès au système d'information Met à jour les systèmes et logiciels pour garantir leur efficacité et leur sécurité Supervise les sauvegardes régulières des données pour prévenir les pertes d'information Collabore avec les différents départements pour optimiser les processus et l'utilisation des systèmes d'information Fournit un support technique et forme les utilisateurs aux nouvelles technologies et systèmes",
    "date_trouvee": "2026-02-06",
    "score": 9,
    "lettre": "Madame, Monsieur,\n\nActuellement en formation DevOps et sur le point d'intégrer un DEUST en alternance, c'est avec un grand intérêt que je vous adresse ma candidature pour le poste d'Administratrice informatique au sein du Groupe IGF. Votre besoin d'un profil capable de gérer et sécuriser une infrastructure correspond parfaitement à la direction que je souhaite donner à ma carrière.\n\nMa formation et mes projets personnels m'ont permis de développer de solides compétences en administration de systèmes Linux (Debian, Ubuntu) et en gestion de réseaux (TCP/IP, DNS, DHCP). Je maîtrise l'automatisation via le scripting Bash et l'utilisation de Docker, des outils essentiels pour garantir l'efficacité, la mise à jour et la sécurité des systèmes d'information que vous décrivez dans votre offre. Mon expérience en maintenance et en relation avec des utilisateurs non-techniciens au Garage Numérique m'a également préparée à assurer un support technique efficace.\n\nMon projet « Grabber » illustre concrètement ma capacité à répondre à vos besoins. Il s'agit d'un outil de monitoring système complet, composé d'un script Bash pour auditer l'état d'un serveur et d'une API REST qui expose ces données sur une interface web pour une supervision en temps réel. Ce projet démontre ma maîtrise de la collecte d'information système et de sa restitution, un aspect central de la gestion d'infrastructure. J'ai également développé un outil en ligne de commande pour automatiser la gestion des fichiers docker-compose, de la création à la validation des images, dans une logique d'optimisation des processus.\n\nAu-delà de la technique, c'est la résolution de problèmes concrets qui m'anime. J'aime comprendre le fonctionnement des systèmes en profondeur et ne recule pas devant un défi, préférant toujours une solution robuste et pérenne à un simple correctif. Rejoindre le Groupe IGF en alternance serait pour moi l'opportunité idéale de mettre cette curiosité et cette rigueur au service de vos équipes, tout en continuant à monter en compétences dans un environnement professionnel stimulant.\n\nJe serai disponible pour un contrat d'alternance à partir de septembre 2026, date de mon intégration au DEUST IOSI. Je serais ravie de pouvoir échanger avec vous plus en détail sur ma motivation et mes projets lors d'un entretien.\n\nDans cette attente, je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.\n\nKenza Filali-Bouami",
    "statut": "en_cours",
    "verdict": "excellent",
    "eligible": true,
    "points_forts": [
      "Solides compétences en administration systèmes Linux et réseau, TCP/IP, SSH.",
      "Expérience pertinente en support technique utilisateurs non-techniciens.",
      "Maîtrise du scripting Bash, Python, et Docker pour l'automatisation."
    ],
    "points_faibles": [
      "Connaissances en sécurité approfondie et gestion de projet encore en cours d'acquisition via le DEUST."
    ],
    "resume_analyse": "Profil très pertinent pour l'administration systèmes, réseau, support et automatisation.",
    "email_candidature": "",
    "date_candidature": "",
    "notes": ""
  },
  {
    "id": "3d32ea308dd8c2e8a55ae84b9f7ce624",
    "titre": "Administrateur / Administratrice informatique (H/F)",
    "entreprise": "GROUPE IGF",
    "lieu": "75 - Paris",
    "zone": "Paris",
    "domaine": "Sys/Réseau",
    "lien": "https://candidat.francetravail.fr/offres/recherche/detail/8768472",
    "source": "France Travail",
    "description": "L'Administrateur de systèmes d'information (SI) joue un rôle crucial dans la gestion et la sécurité des infrastructures informatiques d'une entreprise. Gère et maintient les systèmes d'information et l'infrastructure réseau de l'entreprise Assure la sécurité des données et des accès au système d'information Met à jour les systèmes et logiciels pour garantir leur efficacité et leur sécurité Supervise les sauvegardes régulières des données pour prévenir les pertes d'information Collabore avec les différents départements pour optimiser les processus et l'utilisation des systèmes d'information Fournit un support technique et forme les utilisateurs aux nouvelles technologies et systèmes",
    "date_trouvee": "2026-02-06",



--- FICHIER : data/entreprises_avec_domaines.json (100 premières lignes) ---
[
  {
    "siren": "812773711",
    "nom": "BPCE INFOGERANCE ET TECHNOLOGIES (BPCE-IT)",
    "ville": "PARIS",
    "dept": "75",
    "naf": "62.02A",
    "taille": "42",
    "domaine": "bpce.fr",
    "emails": [
      "recrutement@bpce.fr",
      "rh@bpce.fr",
      "contact@bpce.fr",
      "alternance@bpce.fr",
      "info@bpce.fr"
    ],
    "catchall": false,
    "traite": true
  },
  {
    "siren": "532503067",
    "nom": "SYD INFOGERANCE",
    "ville": "SAINT-HERBLAIN",
    "dept": "75",
    "naf": "62.03Z",
    "taille": "12",
    "domaine": null,
    "emails": [],
    "catchall": null,
    "traite": true
  },
  {
    "siren": "821796786",
    "nom": "I INFOGERANCE",
    "ville": "PARIS",
    "dept": "75",
    "naf": "62.02A",
    "taille": "NN",
    "domaine": null,
    "emails": [],
    "catchall": null,
    "traite": true
  },
  {
    "siren": "939834487",
    "nom": "CYBER INFOGERANCE",
    "ville": "PARIS",
    "dept": "75",
    "naf": "62.02A",
    "taille": "NN",
    "domaine": null,
    "emails": [],
    "catchall": null,
    "traite": true
  },
  {
    "siren": "488375544",
    "nom": "HOUBA INFOGERANCE ET FORMATION (H.I.F)",
    "ville": "PARIS",
    "dept": "75",
    "naf": "62.03Z",
    "taille": "01",
    "domaine": "houba.net",
    "emails": [
      "recrutement@houba.net",
      "rh@houba.net",
      "contact@houba.net",
      "alternance@houba.net",
      "info@houba.net"
    ],
    "catchall": false,
    "traite": true
  },
  {
    "siren": "524871654",
    "nom": "MATIS INFOGERANCE",
    "ville": "PARIS",
    "dept": "75",
    "naf": "62.09Z",
    "taille": "NN",
    "domaine": null,
    "emails": [],
    "catchall": null,
    "traite": true
  },
  {
    "siren": "538592312",
    "nom": "BPCE SOLUTIONS INFORMATIQUES",
    "ville": "PARIS",
    "dept": "75",
    "naf": "62.02A",
    "taille": "51",
    "domaine": "bpce.fr",
    "emails": [
      "recrutement@bpce.fr",
      "rh@bpce.fr",
      "contact@bpce.fr",
      "alternance@bpce.fr",
      "info@bpce.fr"
    ],



--- FICHIER : data/entreprises_enrichies.json (100 premières lignes) ---
[
  {
    "nom": "FIDUCIAL INFORMATIQUE",
    "nom_commercial": null,
    "siret": "31728838900529",
    "siren": "317288389",
    "code_naf": "62.02A",
    "adresse": "41 RUE DU CAPITAINE GUYNEMER 92400 COURBEVOIE",
    "ville": "COURBEVOIE",
    "code_postal": "92400",
    "departement": "92",
    "site_web": "https://jobs.fiducial.fr/",
    "taille": "500-999",
    "categorie": "GE",
    "ca": 102689032,
    "dirigeant": "JEAN-CLAUDE CARQUILLAT",
    "traite": true,
    "emails_trouves": [],
    "telephone": null,
    "contact_rh": null,
    "url_scrapee": "https://jobs.fiducial.fr/"
  },
  {
    "nom": "SOCIETE POUR L'INFORMATIQUE INDUSTRIELLE (SII)",
    "nom_commercial": null,
    "siret": "31500094300862",
    "siren": "315000943",
    "code_naf": "62.02A",
    "adresse": "8 RUE DES PIROGUES DE BERCY 75012 PARIS",
    "ville": "PARIS",
    "code_postal": "75012",
    "departement": "75",
    "site_web": "https://www.lindustrielle.fr/l-industrielle",
    "taille": "5000-9999",
    "categorie": "GE",
    "ca": 828875000,
    "dirigeant": "DIDIER FRANCOIS HUBERT BONNET",
    "traite": true,
    "emails_trouves": [],
    "telephone": "+33 (0) 6 71 51 97 55",
    "contact_rh": null,
    "url_scrapee": "https://www.lindustrielle.fr/l-industrielle"
  },
  {
    "nom": "BPCE SOLUTIONS INFORMATIQUES",
    "nom_commercial": null,
    "siret": "53859231200135",
    "siren": "538592312",
    "code_naf": "62.02A",
    "adresse": "182-188 182 AVENUE DE FRANCE 75013 PARIS",
    "ville": "PARIS",
    "code_postal": "75013",
    "departement": "75",
    "site_web": null,
    "taille": "2000-4999",
    "categorie": "GE",
    "ca": 0,
    "dirigeant": "GWILHERM PAUL PIERRE LE DONNE",
    "traite": true,
    "emails_trouves": [],
    "telephone": null,
    "contact_rh": null
  },
  {
    "nom": "CDC INFORMATIQUE (I.CDC)",
    "nom_commercial": null,
    "siret": "77566543300188",
    "siren": "775665433",
    "code_naf": "62.01Z",
    "adresse": "18 AVENUE ARISTIDE BRIAND 92220 BAGNEUX",
    "ville": "BAGNEUX",
    "code_postal": "92220",
    "departement": "92",
    "site_web": null,
    "taille": "1000-1999",
    "categorie": "GE",
    "ca": 223189871,
    "dirigeant": "MATHIAS SEBASTIEN SERGE GUERIN",
    "traite": true,
    "emails_trouves": [],
    "telephone": null,
    "contact_rh": null
  },
  {
    "nom": "EURO-INFORMATION PRODUCTION - GROUPEMENT INFORMATIQUE (EIP - GROUPEMENT INF)",
    "nom_commercial": null,
    "siret": "32219010900015",
    "siren": "322190109",
    "code_naf": "62.02A",
    "adresse": "4 RUE FREDERIC-GUILLAUME RAIFFEISEN 67000 STRASBOURG",
    "ville": "STRASBOURG",
    "code_postal": "67000",
    "departement": "67",
    "site_web": null,
    "taille": "500-999",
    "categorie": "GE",
    "ca": null,
    "dirigeant": "CINDY MARIN (ANTOINE)",
    "traite": true,
    "emails_trouves": [],



--- FICHIER : data/entreprises_raw.json (100 premières lignes) ---
[
  {
    "nom": "FIDUCIAL INFORMATIQUE",
    "nom_commercial": null,
    "siret": "31728838900529",
    "siren": "317288389",
    "code_naf": "62.02A",
    "adresse": "41 RUE DU CAPITAINE GUYNEMER 92400 COURBEVOIE",
    "ville": "COURBEVOIE",
    "code_postal": "92400",
    "departement": "92",
    "site_web": null,
    "taille": "500-999",
    "categorie": "GE",
    "ca": 102689032,
    "dirigeant": "JEAN-CLAUDE CARQUILLAT",
    "traite": false
  },
  {
    "nom": "SOCIETE POUR L'INFORMATIQUE INDUSTRIELLE (SII)",
    "nom_commercial": null,
    "siret": "31500094300862",
    "siren": "315000943",
    "code_naf": "62.02A",
    "adresse": "8 RUE DES PIROGUES DE BERCY 75012 PARIS",
    "ville": "PARIS",
    "code_postal": "75012",
    "departement": "75",
    "site_web": null,
    "taille": "5000-9999",
    "categorie": "GE",
    "ca": 828875000,
    "dirigeant": "DIDIER FRANCOIS HUBERT BONNET",
    "traite": false
  },
  {
    "nom": "BPCE SOLUTIONS INFORMATIQUES",
    "nom_commercial": null,
    "siret": "53859231200135",
    "siren": "538592312",
    "code_naf": "62.02A",
    "adresse": "182-188 182 AVENUE DE FRANCE 75013 PARIS",
    "ville": "PARIS",
    "code_postal": "75013",
    "departement": "75",
    "site_web": null,
    "taille": "2000-4999",
    "categorie": "GE",
    "ca": 0,
    "dirigeant": "GWILHERM PAUL PIERRE LE DONNE",
    "traite": false
  },
  {
    "nom": "CDC INFORMATIQUE (I.CDC)",
    "nom_commercial": null,
    "siret": "77566543300188",
    "siren": "775665433",
    "code_naf": "62.01Z",
    "adresse": "18 AVENUE ARISTIDE BRIAND 92220 BAGNEUX",
    "ville": "BAGNEUX",
    "code_postal": "92220",
    "departement": "92",
    "site_web": null,
    "taille": "1000-1999",
    "categorie": "GE",
    "ca": 223189871,
    "dirigeant": "MATHIAS SEBASTIEN SERGE GUERIN",
    "traite": false
  },
  {
    "nom": "EURO-INFORMATION PRODUCTION - GROUPEMENT INFORMATIQUE (EIP - GROUPEMENT INF)",
    "nom_commercial": null,
    "siret": "32219010900015",
    "siren": "322190109",
    "code_naf": "62.02A",
    "adresse": "4 RUE FREDERIC-GUILLAUME RAIFFEISEN 67000 STRASBOURG",
    "ville": "STRASBOURG",
    "code_postal": "67000",
    "departement": "67",
    "site_web": null,
    "taille": "500-999",
    "categorie": "GE",
    "ca": null,
    "dirigeant": "CINDY MARIN (ANTOINE)",
    "traite": false
  },
  {
    "nom": "A.V.M. INFORMATIQUE (AVM UP)",
    "nom_commercial": "AVM UP",
    "siret": "32741194800034",
    "siren": "327411948",
    "code_naf": "46.51Z",
    "adresse": "IMMEUBLE LE RIVER SIDE 45 AVENUE LECLERC 69007 LYON",
    "ville": "LYON",
    "code_postal": "69007",
    "departement": "69",
    "site_web": null,
    "taille": "50-99",
    "categorie": "GE",
    "ca": 21123763,



--- FICHIER : data/offres_vues.json (100 premières lignes) ---
["4da4d7a3e7e05dc2df687bce4e558b61", "b6ca533fa02c42c3dcda4becc5471237", "6f876eefafa402a2f7acb0230d7e244a", "8aeb0b58adffca501f329ca23f72b9cd", "9fe1c316bbe7da3479b042de401b21bc", "86086f3857ee0556ae54cc19878d6339", "ce8a1864ce1b97aaf4148195b7a0d6e1", "fff8980697a1143fca09f12cb7a23384", "6bc062832bc6e6b960f5763222d823e3", "e47b0d1ed50ab3df284ae7d572ff58af", "e778725d9906570c0ecbd914ff07759d", "3add83d54ff82367b4b5c44e5519192e", "d00c98b60a5d976ba78c052ce77dce43", "8830cfddf30eda9f2020759af0230575", "aa475415c7537deafb01ade51a813548", "69bb3f7a7a6d379e963b4d96ceef08d7", "555f68a150d8d514b44ffe878445dda9", "3d0bb8f07e482d0e58483c9519783a99", "2443ad052586cfeb2c3e41545461a3de", "5c0bb32a6af2bc329bfbbfb26b5547dd", "489cd31db5b04779c13b511d1f8b2008", "3d32ea308dd8c2e8a55ae84b9f7ce624", "b1481b1399db759d0c763e6d6814a1ed", "ba36e53e159588e142147ac822e15571", "998c3cf9e32c77d6833ab5b187ec806d", "3bc89f62dc665e10934a93289c9d0fa9", "78cadb3cd69cf10538c76bd714a12ab7", "f3049b1b0b4dfb435f5db7e6c65e8030", "d69f92ea685c115433b95135952c85d2", "6cab95073549961aeae41d37349046fe", "5253573bbf03d5484eb8d4db34625184", "0eef9ff56624314c0a2fc581a085fb28", "8917909d12f97f25d854fc8beda63250", "4a241c2359ac2c049875458d7366dc4f", "3f338c3b7cb8503d74a68a2030649adf", "8347c470c1a715bf40d5c5f71edc007e", "73f21fd390384ac6dd42224fbcb1a75b", "81f45c3963340062d144fd6933759353", "f4c27afdbf5dba94b2788b9f6204c6b9", "f7745cb870762df434c820242ccb6a33", "f2aeb0f754b14882c5be4aae2bd1356c", "2c549379874dc526748023b9a845a8b1", "0a9c563ee952079430a817d3815beb78", "393fb2d9f709aee6050ff046b9585d30", "8fbe22dc4be79bf0aa10a744c00595d6", "9b11c0bee92e8ff69b1264359c2b437d", "3cba807b6f25687f9b58b0db9fb47a2f", "2cd502ae1aa34f17cf12633d2b030c4e", "90907d1051489758173ae4cd3c6794e9", "5fbb27758482b133863af89c46251582", "d6f9e6228f04bdc12332494b904e5dab", "fba91d8c17f9db9349497478343d8285", "f889d9538f9ffd203b573e9304f88dc9", "a47f1380cdd603142684d45598bf17d5", "c7e995218d58b27a19d1ada0a016fffc", "0d7d295a20fa1221fc0a2079d65a0bd1", "8ef75724a2fb27e7be96f16fb585d639", "9a289233f3d6190551af1d5fe3ad9895", "e5ed51aff089ca2a61e71c30496c1742", "2f7b5754f977c2f58a9cce10eb3ed176", "3c40c217b9eff264b622eff6cdb91cab", "cc7d26bb7d6699852eee7ce4f2a84378", "6dcd2ce55fb4a2d95aa01e3a7f34a4e1", "7290021d8b378bc4568460c6c6006a74", "d6008f38d012838b4a80ac7544c5f755", "2aea839b9f2af32d4edc33d9705038d8", "af6eb8b6e75d7d3e2ef8b4e3e3275762", "2c945de198e454f39b9c01feec8f6ad8", "bf337a45862e1b1f17d4165dec47e6bc", "426afa8fefe0ca127d65f33e1cec5c66", "f2704f331ea5089a9fa62f38ea311430", "22a8aa0fae476f71564c1fabf7443621", "5b807dc965e08867f337d70e149b78ec", "85d32ca2029fcda8389eddabf391e518", "32daf9d777b610a99dda3ae43198af74", "38a23d927b060f84b8323f340374f64f", "06efaf43cab0ac3e892a70a7a960a70e", "a9903f226d06c4766402e4ceaad2aacd", "f162b9cdb35d35ff0186734a379fc621", "2cae63b2393908e233c54e6c34969e42", "66d8e01d588921a204b411aaa3d18f15", "3bb8b8efe798e189b133d18e62808ef7", "4d8a540a74251b8b5dd0b7d3a1d9889c", "f3b71115cb40839fd1b163b92383e6c5", "e6820f4d5c88b392923e68bd992315b2", "0b197cf74f8123630310faf51d8153c0", "3385b5ffe5bc474dca092f6a1c70a30b", "3d12add0e867583712e93aa6f2577742", "2815ef92d5a57c3117d380c4425ad247", "00f59287398b322f13d0ac706ec77ff7", "e99b77aead220f97a3c44c184125f1d8", "9ddf290b131903a2c01ccefccc25e84e"]


