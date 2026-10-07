# Phase 0 : ménage, rapport

Branche `phase-0-menage`, créée depuis `refonte-multiuser` (5b9a3ef), 7 octobre 2026. Non poussée.
Règle suivie : aucun changement de comportement fonctionnel, schéma de base et authentification intacts, rien modifié dans `data/` ni `.env`, aucun appel réseau (FT, LBA, INSEE, Mistral, SMTP), aucune route /api de pipeline appelée.

## 1. Commits

| Commit | Thème |
|---|---|
| 6e89341 | Suppression du code mort |
| 4f44a09 | Bot Telegram archivé |
| 815744f | Config centralisée `shared/config.py` (corrige le bug 10) |
| b0bb805 | Un seul client Mistral et un seul appel avec retry (`shared/ia.py`) |
| 8b5a203 | `detecter_zone`, `generer_id`, codes ROME/NAF partagés |
| 3b487ac | Règles d'archivage auto dans une seule fonction |
| c831ad2 | requirements.txt, .env.example, README |
| (dernier) | Ce rapport |

## 2. Fichiers supprimés ou déplacés

Supprimés : `app.py`, `templates/index.html`, `static/app.js` (ancienne version Flask), `spontanees/export_excel.py` (lisait le JSON figé), `spontanees/fetch_envoyes_gmail.py` (synchro IMAP one-shot). Tous récupérables depuis 5b9a3ef.
Déplacé : `telegram_bot.py` vers `archive/telegram_bot.py`, avec un en-tête qui explique qu'il est désactivé en attendant sa refonte multi-utilisateur. Il importe toujours `google.genai`, absent de requirements.txt : il ne s'importe plus, c'est voulu.

Code mort retiré dans les fichiers conservés :
- `france_travail/main.py` : `charger_candidatures`, `sauvegarder_candidatures`, `ajouter_candidatures`, `FICHIER_CANDIDATURES`, lock et imports associés. L'écriture passe uniquement par le callback `on_offre`.
- `main.py` : import `json`, `FICHIER_ENRICHIES`, `FICHIER_RAW`, imports des helpers JSON, `load_dotenv`, `Path`. La seconde `api_spontanees_statut` (GET `/api/spontanees/statut`) devient `api_spontanees_etat`. URL inchangée.
- `spontanees/fetch_entreprises.py` : `CODES_NAF`, `FICHIER_RAW`, `FICHIER_SORTIE`, `charger_base`, `sauvegarder`, import `json`.
- `spontanees/scraper_emails.py` : `FICHIER_ENTREE`, `FICHIER_SORTIE`.
- `spontanees/envoyeur.py` : `FICHIER_JSON`, `CV_PATH`, `PLAQUETTE_PATH`, `RECO_PATH`. `LIMITE_PAR_RUN` conservé (défaut de `main()` et de la CLI, donc pas mort).
- `database/entreprises_db.calculer_stats` : champ `mail_generee` (toujours 0, lu nulle part dans `static/js`).
- `france_travail/scraper_lba.py` : `ALL_CODES_ROME_IT`, `DEPTS_IDF`, `generer_id`, `detecter_zone` locaux.
- `france_travail/scraper.py` : `DEPTS_IDF`, `generer_id`, `detecter_zone` locaux.

Commentaires corrigés : `generateur.py` (Gemini devient Mistral), docstrings de `main.py` (plus de référence à Flask ni app.py), `entreprises_db.py` ("lecture seule, le JSON reste la source d'écriture" était faux), `envoyeur.py` (docstring Flask, JSON, fetch_envoyes_gmail). Deux messages de log de l'envoyeur ajustés : "depuis le JSON" devient "depuis la base", et l'avertissement de fichier de dédup absent ne renvoie plus vers le script supprimé.

## 3. Nouveaux modules

