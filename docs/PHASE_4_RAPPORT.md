# Phase 4 : préparation du test réel, rapport

Branche `phase-4-recette`, créée depuis `refonte-multiuser` (93ff2f3), 8 octobre 2026. Non poussée, non fusionnée.
Règles suivies : rien écrit par cette phase dans `data/` ni dans `.env` (voir section 6 : deux modifications extérieures constatées). Aucun appel réseau réel dans les tests : France Travail, LBA, Sirene, DuckDuckGo, Mistral, DNS et SMTP simulés ou coupés. Schéma modifié uniquement par migration Alembic (0006). `compileall -x 'venv/|data/'` propre, `node --check` propre sur les 8 modules JS. Lu avant de commencer : `ARCHITECTURE_ACTUELLE.md` section 8, les rapports des phases 0 à 3, en particulier les limites et les mentions restantes de la phase 3.

## 1. Commits

| Commit | Thème |
|---|---|
| 4b26202 | Mode test d'envoi : colonne et migration 0006, route, envoyeur, interface, logs |
| 972d13d | Limites par lancement réglables dans l'interface, plafonds côté serveur |
| a912976 | Cache navigateur : JS et CSS versionnés par l'empreinte de leur contenu, import map |
| c1ab932 | Polling seulement pendant un pipeline, requêtes de statut hors du journal d'accès |
| 3a8f9cb | Test statique des sélecteurs JS, deux écarts corrigés |
| c0a9133 | Bugs 5, 13 et 14 ; mentions d'un utilisateur réel retirées |
| fb3fa95 | `docs/DECISIONS.md` avec les décisions de la phase 3 |
| 32a4224 | `docs/RECETTE.md` ; README (mode test, limites) |
| (dernier) | Ce rapport |

## 2. Ce qui change

**Mode test d'envoi.** Case « Mode test » dans Profil, section Compte d'envoi (`comptes_envoi.mode_test`, faux par défaut), réglée par `POST /api/compte_envoi/mode_test {actif}` (400 sans compte, 422 sur champ inconnu ; la vérification du compte n'est pas touchée, enregistrer le compte garde l'option). En mode test, chaque candidature spontanée part vers l'**adresse d'expédition** de l'utilisateur, objet `[TEST → rh@entreprise.fr] <objet habituel>` ; aucune adresse n'entre dans `emails_contactes`, aucune entreprise n'est marquée envoyée, y compris celles dont toutes les adresses sont déjà contactées (en envoi réel, elles sont marquées « skip »). Le dédoublonnage reste appliqué en mémoire pendant le lancement, pour qu'une adresse partagée par deux entreprises ne reçoive qu'un mail, comme en réel. Effet = option du compte OU `test` de la requête OU `--test` en ligne de commande. Affichage : état du compte suffixé « 🧪 Mode test actif », encadré orangé dans le profil, bandeau orangé sur la page Spontanées (option active ou envoi de test en cours), message de la carte d'envoi « 🧪 MODE TEST : envoi vers ... », fin « Envoi de test terminé ! ». Logs : ligne de démarrage, bannière de l'envoyeur, chaque mail préfixé `🧪 [TEST]` avec le vrai destinataire, ligne de fin. L'état du pipeline spontané et `/api/spontanees/stats` portent `mode_test` ; la réponse de `/api/spontanees/envoyer` aussi. Les mails de test passent par le vrai serveur SMTP et comptent dans le plafond du jour.

**Limites par lancement.** `LIMITES_LANCEMENT` et `limite_lancement()` dans `shared/config.py` : absente, la valeur par défaut ; inférieure à 1, 1 ; au-delà du plafond, le plafond. Valeur effective renvoyée par la route et écrite dans les logs.

| Limite | Champ de requête | Défaut | Plafond | Où dans l'interface |
|---|---|---|---|---|
| Offres analysées par Mistral (FT et LBA ensemble) | `POST /api/recherche {max_analyses}` | 30 | 200 | page Offres, au-dessus des indicateurs |
| Nouvelles entreprises récupérées | `POST /api/spontanees/fetch {max_entreprises}` | 200 | 5000 | carte Récupérer |
| Entreprises scrapées | `POST /api/spontanees/scraper {max_scrapees}` | 20 | 200 | carte Scraper |
| Mails envoyés | `POST /api/spontanees/envoyer {limite}` | 10 | 50 | carte Envoyer |

