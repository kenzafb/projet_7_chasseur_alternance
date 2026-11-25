# Phase 1 : sécurité du socle, rapport

Branche `phase-1-securite`, créée depuis `refonte-multiuser` (d8cfad2), 8 octobre 2026. Non poussée, non fusionnée.
Règles suivies : schéma de base inchangé (seul un commentaire de `models.py` cite la nouvelle raison `hors_domaine`), rien modifié dans `data/` ni `.env` (le `.env` a seulement été lu, pour vérifier la longueur de `SECRET_KEY` sans l'afficher), aucun appel à FT, LBA, INSEE, Mistral ou SMTP, aucune route de pipeline appelée sur la vraie base.

## 1. Commits

| Commit | Thème |
|---|---|
| cd387b0 | `docs/` : `ARCHITECTURE_ACTUELLE.md` (enfin suivi par git) et `PHASE_0_RAPPORT.md` déplacés, lien du README mis à jour |
| 192efbe | Raison d'archivage `hors_it` renommée `hors_domaine`, règle LBA réparée |
| 8585b7a | Authentification : dépendance unique, inscription sur invitation, `SECRET_KEY` obligatoire, cookie |
| c44e8f9 | Fin des replis vers l'utilisateur 1, erreurs 400 lisibles (profil incomplet, bug 7) |
| 942b839 | Tests pytest |
| (dernier) | Ce rapport |

Étape 3 (requirements.txt) : aucun commit nécessaire. Venv neuf dans `/tmp`, `pip install -r requirements.txt` sans erreur, `pip check` propre, `import main` et rendu d'un PDF WeasyPrint réussis, venv supprimé. Pango et Cairo sont présents sur cette machine, le README les mentionnait déjà.

## 2. Ce qui change pour l'utilisateur

**Authentification**
- Toutes les routes sauf `/login`, `/register`, `/logout` et `/static` exigent une session. Sans session : 401 `{"erreur": "Non connecté"}` sur `/api/...`, redirection 303 vers `/login` ailleurs. Mécanisme : `utilisateur_requis` (`auth/securite.py`) posée sur le routeur `prive` de `main.py`, plus une exception `NonConnecte` traduite par un gestionnaire unique. Les 20 copies du bloc de vérification ont disparu.
- Nouvellement protégées : `/api/logs`, `/api/statut_recherche`, `/api/spontanees/statut`, `/api/spontanees/stop`, ainsi que `/docs` et `/openapi.json` (servies par des routes privées, la doc automatique publique est désactivée).
- Inscription : champ « Code d'invitation » comparé à `CODE_INVITATION` (temps constant). Variable absente ou vide : `/register` affiche « Les inscriptions sont fermées » sans formulaire, et un POST reçoit 403. Mauvais code : 403. Mot de passe de 10 caractères minimum pour les nouveaux comptes (aussi dans `database/migration.py`) ; les hashs existants restent valides, rien n'est demandé aux comptes actuels.
- `SECRET_KEY` : plus de valeur de repli. Absente ou de moins de 32 caractères, `import main` lève une `RuntimeError` qui explique comment en générer une. Cookie de session `samesite=lax`, `httponly`, `secure` si `COOKIE_SECURE=true`.
- Front : une réponse 401 renvoie vers `/login` (fonctions `get` et `post` de `static/js/api.js`).

**Erreurs lisibles au lieu de 500**
- `shared/erreurs.py` : `ErreurUtilisateur` et `ProfilIncomplet`, renvoyées en 400 `{"erreur": message}` par un gestionnaire de `main.py`. La modale de lettre affiche déjà `erreur`.
- Lettre et PDF exigent prénom, nom et email : « Profil incomplet : renseigne prénom, nom dans l'onglet Profil. ». Vérification faite avant l'appel à Mistral. Dans le PDF, les champs facultatifs absents (ville, téléphone, GitHub) donnent des chaînes vides au lieu d'une `KeyError`.
- Analyse, réanalyse et recherche exigent qu'un profil existe pour le mode courant (« Aucun profil pour ce mode... »). `/api/recherche` le vérifie avant de lancer le thread.
- Bug 7 : la lettre type est vérifiée avant usage. Accolade isolée ou balise inconnue (`{prenom}`, `{}`, `{date.__class__}`, `{date!r}`) : 400 qui cite les balises permises. Les espaces dans les balises (`{ date }`), acceptés par le validateur du front, sont tolérés. Bonus : `{date.__class__...}` n'est plus évalué par `str.format`.

**Fin du mono-utilisateur dans le code**
- Plus aucun `user_id=1` ni `lire_profil(1)` : `analyser_offre`, `analyser_offres`, `lancer_recherche`, `generer_lettre`, `generer_pdf_lettre` prennent le profil en paramètre obligatoire ; `main()` de `fetch_entreprises`, `scraper_emails` et `envoyeur` prend `user_id` sans défaut.
- CLI : `--user` obligatoire pour les trois scripts (`fetch_entreprises` n'avait pas de CLI, elle en a une). La ligne cron documentée (`--user 1`) reste valide.

**Hors domaine**
- La boucle LBA compare enfin à « Hors domaine », la valeur renvoyée par l'analyseur : les offres LBA hors domaine sont désormais archivées avec cette raison (avant : `note_basse` ou rien). Paramètre `libelle_hors_domaine` supprimé. Raison stockée `hors_domaine`, libellé et filtre front « Hors domaine ». Les anciennes lignes `hors_it` n'apparaissent plus dans le filtre et leur sélecteur de raison s'affiche sans valeur choisie, en attendant la base neuve de la phase 2.

**Corrections trouvées en route** (signalées car elles changent un comportement)
- `sauvegarder_profil` ignorait la clé `email` envoyée par le formulaire (la colonne s'appelle `email_contact`) : l'email du profil n'était jamais modifiable depuis l'interface, et resterait vide en mode job, ce qui aurait bloqué la lettre. Corrigé.
- `/api/analyser` ne transmettait pas le mode : une réanalyse en mode job utilisait le prompt alternance. Corrigé.

## 3. Tests

`pytest` (9.1.1) + `httpx` dans `requirements-dev.txt` ; `pytest.ini` à la racine. Isolation dans `tests/conftest.py` : `CHASSEUR_ENV_FILE` (nouvelle variable de `shared/config.py`) pointe vers un fichier absent pour ne pas lire le vrai `.env` ; `DATABASE_URL` vers un SQLite temporaire recréé par `creer_tables()` à chaque test, avec un garde-fou qui refuse `data/chasseur.db` ; faux client Mistral qui enregistre ses appels ; `socket.connect`, `socket.create_connection`, `smtplib.SMTP` et `SMTP_SSL` lèvent une erreur ; PDF et pièces jointes écrits dans `tmp_path`.

| Fichier | Couvre |
|---|---|
| `test_routes_protegees.py` | Liste lue dans `app.routes` (aplatie, FastAPI 0.137 range les routeurs inclus dans des objets à part) : chaque route privée renvoie 401 JSON ou 303 vers `/login` sans session ; inventaire minimal (dont les 4 routes autrefois ouvertes, `/`, `/docs`) ; toute route hors du routeur protégé est l'une des 3 publiques ; cookie falsifié refusé ; `/login`, `/register`, `/static` accessibles |
| `test_auth.py` | Inscription désactivée (variable absente ou blanche), refusée sans code, avec mauvais code, avec mot de passe de 9 caractères, email déjà pris ; acceptée avec le bon code (session et profil créés) ; connexion (mauvais mot de passe, email en casse différente), déconnexion ; attributs du cookie ; démarrage refusé sans `SECRET_KEY`, vide, ou de 31 caractères, accepté à 32 (processus Python séparé) |
| `test_isolation.py` | A et B : chacun lit son profil, A modifie le sien sans toucher celui de B, candidatures de B invisibles, `maj_statut`, `archiver`, `offre/archivage`, `sauvegarder` sans effet sur B, `generer_lettre`, `analyser`, `telecharger_pdf` en 404 sans appel à Mistral, suivi et stats spontanées de B inaccessibles |
| `test_lettre.py` | 400 profil incomplet (lettre et PDF, champs cités), recherche sans profil en mode job, 6 formes d'accolade invalide, lettre valide avec balises espacées (prouve que le faux Mistral sert), PDF généré avec profil complet |

Résultat : **71 passed** en 8 s, aucun avertissement (deux filtrés et commentés dans `pytest.ini` : `httpx` pour le TestClient de Starlette, `datetime.utcnow` de `models.py`).

Vérification finale : `compileall -x 'venv/|data/'` sans erreur, aucun `__pycache__` créé dans `data/` ; `uvicorn main:app --port 5099` avec le vrai `.env` : `GET /login` 200, `/` 303 vers `/login`, `/api/logs` 401, `/register` affiche « inscriptions fermées », arrêt propre. Un PDF de test écrit dans `lettres_pdf/` par un essai manuel en cours de route a été supprimé ; les tests ne l'écrivent plus là.

## 4. Limites qui restent (phase 2)

1. **États partagés entre utilisateurs connectés** : `etat_recherche`, `etat_spontanees`, `_stop_event` et `_logs` sont globaux. Tout utilisateur voit les logs et la progression des autres, peut arrêter leur pipeline via `/api/spontanees/stop`, et un seul pipeline de chaque type tourne à la fois pour toute l'app. Écritures depuis les threads sans verrou, threads perdus au redémarrage.
2. **Dédoublonnage global** : `data/offres_vues_{mode}.json` et `data/emails_deja_envoyes.json` ne sont pas par utilisateur (une offre vue par A n'est jamais proposée à B). Bug 1 (`sauvegarder_offres_vues` sans `mode`) toujours présent.
3. **Compte Gmail partagé** : tout invité envoie depuis l'adresse `GMAIL_SENDER`. L'invitation réduit le risque, elle ne le supprime pas.
4. **PDF** : la lettre (texte libre de l'utilisateur) et les champs du profil sont insérés tels quels dans du HTML rendu par WeasyPrint, sans échappement ni `url_fetcher` restrictif ; un contenu piégé pourrait faire lire des ressources locales ou réseau par le serveur. Fichiers nommés `Lettre_{prenom}_{nom}.pdf` dans un dossier commun : deux homonymes s'écrasent.
5. Pas de limitation de débit sur `/login` et `/register` (force brute du mot de passe ou du code d'invitation). Pas de jeton CSRF (atténué par `SameSite=lax` ; `/logout` reste un GET).
6. Sessions non révocables : cookie signé valable 14 jours, seule une rotation de `SECRET_KEY` les invalide. Pas de changement ni de réinitialisation de mot de passe.
7. Front : les `fetch` directs de `profil.js`, `suivi.js` et `app.js` ne redirigent pas sur 401 (seuls ceux de `api.js` le font).
8. Routes à corps `dict` sans validation (`/api/maj_statut` accepte n'importe quel statut, `/api/offre/archivage` n'importe quelle raison).
9. `/docs` charge Swagger UI depuis le CDN jsdelivr.
10. Hérité, inchangé : `models.py` diverge du schéma réel, `migration.py` ignore `mode`, chemins relatifs des pièces jointes résolus depuis le dossier courant, contenus « Kenza » codés en dur (trame de lettre, prompt job).

## 5. À faire par l'humain dans son `.env`

- `SECRET_KEY` : la valeur actuelle fait déjà au moins 32 caractères, l'app démarre. Pour la production, en générer une neuve : `python -c "import secrets; print(secrets.token_urlsafe(48))"` (cela déconnecte toutes les sessions).
- `CODE_INVITATION=` : à ajouter, avec un code long, pour rouvrir l'inscription. Absente aujourd'hui, donc **inscriptions fermées**.
- `COOKIE_SECURE=true` en production derrière HTTPS ; laisser absent ou `false` en local (sinon le cookie n'est pas renvoyé en http et la connexion échoue).
- Pour lancer les tests : `pip install -r requirements-dev.txt` puis `pytest` (déjà installé dans `venv/`).
- Ensuite : relire la branche, la fusionner dans `refonte-multiuser`, pousser.
