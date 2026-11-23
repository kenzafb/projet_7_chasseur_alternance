# Phase 15, étape 3 : scraper, éligibilité par Python, prompt v2

Branche `phase-15-audit-backend`. Mesures lourdes lancées une par une, jamais deux à la fois. Bancs : seules les variables `IA_*` du `.env` lues. `data/` lu en lecture seule seulement (garde-fou D164 actif). 1428 tests passent sous `MemoryMax=2G`.

## A. Scraper : retrouver les sites (D166 à D168, D171, D172)

Méthode :
- 40 entreprises de l'échantillon, comparées à `scraper_reference.json` (27 entreprises tranchées).
- Chaque groupe mesuré sur son propre commit (`git worktree`), dans l'ordre.
- Depuis le groupe 1, les résultats de recherche web sont gardés en cache et rejoués à l'identique (`--cache-recherche`) : les écarts entre groupes viennent du code, pas du moteur, qui varie d'un passage à l'autre et refuse des requêtes.
- France Université Numérique : `france-universite-numerique.fr` affiche leur SIRET. Selon ta règle, il compte comme juste, mais il n'est pas encore dans la référence ; les chiffres ci-dessous le comptent faux, sauf mention.
- Temps : moyenne sur les 40 entreprises.

**Avant l'étape 2 (ancien scraper)**
- Sites : 12 justes, 12 faux, 3 non trouvés.
- Emails : 4 validés et 43 douteux, chez 20 entreprises (en majorité fausses).
- 61 s par entreprise.

**Fin de l'étape 2**
- Sites : 12 justes, 2 faux, 13 non trouvés.
- Emails : 1 validé, 10 douteux, chez 6 entreprises.
- 66,7 s par entreprise.

**Groupe 1 : A1 (sources sûres) et A2 (autres noms)**
- Sites : 11 justes, 4 faux, 12 non trouvés.
- Emails : 2 validés, 9 douteux, chez 6 entreprises.
- 82,0 s par entreprise.
- A1 : l'export LBA n'a de site que sur 328 offres et aucun recruteur (140 SIREN), aucun dans l'échantillon. Effet nul ici.
- A2 : sigle, dénominations usuelles et enseignes de Sirene. TIDF n'a ni sigle ni enseigne dans Sirene, donc « Toshiba Île-de-France » reste introuvable par ce moyen.
- Faux nouveaux : siteindices.com et un blog home.blog (ajoutés aux domaines interdits), alliancesante.net, fermat.app.

**Groupe 2 : + A3 (domaines devinés)**
- Sites : 12 justes, 7 faux, 8 non trouvés.
- Emails : 2 validés, 15 douteux, chez 8 entreprises.
- 35,8 s par entreprise (deux fois plus rapide).
- 14 sites viennent d'un domaine deviné.
- 5 des 7 faux étaient en fait le bon site atteint par redirection (cartadis.fr vers cartadis.com, prodware.fr vers prodwaregroup.com, theatredelaville.fr vers theatredelaville-paris.com, altizem.fr vers altizem.com). Le site retenu n'était pas le domaine d'arrivée et les mentions légales n'étaient pas lues. Corrigé : la redirection est suivie (complément de D168).