- `shared/config.py` : charge `BASE_DIR/.env` à l'import (avant toute lecture d'env), expose `BASE_DIR`, `DATA_DIR`, `UPLOADS_DIR`, `LETTRES_PDF_DIR`, `TEMPLATES_DIR`, `STATIC_DIR`, `DATABASE_URL`, `MODELE_MISTRAL`, `FT_REGION`, `DEPTS_IDF`, `DEPTS_PETITE_COURONNE`, `LBA_LATITUDE`, `LBA_LONGITUDE`, `LBA_RAYON_KM`, `SIRENE_DEPARTEMENTS`. `database/connexion.py` lit `DATABASE_URL` depuis ce module, ce qui corrige le bug 10. Tous les `load_dotenv()` dispersés sont supprimés.
- `shared/ia.py` : `client` Mistral unique et `appeler_mistral(messages, tentatives, attente, rate_limit, on_attente, **options)`. Politique de chaque appelant reproduite : analyseur 4 essais avec pauses 15, 30, 45 s (message console conservé pour le prompt alternance, silencieux pour le prompt job), générateur 1 seul essai (aucun retry, comme avant), scraper 20 essais avec 60 s doublées jusqu'à 300 s et sa propre détection du rate limit (`429`, `rate_limit`, `rate limited`).
- `shared/offres.py` : `generer_id`, `detecter_zone` (sur `DEPTS_IDF` et `DEPTS_PETITE_COURONNE` de la config).
- `france_travail.analyseur.appliquer_archivage_auto(offre, analyse, mode, libelle_hors_domaine, verbeux)` : appelée par `analyser_offres` (défauts : "Hors domaine", logs) et par la boucle LBA de `main.py` ("Hors IT", sans log).
- Codes ROME et NAF : seulement dans `shared/domaines.py`. Le défaut de `chercher_offres_lba` vient de `lba_romes([])`, celui de `chercher_offres` de `ft_grands_domaines([])` (même liste M1801 à M1810, même "M18").

## 4. Incohérence "Hors IT" / "Hors domaine" (signalée, non corrigée)

Le prompt alternance demande à Mistral d'écrire exactement `Hors domaine` et `analyser_offres` compare à cette valeur. La boucle LBA de `main.py` compare à `Hors IT`, que l'analyseur ne renvoie jamais : la règle "hors domaine" ne se déclenche donc jamais sur les offres LBA. En pratique, le même prompt rend ces offres inéligibles (score plafonné à 2), donc la plupart finissent archivées quand même, mais avec la raison `note_basse` au lieu de `hors_it`. Le comportement est conservé tel quel, avec un commentaire à l'appel dans `main.py`. À noter aussi : la raison stockée s'appelle `hors_it` et le front l'affiche "Hors IT" (`static/js/offres.js:13`, `templates/partials/offres.html:58`) même pour le domaine immobilier.

## 5. Vérifications faites

- Tests unitaires ad hoc, sans réseau, avec un faux client Mistral : séquences d'attente de `appeler_mistral` (15/30/45 s puis levée de l'erreur ; erreur non rate limit levée immédiatement ; 1 seul appel pour le générateur ; 60, 120, 240, 300 s pour le scraper).
- `detecter_zone` et `generer_id` partagés donnent les mêmes résultats que les anciens sur des cas Paris, petite et grande couronne, hors IDF, vide, "093 - Bobigny", "92 - Paris La Défense".
- `lba_romes([])` et `ft_grands_domaines([])` égaux aux anciennes constantes en dur.
- `appliquer_archivage_auto` : les 5 raisons du mode alternance, le mode job, le cas "Hors IT".
- `python -m compileall -x venv/ .` sans erreur ; `import main` sans erreur.
- `uvicorn main:app --port 5099` (port à part pour ne pas gêner une instance sur 5002) : démarrage propre, `GET /login` 200, `GET /static/js/app.js` 200, `GET /` 303 vers `/login`, arrêt propre. Aucune autre route appelée.
- `data/chasseur.db` et `.env` : dates de modification inchangées.

Incident corrigé : `compileall` a créé `data/backup_avant_migration/__pycache__/profil.cpython-313.pyc` (ce dossier contient un `profil.py`). Je l'ai supprimé aussitôt ; le contenu de `data/` est identique à avant, seule la date de modification du dossier `backup_avant_migration` a changé. Pour la suite, lancer `compileall` avec `-x 'venv/|data/'`.

## 6. Écarts minimes de comportement (à connaître)

