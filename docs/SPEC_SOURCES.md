# Spécification des sources : France Travail, La Bonne Alternance, Sirene

Rédigée le 8 octobre 2026 à partir des référentiels France Travail téléchargés le même jour (docs/referentiels/france_travail/), de la documentation publique de LBA et de Sirene. Décisions validées par l'humain sauf mention « proposition ».

Contexte : l'IA est coupée (ANALYSE_IA=false). Rien dans ce document ne dépend de l'IA.

## 0. Principes

- Les listes de codes viennent des référentiels officiels, jamais d'une liste écrite de mémoire. Les référentiels sont versionnés dans le dépôt avec leur date de téléchargement.
- Une même nomenclature sert partout quand c'est possible : les « secteurs d'activité » de France Travail (88 codes à 2 chiffres) sont exactement les divisions NAF utilisées par Sirene. Un seul filtre « secteur » sert donc aux offres et aux candidatures spontanées.
- Les libellés des référentiels contiennent parfois des restes de code (exemple : `'Fabrication industrielle de pain et de pâtisserie fraîche');`). Ils sont nettoyés avant affichage (apostrophes et `');` parasites retirés).
- Tout résultat trop volumineux pour une seule requête est découpé automatiquement, jamais tronqué en silence.

## 1. Modèle des domaines

### 1.1 Nomenclature (France Travail, reprise par LBA)

Trois niveaux emboîtés :
- 14 grands domaines, une lettre : A Agriculture et pêche, espaces naturels et espaces verts, soins aux animaux ; B Arts et façonnage d'ouvrages d'art ; C Banque, assurance, immobilier ; D Commerce, vente et grande distribution ; E Communication, média et multimédia ; F Construction, bâtiment et travaux publics ; G Hôtellerie-restauration, tourisme, loisirs et animation ; H Industrie ; I Installation et maintenance ; J Santé ; K Services à la personne et à la collectivité ; L Spectacle ; M Support à l'entreprise ; N Transport et logistique.
- 110 domaines, 3 caractères (référentiel `domaines.json`) : `M18` Systèmes d'information et de télécommunication, `C15` Immobilier, etc.
- environ 1900 métiers, 5 caractères (référentiel `metiers.json`), dont le code commence par celui du domaine : `M1805` appartient à `M18`.

France Travail classe une offre selon le métier, pas selon le secteur de l'employeur : chercher `M18` trouve aussi les postes informatiques des banques, hôpitaux, etc.

### 1.2 Dans le profil

- Choix multiple de grands domaines et de domaines, ou case « indifférent ». Stockage en codes (`["M18"]`, `["C"]`, `[]` pour indifférent).
- Interface : grands domaines d'abord, possibilité d'affiner par domaine.
- Remplace `shared/domaines.py` et ses domaines écrits à la main. Migration des profils existants : `informatique` devient `M18`, `immobilier` devient `C15`.

## 2. France Travail (API Offres d'emploi v2)

### 2.1 Filtres par mode

