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

## Remesure de l'éligibilité avec le profil job rempli (23 novembre 2026)

v2, ministral-3:3b, moitié test (68 offres), profils relus en base (`audit_exports/banc_test_profils_a_jour.json` : job et stage avec aucun permis, 3 mois d'expérience, aucune certification).

- **Résultats** :
  - éligibilité juste : 72,1 %, comme avant, mais 13 faux éligibles (18 avant) et 6 faux inéligibles (1 avant) ;
  - catégorie exacte : 51,5 %, écart moyen 0,63 rang ;
  - 23,9 s par offre.
- **Faux inéligibles nouveaux** (6) : la règle demandée s'applique, l'annotation ne la suit pas.
  - 5 offres job exigent 1 ou 2 ans d'expérience (`experienceExige` E), pour un profil de 3 mois. Elles avaient été annotées éligibles (« vente en magasin, accepté par le profil »…).
  - 1 offre exige un CACES, absent du profil.
  - À trancher : mettre à jour ces annotations, ou assouplir la règle (par exemple, en job, n'écarter qu'à partir de 2 ans exigés, ou si l'écart dépasse 12 mois).
- **Faux éligibles restants, par cause** (13) :
  - **Permis (3, « Conducteur de bus »)** : v2 extrait « permis C » ; le texte écrit probablement une autre catégorie (D, transport en commun), donc le contrôle contre le texte le rejette. Piste : profil « Aucun permis » et texte qui exige un permis, quelle que soit la catégorie, donne inéligible.
  - **Expérience (2, « Conseiller en gestion de patrimoine »)** : v2 extrait 3 ans ; le texte l'écrit sous une forme que le contrôle ne lit pas (« trois ans », « 3 à 5 ans »). Piste : lire les nombres en lettres et les fourchettes.
  - **Niveau Bac+5 non retenu comme exigé (3)** : stage de fin d'études en école d'ingénieurs, alternance Bac+5 (CRM, architecte logiciel). v2 dit « exigé », mais le contrôle Python (D103) ne voit pas de mot d'exigence à côté et le rend « souhaité » ; le plafond Moyen s'applique, pas l'inéligibilité. Pistes : « stage de fin d'études », « dernière année » valent Bac+5 exigé ; en alternance, comparer le diplôme préparé au niveau visé.
  - **Diplôme préparé trop haut en alternance (1)** : Product Owner ISCOD Bac+4/5 pour un DEUST Bac+2 ; seulement 1 an d'expérience extrait, sous le seuil de 2 ans.
  - **Métier qualifié sans exigence écrite (3)** : frigoriste, technicien CVC, gestion locative. Rien d'explicite à lire ; c'est un jugement de l'annotation. Le champ `qualificationLibelle` (« Ouvrier qualifié », « Technicien ») pourrait servir, si on le décide.
  - **Poste confirmé (1)** : « Responsable commercial » confirmé, rien d'extrait. Piste : étendre au job la règle « poste senior » de l'alternance.

## Remesure après les règles D174 à D179 (23 novembre 2026)

v2, ministral-3:3b, moitié test (68 offres), profils à jour. Annotation corrigée : l'offre job « Magasinier, préparateur de commande polyvalent », qui exige un CACES, est inéligible (point 2).

- **Résultats** :
  - éligibilité juste : 82,4 %, contre 72,1 % avant ces règles et 60,3 % pour v1 ;
  - 10 faux éligibles (13 avant), 2 faux inéligibles (6 avant) ;
  - catégorie exacte : 54,4 % (51,5 % avant), écart moyen 0,60 rang ;
  - 25,6 s par offre.
- **Faux éligibles restants** (10) :
  - **Métiers qualifiés sans exigence écrite (4)** : métallier, frigoriste, technicien CVC, gestion locative. Sans règle, laissés à l'IA (point 8).
  - **Permis (3, « Conducteur de bus »)** : la description stockée (moins de 1 000 caractères) ne contient pas le mot « permis » ; le « permis C » est une invention du modèle. D175 ne s'applique qu'à un permis écrit dans le texte.
  - **Expérience (2, « Conseiller en gestion de patrimoine »)** : le texte n'écrit que « Expérience : Expérience exigée », sans durée ; les 3 ans du modèle ne sont pas dans le texte. Sans durée, la règle job ne s'applique pas.
  - **Poste confirmé (1, « Responsable commercial Clients Directs Ouest »)** : ni le titre ni le texte ne disent « confirmé » (« Débutant accepté ») ; c'est un jugement de l'annotation.
- **Faux inéligibles restants** (2) :
  - « Assistant(e) administratif(ve) polyvalent(e) » : 2 ans exigés pour 3 mois d'expérience, soit 21 mois d'écart, au-delà des 12 de D174. Inéligible selon la règle, éligible selon l'annotation, que tu as choisi de garder.
  - « Adjoint en scolarité » : effet de bord de D177. Les missions citent « Master 1 et Master 2 » (les dossiers des étudiants), et « M2 » vaut Bac+5 exigé. Piste si tu le souhaites : ne retenir « M2 » qu'avec « en », « de », « niveau », « étudiant » ou « préparez » devant.

## Remesure après D180 à D183 (23 novembre 2026)

v2, ministral-3:3b, moitié test (68 offres), profils à jour, annotation « Assistant(e) administratif(ve) polyvalent(e) » corrigée (D181).

- **Résultats** :
  - éligibilité juste : 89,7 % (82,4 % avant ces règles, 72,1 % avant D174, 60,3 % pour v1) ;
  - 7 faux éligibles, aucun faux inéligible ;
  - catégorie exacte : 54,4 %, écart moyen 0,57 rang ;
  - 22,0 s par offre.
- **Les 7 faux éligibles restants** sont ceux que tu as choisi de laisser :
  - 4 métiers qualifiés sans exigence écrite (point 8) ;
  - 2 « Conseiller en gestion de patrimoine » (expérience exigée sans durée, D183) ;
  - 1 « Responsable commercial », débutant accepté (D183).
- « Conducteur de bus » (permis implicite, D182) et « Adjoint en scolarité » (M2 cité sans être exigé, D180) sont maintenant bien classés.