Défauts et plafonds viennent du serveur (contexte du gabarit), pas du JS. Recherche : France Travail reçoit la limite comme taille de lot, donc seules les offres retenues sont marquées vues et celles qui dépassent reviennent au lancement suivant (auparavant, en alternance, toutes les offres reçues étaient marquées vues) ; LBA reçoit le reste du budget, ou est ignorée si FT l'a épuisé, et ses offres non analysées ne sont pas écrites en base. En mode job, le lot de 100 du mode reste un plafond supplémentaire. Fetch : arrêt de la pagination et des requêtes Sirene dès la limite atteinte, les entreprises déjà en base ne comptent pas. Scraper : seules les N premières entreprises à traiter le sont. Les corps de requête de recherche, fetch et scraper sont facultatifs et refusent tout champ inconnu.

**Cache navigateur.** `shared/statique.py` : `statique('css/base.css')` donne `/static/css/base.css?v=<12 caractères de sha256 du contenu>`, recalculé quand la date ou la taille du fichier change (pas besoin de redémarrer). Les modules JS s'importent entre eux par `./api.js` : une import map placée avant le premier module associe chaque `/static/js/*.js` à son URL versionnée, sinon seul `app.js` aurait échappé au cache. Les 3 CSS et `app.js` de `base.html` passent par `statique()`.

**Polling.** Nouvelle route `GET /api/statut_pipelines` (les deux états en une requête). Le front interroge une fois au chargement, puis toutes les 5 s (au lieu de 2,5 s, deux requêtes) **seulement** tant qu'un pipeline tourne ; chaque lancement, arrêt ou retour sur l'onglet relance la surveillance ; une seule chaîne de requêtes à la fois. Filtre `SansRequetesDeStatut` posé sur le logger `uvicorn.access` (résiste au `dictConfig` d'uvicorn) : `/api/statut_pipelines`, `/api/statut_recherche` et `/api/spontanees/statut` disparaissent du journal, requête comprise. Vérifié sur un vrai uvicorn (base temporaire) : 6 requêtes de statut absentes, les autres présentes. Les anciennes routes de statut restent ; leurs fonctions JS, inutilisées, sont retirées d'`api.js`.

**Test statique et écarts corrigés.** Les JS n'utilisent aucun `id` : ils ciblent des attributs `data-*` et quelques classes. Le test extrait de chaque module les ids, attributs (avec leur valeur quand elle est écrite en clair) et classes cherchés par `querySelector`, `querySelectorAll`, `getElementById`, `closest`, `matches` ou rangés dans une table de sélecteurs, et vérifie leur présence dans les templates ou dans le balisage généré par les JS. Vérifié par mutation (attribut, valeur et id fautifs détectés). Écarts trouvés : `[data-pj-nom]` dans `profil.js` (variable morte : le nom de la pièce vient du fichier, comme le dit l'aide) et `.offre__card` dans la recherche de `app.js` (classe inexistante, les cartes sont des `.offre`). Supprimés tous deux.

**Bug 5.** `sauvegarder_enrichissement` enregistre `site_web` (colonne) et, dans `extra`, `url_scrapee`, `source_recherche`, `tentatives_site` (avec `telephone` comme avant) ; `_entreprise_vers_dict` les relit (`tentatives_site` entier, 0 par défaut). Un site trouvé sert au lancement suivant sans nouvelle recherche DuckDuckGo. Une valeur vide n'ajoute pas de clé dans `extra` (le scraper sauvegarde toute la liste). L'envoyeur ne les écrase pas.
**Bug 13.** Les 5 dernières candidatures de `calculer_stats` sont triées par `mail_envoye_le` décroissant (instant UTC), à date égale la dernière insérée d'abord, sans date en dernier.
**Bug 14.** `normaliser_contact_rh` (dans `entreprises_db`) : chaîne, dict `{prenom, nom, poste}`, liste mixte ou ancien JSON brut deviennent « Prénom Nom (poste), Autre Nom », espaces réduits, borné à 200 caractères (taille de la colonne, qui aurait fait échouer PostgreSQL). Appliquée à l'écriture et à la lecture : les anciennes lignes en JSON s'affichent lisibles sans migration de données. C'est la logique de l'ancien `migration.py`, désormais unique.

**Mentions d'un utilisateur réel.** `shared/profil.example.py` supprimé (plus référencé nulle part). Prompt de `archive/telegram_bot.py` neutralisé (prénom, poste visé et rentrée retirés). Vérifié sans objet : `tests/donnees/ancien_schema.sql` (schéma seul, aucune donnée). Laissés : `docs/` (historique), titre de l'application, géographie Île-de-France, `shared/profil.py` (non suivi).

**Documentation.** `docs/DECISIONS.md` (nouveau, règle de mise à jour et décisions D1 à D4 de la phase 3, comportement inchangé), `docs/RECETTE.md` (nouveau), README (mode test, limites, renvois). Les lignes de log ajoutées sont formulées pour être citées telles quelles dans la recette.