| | Alternance | Job | Stage |
|---|---|---|---|
| Contrat | natureContrat `E2` (apprentissage) et `FS` (professionnalisation) | typeContrat `CDD`, `MIS`, `SAI` | aucune recherche France Travail : le stage n'existe dans aucune nature ni aucun type de contrat |
| Qualification | aucun filtre | aucun filtre (le filtre `qualification=0` actuel est retiré : il écartait les offres `X`, 61 % du total en IDF) | |
| Domaine | domaines du profil, ou aucun filtre si indifférent | idem, indifférent par défaut | |
| Options | secteur employeur | secteur employeur ; thèmes `13` (saisonniers, jobs d'été) et `17` (sans diplôme ni expérience), décochés par défaut car renseignés volontairement par l'employeur | |

Répartition observée en Île-de-France le 8 octobre 2026 : 66 915 offres au total, 2541 `E2`, 772 `FS`, 10 800 `CDD`, 10 795 `MIS`, 47 `SAI`.

### 2.2 Plafond et découpage

Mesuré le 8 octobre 2026 : 150 offres maximum par page (`range` de 150 éléments), début de plage au plus 3000, donc au plus 3150 offres par requête. Au-delà : erreur 400.

Découpage adaptatif :
1. une première page donne le total (en-tête `Content-Range`, par exemple `offres 0-149/66915`) ;
2. si le total dépasse 3150, la requête est redécoupée par département d'Île-de-France (75, 77, 78, 91, 92, 93, 94, 95) ;
3. si un département dépasse encore, redécoupage par domaine, puis par fenêtre de publication (`minCreationDate`, `maxCreationDate`) ;
4. dédoublonnage par identifiant d'offre.

Même l'alternance tous domaines confondus dépasse le plafond en IDF (3313 offres).

### 2.3 Taille d'entreprise

L'API ne filtre pas sur la taille dans la recherche. Les offres contiennent en général une tranche d'effectif de l'établissement : filtre appliqué après récupération, avec option « garder les offres sans information ».

## 3. La Bonne Alternance (mode alternance uniquement)

- Deux types de résultats : des offres, et des entreprises sans offre publiée mais repérées comme ayant un fort potentiel d'embauche d'alternants. Ces entreprises alimentent la base des candidatures spontanées du mode alternance (source `lba`), en priorité sur les entreprises trouvées via Sirene.
- Critères : codes métiers (déduits automatiquement des domaines du profil via `metiers.json`, par lots de 20 comme aujourd'hui), géolocalisation et rayon, niveau de diplôme (depuis le niveau visé du profil), RNCP.
- Plafond : 150 résultats par source, 450 au total. Découpage géographique : plusieurs centres répartis sur l'IDF avec un rayon réduit, plutôt qu'un seul cercle de 60 km autour de Paris.
- Les offres déjà relayées depuis France Travail restent exclues (comme aujourd'hui).
- Usage gratuit et réservé aux usages non lucratifs : toute revente ou facturation d'accès est interdite. À garder en tête si l'app devient payante.
- Proposition, hors périmètre immédiat : LBA propose une API qui transmet directement une candidature (CV, lettre facultative) au recruteur, sans passer par le scraper ni par Gmail. À étudier dans une phase dédiée.

## 4. Sirene (candidatures spontanées)

### 4.1 Correspondance domaine vers secteurs NAF

Principe des secteurs cœurs et transverses :
- secteurs cœurs : le métier est l'activité de l'entreprise, toutes tailles ;
- secteurs transverses : le métier existe comme service interne, seulement pour les entreprises dont l'unité légale compte au moins 250 salariés (tranche d'effectif de l'unité légale, ou catégorie ETI ou GE). La taille se lit sur l'unité légale et non sur l'établissement : une agence bancaire de 5 personnes appartient à un groupe de plusieurs milliers.

`M18` (informatique)
- Cœurs : 62.01Z, 62.02A, 62.02B, 62.03Z, 62.09Z, 63.11Z, 63.12Z, 58.21Z, 58.29A, 58.29B, 58.29C, 61.10Z, 61.20Z, 61.30Z, 61.90Z, 26.20Z, 46.51Z, 95.11Z.
- Transverses (250 salariés et plus) : 64.19Z, 65.11Z, 65.12Z, 70.10Z, 70.22Z, 71.12B.

`C15` (immobilier)
- Cœurs : 68.31Z, 68.32A, 68.20A, 68.20B, 68.10Z, 41.10A, 41.10B, 41.10C.
- Transverses (250 salariés et plus) : 64.19Z, 65.11Z, 65.12Z.

Exclusions systématiques, tous domaines : codes « supports juridiques » 68.32B, 41.10D, 66.19A (sociétés sans salarié).

Autres domaines et « indifférent » : l'utilisateur choisit directement des secteurs parmi les 88 divisions. Les correspondances soignées sont ajoutées au fur et à mesure des domaines réellement utilisés.

La correspondance est un fichier de données versionné (par exemple `shared/referentiels/correspondance_naf.json`), pas du code.

### 4.2 Filtres

- Établissements sièges, actifs (comme aujourd'hui).
- Localisation : départements d'IDF à choix multiple, option par commune.
- Taille, choix multiple dans l'interface, converti en tranches INSEE :
  - moins de 10 : 00, 01, 02, 03 (avec l'avertissement « moins de chances d'accueillir un alternant »)
  - 10 à 49 : 11, 12
  - 50 à 249 : 21, 22, 31
  - 250 à 4999 : 32, 41, 42, 51
  - 5000 et plus : 52, 53
  - option « inclure les effectifs inconnus » (NN ou absent) : l'effectif Sirene n'est pas toujours renseigné et n'est mis à jour qu'une fois par an.
- Remplace le « au moins 10 salariés » écrit en dur.

### 4.3 Bascule NAF 2025 au 1er janvier 2027

Le décret 2025-736 fixe l'entrée en vigueur de la NAF 2025 au 1er janvier 2027 : à cette date, tous les codes APE de Sirene changent. Pendant 2026, Sirene affiche les deux codes.
- La correspondance de 4.1 stocke pour chaque entrée le code NAF rév. 2 et le code NAF 2025, établi à partir de la table de correspondance officielle de l'INSEE (insee.fr/fr/information/8181066).
- Le code utilisé dans les requêtes dépend d'une variable de configuration (NOMENCLATURE_NAF) dont la valeur par défaut bascule automatiquement au 1er janvier 2027.
- Les référentiels France Travail (`nafs`, `secteursActivites`) seront à retélécharger après la bascule.
- À terminer avant fin décembre 2026.

## 5. Champs de profil concernés

Domaines (ou indifférent), secteurs employeur (option), tailles d'entreprise et option effectif inconnu, départements et communes, thèmes (mode job), niveau de diplôme visé (LBA).

## 6. Découpage de la mise en œuvre

- 5b : modèle des domaines, référentiels versionnés, France Travail (filtres par mode, découpage adaptatif, taille après récupération).
- 5c : LBA (codes métiers dérivés, niveau de diplôme, découpage géographique, entreprises à fort potentiel vers les spontanées).
- 5d : Sirene (correspondance cœurs et transverses, filtres taille et localisation, bascule NAF 2025).

Hors périmètre de ces phases : mode stage complet, URL par mode, base d'entreprises partagée entre utilisateurs, API de candidature LBA.

## 7. Points à vérifier sur la vraie API

Le développement se fait sans réseau ; ces points sont vérifiés par un script lancé par l'humain avant ou pendant chaque phase :
- France Travail : nom exact du paramètre de domaine, acceptation de plusieurs valeurs séparées par des virgules pour `natureContrat` et `domaine` (sinon une requête par valeur), nom et présence du champ de tranche d'effectif dans les offres.
- LBA : paramètres exacts (codes métiers, niveau de diplôme, rayon), structure des entreprises à fort potentiel.
- Sirene : syntaxe des filtres de tranche d'effectif et de catégorie d'entreprise, nom de la variable du code NAF 2025 pendant la transition.
