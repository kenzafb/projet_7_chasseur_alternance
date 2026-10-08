# Phase 5a : préparation de l'étude des sources, rapport

Branche `phase-5a-sources` (depuis `refonte-multiuser`), 8 octobre 2026. Non poussée, non fusionnée. Lus avant de commencer : `DECISIONS.md`, `PHASE_4B_RAPPORT.md`. Rien écrit dans `data/` ni `.env`. Aucun appel réseau dans les tests. Pas de changement de schéma, donc pas de migration (`candidatures.score` acceptait déjà NULL).

## Commits

| Commit | Contenu |
|---|---|
| f1e87a9 | Interrupteur `ANALYSE_IA`, tests, décision D19, `.env.example`, README |
| 46aa1b0 | `scripts/explorer_france_travail.py` et ses tests |
| (dernier) | Ce rapport |

## 1. Interrupteur ANALYSE_IA

`shared.config.analyse_ia_active()`, relu à chaque appel ; `false`, `0`, `non`, `no`, `off` coupent l'IA, toute autre valeur ou l'absence la laisse active.

- **Aucun appel à Mistral.** Chaque pipeline teste l'interrupteur avant ; en dernier rempart, `appeler_mistral` lève `IADesactivee` (sous-classe de `ErreurIABloquante`) sans rien appeler. `verifier_mistral.py` affiche un message et sort en 0.
- **Recherche.** Offres France Travail et LBA insérées avec `verdict = "non_analysee"`, `score` NULL, ni points ni résumé, statut `nouveau`, puis marquées vues une à une. Pas d'archivage pour note basse ni hors domaine ; les règles par mots-clés restent en mode alternance (public réservé D12, école ou CFA, « stage » dans le titre), voir points à valider. La limite « analyses » borne aussi le nombre d'offres ajoutées. Non analysées triées après les autres (`nullslast`).
- **Interface.** « non analysée » à la place du viseur et en étiquette, exclues du score moyen ; « Générer la lettre » et « Réanalyser » désactivés avec la mention « Génération de lettre indisponible : l'IA est désactivée » (une lettre déjà écrite reste ouvrable). Côté serveur : 503 avec message pour `/api/generer_lettre` et `/api/analyser`, 400 pour `/api/spontanees/revalider`. Bandeau discret en haut de page ; bouton de revalidation IA remplacé par « valide les emails à la main ».
- **Scraper.** Lecture directe seulement, un seul message en début de lancement, emails notés non validés (D13), donc jamais envoyés automatiquement (D15).

## 2. Script d'exploration France Travail

La documentation officielle (francetravail.io, application JavaScript) n'a pas pu être lue. La liste des routes est donc en tête de script (`ROUTES_REFERENTIELS`), à corriger au besoin : metiers, domaines, appellations, secteursActivites, naturesContrats, typesContrats, niveauxFormations, themes, nafs, permis, langues, regions, departements, continents, pays, communes. Elle reprend les référentiels connus de l'API v2 et ceux qu'expose un client tiers ; une route absente donne « absent (404) » et l'exploration continue.

- Un fichier par référentiel : route, date, nombre, données. Au-delà de 1 Mo (cas attendu : communes), seuls le nombre et les 20 premiers éléments sont écrits (`resume_seulement`).
- `repartition_idf.json` : recherche avec le seul paramètre `region=11`, plage 0-149 ; total tiré de `Content-Range`, `filtresPossibles` bruts et regroupés par filtre, libellés des types et natures de contrat ajoutés depuis les référentiels téléchargés.
- `test_pagination.json` : plages 0-149, 0-199 (taille au-delà de 150), 1000-1149, 1050-1199, 1150-1299, 2000-2149, 3000-3149, 3150-3299 (`PLAGES_PAGINATION`) ; pour chacune code, `Content-Range`, `Accept-Range`, nombre de résultats ou message d'erreur ; plus le dernier index obtenu.
- Pause de 0,5 s entre requêtes, une nouvelle tentative sur 429. Les fichiers ne contiennent que des données de l'API, et tout texte écrit est purgé de l'identifiant, du secret et du token. Code de sortie 1 si le token est refusé ou les identifiants absents.

**Commande à lancer** (depuis la racine du projet, `.env` rempli avec `FT_CLIENT_ID` et `FT_CLIENT_SECRET`) :

```bash
venv/bin/python scripts/explorer_france_travail.py
```

Une cinquantaine de requêtes, moins d'une minute. Fichiers dans `docs/referentiels/france_travail/` (`--sortie <dossier>` pour un autre emplacement).

## Tests

`systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q` : **453 passed** (398 à la fin de la phase 4b, plus les ajouts de D15). Nouveaux : `test_analyse_ia_desactivee.py` (26 : valeurs de l'interrupteur, refus d'appel, recherche FT et LBA sans aucun appel, offres vues et non reprises, limite, archivage par mots-clés gardé et rien d'autre, tri, lettre et réanalyse en 503, page avec et sans bandeau, scraper en lecture directe, revalidation refusée, script de vérification), `test_explorer_france_travail.py` (10 : référentiels et 404, communes en résumé, répartition et libellés, pagination, aucun secret écrit, 429, recherche en 404, token refusé ou injoignable, identifiants absents). `ANALYSE_IA` retirée de l'environnement des tests. `compileall` et `node --check` propres.

## Limites

- Liste des routes et forme des réponses (`filtresPossibles`, `agregation`, `valeurPossible`, `nbResultats`, en-têtes de plage) non vérifiées contre l'API réelle : les tests reposent sur la forme attendue. Si l'API ne renvoie pas les natures de contrat dans ses filtres, le résumé l'indique (« Filtres non renvoyés par l'API »).
- La recherche ne lit qu'une page pour la répartition : les effectifs sont ceux des agrégations de l'API, pas un comptage.
- Les offres déjà insérées « non analysées » ne seront pas analysées d'elles-mêmes au retour de l'IA (bouton « Analyser » une à une).

## Points à valider

1. Archivage par mots-clés (public réservé, école ou CFA, stage) conservé sans IA ; seuls note basse et hors domaine disparaissent.
2. Limite « analyses » appliquée aussi aux offres ajoutées sans analyse, ou plafond distinct (voire aucun) quand l'IA est coupée.
3. Analyse en lot des offres `non_analysee` à prévoir avec le modèle local.
