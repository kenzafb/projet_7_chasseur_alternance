# Phase 6b : le mode stage, rapport

Branche `phase-6b-stage`, 9 octobre 2026, créée depuis `refonte-multiuser` (qui contient la phase 6a). Non poussée, non fusionnée. Lus avant de commencer : `DECISIONS.md`, `SPEC_SOURCES.md`, `PHASE_6A_RAPPORT.md`. Rien écrit dans `data/` ni `.env` : `data/chasseur_v2.db` et `data/chasseur.db` lus en lecture seule (essai à blanc de l'import, liste du nettoyage ; empreinte de `chasseur_v2.db` identique avant et après), migration et nettoyage essayés sur une copie dans le dossier temporaire de la session. Aucun appel réseau dans les tests. L'IA reste coupée et rien de ce qui suit n'en dépend. Décisions D68 à D72.

## Commits

| Commit | Contenu |
|---|---|
| 9ae3c9f | Mode stage ouvert : profil propre, migration 0012, balises du mail, objet et trame par défaut, offres pas encore disponibles |
| f3fdf61 | `verifier_france_travail.py` : essai `motsCles=stage`, option `--stage` |
| ddf546f | Case « tous les secteurs », message avant lancement, refus de « Récupérer » sans source, `verifier_sirene.py --tous-secteurs` |
| 1d9a907 | Étiquette « déjà contactée » : test de bout en bout sur une entreprise récupérée après l'import |
| 2c95f7f | Nettoyage des adresses contactées exclues, exclusion dès l'import |
| (dernier) | README, décisions D68 à D72, ce rapport |

## À lancer par l'humain

Depuis la racine du projet, dans cet ordre :

```bash
git checkout phase-6b-stage

# 1. Sauvegarde, puis migration 0012 (colonnes du profil de stage, rien d'autre)
cp data/chasseur_v2.db data/chasseur_v2.db.avant-0012
venv/bin/alembic upgrade head
venv/bin/alembic check

# 2. France Travail, essai motsCles=stage (33 requêtes, identifiants FT du .env)
venv/bin/python scripts/verifier_france_travail.py --stage

# 3. Volume réel de « tous les secteurs » en Île-de-France (4 requêtes, clé INSEE)
venv/bin/python scripts/verifier_sirene.py --tous-secteurs

# 4. Adresses contactées exclues : liste, puis suppression
venv/bin/python scripts/nettoyer_emails_exclus.py
venv/bin/python scripts/nettoyer_emails_exclus.py --appliquer

# 5. Relancer l'application
uvicorn main:app --reload --port 5002
```

Étape 2 : lire `docs/referentiels/france_travail/verification_stage.json` (ou la sortie du terminal) avant de décider si France Travail entre dans le mode stage. Étape 3 : reporter les nombres de `docs/referentiels/insee/verification_tous_secteurs.json` dans `VOLUME_TOUS_SECTEURS` (`shared/naf.py`), affiché à côté de la case. Étape 4 : la liste faite en lecture seule le 9 octobre donne 6 adresses de l'utilisateur 1 en alternance (5 en `sentry.wixpress.com` ou `sentry-next.wixpress.com`, plus `contact@monsite.com`) et aucune entreprise ; sur la copie, il reste 792 adresses contactées après `--appliquer`.

Étape 5, recette du mode stage : ouvrir http://localhost:5002, choisir Stage. Profil : remplir les dates (la durée s'affiche sous les champs), l'établissement, la formation, des domaines ou secteurs, puis enregistrer. Page Spontanées : sans domaine, secteur ni « tous les secteurs », un bandeau le dit et « Récupérer » est refusé ; avec M18 et une limite de 10, « Récupérer » remplit avec Sirene seulement. Mode test du compte d'envoi coché, « Envoyer » : le mail reçu doit annoncer le stage avec ses dates et sa durée.

Retour arrière de la migration si besoin : `venv/bin/alembic downgrade 0011` (les champs du stage sont perdus), ou recopier la sauvegarde.

## 1. Mode stage (D68)

**Mode.** `shared/modes.py` : `stage` rejoint `MODES` (label « Chasseur de Stage », couleur verte, sources vides, `offres: False`). `MODES_A_VENIR` est vide ; le mécanisme reste pour un futur mode. `/stage` sert l'application comme `/alternance` et `/job` ; `templates/bientot.html` est supprimé. L'API accepte `mode=stage` sur toutes les routes du mode.

**Profil (migration 0012).** Colonnes `profils.date_debut` et `date_fin` (type `Date` : des jours du calendrier, pas des instants, donc sans fuseau), `etablissement`, `missions`, `portfolio`. La formation utilise la colonne commune `profils.formation` (les profils sont par mode, rien ne se mélange). `lire_profil` rend les dates en `AAAA-MM-JJ` (vides si absentes) et `duree_semaines` calculée. À l'enregistrement : date illisible ou fin antérieure au début (y compris quand une seule des deux dates est envoyée), 400 et rien n'est écrit.

**Durée** (`shared/stage.py`, même règle dans `profil.js`) : jours du premier au dernier compris, divisés par 7, arrondis à la semaine la plus proche, au moins 1. Du lundi 4 janvier au vendredi 25 juin 2027 : 173 jours, 25 semaines.

**Interface.** Deux sections propres au stage : « Ton stage » (dates en champs date, durée affichée en direct, établissement, formation, missions visées, portfolio) et « Domaines et candidatures spontanées » (domaines, tailles des spontanées, départements, secteurs). Pas de tailles des offres en stage. Identité, mail de candidature, pièces jointes et compte d'envoi sont communs, comme avant. Page Offres : encadré « Les offres de stage ne sont pas encore disponibles », ni limite ni bouton de lancement ; `POST /api/recherche?mode=stage` répond 400 avec le même message. Page Spontanées : sous-titre de « Récupérer » sans LBA.

**Balises du mail** (`shared/balises_mail.py`). Le mail de candidature spontanée n'avait jusqu'ici aucune balise (seule la lettre type en avait : `{contact_entreprise}`, `{date}`, `{paragraphe_entreprise}`). Balises ajoutées, dans l'objet comme dans le message :
- tous les modes : `{prenom}`, `{nom}`, `{telephone}`, `{email}`, `{date}` (date du jour) ;
- stage seulement : `{date_debut}`, `{date_fin}` (en toutes lettres : « 4 janvier 2027 », « 1er février 2027 »), `{duree_semaines}` (le nombre seul), `{etablissement}`, `{formation}`, `{missions}`, `{portfolio}`.

Espaces tolérés dans une balise (`{ date_debut }`), toute autre accolade refusée, comme pour la lettre type. Vérification à l'enregistrement du profil (400) et avant le premier envoi : une balise dont la valeur est vide dans le profil bloque l'envoi (400 sur la route, avant tout lancement), plutôt que de partir avec un trou dans le texte. Aucune trame existante ne contenait d'accolade (vérifié en lecture seule sur `chasseur_v2.db`).

**Objet et trame par défaut du stage** (`spontanees/envoyeur.py`), signés comme les autres de nom, téléphone et email :

> Objet : Candidature spontanée : stage du {date_debut} au {date_fin}
>
> Bonjour,
>
> Je me permets de vous adresser ma candidature spontanée pour un stage conventionné de {duree_semaines} semaines, du {date_debut} au {date_fin}, au sein de votre entreprise.
>
> Actuellement en formation, je recherche une structure où mettre en pratique mes compétences et contribuer concrètement aux projets de votre équipe.
>
> Vous trouverez mon CV en pièce jointe. Je reste à votre disposition pour tout échange.
>
> Cordialement,

Ni établissement, ni formation, ni accord de genre : la trame reste valable pour n'importe qui. Elle exige les dates du stage.

## 2. Sources du mode stage (D69)

- **Sirene** : même chemin qu'en alternance (`fetch_entreprises.main` avec le profil du mode : cœurs, transverses, tailles et départements des spontanées). Un test vérifie que LBA n'est jamais appelée en stage.
- **LBA** : absente (`sources` vide).
- **France Travail** : non branché. `scripts/verifier_france_travail.py` gagne une étape 5 : `motsCles=stage` en Île-de-France, total, répartition exacte par `typeContrat` et par `natureContrat` (un comptage par code des référentiels, 12 types et 19 natures), puis sur les 150 plus récentes : types, natures, nombre en alternance, nombre d'intitulés qui contiennent « stage » ou « stagiaire », 20 intitulés d'exemple. Résultat dans `verification_stage.json`, à part de `verification_api.json`. Lancement complet (étapes 1 à 5) ou `--stage` seul (33 requêtes).

## 3. « Tous les secteurs » et message avant lancement (D70)

**Profil.** Dans chaque mode, un bloc « Candidatures spontanées : tous les secteurs » : une case non cochée par défaut (`recherche.tous_secteurs`, vrai seulement si coché), le volume indiqué à côté, et un message qui apparaît en direct quand rien ne sera cherché sur Sirene. Le message suit la règle du serveur : aucun domaine, aucun secteur et la case non cochée ; ou un domaine sans correspondance NAF (tout sauf M18 et C15) sans secteur ni case.

**Volume affiché.** « plus d'un million d'entreprises en Île-de-France toutes tailles confondues, encore plusieurs dizaines de milliers à partir de 10 salariés ». C'est un ordre de grandeur, non mesuré : `scripts/verifier_sirene.py --tous-secteurs` compte les sièges actifs des 8 départements toutes tranches, hors « sans salarié », à partir de 10 salariés, et la requête réelle ; les nombres sont à reporter dans `VOLUME_TOUS_SECTEURS`.

**Page Spontanées.** `/api/spontanees/stats` rend `avertissement_recuperer` ; un bandeau l'affiche dès l'ouverture de la page, avant tout lancement. Le message est le même que celui du lancement et des logs.

**Récupérer.** En job et en stage (Sirene seule source), sans rien à chercher : 400 avec ce message, rien ne démarre. En alternance, le lancement a lieu (LBA cherche quand même) et la confirmation reprend le message.

**Recherche Sirene** avec la case : groupe « tous secteurs » ajouté en fin de plan (après cœurs, secteurs choisis et transverses), mêmes tailles que les cœurs (requête à part pour les effectifs inconnus, comme D64), départements du profil, activités exclues de D49 retirées par une clause `-activitePrincipaleUniteLegale:(41.10D OR 66.19A OR 68.32B)` en ET (jamais dans un OU). Les logs nomment le groupe et le comptent dans la répartition finale.

## 4. Étiquette « déjà contactée » pour les entreprises récupérées plus tard (D71)

Rien à changer dans le code : `contacts_autres_modes` (phase 6a) calcule l'étiquette à chaque lecture, d'après les adresses actuelles de l'entreprise comparées aux adresses contactées des autres modes (table `emails_contactes`, import historique compris). Une entreprise récupérée après l'import reçoit donc l'étiquette dès que le scraper lui trouve une de ces adresses. Nouveau test de bout en bout, en job et en stage : import du groupe a sur une base vide, « Récupérer » par Sirene, adresse de l'historique trouvée (casse différente), étiquette « déjà contactée en alternance le 29/05/2026 » dans `lire_entreprises`, `/api/spontanees/stats` et `calculer_stats`, envoi toujours possible.

## 5. Nettoyage des adresses contactées (D72)

- `scripts/nettoyer_emails_exclus.py` traite désormais deux parties : les entreprises (inchangé) et les adresses contactées, tous utilisateurs et tous modes. Sans `--appliquer`, liste seulement ; avec, les lignes des adresses exclues sont supprimées de `emails_contactes`. La sortie garde la trace de ce qui est retiré.
- `scripts/importer_contacts_historiques.py` écarte ces adresses avant le classement : elles ne sont plus jamais importées. Essai à blanc réel : 11 adresses écartées, 1074 classées, groupe a 792 (au lieu de 798).

## Tests

`systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q` : **750 passed** (709 au début de la phase). Chaque commit de thème passe seul. `node --check` propre sur tous les modules. Nouveaux ou adaptés :
- `test_mode_stage.py` (26) : durée et dates en lettres, page `/stage` et offres indisponibles, aide des balises propre au stage, mode à venir toujours refusé, profil de stage (lecture, effacement, refus sans écriture), balises par mode, balise vide, objet et trame par défaut, envoi réel simulé avec balises, refus d'envoi sans dates avant lancement, « Récupérer » en stage par Sirene sans LBA, migration 0012 montée et retour arrière.
- `test_tous_secteurs.py` (8) : normalisation, options du profil, avertissements, plan (tous secteurs en dernier, exclusion, effectifs inconnus), récupération en job sans domaine, cœurs d'abord en stage, refus en job et en stage avec message dans les statistiques, alternance lancée pour LBA.
- `test_verifier_france_travail.py` (2), `test_verifier_sirene.py` (1) : essai `motsCles=stage` (comptages, échantillon, `--stage` seul), volume « tous les secteurs ».
- `test_importer_contacts_historiques.py` (3), `test_nettoyer_emails_exclus.py` (1) : étiquette sur une entreprise récupérée après l'import, adresses exclues jamais importées, nettoyage des adresses contactées.
- Adaptés : `test_modes_url.py`, `test_routes_protegees.py` (stage ouvert), `test_naf.py`, `test_sirene.py` (texte du message), `test_etat_par_mode.py` (0011 n'est plus la dernière migration). L'API France Travail simulée comprend `motsCles` (intitulé ou description, sans casse).

Migration 0012 et nettoyage essayés sur une copie de `data/chasseur_v2.db` : montée en 0012, `alembic check` propre, profils existants aux champs vides. L'interface n'a pas été vérifiée dans un navigateur.

## Limites

- **Volume de « tous les secteurs »** : ordre de grandeur non mesuré tant que `verifier_sirene.py --tous-secteurs` n'a pas tourné.
- **Clause d'exclusion en ET** (`-activitePrincipaleUniteLegale:(...)`) : acceptée par l'API simulée ; la vraie API n'a vérifié que `-trancheEffectifsUniteLegale:*` (D54). La quatrième mesure du script la vérifie.
- **« stage » et « stagiaire »** : l'API simulée cherche le mot comme une sous-chaîne, donc « stagiaire » ne correspond pas à « stage ». Le comportement réel de `motsCles` (racine, mot entier) n'est pas connu : l'échantillon de l'étape 2 le montrera.
- **Ordre de Sirene** sans filtre d'activité : sans lien avec les domaines ; la limite prend les premières entreprises rendues.
- **Étiquette « historique »** : une entreprise reconnue par une adresse importée affiche la date de l'ancien envoi, mais pas la mention « contact antérieur à la refonte » (la table `emails_contactes` ne dit pas d'où vient une adresse). Seules les entreprises marquées par l'import l'ont.
- **Même mode** (préexistant) : une entreprise récupérée plus tard en alternance, dont l'adresse est dans l'historique, n'a pas d'étiquette (même mode) ; l'envoyeur la saute et la marque envoyée avec la note « skip, tous emails déjà contactés », ce qui la compte dans « Envoyés ».
- **Nettoyage** : les adresses supprimées de `emails_contactes` restent dans `mail_destinataires` des entreprises marquées, où elles ne servent qu'au dédoublonnage.

## Points à valider

1. **Balises communes** ajoutées au mail (`{prenom}`, `{nom}`, `{telephone}`, `{email}`, `{date}`), puisqu'il n'en existait aucune ; balises du stage réservées au mode stage ; `{missions}` ajoutée à la liste demandée.
2. **Règle de durée** : arrondi à la semaine la plus proche, jours du premier au dernier compris, au moins 1.
3. **Dates en toutes lettres** dans les balises (« 4 janvier 2027 », « 1er »), et `{duree_semaines}` sans le mot « semaines ».
4. **Balise vide = envoi refusé** avant le premier mail ; la trame par défaut du stage exige donc les dates.
5. **Texte de l'objet et de la trame par défaut** du stage (section 1).
6. **« Tous les secteurs » cherché en dernier**, en complément des domaines et secteurs, plutôt qu'à leur place ; mêmes tailles que les cœurs ; activités exclues de D49 conservées.
7. **« Récupérer » refusé (400)** en job et en stage quand rien n'est à chercher ; lancé en alternance pour LBA.
8. **Profil job** : la case « tous les secteurs » y est, mais toujours ni départements ni tailles des spontanées (point 7 de la phase 6a, ouvert) : toute l'Île-de-France, toutes tailles sauf « sans salarié ».
9. **« Sans salarié » proposée en stage**, avertissements des petites tailles écrits pour un stagiaire.
10. **Nettoyage par suppression** des lignes de `emails_contactes`, sans trace en base autre que la sortie de la commande.
11. **Exclusion dès l'import** de l'historique (792 au lieu de 798 dans le groupe a).
12. **Couleur verte** du mode stage.
