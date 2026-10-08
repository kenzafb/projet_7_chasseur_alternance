# Phase 5c : La Bonne Alternance, rapport

Branche `phase-5c-lba` (depuis `refonte-multiuser`), 8 et 9 octobre 2026. Non poussée, non fusionnée. Lus avant de commencer : `SPEC_SOURCES.md` (sections 0, 3 et 7), `DECISIONS.md`, `PHASE_5B_RAPPORT.md`. Rien écrit dans `data/` ni `.env`. Aucun appel réseau dans les tests. L'IA reste coupée et rien de ce qui suit n'en dépend. Une migration de schéma (0008).

## Commits

| Commit | Contenu |
|---|---|
| 3859f4b | `scripts/verifier_lba.py`, `france_travail/parametres_lba.py`, API LBA simulée pour les tests |
| d949fa2 | Valeurs vérifiées reportées dans `parametres_lba.py`, niveau jamais envoyé, résultat du script versionné |
| 64cf00d | Recherche LBA : codes métiers du référentiel, recherche sans code, niveau filtré après récupération, centres et redécoupage, taille des entreprises, message « Aucune offre LBA » |
| ea83a3a | Entreprises à fort potentiel dans les spontanées : colonne `source`, migration 0008, dédoublonnage par SIRET, priorité, interface, étape « Récupérer » |
| 8ba1116 | France Travail : arrêt du téléchargement dès que le lot est plein |
| (dernier) | README, décisions D36 à D43, ce rapport |

## 0. À lancer par l'humain

Avant tout lancement sur la vraie base (`entreprises.source`, migration 0008) :

```bash
venv/bin/alembic upgrade head
```

Vérification de l'API LBA (déjà faite le 9 octobre 2026 ; à relancer si l'API change), depuis la racine du projet, `LBA_API_KEY` dans `.env` :

```bash
venv/bin/python scripts/verifier_lba.py
```

Une trentaine de requêtes, moins d'une minute. Détail dans `docs/referentiels/lba/verification_api.json` (`--sortie <dossier>` pour un autre emplacement), sans clé, emails réduits au domaine, téléphones masqués. Le script termine par un bloc « À reporter dans france_travail/parametres_lba.py », seul fichier du code qui dépend de ces réponses. Il vérifie : codes métiers par requête (20 à 100) et recherche sans code ; rayon (10 à 201 km) ; coordonnées (Paris et Cergy comparées) ; nom et format du paramètre de niveau, et niveau lu dans les offres ; plafond par source ; tous les champs des entreprises à fort potentiel ; offres France Travail avec et sans exclusion.

## 1. Résultats de la vérification (D42)

- 100 codes acceptés en une requête ; recherche sans code acceptée ; rayon jusqu'à 200 km (201 refusé).
- Entreprises : 150 sur tous les cercles essayés, seul Cergy à 10 km en donne 98. Offres : 150 par source, 450 en tout.
- `target_diploma_level` filtre, les autres noms essayés sont ignorés ; il écarte les offres sans niveau.
- Entreprises (4148 lues) : SIRET, nom, adresse, effectif, NAF, `apply.url` toujours présents ; aucun email ni téléphone ; `apply.recipient_id` dans 772.
- `partners_to_exclude=France Travail` retire les 28 offres France Travail d'une recherche avec codes, mais une recherche sans code en renvoie 261 : le filtre par nom de partenaire reste indispensable.

## 2. Recherche LBA (`france_travail/scraper_lba.py`)

**Codes métiers (D37).** `shared.domaines.codes_metiers` : tous les métiers de `metiers.json` dont le code commence par un domaine ou un grand domaine du profil (M18 : 96 codes ; C : 64). Lots de 100. Profil indifférent : recherche sans code. Les anciennes listes écrites à la main (10 codes ROME pour M18, 4 pour C15) disparaissent ; Sirene garde les siennes jusqu'à la phase 5d.

**Niveau (D38).** `shared/niveaux.py` lit le niveau visé, texte libre du profil, en niveau européen : « Bac+2 », « BTS », « DUT » : 5 ; « Bac+3 », « Bac+4 », « Licence », « BUT », « Bachelor » : 6 ; « Bac+5 », « Master », « ingénieur » : 7 ; « Bac » : 4 ; « CAP » : 3 ; « niveau N » : N. Le premier niveau écrit compte (« Bac+2 à Bac+3 » : 5). Rien n'est envoyé à l'API ; après récupération, les offres d'un autre niveau sont écartées, celles sans niveau gardées. Logs : niveau retenu, ou « non renseigné », « non reconnu » (aucun filtre), puis le nombre d'offres écartées.

