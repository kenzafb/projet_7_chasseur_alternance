# Phase 5d : Sirene, rapport

Branche `phase-5d-sirene`, 9 octobre 2026, créée depuis `phase-5c-lba` et non depuis `refonte-multiuser` : elle s'appuie sur les suites de la phase 5c (liste des sources, D44 à D48), pas encore dans `refonte-multiuser`. Non poussée, non fusionnée. Lus avant de commencer : `SPEC_SOURCES.md` (sections 0, 4 et 7), `DECISIONS.md`. Rien écrit dans `data/` ni `.env`. Aucun appel réseau dans les tests. L'IA reste coupée et rien de ce qui suit n'en dépend. Pas de changement de schéma.

## Commits

| Commit | Contenu |
|---|---|
| 8564f75 | `scripts/verifier_sirene.py`, `spontanees/parametres_sirene.py`, API Sirene simulée, table INSEE NAF rév. 2 vers NAF 2025 en CSV |
| 411e64f | Correspondance domaine vers NAF (`correspondance_naf.json`, `shared/naf.py`), `NOMENCLATURE_NAF` |
| 6079034 | Filtres du profil (tailles, effectifs inconnus, départements, secteurs), transverses, recherche Sirene réécrite, pas de doublon avec LBA |
| (dernier) | README, décisions D49 à D53, ce rapport |

## 0. À lancer par l'humain : vérification de l'API

Depuis la racine du projet, `INSEE_API_KEY` dans `.env` :

```bash
venv/bin/python scripts/verifier_sirene.py
```

Une soixantaine de requêtes espacées de 2 s (quota de 30 par minute), environ deux minutes. Détail dans `docs/referentiels/insee/verification_api.json` (`--sortie <dossier>` pour un autre emplacement), sans clé. Le script termine par un bloc « À reporter dans spontanees/parametres_sirene.py », seul fichier du code qui dépend de ces réponses. Requête de référence : sièges actifs à Paris, NAF 62.01Z. Il vérifie :
1. **Tranche d'effectif**, sur l'unité légale et sur l'établissement : liste `(11 OR 12)` comparée à la somme des tranches seules, nombre de « NN », trois syntaxes pour les unités sans tranche du tout, part des effectifs non renseignés (par requête, et comptée sur 1000 établissements lus).
2. **Catégorie** : PME, ETI, GE seules et en liste ; essai sur l'établissement ; clause des transverses « 250 et plus OU ETI ou GE ».
3. **Plusieurs codes NAF par requête** : 2 et 10 codes comparés à la somme des codes seuls, puis 30, 60, 120, 250 codes (limite de longueur).
4. **Plusieurs départements** : `(75* OR 92*)` comparé à la somme.
5. **Code NAF 2025** : cinq noms de variable candidats essayés dans une requête, et tous les champs des réponses dont le nom évoque une nomenclature ou la NAF 2025, avec leur présence réelle (le nom vu dans les réponses est signalé même s'il n'était pas parmi les candidats).
6. **Pagination** : `nombre` 1000 et 1001, `debut` 1000 et 20000, trois pages par curseur.

Valeurs prudentes en attendant (D53) : un code NAF et un département par requête (comme avant la phase), « NN » seulement pour les effectifs inconnus, variable NAF 2025 inconnue.

## 1. Correspondance domaine vers NAF (D49)

`shared/referentiels/correspondance_naf.json`, généré à partir des listes de la spec 4.1 et de la table officielle :
- M18 : 18 cœurs, 6 transverses ; C15 : 8 cœurs, 3 transverses ; exclusions 68.32B, 41.10D, 66.19A.
- **Codes NAF 2025 : établis à partir de la table officielle de l'INSEE**, accessible le 9 octobre 2026 (insee.fr/fr/information/8181066, `Correspondances_NAFrev2-NAF2025.xlsx`, édition janvier 2026). Copie des six colonnes utiles dans `docs/referentiels/insee/correspondance_naf_rev2_naf2025.csv` (1223 lignes, 732 codes rév. 2, 746 codes 2025). Aucun code inventé : un test vérifie que chaque cible et chaque code retenu figure dans la table pour ce code.
- Pour chaque code : ses cibles officielles (code, intitulé, type unique ou multiple, contenu commun), les cibles retenues (`retenus_2025`), et pour une correspondance multiple `a_valider` et une note.

