# Phase 5b : domaines et France Travail, rapport

Branche `phase-5b-france-travail` (depuis `refonte-multiuser`), 8 octobre 2026. Non poussée, non fusionnée. Lus avant de commencer : `SPEC_SOURCES.md` (sections 0, 1, 2 et 7), `DECISIONS.md`, `PHASE_5A_RAPPORT.md`. Périmètre : sections 1 et 2 de la spec ; LBA et Sirene seulement adaptés au nouveau modèle des domaines, sans changement de comportement pour les profils existants. Rien écrit dans `data/` ni `.env`. Aucun appel réseau dans les tests. L'IA reste coupée et rien de ce qui suit n'en dépend. Une migration de données (0007), pas de changement de schéma.

## Commits

| Commit | Contenu |
|---|---|
| 8e800ff | Référentiels lus par le code, libellés nettoyés, 14 grands domaines, tailles d'entreprise |
| 55acb41 | `scripts/verifier_france_travail.py`, `france_travail/parametres_api.py`, API France Travail simulée pour les tests |
| 4d0c035 | Modèle des domaines, migration 0007, interface du choix des domaines, LBA et Sirene adaptés |
| 451512f | Filtres par mode, découpage adaptatif, filtre de taille, options du profil (taille, secteur, thèmes), README |
| 6452bec | Garde-fou du découpage : étape sans effet abandonnée |
| (dernier) | Décisions D22 à D26, ce rapport |

## 0. À lancer par l'humain : vérification de l'API

Depuis la racine du projet, `.env` rempli avec `FT_CLIENT_ID` et `FT_CLIENT_SECRET` :

```bash
venv/bin/python scripts/verifier_france_travail.py
```

Une soixantaine de requêtes, moins d'une minute. Détail dans `docs/referentiels/france_travail/verification_api.json` (`--sortie <dossier>` pour un autre emplacement), sans identifiant ni token. Le script termine par un bloc « À reporter dans france_travail/parametres_api.py » qui donne chaque valeur proposée, avec « inchangé » ou la valeur actuelle. Il suffit de recopier ce bloc dans ce fichier : c'est le seul endroit du code qui dépend de ces réponses.

Ce qu'il vérifie (section 7 de la spec, partie France Travail) :
1. **Paramètre de domaine.** Total IDF avec `domaine=M18`, `grandDomaine=M18`, `grandDomaine=M`, `domaine=M`, `codeROME=M1805` et des valeurs inexistantes, comparé au total sans filtre (identique : paramètre ignoré). Couverture : somme des 14 grands domaines et des 8 départements comparée au total.
2. **Valeurs multiples.** Pour `natureContrat`, `typeContrat`, `theme`, grand domaine, domaine, `secteurActivite` : total de chaque valeur seule puis de la liste. Liste acceptée si son total est au-dessus du plus grand total seul et au plus leur somme ; « première valeur seulement » si elle vaut le total de la première ; liste refusée (400) : nouvel essai à deux valeurs.
3. **Tranche d'effectif.** Sur 300 offres réelles (150 sans filtre, 150 en apprentissage) : chaque champ dont le nom contient « effectif » ou « tranche », sa présence, ses valeurs fréquentes, la part reconnue par `taille_depuis_tranche` et les valeurs non reconnues. Liste aussi toutes les clés des offres et de `entreprise`.
4. **Découpage.** `departement=75`, fenêtre `minCreationDate`/`maxCreationDate` sur 7 jours et depuis `DATE_PLUS_ANCIENNE` (doit retrouver le total).

Si le comptage par plage `0-0` est refusé, le script passe à `0-149`.

## 1. Référentiels