1. Scraper d'emails, 20e rate limit consécutif : l'ancien code affichait encore "tentative 20/20, attente 300s" et dormait 300 s avant d'abandonner ; maintenant il abandonne tout de suite avec le même message final "inaccessible après 20 tentatives". Seul ce délai final disparaît.
2. `lancer_recherche` sans `on_offre` lève une erreur au lieu d'écrire dans `data/candidatures.json` ; avec `analyser=False`, chaque offre passe par `on_offre` au lieu du JSON. Aucun appelant n'utilise ces chemins (`main.py` passe toujours `on_offre` et `analyser=True`).
3. Chemins absolus à partir de `BASE_DIR` : l'app fonctionne désormais lancée depuis un autre dossier. Les chemins stockés en base (pièces jointes, `data/uploads/user_N/...`) et le chemin PDF renvoyé au front (`lettres_pdf/...`) restent relatifs, identiques à avant. Les chemins relatifs déjà en base restent résolus par rapport au dossier courant à la lecture (comportement préexistant).
4. Bug 10 corrigé : une `DATABASE_URL` dans `.env` serait maintenant prise en compte. Elle est absente aujourd'hui, donc rien ne change.
5. `/api/spontanees/stats` ne renvoie plus `mail_generee`.

## 7. Ce que je n'ai pas touché, et pourquoi

- Bugs 1 à 9 et 11 à 14 de l'état des lieux : hors périmètre "sans changement de comportement". Le bug 1 (`sauvegarder_offres_vues(offres_vues)` sans `mode`, `france_travail/main.py`) est toujours là.
- `database/models.py` : import `Float` inutilisé, laissé pour ne pas toucher au fichier de schéma.
- Auth : repli codé en dur de `SECRET_KEY`, bloc "vérifier l'utilisateur" copié dans chaque route, routes non authentifiées. Phase 1.
- Liste des mois dupliquée (`generateur.py`, `pdf_generator.py`) et nettoyage des balises de code dans les réponses Mistral (trois regex légèrement différentes) : non demandés, fusion qui pouvait changer le parsing.
- Calcul de zone par code postal dans `_normaliser_offre_lba` : logique différente de `detecter_zone` (pas de `lstrip("0")`, entrée = code postal), gardée en place ; seul l'ensemble petite couronne vient de la config.
- `charger_json` et `sauvegarder_json` de l'envoyeur : noms trompeurs (ils lisent la base), commentaires corrigés mais noms gardés.
- Mentions "Kenza" dans les commentaires et contenus codés en dur (trame de lettre, prompt job, mail type) : sujet de la refonte multi-utilisateur, pas du ménage.
- `.gitignore` : entrées obsolètes (`credentials.json`, `token_chasseur.json`, `app_route_envoi.py`, `offres_vues.json`, `candidatures.json`...) laissées, inoffensives.
- Fichiers hérités dans `data/` (`candidatures.json`, `entreprises_raw.json`, `offres_vues.json`...) : interdiction de toucher à `data/`.
- `database/migration.py` : seuls ses deux chemins passent par `DATA_DIR`. Il reste désynchronisé du schéma (ne connaît pas `mode`).
- La ligne cron (commentée, hors dépôt) utilise des chemins absolus `/home/kenza/...` ; elle lance `python -m spontanees.envoyeur --limite 50 --user 1`, toujours valide.

## 8. Points à valider par un humain

1. Corriger ou non "Hors IT" en "Hors domaine" dans `main.py` (section 4). La correction changerait la raison d'archivage des futures offres LBA hors domaine.
2. Suppression de `fetch_envoyes_gmail.py` : c'était le seul moyen de reconstruire `data/emails_deja_envoyes.json` depuis la boîte Gmail. Récupérable dans 5b9a3ef si besoin.
3. Suppression d'`export_excel.py` : il n'y a plus d'export Excel. À réécrire sur la base si la fonctionnalité sert.
4. requirements.txt : versions reprises du venv, mais pas d'installation testée dans un venv neuf (aucun accès réseau utilisé). `pwdlib`, `argon2-cffi` et `bcrypt` sont épinglés explicitement car indispensables à la vérification des hashs existants.
5. README : pour une base neuve, `creer_tables()` part de `models.py`, dont le schéma diffère de la base réelle (cf. état des lieux §3). À confirmer avant de documenter une installation de zéro.
6. `ARCHITECTURE_ACTUELLE.md` est toujours non suivi par git : à committer ou non.
7. Fusionner `phase-0-menage` dans `refonte-multiuser`, puis pousser.