Correspondances multiples (point à valider 1) :

| NAF rév. 2 | Cibles officielles | Retenues | Raison |
|---|---|---|---|
| 63.11Z | 60.20H, 60.39Y, 63.10Y | 60.39Y, 63.10Y | 60.20H (médias à la demande) réunit aussi les chaînes de télévision ; seule la diffusion en continu de jeux vidéo y vient de 63.11Z |
| 63.12Z | 60.39Y, 63.91Y | les deux | ne viennent que de 63.11Z et 63.12Z |
| 61.20Z | 61.10Y, 61.90Y | les deux | télécommunications |
| 61.90Z | 61.20Y, 61.90Y | les deux | 61.20Y reçoit aussi une partie de 82.99Z |
| 26.20Z | 26.20Y, 26.40Y | 26.20Y | 26.40Y (électronique grand public) ne reçoit de 26.20Z que les casques de réalité virtuelle |
| 68.31Z | 68.31Y, 68.32H | les deux | immobilier |
| 68.20A | 55.90Y, 68.20G | 68.20G | 55.90Y (autres hébergements) ne reçoit que la location de moins d'un an et réunit l'hébergement touristique |

Cibles uniques qui élargissent la recherche (elles réunissent d'autres codes rév. 2, point à valider 2) : 46.50Y (avec 46.52Z et 46.66Z), 95.10Y (avec 95.12Z), 71.12Y (avec 71.12A et une partie de 74.90A), 68.12Y (avec une partie de 42.99Z). Les exclusions deviennent 68.32G et 66.19G en NAF 2025.

`shared/naf.py` en tire les codes d'un profil dans la nomenclature active. Un code déjà cherché comme cœur n'est pas répété en transverse (64.19Z, 65.11Z, 65.12Z communs à M18 et C15 : une fois). Un grand domaine (« M ») cherche ceux de ses domaines qui ont une correspondance (M18) et compte comme « sans correspondance » pour le reste. Les anciennes listes de `shared/domaines.py` (16 codes M18 dont 74.90B, 7 codes C15 dont 68.32B) disparaissent.

## 2. NOMENCLATURE_NAF (D50)

`shared.config.nomenclature_naf()` : `NAFRev2` jusqu'au 31 décembre 2026, `NAF2025` à partir du 1er janvier 2027 (jour de Paris), relue à chaque recherche ; `NOMENCLATURE_NAF=NAFRev2` ou `NAF2025` dans `.env` pour forcer (valeur inconnue ignorée). Le code envoyé dépend de la nomenclature ; la variable de l'API aussi (`parametres_sirene.VARIABLE_NAF`). Tant que le nom de la variable NAF 2025 n'est pas vérifié, une recherche en NAF 2025 se fait en NAF rév. 2 avec un message : rien ne casse au 1er janvier, mais il faut lancer le script avant (spec 4.3 : avant fin décembre 2026). Les référentiels France Travail (`nafs`, `secteurs_activites`) seront à retélécharger après la bascule.

## 3. Filtres du profil et recherche (D51, D52)

- **Tailles** : celles du profil, converties en tranches INSEE de l'unité légale (moins de 10 : 00 à 03 ; 10 à 49 : 11, 12 ; 50 à 249 : 21, 22, 31 ; 250 à 4999 : 32, 41, 42, 51 ; 5000 et plus : 52, 53) ; option effectifs inconnus : « NN » ajouté. Rien de coché : aucun filtre. Le « au moins 10 salariés » écrit en dur disparaît.
- **Transverses** : `(tranche 250 et plus OU catégorie)`, restreint aux tailles choisies (250 à 4999 : ETI, 5000 et plus : GE) ; si le profil ne choisit aucune taille de 250 salariés et plus, les transverses ne sont pas cherchés (message).
- **Départements** : nouveau choix dans le profil d'alternance (« Départements des candidatures spontanées »), parmi les 8 départements d'Île-de-France ; rien de coché : les 8. Remplace `SIRENE_DEPARTEMENTS` (75, 92, 93, 94).
- **Secteurs** : pour un profil indifférent ou un domaine sans correspondance, les secteurs choisis dans le profil (le champ « secteur de l'employeur » déjà utilisé par France Travail) sont cherchés, toutes leurs sous-classes ; en NAF 2025, toutes les cibles officielles de ces sous-classes. Le texte du profil l'explique. Sans domaine couvert ni secteur : Sirene n'est pas interrogé ; le message de lancement de « Récupérer » le dit, et nomme les domaines sans correspondance.
- **Recherche** : sièges actifs ; une requête par paquet de codes et de départements (`NAF_PAR_REQUETE`, `DEPARTEMENTS_PAR_REQUETE`) ; pagination par curseur ; une recherche en erreur est abandonnée, les autres continuent (clé refusée : arrêt) ; 429 : une nouvelle tentative après 10 s. Logs : nomenclature, nombre de codes par groupe, départements, tailles, nombre de recherches, puis nouvelles entreprises par groupe, entreprises déjà en base retrouvées, requêtes et durée.
- **LBA** : une entreprise déjà en base (même SIRET) n'est pas dupliquée ; Sirene ajoute sa source (D44).

Un défaut corrigé au passage : `main` de la récupération prenait un journal de logs vide pour « pas de journal » (`log_fn or print`).

## Tests

`systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q` : **655 passed** (636 au début de la phase). Chaque commit de thème passe seul. Nouveaux :
- `test_verifier_sirene.py` (4) : valeurs trouvées, autres réponses de l'API (variable NAF 2025 absente, OU limité, syntaxe d'absence refusée), variable vue dans les réponses mais pas essayée, clé absente ou refusée, clé jamais écrite.
- `test_naf.py` (6) : codes NAF 2025 tous présents dans la table officielle et multiples marqués, cœurs, transverses et exclusions en NAF rév. 2 et en NAF 2025, secteurs choisis (indifférent, domaine sans correspondance, grand domaine, division entière), avertissements, bascule au 1er janvier 2027 et `NOMENCLATURE_NAF`.
- `test_sirene.py` (11) : tranches et clauses, absents ajoutés quand la syntaxe sera vérifiée, départements du profil, plan des recherches, NAF 2025 sans puis avec variable, recherche complète selon le profil (taille, inconnus, départements, transverses, exclusions), toutes tailles, pas de doublon avec LBA, pagination par curseur et limite, rien à chercher ou clé absente, erreur isolée.
- `test_domaines.py` : 2 tests Sirene retirés (remplacés par les précédents), avertissement de lancement mis à jour.

API simulée `tests/faux_sirene.py` : établissements filtrés par le sous-ensemble de la syntaxe Lucene employé par le code (ET, OU, valeurs entre parenthèses, préfixe, existence), pagination par curseur, 404 sans résultat ; nom de la variable NAF 2025, nombre de valeurs par OU et syntaxe d'absence réglables. `compileall` et `node --check` propres. Le profil n'a pas été vérifié dans un navigateur dans cette phase.

## Limites

- **Durée tant que le script n'a pas tourné.** Un code et un département par requête : M18 sans taille fait 18 x 8 + 6 x 8 = 192 recherches, au-dessus du quota de 30 par minute (pauses de 10 s sur 429), soit plusieurs minutes. Regrouper codes et départements dépend du script.
- **Unités sans tranche** perdues quand un filtre de taille est appliqué, tant que `ABSENTS_PAR` n'est pas vérifié (le script mesure leur part).
- **SIRET de LBA et sièges de Sirene** : LBA donne le SIRET de l'établissement qui recrute, Sirene les sièges ; une même entreprise peut entrer deux fois si LBA donne un établissement secondaire (point à valider 6).

## Points à valider

1. **Cibles NAF 2025 des correspondances multiples** (tableau de la section 1) : 60.20H, 26.40Y et 55.90Y écartés, les autres gardés.
2. **Cibles uniques qui élargissent** (46.50Y, 95.10Y, 71.12Y, 68.12Y) : gardées telles que la table les donne.
3. **Aucune taille cochée : toutes les tailles**, y compris moins de 10 salariés et effectifs inconnus (même règle que France Travail, D25). Avant la phase, Sirene se limitait à 10 salariés et plus : un profil sans taille reçoit désormais les très petites entreprises. Autre choix : un défaut de 10 salariés et plus pour Sirene seulement.
4. **Aucun département coché : les 8**, alors que l'ancien réglage n'interrogeait que 75, 92, 93, 94.
5. **Secteurs choisis** utilisés seulement pour l'indifférent et les domaines sans correspondance ; pour un domaine couvert, ils ne restreignent pas la recherche Sirene (ils restent un filtre de France Travail).
6. **Dédoublonnage par SIREN** en plus du SIRET, pour ne pas garder un établissement LBA et le siège Sirene de la même entreprise.
7. **Division entière en NAF 2025** : toutes les cibles officielles de ses sous-classes, qui peuvent sortir de la division (la division 68 amène 55.90Y par 68.20A).
8. **Départements pour les entreprises LBA** : le choix du profil ne s'applique qu'à Sirene ; LBA cherche toujours dans toute l'Île-de-France.

## Suite : vérification de l'API et points tranchés

Décisions D54 à D62 de `docs/DECISIONS.md`. Points 1, 2 et 5 validés tels quels ; 3, 4, 6, 7 et 8 mis en œuvre :
- **D54.** Valeurs du script reportées : 120 codes NAF et 8 départements par requête (M18 sans taille : 2 recherches au lieu de 192), variable NAF 2025 vérifiée, syntaxe d'absence de tranche, pagination toujours par curseur (`debut` plafonné à 10000).
- **D55, D56.** NN est une unité non employeuse (documentation des variables Sirene), pas un effectif inconnu : nouvelle taille « Sans salarié » (alternance), non cochée, gardée seulement si elle est cochée ; « 0-0 » de LBA rangé avec elle ; effectif inconnu : tranche absente.
- **D57.** Division en NAF 2025 : cible hors division gardée seulement si l'ancien code n'en a qu'une.
- **D58.** Départements du profil appliqués aux entreprises LBA.
- **D59.** Dédoublonnage par SIREN, dans les deux sens (LBA puis Sirene, Sirene puis LBA).
- **D60, D63.** Migration 0010 : profils d'alternance existants sans choix pré-cochés avec l'ancien réglage (10 salariés et plus pour les tailles des candidatures spontanées ; 75, 92, 93, 94). Les tailles des offres sont un réglage distinct, jamais pré-coché : une petite entreprise qui publie une offre n'est pas écartée.
- **D62.** Nettoyage des adresses exclues déjà en base, à lancer :

```bash
venv/bin/python scripts/nettoyer_emails_exclus.py              # liste seulement
venv/bin/python scripts/nettoyer_emails_exclus.py --appliquer  # écrit en base
```

Avant la recette : `venv/bin/alembic upgrade head` (migrations 0008 à 0010).

Lecture validée (D63) : rien de coché dans les tailles des spontanées veut dire toutes les tailles sauf « sans salarié ». Tests : 660 passed.