## 3. Migration

| Révision | Contenu | Données existantes |
|---|---|---|
| 0006 | `comptes_envoi.mode_test` BOOLEAN NOT NULL, défaut serveur faux | comptes existants en envoi réel ; downgrade : colonne retirée |

Écrite à la main en mode batch, comme 0005. Vérifié sur base temporaire : `upgrade head`, `alembic check` « No new upgrade operations detected », `downgrade 0005`, `upgrade head`, `alembic current` = `0006 (head)`. Aucune nouvelle dépendance.

## 4. Tests

Commande : `systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q`. Résultat : **325 passed** en 25 s (246 avant la phase, tous toujours verts). Adapté : le faux scraper de `test_pipelines.py` accepte les nouveaux paramètres (`**_`) ; la route de recherche tolère un `lancer_recherche` qui ne renvoie rien. `test_routes_protegees.py` couvre d'office les deux nouvelles routes (+2).

| Fichier | Couvre |
|---|---|
| `test_mode_test.py` (13) | option coupée par défaut, réglable, propre à chaque utilisateur, gardée à l'enregistrement du compte, refusée sans compte, corps validé ; redirection vers l'adresse d'expédition avec le vrai destinataire dans l'objet ; aucune adresse enregistrée, aucune entreprise marquée (date et destinataires compris) ; envoi réel suivant qui vise bien les entreprises ; entreprise déjà contactée non marquée ; adresse partagée visée une fois ; `test=True` sans l'option ; par la route : réponse, état, stats, logs et message de fin ; envoi réel sans aucune mention du mode test ; éléments d'interface présents |
| `test_limites.py` (18) | règle commune pour les 4 limites (défaut, 0, négatif, énorme) ; plafond des mails inchangé ; défauts et plafonds rendus dans la page ; recherche : FT et LBA dans le même budget (5 appels Mistral pour 3 FT et 10 LBA), offres au-delà de la limite reproposées, LBA ignorée quand FT épuise le budget, défaut 30, plafond 200, champ inconnu 422, mode job ; fetch arrêté à la limite sans requête de plus, sans limite tout parcouru, route qui borne ; scraper limité sur deux lancements, route qui borne ; envoi : route qui borne (10, 3, 50) et limite respectée |
| `test_statique.py` (8) | URL des CSS et de `app.js` versionnées par l'empreinte réelle ; aucune URL `/static/` sans version dans la page ni dans les gabarits ; import map avant le premier module et complète ; imports relatifs couverts ; version qui change avec le contenu ; URL versionnée servie ; extraction des sélecteurs non vide ; chaque sélecteur existe |
| `test_polling.py` (15) | 4 chemins de statut filtrés (avec requête), 6 autres gardés, filtre posé sur `uvicorn.access` et effectif, maintenu après le `dictConfig` d'uvicorn ; route commune, isolée par utilisateur, fermée sans session ; front sans `setInterval`, 5 s au moins, prochain poll seulement si un pipeline est actif, une requête par poll |
| `test_entreprises.py` (23) | bug 5 : site, page, source conservés, tentatives après un site non fiable, site connu réutilisé sans recherche, pas de clé vide ajoutée, rien perdu après l'envoyeur ; bug 13 : ordre par date sur 8 entreprises dans le désordre, sans date en dernier ; bug 14 : 12 formes normalisées, borne de 200, écriture lisible, ancien JSON relu lisible (liste et suivi), contact du scraper normalisé. 20 de ces tests échouent sur l'ancien `entreprises_db.py` |