`shared/referentiels/` lit les fichiers téléchargés en phase 5a (`docs/referentiels/france_travail/`) et `grands_domaines.json` (les 14 lettres, que l'API ne publie pas ; libellés de la spec 1.1). Libellés nettoyés à la lecture : apostrophe initiale et `');` final retirés (9 libellés de `nafs`), virgule collée au mot suivant espacée (« liège,à » dans `secteurs_activites`), espaces normalisés. Les fichiers versionnés ne sont pas modifiés.

`shared/tailles.py` : les cinq tailles de la spec 4.2, partagées avec Sirene en 5d. Une tranche est rangée selon sa borne basse ; elle est lue en code INSEE (« 12 ») ou en libellé (« 20 à 49 salariés », « 1 ou 2 salariés », « 10 000 salariés et plus », « Moins de 10 »). « NN », « Non renseigné » ou absence : taille inconnue.

## 2. Modèle des domaines

- `recherche.domaines` : codes, `["M18"]`, `["C"]`, `[]` pour indifférent. `normaliser_domaines` convertit les anciennes clés, retire inconnus et doublons, et retire un domaine déjà couvert par son grand domaine (`["C", "C15"]` devient `["C"]`). Appliqué à chaque enregistrement du profil (`shared/criteres.py`) et à chaque lecture par la recherche (un profil importé de l'ancienne base avec `informatique` reste compris).
- **Migration 0007.** Dans `profils.recherche.domaines`, `informatique` devient `M18`, `immobilier` devient `C15`, doublons retirés ; profils sans domaines inchangés. Retour arrière : anciennes clés, autres codes retirés.
- **Interface.** Case « Indifférent », puis les 14 grands domaines ; « Affiner » déplie les domaines d'une lettre. Cocher une lettre grise ses domaines (« Tout le domaine ») ; cocher un domaine décoche « Indifférent » ; tout décocher le recoche. Même composant en alternance et en job. Vérifié dans Chromium sans interface sur une base temporaire : choix, enregistrement, rechargement, largeur 390 px.
- **Analyse IA** (coupée, mais prompts à jour) : libellés officiels (« Systèmes d'information et de télécommunication » au lieu de « Informatique & Télécoms »).
- **LBA et Sirene** (phases 5c et 5d) : leurs listes d'avant la phase (10 codes ROME et 16 codes NAF pour M18, 4 ROME et 7 NAF pour C15) sont gardées telles quelles sous les nouveaux codes. Profil indifférent : ancien défaut, informatique. Domaine sans correspondance : non cherché, signalé dans les logs (« LBA : domaines pas encore pris en charge, ignorés : J ») ; si aucun domaine n'en a, LBA est ignorée et la récupération Sirene s'arrête avec un message.

## 3. France Travail

### Filtres par mode (D23)

| | Alternance | Job |
|---|---|---|
| Contrat | `natureContrat` E2, FS | `typeContrat` CDD, MIS, SAI ; offres `alternance` écartées comme avant |
| Qualification | aucun filtre | aucun filtre (`qualification=0` retiré) |
| Domaine | profil, indifférent : aucun | idem |
| Options | secteur employeur | secteur employeur, thèmes 13 et 17 (décochés) |
| Taille | après récupération | idem |

`shared/modes.py` décrit les filtres (`ft_filtres`, `ft_options`) ; `shared/criteres.criteres_france_travail(profil, mode)` en tire la recherche. Les valeurs d'un même filtre sont réunies (OU), les filtres entre eux combinés (ET). Grands domaines et domaines passent par deux paramètres, donc deux groupes de requêtes. Chaque liste est envoyée par paquets de `VALEURS_PAR_REQUETE` (1 en attendant la vérification : une requête par valeur, résultats réunis).

### Découpage adaptatif (D24)

`Collecte.recuperer` lit la première page (total dans `Content-Range`). Au plus 3150 : pagination. Au-delà, la première étape applicable découpe, et chaque sous-requête recommence :
1. **département** : `region=11` remplacé par chacun des 8 départements ;
2. **domaine** : liste éclatée en valeurs ; sans domaine, les 14 grands domaines ; un grand domaine, ses domaines ;
3. **valeur** : autres filtres à plusieurs valeurs éclatés (cas où l'API accepte les listes) ;
4. **date de publication** : fenêtre `[DATE_PLUS_ANCIENNE, maintenant]` coupée en deux, récursivement, jusqu'à une minute.

Dédoublonnage par identifiant d'offre. Trois messages dans les logs du pipeline : sous-requêtes qui retrouvent moins d'offres que leur parent (offre rattachée à la région sans département, par exemple), plus aucun découpage possible (« N non récupérées »), étape sans effet. **Garde-fou** : si les deux premières sous-requêtes renvoient chacune le total entier, le paramètre est ignoré par l'API ; l'étape est abandonnée avec un message plutôt que de multiplier les requêtes (sans lui, des dates ignorées feraient jusqu'à 2^24 requêtes). Bilan dans les logs : offres distinctes, requêtes, erreurs, non récupérées. Une requête en erreur est abandonnée, les autres continuent ; 429 : une nouvelle tentative.

Les offres sont triées par date de création décroissante avant la limite par lancement (le découpage mélange l'ordre de l'API).

### Taille d'entreprise (D25)

Champ lu par `parametres_api.tranche_effectif` (`trancheEffectifEtab` en attendant), converti par `taille_depuis_tranche`. Rien de coché : aucun filtre. Les offres écartées par la taille ne sont pas marquées vues : elles reviennent si la taille change. Logs : « N offres écartées par la taille d'entreprise (dont M sans information) ».

### Profil

Sous les domaines, dans les deux modes : tailles (avertissement pour moins de 10 en alternance), « Garder les offres sans information de taille » (cochée par défaut), secteur de l'employeur (88 divisions, repliées) ; en job, les deux thèmes. Route `GET /api/criteres_options`. `/api/domaines` renvoie désormais l'arbre des grands domaines. Valeurs inconnues retirées à l'enregistrement.

## Tests

`systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q` : **537 passed** (453 à la fin de la phase 5a). Nouveaux : `test_referentiels.py` (35 : nettoyage, référentiels, tranches), `test_verifier_france_travail.py` (7), `test_domaines.py` (17 : arbre, normalisation, LBA et Sirene inchangés, enregistrement, route, LBA ignorée, migration aller et retour), `test_france_travail.py` (19 : requêtes par mode, options, découpage par département, domaines et dates, valeurs multiples, troncature signalée, couverture incomplète, erreur isolée, paramètres ignorés sans explosion, taille, tri et lot, profil). Ils reposent sur `tests/faux_france_travail.py`, API simulée qui filtre un jeu d'offres et applique les limites de pagination mesurées ; paramètres reconnus et valeurs multiples y sont réglables, pour tester chaque réponse possible du script de vérification. Les simulacres `_paginer` des anciens tests visent maintenant `recuperer_offres`. `compileall` et `node --check` propres.

Une fois, pendant la phase, `test_limiteur_mistral.py::test_appels_de_plusieurs_threads_espaces` a échoué dans la suite complète puis est passé seul, avec et sans les changements de la phase (test de minutage sensible à la charge, sans lien avec cette phase).

## Limites

- **Tout dépend encore de `parametres_api.py`**, non vérifié : si `domaine` ou `grandDomaine` n'est pas le bon nom, la recherche filtrée par domaine renverra tous les domaines (le garde-fou le signale dès qu'un découpage est nécessaire, pas sur une petite recherche). Lancer le script avant tout test réel.
- **Volume de requêtes.** Une requête par valeur tant que la vérification n'a pas tranché ; le mode job indifférent (environ 21 600 offres CDD et MIS en IDF) demande de l'ordre de 200 requêtes, soit 2 à 3 minutes à 0,4 s d'intervalle. Toutes les offres sont lues à chaque lancement, même si la limite n'en garde que 100.
- **Lecture complète, puis filtre de taille** : une recherche restreinte aux grandes entreprises lit quand même toutes les offres.
- **Référentiels lus dans `docs/referentiels/`** : le code dépend d'un dossier de documentation. Pratique (un seul exemplaire, celui que le script d'exploration met à jour), à déplacer si gênant.
- LBA et Sirene ne connaissent que M18 et C15 (phases 5c et 5d).

## Points à valider

Tranchés après le rapport : D27 (pas de migration vers M18, bandeau d'invitation dans le profil d'alternance), D28 (domaines filtrants en job), D29 (LBA et Sirene inchangés, domaines non couverts nommés dans la confirmation de lancement), D30 (taille inconnue gardée par défaut) dans `docs/DECISIONS.md`. Puis, après la vérification de l'API : D31 (découpage par date seulement, l'étape « valeur » du point 5 disparaît), D32 et D33 (valeurs de `parametres_api.py`), D34 (points 6 et 7 validés). Plus aucun point ouvert. Le découpage décrit en section 3 est remplacé par D31.

1. **Profils d'alternance sans domaine** : ils passent d'informatique par défaut à « tous les domaines » sur France Travail (conséquence de `[]` = indifférent). Les migrer vers `M18` pour garder l'ancien comportement ?
2. **Mode job** : les domaines cochés comme préférence filtrent désormais la recherche (spec 2.1). Un profil job existant avec `informatique` ne verra plus que des jobs M18.
3. **LBA et Sirene en attendant 5c et 5d** : profil indifférent cherché en informatique, domaine sans correspondance ignoré avec un message. Autre choix possible : désactiver ces sources pour tout profil autre que M18 ou C15.
4. **« Garder les offres sans information de taille »** cochée par défaut.
5. **Étape « valeur » du découpage**, ajoutée entre domaine et dates (n'agit que si l'API accepte les listes).
6. **Offres écartées par la taille non marquées vues** (elles reviennent si la taille change), et tri par date avant la limite.
7. **Secteur de l'employeur** proposé aussi en alternance (la spec le liste dans les deux modes) ; vide par défaut.