**Géographie et plafond (D36).** 19 centres dans `shared/config.py` (`LBA_CENTRES`) : Paris 8 km ; Nanterre, Clamart, Bobigny, Créteil 10 km ; Versailles, Cergy, Roissy, Marne-la-Vallée, Évry, Melun, Meaux, Coulommiers, Nemours 18 à 20 km ; Provins, Fontainebleau, Étampes, Rambouillet, Mantes-la-Jolie 22 à 25 km. Un test vérifie que 17 communes en bordure de la région (Château-Landon, Provins, Houdan, Magny-en-Vexin, Beaumont-sur-Oise...) sont dans au moins un cercle. Une réponse au plafond (une source à 150, ou 450 offres) fait redécouper le cercle en sept cercles de rayon moitié (un au centre, six autour à racine de 3 sur 2 du rayon, ce qui recouvre tout le cercle), jusqu'à 1 km, puis le lot de codes en deux. Les requêtes sont parcourues en largeur, au plus 300 par recherche (`LBA_REQUETES_MAX`). Logs : nombre de requêtes, cercles encore au plafond au rayon minimal (nom, rayon, coordonnées, offres ou entreprises), requêtes non faites faute de budget.

Les entreprises sont au plafond presque partout. Les redécouper à chaque recherche d'offres coûterait des centaines de requêtes ; la recherche d'offres ne redécoupe donc que pour les offres, et écrit dans les logs les cercles au plafond d'entreprises laissés tels quels. Le redécoupage des entreprises se fait dans l'étape « Récupérer » des spontanées.