**Groupe 3 : + A4 (recherche : 8 candidats, interdits écartés avant de compter, requête sans ville, liste noire complétée), A5 (SIREN obligatoire pour un nom d'un seul mot) et le correctif de redirection**
- Sites : 12 justes, 2 faux, 13 non trouvés. Avec ta règle du SIRET : 13 justes, 1 faux (alliancesante.net).
- Emails : 2 validés, 8 douteux, chez 7 entreprises.
- 66,0 s par entreprise.
- A5 écarte Fermat et Bellon, mais fait perdre 7 sites justes : WeTradeLocal, AMUE, Theatre de la Ville, Degetel, Cartadis, Lexmark, Murex. Leurs mentions légales n'affichent ni SIREN, ni RCS, ni TVA (vérifié à la main sur cartadis.com, degetel.com, wetradelocal.io et theatredelaville-paris.com).

**Même groupe 3, sans A5** (comparaison, sur les mêmes recherches)
- Sites : 18 justes, 4 faux, 5 non trouvés. Avec ta règle du SIRET : 19 justes, 3 faux (Alliance Santé, Bellon, Fermat sur un site Mobirise ; mobirisesite.com est désormais interdit).
- Emails : 4 validés, 19 douteux, chez 12 entreprises.
- 36,4 s par entreprise.

**Groupe 4 : A5 assouplie (D173)** : nom d'un seul mot accepté sans SIREN si le domaine principal est exactement le nom et que l'accueil, le contact ou les mentions légales portent le code postal ou la voie d'une adresse Sirene.
- Sites : 14 justes, 2 faux, 11 non trouvés. Avec ta règle du SIRET : 15 justes, 1 faux (alliancesante.net).
- Emails : 3 validés, 13 douteux, chez 9 entreprises.
- 42,2 s par entreprise.
- Retrouvés par l'adresse :
  - Degetel (code postal 75015 sur l'accueil) ;
  - Cartadis (94120 sur l'accueil) ;
  - Regy (« boulevard de Grenelle » sur l'accueil ; non tranché dans la référence).
- Fermat et Bellon ne reviennent pas.
- Toujours manqués :
  - Theatre de la Ville et AMUE : domaine différent du nom ;
  - WeTradeLocal, Lexmark, Murex : ni code postal ni voie de leur adresse sur les pages lues.

**À trancher (avant D173)**
- A5 telle que demandée coûte 7 sites justes pour 2 faux évités.
- Choix possibles :
  - garder A5 (précision maximale, 12 ou 13 justes) ;
  - la retirer (18 ou 19 justes, 3 ou 4 faux) ;
  - l'assouplir, avec une règle à mesurer, par exemple : nom d'un seul mot accepté si le domaine est exactement ce nom et que le titre le porte. Cela garde Cartadis, Degetel et Murex, mais aussi fermat.app et bellon.com.
- A5 est en place (`MOTS_DISTINCTIFS_MIN = 2`) ; `audit_scraper.py mesure --nom-un-mot` mesure sans elle.

**Emails gardés** : la validation (D162) reste stricte. Les adresses validées d'office sont rares parce que la plupart des sites vérifiés n'ont qu'un formulaire ou des adresses nominatives : ces douteuses passent à l'IA dans l'application.

## B. Éligibilité par Python à partir des champs structurés (D169)

- **Champs France Travail** : permis, expérience exigée, formations et compétences avec leur exigence, ajoutés en lignes structurées à la fin de la description (jamais coupées).
  - Vus en base : les libellés d'expérience (« 2 An(s) », « 6 Mois », « Débutant accepté », « Expérience exigée »), les formations et compétences avec « (indispensable) », et « CASES 1-3-5 », coquille de CACES.
  - Les noms et valeurs exacts de `permis`, `experienceExige` et `qualification`, ainsi que le nombre d'offres avec `entreprise.url`, restent à confirmer par `scripts/audit_champs_france_travail.py` (clé France Travail).
- **Champs LBA** : les fourchettes d'expérience de `access_conditions` (« 3-5 ans ») sont prises en compte. Les textes génériques du métier ne le sont pas (1 897 offres sur 12 507 en ont).
- **Profil** : permis en cases (avec « Aucun permis »), expérience totale en mois, certifications en étiquettes avec suggestions. Communs aux trois modes, copiables, rangés dans `profils.recherche` (pas de migration).
- **Règles** :
  - permis exigé absent ;
  - formation exigée au-dessus du profil ;
  - diplôme d'État exigé (sauf en alternance) ;
  - expérience exigée supérieure à celle du profil en job ;
  - deux ans ou plus en alternance ;
  - certification exigée absente.

  Un permis ou une expérience non renseignés dans le profil ne bloquent pas.
- **Mesure** (moitié test, 68 offres) :
  - avec les lignes structurées seules (v1) : 3 offres rendues inéligibles, 2 à raison (formation exigée), 1 à tort (certification) ;
  - avec les exigences extraites du texte par v2 : 11 offres rendues inéligibles, 10 à raison (6 certifications, 3 formations ou diplômes, 1 expérience), 1 à tort.
- **Pourquoi l'effet est encore limité** :
  - les offres du jeu de référence datent d'avant B et n'ont pas les lignes de permis ni d'expérience exigée ;
  - le profil de référence n'a ni permis ni expérience renseignés.

  L'effet complet viendra des nouvelles offres et d'un profil rempli.

**Audit des champs France Travail** (`audit_champs_france_travail.json`, 600 offres job, 56 alternance, 140 stage) :
- `experienceExige` ne vaut que D (débutant accepté) ou E (exigée), jamais S : 30 % des offres job exigent de l'expérience (180 sur 600), surtout « N An(s) ».
- `permis` est presque toujours absent (1 offre stage sur 796, souhaité) : le permis se lit surtout dans le texte libre, par l'extraction de v2.
- Formations et compétences exigées sont rares (2 formations et 4 compétences exigées en job), et aucune certification n'est exigée dans les champs structurés.
- `entreprise.url` est absent des 796 offres (l'API ne donne que nom, entrepriseAdaptee, logo, description) : la source « site donné par une offre France Travail » (D166) ne sert pas.

## C. Prompt d'analyse v2 (D170)

- **Appel 1, extraction** : il ne voit pas le profil et lit jusqu'à 8 000 caractères. Il donne niveau et exigence, durée, date, alternance seulement, expérience, permis, certifications et diplôme d'État exigés. Python contrôle chaque valeur contre le texte, puis applique les règles de B.
- **Appel 2, jugement** : un mot (Très bien, Bien, Moyen, Faible, Hors sujet), chacun défini, par un arbre ordonné : hors sujet ou non, puis missions, puis réserves.
- **Python** convertit le mot en note (9, 7, 5, 3, 1), plafonne (niveau souhaité deux crans ou plus au-dessus du profil : Moyen au plus) et ne garde « Hors sujet » que si le modèle cite une phrase d'un champ d'exclusion du profil (sinon Faible).
- v2 est désormais le prompt de l'application (`IA_VERSION_ANALYSE=v2` par défaut, `v1` pour revenir).

## D. Méthode et mesure finale

- **Découpage** : deux moitiés fixes du jeu annoté (graine 15, réparties par mode). Réglage : 69 offres (5 alternance, 50 job, 14 stage). Test : 68 offres (5, 50, 13).
- **Réglage de v2**, sur la moitié réglage seulement, avec ministral-3:3b, en 3 passages :
  - éligibilité : 87 % aux trois passages ;
  - catégorie exacte : 26 %, puis 36 %, puis 49 % ;
  - écart moyen : 1,14, puis 0,88, puis 0,61 rang.
- **Mesure finale** sur la moitié test, jamais regardée avant, 1 essai, température 0 :
  - **v1, ministral-3:3b** :
    - éligibilité 60,3 % (26 faux éligibles, 1 faux inéligible), niveau 86,8 %, aucun faux positif de niveau ;
    - catégorie exacte 32,4 %, écart moyen 0,76 rang, 4 réponses à 2 rangs ou plus ;
    - 23,3 s par offre.
  - **v2, ministral-3:3b** :
    - éligibilité 72,1 % (18 faux éligibles, 1 faux inéligible), niveau 89,7 %, aucun faux positif de niveau ;
    - catégorie exacte 51,5 %, écart moyen 0,63 rang, 8 réponses à 2 rangs ou plus ;
    - 23,8 s par offre.
  - **v2, ministral-3:8b** :
    - éligibilité 70,6 % (19 faux éligibles, 1 faux inéligible), niveau 86,8 %, aucun faux positif de niveau ;
    - catégorie exacte 55,9 %, écart moyen 0,56 rang, 6 réponses à 2 rangs ou plus ;
    - 50,2 s par offre.
  - Aucune réponse invalide.
- **Lecture** :
  - v2 gagne nettement sur v1, pour le même temps ;
  - le 8b gagne un peu en catégorie, pas en éligibilité, et double le temps : le 3b reste le modèle d'analyse ;
  - v2 fait plus d'erreurs à 2 rangs (8 contre 4), mais beaucoup plus de réponses justes.

## À lancer de ton côté

- `venv/bin/python scripts/audit_champs_france_travail.py --user 1 --max 600` : noms et valeurs réels des champs France Travail ; renvoie `audit_exports/audit_champs_france_travail.json`.
- Dans Mon profil, partie « Ton parcours » : permis, expérience en mois et certifications, pour que les règles de B s'appliquent pleinement.
