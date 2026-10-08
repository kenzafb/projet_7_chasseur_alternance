# Recette : test réel de bout en bout

Procédure à suivre par un humain, sur la vraie application, avec deux comptes : **A** (ton compte habituel) et **B** (un compte de test créé avec le code d'invitation). Elle vérifie les profils, le compte d'envoi en mode test, une petite recherche d'alternance limitée à 5 offres, une lettre et son PDF, un petit pipeline de candidatures spontanées envoyé en mode test vers toi, et l'isolation entre les deux comptes.

Durée : environ 45 minutes, dont une bonne part d'attente (pauses entre appels Mistral, recherche des sites, pauses de 30 à 90 s entre deux mails). Aucun mail ne doit partir vers une entreprise : le mode test est activé avant tout envoi.

Pour chaque étape : **Faire**, **Observer** (ce qui doit se passer), **Échec si** (ce qui doit faire arrêter la recette et noter le problème). Noter l'heure, l'étape et le message exact de tout échec ; les lignes du terminal correspondantes sont les plus utiles.

## 0. Préparation (avant la recette)

1. Fusionner la branche `phase-4-recette` (voir `docs/PHASE_4_RAPPORT.md`, section « Avant la recette »), application arrêtée.
2. Sauvegarder la base puis la migrer :
   ```bash
   cd /home/kenza/Bureau/chasseur_alternance
   source venv/bin/activate
   cp data/chasseur_v2.db data/chasseur_v2_avant_recette.db
   alembic upgrade head
   alembic current          # attendu : 0006 (head)
   ```
3. Vérifier dans `.env` la présence de : `SECRET_KEY`, `DATABASE_URL` (la base v2), `CODE_INVITATION`, `CLE_CHIFFREMENT`, `MISTRAL_API_KEY`, `FT_CLIENT_ID`, `FT_CLIENT_SECRET`, `LBA_API_KEY`, `INSEE_API_KEY`. Ne pas y laisser `GMAIL_SENDER` ni `GMAIL_APP_PASSWORD` (plus lus).
4. Vérifier les modèles Mistral (appels réels, quelques tokens) : `venv/bin/python scripts/verifier_mistral.py`. Attendu : une ligne `OK` par usage (analyse, lettre, extraction) et « Tout est prêt. ». Sinon, choisir dans la liste affichée un modèle qui répond et le mettre dans `.env` (`MODELE_MISTRAL` ou `MODELE_MISTRAL_<USAGE>`).
5. Lancer l'application **sans `--reload`** (le rechargement tue les pipelines en cours à chaque modification de fichier) et garder le terminal visible : c'est là que s'affichent les logs des pipelines, préfixés `[user N]`.
   ```bash
   uvicorn main:app --port 5002
   ```
6. Préparer deux navigateurs indépendants : une fenêtre normale pour A, une fenêtre de navigation privée (ou un autre navigateur) pour B. Les deux sessions doivent rester ouvertes en même temps.
7. Avoir accès à la boîte de réception de l'adresse d'expédition de A (celle du compte Gmail utilisé pour l'envoi).

**Observer** au démarrage : `Application startup complete`, et **pas** de ligne `⚠️  Envoi de mails désactivé`.
**Échec si** : l'application refuse de démarrer (`SECRET_KEY`), `alembic current` n'affiche pas `0006 (head)`, ou l'avertissement sur `CLE_CHIFFREMENT` apparaît.

## 1. Connexion de A, cache et polling

**Faire** : dans la fenêtre normale, ouvrir http://localhost:5002, se connecter avec A. Ouvrir les outils de développement (F12), onglet Réseau, en laissant « Désactiver le cache » décoché (on veut voir le comportement normal), puis recharger la page.

**Observer** :
- les fichiers CSS et JS sont demandés avec un suffixe `?v=` suivi de 12 caractères (`base.css?v=...`, `app.js?v=...`, `api.js?v=...`) ;
- une seule requête `statut_pipelines` au chargement, puis plus aucune tant qu'aucun pipeline ne tourne (attendre 30 s pour s'en assurer) ;
- dans le terminal, aucune ligne `GET /api/statut_pipelines`.

**Échec si** : des requêtes de statut partent en continu sans pipeline en cours, un JS est demandé sans `?v=`, ou la console du navigateur affiche une erreur de module (page blanche, boutons sans effet).

## 2. Création du compte de test B

**Faire** : dans la fenêtre privée, ouvrir http://localhost:5002/register, saisir une adresse de test qui t'appartient (ou une adresse fictive : elle ne recevra rien pendant la recette), un mot de passe d'au moins 8 caractères et le code d'invitation.

**Observer** : redirection vers la page Profil avec le message de bienvenue ; le bouton de mode indique Alternance.

**Échec si** : « code d'invitation invalide » alors que le code est celui du `.env`, erreur 500 dans le terminal, ou la page affiche des données de A.

## 3. Profils

**Faire (A)** : page Profil, mode Alternance. Vérifier que l'identité (prénom, nom, email), la formation, les compétences, les domaines recherchés et les pièces jointes (CV au moins) sont remplis. Corriger si besoin, puis « Enregistrer ».

**Faire (B)** : remplir un profil minimal mais distinct : prénom « Test », nom « Recette », un email, une ville, une formation courte, un domaine (de préférence différent de celui de A), « Enregistrer ». Recharger la page.

**Observer** : « ✓ Profil enregistré » ; après rechargement, B retrouve exactement ses valeurs. Passer B en mode Job puis revenir en Alternance : le profil Job est vide (il est propre au mode), le profil Alternance est intact.

**Échec si** : une valeur saisie disparaît après rechargement, le profil de B contient des informations de A, ou le profil Job reprend celui d'Alternance.

## 4. Compte d'envoi de A, en mode test

**Faire (A)** : Profil, section 09 « Compte d'envoi ».
1. Si aucun compte n'est configuré : choisir Gmail, saisir l'adresse d'expédition et le mot de passe d'application (16 caractères), « Enregistrer et tester ».
2. « Tester la connexion ».
3. « M'envoyer un mail de test ».
4. Vérifier que **Mode test** est coché : il l'est d'office pour un compte créé à partir de la phase 4 (décision D7) ; un compte plus ancien doit être coché à la main.

**Observer** :
- après le test : « configuré, vérifié le JJ/MM/AAAA à HH:MM » en vert ; le champ mot de passe reste vide ;
- le mail « Test du compte d'envoi » arrive dans la boîte de A ;
- après avoir coché le mode test : message « Mode test activé : les envois partiront vers toi. », encadré du mode test sur fond orangé, et l'état se termine par « 🧪 Mode test actif : les envois partent vers cette adresse. » ;
- recharger la page : la case reste cochée ;
- page Spontanées : bandeau orangé « 🧪 Mode test actif : les mails partiront vers <adresse de A>, pas vers les entreprises ».

**Faire (B)** : Profil, section 09 : ne rien configurer.

**Observer (B)** : « Aucun compte configuré », pas de case Mode test, pas de bandeau sur la page Spontanées.

**Échec si** : la vérification échoue avec un bon mot de passe d'application (noter le message exact), le mail de test n'arrive pas en quelques minutes, la case se décoche au rechargement, le bandeau n'apparaît pas chez A, ou B voit le compte ou le mode test de A.

## 5. Recherche d'alternance limitée à 5 offres (A)

**Faire (A)** : page Offres, champ « Offres analysées au plus par lancement » : **5**. Noter le nombre d'offres actives affiché. Cliquer « Lancer la recherche ».

**Observer** :
- le bandeau d'exécution apparaît avec sa jauge ; dans l'onglet Réseau, une requête `statut_pipelines` toutes les 5 s environ ;
- dans le terminal :
  - `[user A] 🔍 Recherche France Travail démarrée (au plus 5 offres analysées)`
  - `✅ France Travail terminé : N offres analysées` avec N ≤ 5
  - puis soit `LBA ignorée : limite de 5 offres analysées atteinte`, soit `Limite : M offres LBA analysées sur ...` avec N + M ≤ 5, soit `Aucune offre LBA récupérée`
  - `✅ Recherche complète terminée`
- à la fin : le bandeau disparaît, la liste se rafraîchit seule, **au plus 5** nouvelles offres (actives ou archivées automatiquement) ; les requêtes de statut s'arrêtent.
- facultatif : relancer avec 5 ; les nouvelles offres sont différentes des premières (celles qui dépassaient la limite n'ont pas été perdues).

**Échec si** : plus de 5 offres nouvelles, plus de 5 lignes « Score : » dans le terminal, la recherche ne finit pas (plus de 5 minutes), le bandeau reste affiché après « Recherche complète terminée », ou le polling continue après la fin.

Les erreurs de France Travail ou de LBA (identifiants, quota) apparaissent dans le terminal et dans le message du bandeau : les noter, elles ne relèvent pas de cette phase.

## 6. Lettre de motivation et PDF (A)

**Faire (A)** : ouvrir une des nouvelles offres, « Générer la lettre ». Modifier une phrase dans la fenêtre, « Enregistrer ». Rouvrir la lettre (« Voir la lettre »), puis « Télécharger en PDF ».

**Observer** :
- la lettre contient le nom de l'entreprise de l'offre et un paragraphe qui lui est propre, ton identité en signature, aucune information inventée ;
- la modification est conservée à la réouverture ;
- un fichier `Lettre_<Prénom>_<Nom>_<Entreprise>.pdf` est téléchargé (vrai téléchargement, pas un chemin affiché) ; il s'ouvre, montre « <ta ville>, le <date> », l'objet « Candidature » et le texte modifié.

**Échec si** : message « profil incomplet » alors que prénom, nom et email sont remplis, lettre vide ou sans rapport avec l'offre, PDF illisible ou vide, ou PDF contenant le texte d'avant la modification.

Noter la référence de l'offre pour l'étape 8 : ouvrir http://localhost:5002/api/candidatures dans la fenêtre de A et copier la valeur `"id"` de cette offre.

## 7. Petit pipeline de candidatures spontanées, en mode test (A)

Vérifier d'abord que le bandeau orangé du mode test est affiché sur la page Spontanées. **S'il ne l'est pas, ne pas lancer l'envoi** : revenir à l'étape 4.

**7.1 Récupérer** : champ « Nouvelles entreprises au plus » : **10**, « Lancer ».
- Terminal : `▶ Fetch entreprises démarré (au plus 10 nouvelles entreprises)`, puis `10 nouvelles entreprises ajoutées en base` (moins si Sirene en renvoie moins).
- Carte 01 : message et pourcentage pendant l'exécution ; à la fin, la carte « Entreprises » augmente de 10 au plus.
- **Échec si** plus de 10 entreprises ajoutées, ou message `INSEE_API_KEY manquante`.

**7.2 Scraper** : champ « Entreprises à scraper au plus » : **5**, « Lancer ».
- Terminal : `▶ Scraper emails démarré (au plus 5 entreprises)`, éventuellement `Limite du lancement : 5 entreprises, les autres au prochain lancement`, puis pour chacune `🌐 <site> [ddg]` (ou `Site introuvable`) et `✅ <emails>` ou `Aucun email` ; enfin `✅ Scraping terminé`.
- La carte « Emails trouvés » augmente.
- **Échec si** plus de 5 entreprises traitées, ou le pipeline s'arrête sur une erreur (noter la ligne `❌ Erreur scraper`).
- Si aucune adresse n'est trouvée sur ces 5 entreprises, relancer le scraper avec 5 avant de passer à l'envoi.

**7.3 Envoyer** : champ « Nombre de mails à envoyer » : **3**, « Lancer ».
- Carte 03 : « 🧪 MODE TEST : envoi vers <adresse de A> (limite : 3)... », puis la progression.
- Terminal :
  - `▶ Envoi démarré, limite 3. 🧪 MODE TEST : tout part vers <adresse de A>`
  - `🧪 MODE TEST : chaque mail part vers <adresse de A>, le vrai destinataire dans l'objet...`
  - pour chaque mail : `[i/n] 🧪 [TEST] <Entreprise> → <adresse de A> (vrai destinataire : <adresse de l'entreprise>)` puis `✅ Envoyé à 1 adresse(s)`
  - la ligne de fin `✅ Envoi terminé` avec `3 envoyés, 0 échecs`, suivie de `🧪 Mode test : tous les mails sont partis vers l'adresse d'expédition, rien n'est enregistré.`
- Boîte de réception de A : 3 mails (ou autant que d'entreprises avec email), objet `[TEST → <adresse de l'entreprise>] Candidature spontanée en alternance` (ou l'objet du profil), corps du profil signé, pièces jointes du profil en PDF.
- Dossier « Envoyés » de Gmail : **tous** les mails envoyés pendant la recette ont pour destinataire l'adresse de A.
- À la fin : carte 03 « Envoi de test terminé ! », la carte « Envoyés » ne bouge pas, la page « Spontanées envoyées » reste inchangée (aucune entreprise marquée envoyée).
- Relancer « Envoyer » avec 3 : les mêmes entreprises sont de nouveau visées (rien n'a été enregistré comme contacté).

**Échec (grave) si** : un mail part vers une adresse autre que celle de A, un objet ne commence pas par `[TEST →`, le compteur « Envoyés » augmente, une entreprise apparaît dans « Spontanées envoyées », ou le second lancement ne vise pas les mêmes entreprises. Dans ce cas : cliquer « Arrêter », ne rien modifier d'autre, noter et arrêter la recette.

Autres échecs : pièces jointes absentes, corps vide, `Erreur envoi : Authentification refusée` (refaire « Tester la connexion »), `Plafond de 50 mails par jour atteint` (normal si beaucoup de mails ont déjà été envoyés aujourd'hui).

## 8. Isolation entre A et B

Faire ces vérifications dans la fenêtre privée de B, les deux sessions ouvertes.

1. **Données** : pages Offres, Candidatures, Spontanées et Spontanées envoyées de B : aucune offre, entreprise ou candidature de A ; compteurs de la barre latérale à 0 (ou aux seules valeurs de B).
2. **PDF de A** : ouvrir http://localhost:5002/api/lettre_pdf/<id noté à l'étape 6>. Attendu : `{"erreur":"PDF introuvable"}` (code 404). Dans la fenêtre de A, la même adresse télécharge le PDF.
3. **Logs** : ouvrir http://localhost:5002/api/logs. Attendu : aucune ligne des pipelines de A (liste vide si B n'a rien lancé).
4. **Compte d'envoi** : Spontanées, « Envoyer » avec 1. Attendu : message « Aucun compte d'envoi configuré... » ; le terminal ne montre aucune connexion SMTP ; aucun mail ne part du compte de A.
5. **Pipelines simultanés** : dans A, relancer « Scraper » avec 5. Pendant qu'il tourne :
   - B ne voit pas le bandeau d'exécution ; sur la page Spontanées de B, aucune carte n'est « en cours » ;
   - B clique « Arrêter » sur une carte : le scraper de A continue (terminal : pas de `Arrêt demandé par l'utilisateur` pour A) ;
   - B lance sa propre recherche limitée à 5 : elle démarre (pas de « Recherche déjà en cours »), ses logs portent le numéro de B, ses offres n'apparaissent pas chez A.
6. **Profils et mode test** : le profil de B n'a pas changé ; chez A, le mode test est toujours coché.

**Échec si** : une seule donnée de A est visible depuis B (offre, entreprise, PDF, log, compte), B peut arrêter un pipeline de A, ou un lancement de B est refusé parce que A a un pipeline en cours.

## 9. Fin de la recette

- Terminal : rechercher `Traceback` ; il ne doit y en avoir aucun.
- Facultatif, contrôle en base (adapter le chemin) : aucune adresse enregistrée comme contactée pendant les envois de test.
  ```bash
  venv/bin/python -c "import sqlite3; c=sqlite3.connect('data/chasseur_v2.db'); print(c.execute('select user_id, mode, count(*) from emails_contactes group by user_id, mode').fetchall())"
  ```
  Comparer avec la même commande lancée avant l'étape 7 : les nombres ne doivent pas avoir changé.
- Laisser le mode test coché tant que les envois réels n'ont pas été décidés. Pour un envoi réel plus tard : décocher le mode test, vérifier que le bandeau a disparu de la page Spontanées, et commencer par une limite de 1.
- Le compte B peut être gardé pour les recettes suivantes. Les entreprises récupérées par A pendant la recette restent en base ; elles seront proposées aux prochains envois réels.

## Reconnaître un échec, en général

| Symptôme | Où le voir | Signification probable |
|---|---|---|
| `Traceback` | terminal | erreur non gérée : noter les 20 dernières lignes |
| Retour à la page de connexion | navigateur | session expirée (14 jours) ou `SECRET_KEY` changée |
| Message rouge « Requête invalide » | navigateur | valeur refusée par le serveur : noter le champ cité |
| Message « Envoi de mails désactivé » | profil, envoi | `CLE_CHIFFREMENT` absente ou invalide |
| Bandeau d'exécution bloqué | navigateur | pipeline mort (serveur relancé ?) : vérifier le terminal |
| Page qui ne reflète pas une modification du code | navigateur | fichier statique en cache : comparer le `?v=` dans l'onglet Réseau avant et après |