Autres vérifications : uvicorn réel sur base temporaire migrée (inscription, page avec URL versionnées et import map, URL versionnée servie, journal d'accès sans requêtes de statut). Non faits : parcours dans un vrai navigateur, appels réels à FT, LBA, Sirene, Mistral, envoi SMTP réel (c'est l'objet de la recette).

## 5. Limites restantes

1. Mode test : il passe par le vrai serveur SMTP (un compte refusé arrête l'envoi comme en réel) et ses mails consomment le plafond quotidien. Les entreprises restant non marquées, chaque lancement de test vise les mêmes ; la carte « Envoyés » et la page de suivi ne bougent pas.
2. Recherche : les offres FT archivées automatiquement après analyse comptent dans la limite (elles ont coûté un appel Mistral). Les offres LBA au-delà du budget sont redemandées à LBA au lancement suivant (un appel LBA, pas Mistral). En mode job, la limite effective ne dépasse pas le lot de 100 du mode.
3. Fetch : la limite porte sur les entreprises gardées ; la première page Sirene peut en renvoyer jusqu'à 1000, dont seules les N premières sont gardées.
4. Scraper : la limite porte sur les entreprises, chacune pouvant coûter jusqu'à deux recherches DuckDuckGo, deux scrapings et deux appels Mistral. `tentatives_site` est conservé mais le scraper ne retente toujours qu'au sein d'un même lancement (une entreprise traitée n'est pas reprise) : comportement inchangé.
5. Polling : un pipeline lancé depuis un autre appareil n'est vu qu'au rechargement ou au retour sur l'onglet. Une erreur réseau pendant un pipeline garde le polling actif.
6. Import map : navigateurs récents seulement (Chrome 89, Firefox 108, Safari 16.4 et suivants). Les polices Google ne sont pas versionnées (externes). Pas d'en-tête `Cache-Control` long sur `/static` : le gain de la version est la fraîcheur, pas encore la mise en cache longue.
7. Filtre de journal : lié au logger `uvicorn.access` ; sous un autre serveur que uvicorn, il faudra le poser sur le journal d'accès de ce serveur.
8. Test statique : par expressions régulières ; un sélecteur construit par concaténation n'est pas vu, et une valeur dynamique (`${...}`) n'est vérifiée que par le nom de l'attribut.
9. Bug 14 : les anciennes lignes ne sont réécrites normalisées que lorsque le scraper les sauvegarde ; la lecture les normalise de toute façon.
10. Héritées, inchangées : entreprises communes aux deux modes (décision D2), threads et états en mémoire, pas de limitation de débit sur `/login` ni de jeton CSRF, aucune limite de fréquence sur « Tester la connexion ».

## 6. Avant la recette (humain)

**Constat à lire d'abord.** Pendant la phase, `data/chasseur_v2.db` a été modifiée à 11:49:32 et `.env` à 11:36, par une activité extérieure à cette phase (mes commandes Alembic et uvicorn visaient une base du dossier temporaire avec un `.env` absent). Lecture seule de la base : révision `0005`, 3 utilisateurs, 1 compte d'envoi, 0 entreprise. Aucune instance de l'application ne tournait à la fin de la phase. Conséquence : **si l'application est lancée depuis ce dossier avec le code de la phase 4 sans migrer, toute lecture de `comptes_envoi` échoue** (colonne `mode_test` absente). Migrer avant de relancer.

Après relecture et fusion de la branche dans `refonte-multiuser`, application arrêtée :

```bash
cd /home/kenza/Bureau/chasseur_alternance
source venv/bin/activate
cp data/chasseur_v2.db data/chasseur_v2_avant_phase4.db
alembic upgrade head          # DATABASE_URL du .env ; sinon préfixer DATABASE_URL=sqlite:////chemin/absolu/data/chasseur_v2.db
alembic current               # attendu : 0006 (head)
uvicorn main:app --port 5002  # sans --reload pendant la recette
```

Aucune nouvelle variable d'environnement. Si la section 8 du rapport de la phase 3 n'a pas été appliquée, l'appliquer d'abord (`CLE_CHIFFREMENT`, retrait des variables `GMAIL_*`). Puis suivre `docs/RECETTE.md`, en activant le mode test du compte d'envoi **avant** toute étape d'envoi. Une fois la recette faite, reporter dans `docs/DECISIONS.md` les points ci-dessous qui auront été tranchés.

## 7. Points à valider

1. **Destinataire du mode test** : l'adresse d'expédition du compte d'envoi (une boîte dont l'utilisateur a forcément le mot de passe), et non l'adresse de connexion, qui n'est pas vérifiée à l'inscription.
2. Mails du mode test comptés dans le plafond quotidien de 50 (ce sont de vrais mails).
3. Mode test coupé par défaut pour les nouveaux comptes et les comptes existants. Alternative plus prudente : activé par défaut à la création d'un compte d'envoi.
4. En mode test, une entreprise dont toutes les adresses sont déjà contactées est sautée sans être marquée (en réel, elle est marquée « skip »).
5. Défauts et plafonds des limites (30/200, 200/5000, 20/200, 10/50), et valeur hors bornes **ramenée** dans les bornes plutôt que refusée en 400.
6. Une seule limite d'analyses pour FT et LBA, FT servi en premier.
7. Polling à 5 s pendant un pipeline ; anciennes routes de statut gardées (plus utilisées par le front).
8. Suppression de `shared/profil.example.py`.
9. Ensuite : relire la branche, la fusionner dans `refonte-multiuser`, appliquer la section 6, faire la recette, pousser.