**Exclusions.** Offres dont le partenaire contient « France Travail » ou « Pôle emploi » (casse et accents ignorés) écartées, comptées dans les logs. Hors Île-de-France (code postal de l'adresse) écartées. Une requête en erreur est abandonnée, les autres continuent ; 429 : une nouvelle tentative ; clé refusée : arrêt, résultats déjà reçus gardés.

**Point 8.** « Aucune offre LBA récupérée » n'est écrit que si LBA a tourné : plus après « LBA ignorée : limite atteinte », ni après une clé absente.

## 3. Entreprises à fort potentiel (D39, D40, D41)

- **Schéma.** `entreprises.source`, « sirene » ou « lba », non nul, défaut « sirene » (migration 0008, entreprises existantes en « sirene » ; retour arrière : colonne retirée, lignes gardées).
- **Insertion** (`ajouter_entreprises_lba`). Mode alternance, source « lba ». Dédoublonnage par SIRET avec toutes les entreprises de l'utilisateur, à défaut par identifiant LBA. Une entreprise Sirene retrouvée sur LBA passe en source « lba » et garde ses données. `apply.recipient_id` gardé dans `extra.lba.candidature_id` avec `apply.url`, l'API de candidature directe n'est pas branchée. Email éventuel noté dans `extra.emails_lba` et ajouté aux emails s'il n'a pas encore été contacté.
- **Taille.** Les tailles cochées du profil d'alternance s'appliquent (`workplace.size` lu par `taille_depuis_tranche` : « 0-0 » et « 6-9 » moins de 10, « 50-99 » 50 à 249) ; l'option « garder les tailles inconnues » aussi.
- **Priorité.** `lire_entreprises` rend les entreprises LBA d'abord : le scraper et l'envoyeur les traitent avant celles de Sirene. Page Spontanées : la table montre les 30 prochaines entreprises (LBA d'abord) puis les dernières envoyées, pastille « LBA », filtre « Fort potentiel (LBA) », compteur « dont N à fort potentiel ».
- **Recherche d'offres.** Les entreprises reçues sont versées dans les spontanées (« N entreprises à fort potentiel ajoutées »).
- **Étape « Récupérer ».** LBA d'abord, cercles au plafond d'entreprises redécoupés, arrêt dès que la limite de nouvelles entreprises est atteinte (les entreprises déjà en base ne comptent pas) ; puis Sirene pour le reste de la limite, ou pas du tout si LBA l'a remplie. Le message de lancement nomme toujours les domaines non couverts par Sirene.

## 4. France Travail : arrêt dès que le lot est plein (D43)

Vérifié : avant cette phase, une recherche limitée à N offres lisait toutes les tranches du découpage puis n'en gardait que N. Corrigé : `Collecte` compte les offres qui entreront dans le lot (mêmes filtres que `chercher_offres` : non vues, en IDF, titre présent, bonne taille, hors alternance en mode job) et ne demande plus aucune page ni tranche une fois N atteint. Les pages arrivent des plus récentes aux plus anciennes (`sort=1`) et la moitié la plus récente d'une fenêtre est lue d'abord : le lot contient les N offres nouvelles les plus récentes. Sur 3313 offres simulées étalées sur 50 jours : 17 requêtes pour un lot de 100, contre 38 pour tout lire. Les logs donnent le nombre de requêtes et « arrêt dès N nouvelles offres obtenues » ; le bilan « annoncé, récupéré, écart » n'est écrit que pour une recherche lue en entier (il donnerait un faux écart). Sans lot (ligne de commande), tout est lu comme avant.

## Tests

`systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q` : **610 passed** (544 au début de la phase). Chaque commit de thème passe seul. Nouveaux :
- `test_verifier_lba.py` (5) : valeurs trouvées, autres réponses possibles de l'API, niveau introuvable, clé absente ou refusée, aucune donnée sensible dans le fichier.
- `test_lba.py` (48) : lecture du niveau (17 cas), tailles au format LBA, recouvrement des sept sous-cercles, couverture de 17 communes de bordure, recherche (codes, niveau, taille, exclusions, une requête par centre), indifférent sans code, niveau non renseigné, normalisation d'une entreprise, cercles au plafond comptés ou redécoupés, offres au plafond, cercle encore au plafond au rayon minimal, limite de requêtes, objectif de nouvelles entreprises, clé, erreur isolée.
- `test_entreprises_lba.py` (8) : dédoublonnage par SIRET et priorité, limite, email d'une entreprise déjà contactée, statistiques et page, migration 0008 aller et retour, recherche qui verse les entreprises, point 8, étape « Récupérer ».
- `test_france_travail.py` (4) : arrêt anticipé (offres les plus récentes, moins de la moitié des requêtes), offres déjà vues non comptées, offres écartées par la taille non comptées, sans lot tout est lu.
- `test_domaines.py` : 4 tests réécrits, devenus 5 (codes métiers du référentiel, Sirene inchangé, LBA pour tout domaine et l'indifférent, avertissements de Sirene seulement).

API simulée `tests/faux_lba.py` : offres et entreprises placées sur une carte, filtrées par codes, distance, niveau et partenaire, plafond par source ; nom du paramètre de niveau, codes par requête, rayon maximal, recherche sans code et exclusion réglables. L'API France Travail simulée trie désormais par date décroissante quand `sort=1`, comme la vraie. `compileall` et `node --check` propres.

## Limites

- **Redécoupage testé sur l'API simulée seulement.** On ne sait pas dans quel ordre la vraie API choisit les 150 entreprises d'un cercle plein ; le recouvrement par sous-cercles ne dépend pas de cet ordre, mais le nombre de requêtes nécessaires, si. À observer dans les logs de la première recette.
- **Durée de l'étape « Récupérer ».** Jusqu'à 300 requêtes LBA, environ 3 minutes, avant Sirene.
- **Indifférent sans code à Paris** : des milliers d'entreprises par kilomètre carré, des cercles d'1 km resteront au plafond (signalé dans les logs).
- **Coût du découpage par date France Travail** : la fenêtre part de 2000 ; à chaque niveau de la dichotomie, la moitié ancienne vide est quand même demandée (garde-fou de D24 contre des dates ignorées), d'où 17 requêtes et non 2 ou 3 pour un lot de 100.

## Points à valider

1. **« 0-0 » lu comme « moins de 10 salariés ».** Valeur fréquente chez LBA (« WETRADELOCAL », « GRANITE » dans les exemples) ; elle peut vouloir dire « 0 salarié » ou « non renseigné ». Lue comme 0, une entreprise « 0-0 » est écartée par un profil qui ne coche que 10 salariés et plus. La lire comme « inconnue » la ferait dépendre de l'option « garder les tailles inconnues ».
2. **Recherche d'offres : toutes les entreprises reçues versées dans les spontanées**, sans la limite « nouvelles entreprises » (jusqu'à 19 x 150 = 2850 par recherche). Autre choix : ne les verser que par l'étape « Récupérer ».
3. **Objectif de l'étape « Récupérer » et parcours en largeur** : la limite atteinte arrête la recherche ; les premiers centres (Paris d'abord) sont favorisés à chaque lancement, les suivants viennent aux lancements d'après (les entreprises déjà en base ne comptent pas).
4. **Rayon minimal 1 km, 300 requêtes au plus par recherche LBA** : valeurs choisies sans mesure, dans `shared/config.py`.
5. **Arrêt anticipé France Travail avec plusieurs requêtes de départ** (plusieurs domaines à trois caractères : une requête par domaine) : la première requête remplit le lot en priorité ; les offres des autres domaines viennent aux lancements suivants.
6. **Lecture du niveau visé en texte libre** : règles de la section 2 (« Bac+1 » lu 5). Une liste à choix dans le profil serait plus sûre.
7. **Email fourni par LBA envoyable sans validation**, comme un email validé. Théorique : aucune entreprise n'en a.
8. **Offres LBA d'un autre niveau** : non mémorisées, relues et réécartées à chaque lancement (pas d'« offres vues » pour LBA, comme avant).
