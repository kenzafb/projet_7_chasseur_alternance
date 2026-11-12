# Configuration

Toutes les variables se règlent dans le fichier `.env`, copié depuis `.env.example`. Une variable vide prend sa valeur par défaut. Les modifications valent au lancement suivant de l'application.

## Application

| Variable | Rôle | Défaut |
|---|---|---|
| `SECRET_KEY` | Clé de signature des cookies de session, 32 caractères au moins. Obligatoire : sans elle, l'application refuse de démarrer. Générer : `venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"` | aucun |
| `COOKIE_SECURE` | `true` pour n'envoyer le cookie de session qu'en HTTPS (production), `false` en local. | `false` |
| `CODE_INVITATION` | Code à saisir pour créer un compte sur `/register`. Vide : inscriptions fermées. | vide |
| `FUSEAU_AFFICHAGE` | Fuseau d'affichage des dates (elles sont stockées en UTC). | `Europe/Paris` |

## Base et fichiers

| Variable | Rôle | Défaut |
|---|---|---|
| `DATABASE_URL` | Base SQLite, créée par `venv/bin/alembic upgrade head`. Chemin absolu : quatre barres obliques après `sqlite:`. Le fichier `.env.example` contient un chemin d'exemple, à remplacer ou à vider. | `DATA_DIR/chasseur_v2.db` |
| `DATA_DIR` | Dossier des données : base par défaut et pièces jointes. Chemin relatif : depuis la racine du projet. | `data/` |
| `UPLOADS_DIR` | Pièces jointes envoyées par les utilisateurs (CV...). | `DATA_DIR/uploads` |
| `LETTRES_PDF_DIR` | PDF des lettres de motivation générées. | `lettres_pdf/` |

La base, `UPLOADS_DIR` et `LETTRES_PDF_DIR` sont à sauvegarder ensemble.

## Sources

| Variable | Rôle | Défaut |
|---|---|---|
| `FT_CLIENT_ID` | Identifiant de l'application sur francetravail.io (API Offres d'emploi v2). Nécessaire pour chercher des offres. | vide |
| `FT_CLIENT_SECRET` | Secret associé à `FT_CLIENT_ID`. | vide |
| `LBA_API_KEY` | Clé de l'API de La Bonne Alternance (api.apprentissage.beta.gouv.fr), mode alternance. | vide |
| `INSEE_API_KEY` | Clé de l'API Sirene 3.11 (portail-api.insee.fr), pour les entreprises à contacter. | vide |
| `NOMENCLATURE_NAF` | `NAFRev2` ou `NAF2025` pour forcer la nomenclature cherchée sur Sirene. Vide (conseillé) : NAF rév. 2 jusqu'au 31 décembre 2026, NAF 2025 à partir du 1er janvier 2027. | vide |

## IA locale

| Variable | Rôle | Défaut |
|---|---|---|
| `ANALYSE_IA` | Interrupteur général. `false` : aucun appel à l'IA, les offres restent sans note, la lettre et la validation des emails douteux se font à la main. | `true` |
| `IA_API` | `ollama` (API native) ou `openai` (serveur compatible OpenAI). | `ollama` |
| `IA_BASE_URL` | Adresse du serveur d'IA. Avec `openai`, terminer par `/v1`. | `http://localhost:11434` |
| `IA_API_KEY` | Clé, seulement si le serveur en demande une (Ollama : vide). | vide |
| `IA_MODELE_ANALYSE` | Modèle qui note les offres. | `ministral-3:3b` |
| `IA_MODELE_LETTRE` | Modèle qui rédige le paragraphe de la lettre. | `ministral-3:8b` |
| `IA_MODELE_EXTRACTION` | Modèle qui tranche les emails douteux. | `ministral-3:3b` |
| `IA_DELAI_S` | Attente maximale d'une réponse, en secondes, chargement du modèle compris. | `600` |
| `IA_LONGUEUR_DESCRIPTION` | Caractères de la description d'une offre envoyés à l'IA. | `2000` |
| `IA_NUM_CTX` | Contexte demandé à Ollama, en tokens. | `8192` |
| `IA_KEEP_ALIVE` | Durée pendant laquelle Ollama garde le modèle chargé après un appel. | `10m` |
| `IA_REFLEXION` | Mode de réflexion des modèles qui en ont un. | `false` |

Sur une machine avec peu de mémoire, Ollama peut être limité à un modèle chargé à la fois : `sudo systemctl edit ollama`, puis ajouter `Environment="OLLAMA_MAX_LOADED_MODELS=1"` dans la section `[Service]`, et `sudo systemctl restart ollama`.

## Envoi des candidatures

| Variable | Rôle | Défaut |
|---|---|---|
| `CLE_CHIFFREMENT` | Clé Fernet qui chiffre les mots de passe SMTP des comptes d'envoi. Absente : l'application démarre, mais l'envoi de mails est désactivé. Ne plus la changer une fois des comptes enregistrés. Générer : `venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | vide |
| `PLAFOND_ENVOIS_JOUR` | Mails envoyés au plus par utilisateur et par jour, tous lancements confondus. | `50` |
| `DEBUG_SCRAPER` | `true` pour des journaux détaillés de la recherche d'emails. | `false` |

Chaque utilisateur configure son propre compte d'envoi (Gmail avec un mot de passe d'application, ou un serveur SMTP sur le port 465 ou 587) dans Paramètres. Les plafonds de chaque lancement se règlent par mode dans Paramètres, section Réglages avancés.
