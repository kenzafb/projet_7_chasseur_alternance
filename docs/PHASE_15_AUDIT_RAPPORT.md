# Phase 15, audit du backend : étape 1, diagnostic

22 novembre 2026, branche `phase-15-audit-backend`. Aucun changement de comportement de l'application : seuls des scripts de mesure (`scripts/audit_*.py`, `scripts/banc_ia/`), ce rapport et une ligne de `.gitignore` (`audit_exports/`). La base a été lue en lecture seule (`mode=ro`) et le `.env` n'a pas été chargé (`CHASSEUR_ENV_FILE=/dev/null`). Les API France Travail, LBA et Sirene n'ont pas été appelées : leurs scripts sont à lancer par toi.

Légende : **vérifié** = reproduit ici sur la base ou le code ; **mesuré le 8 ou le 9 octobre** = déjà dans `docs/referentiels/` ; **à mesurer** = le script donne le chiffre.

## 1. Constats classés par impact

### Offres ou entreprises ratées

1. **Niveau Bac+5 non pris en compte quand le modèle recopie le profil (vérifié, cause principale de B5).** Dans `controler_extraits`, un `niveau_requis` absent du texte est remis à `non_precise`, mais le secours D100 (`niveau_detecte`) ne tourne que si le modèle a répondu `non_precise` lui-même (branche `elif`, `shared/eligibilite.py:152-158`). J'ai lancé `ministral-3:3b` sur les offres #13 et #119, 2 essais à température 0 : il répond `bac+2` (le niveau **du profil**), plus 2,5 mois et « février 2027 » (la période du profil). Les trois valeurs sont rejetées, le niveau tombe à `non_precise`, et il n'y a ni malus ni inéligibilité. #119 (« Vous préparez un diplôme de niveau Bac +5 ») sort donc éligible à 6/10, et #13 à 8/10 (Bien). Détail dans la section 3.
2. **Un niveau marqué « indispensable » par France Travail n'est jamais exigé (vérifié).** `_normaliser_une` écrit « Formation : … Bac+5 et plus ou équivalents (indispensable) ». Les libellés du référentiel `niveauxFormations` contiennent tous « ou équivalent(s) », et ce texte est un marqueur de souhait (`MARQUEURS_SOUHAIT`) : la ligne donne donc `souhaite`. Le champ structuré `formations[].exigence == "E"` est perdu.
3. **Les mots-clés école/CFA archivent de vraies offres d'alternance (vérifié sur des phrases).** `est_ecole_cfa` cherche des sous-chaînes partout dans la description. Résultat `True` pour : « formation au CFA de votre choix », « sur la plateforme e-commerce », « notre studio », « H3 index », « ecole partenaire ». « Groupe IGF » ne correspond jamais (majuscules comparées à un texte en minuscules). C'est presque toute offre d'alternance qui cite son CFA. Volume : `audit_france_travail.py` (alternance, `archivage_ecole_cfa.par_mot`) et `audit_lba.py`.
4. **LBA : `is_delegated` et l'export complet (doc officielle, à mesurer).** L'OpenAPI de LBA (`/api/documentation/json`, version 62a4dd4) indique :
   - `is_delegated` : « true if offer management is delegated to a partner school ». Dans ce cas, `workplace.name`, `siret`, `address` et `apply.phone` sont ceux de l'école. Une offre déléguée affiche donc le nom d'une école, se fait archiver « école/CFA » et reçoit une lettre adressée à l'école.
   - Réponse : le champ peut remplacer les mots-clés **pour LBA**. C'est le signal exact d'une « offre déposée par un organisme de formation », même si l'employeur est réel. France Travail n'a pas d'équivalent : il y faut garder des mots-clés, réécrits en mots entiers.
   - Export `GET /job/v1/export` : « Lists all job opportunities (job postings and companies…) », mis à jour chaque jour à 3 h, 2 appels par minute, même structure que la recherche. La recherche, elle, est limitée : « limited to 150 for each of the three sources… not possible to retrieve all the offers ».
   - Réponse : l'export peut remplacer nos recherches plafonnées à 150 par source (offres et entreprises à fort potentiel). Le script chiffre ce que la collecte rate dans l'export (IDF, codes ROME du profil, hors France Travail).
   - La recherche accepte aussi `departements` (tableau), qu'on n'utilise pas.
5. **France Travail, offres « hors IDF » qui sont en IDF (probable, à mesurer).** Le 8 octobre, 66 932 offres en région 11, mais seulement 64 034 dans les 8 départements : 2 898 (4,3 %) n'ont pas de département. `detecter_zone` exige un libellé « NN - … » et rejette les autres comme « hors IDF », même si `region=11` est envoyé. Le script liste les libellés rejetés.
6. **France Travail, domaines (mesuré le 8 octobre, à confirmer par mode).** L'union des 14 grands domaines donne 56 982 offres sur 66 932 : 9 950 offres (15 %) ne sont trouvées par aucun domaine. Dès qu'un profil choisit des domaines (cas de l'utilisateur 1 : `domaine=M18` en alternance **et en stage**), ces offres ne sont jamais cherchées. Le script en donne des exemples, pour juger si elles comptent.
7. **Stage (mesuré le 9 octobre, à compléter).**
   - `motsCles=stage` ne donnait que 73 offres en IDF, et l'app y ajoute `domaine=M18`. Sur ces 73, 18 (25 %) sont en E2 ou FS et partent par `exclure_alternance`, y compris « Candidature spontanée ALTERNANCE/STAGE ».
   - Le script mesure ce que trouvent « stagiaire », « internship », « intern », « stage de fin d'études », « fin d'études » et « convention de stage » sans le mot « stage ». Il liste les intitulés rejetés par `intitules_stage.txt` et dit si la liste `stage,stagiaire` vaut un OU ou un ET.
8. **LBA, filtre de niveau à égalité stricte (vérifié dans le code).** `filtrer_niveau` ne garde que le niveau égal à celui du profil (ou une offre sans niveau). Le script compte, sur la collecte, ce qu'écarte chaque niveau.
9. **France Travail, découpage au-delà de 3150 (à mesurer).** Le code est cohérent : moitiés à borne partagée, dédoublonnage par `id`, garde-fou, marge de fuseau de 24 h. Le script compare total annoncé, offres distinctes, doublons reçus et tranches au plafond. Contrôle indépendant : les 150 plus récentes de chaque département doivent être dans la collecte.
   - Seul point faible relevé dans le code : une offre sans `id` est indexée par `id(o)` et ne serait jamais dédoublonnée. Le script compte ces cas (`sans_identifiant`).
10. **Sirene (à mesurer).**
    - « Siège uniquement » : le script compte les établissements actifs non sièges d'IDF pour tes codes NAF, puis, pour leurs SIREN, si le siège est hors IDF (entreprises jamais trouvées).
    - Sièges fermés : la requête n'exige que `etatAdministratifUniteLegale:A`, et l'INSEE écrit qu'il existe des « unités légales avec un état administratif actif dont tous les établissements sont fermés » ([actualités Sirene, septembre 2026](https://www.insee.fr/fr/information/9053325)).
    - Effectif : répartition par tranche, NN écartés par défaut (857 sièges sur 1000 à Paris en 62.01Z le 9 octobre), année de l'effectif.
    - Pagination : la plus grosse requête du plan est lue jusqu'au bout, par la classe `Collecte` de l'app puis par une boucle indépendante.
    - Hors périmètre, mais à noter : l'INSEE annonce que `activitePrincipaleNAF25UniteLegale` disparaît au 1er janvier 2027 ; le repli D113 est donc nécessaire.

### Mauvais résultats (pas ratés, mais faux)

11. **Spontanées : les 2 seules entreprises « avec email » ont des adresses fausses, comptées comme validées (vérifié en base).**
    - Base : 420 entreprises, 16 traitées, 2 avec email.
    - #20 France Université Numérique : site retenu par DDG `companyfrance.fr` (un annuaire), adresses `contact@monentreprise.fr`, `info+dpo@companyfrance.fr.nous`, `info+dsa@companyfrance.fr.pour`.
    - #18 Plateforme des données de santé : page `gnius.esante.gouv.fr`, adresses `contact@gerontopole-aura.fr`, `gerald.comtet@i-carelab.org`.
    - Les deux sont dans l'état d'avant la phase 7 (`emails_douteux` absent, `emails_non_valides` faux) : `emails_valides` les considère toutes envoyables. Aucun mail n'est parti (`mail_envoye = 0`).
    - D'autres annuaires choisis par DDG ne sont pas dans `DOMAINES_ANNUAIRES` : `lagazettefrance.fr`, `annonces-legales.liberation.fr`, `pros.informatique.free.fr`.
12. **Scraper (lu dans le code, chiffré par `audit_scraper.py mesure`).**
    - Pas de robots.txt.
    - Pas de JavaScript : `requests` seul.
    - Formulaires de contact ignorés.
    - `fiable` vaut toujours `True`, donc la nouvelle tentative de site (FIX 11) ne sert jamais.
    - Erreurs HTTP avalées sans trace.
    - Les adresses écartées par les règles et les pages visitées ne sont pas enregistrées.
    - Le texte de contexte retire `header` et `footer`, là où se trouvent souvent les adresses : l'IA les juge alors sans contexte.
    - Un TLD comme « .pour » ou « .nous » passe (`FAUX_TLDS` incomplet).
    - Le mot « informatique » est écrit en dur dans les requêtes DDG.
    - Jusqu'à une trentaine de requêtes par site, avec 0,6 à 1,5 s de pause entre chacune.

### IA, autres causes de notes trop hautes (vérifié)

13. Le malus « souhaité » vaut au plus 2 points : une note de 10 devient 8 (Bien).
14. Le prompt dit au modèle : « Le niveau, la durée et les dates sont vérifiés à part : ne les compte pas dans la note » (`offres/analyse.py:41`).
15. Le modèle ne voit que les 2000 premiers caractères (`IA_LONGUEUR_DESCRIPTION`). Dans #119, les indices de niveau sont aux caractères 2070 et 2095 : seul Python les lit.
16. Détection du niveau :
    - « Bac+4/5 » donne bac+4 et « Master… après votre bac » donne bac, car c'est l'indice le plus bas qui gagne ;
    - « 50 m2 » donne bac+5 ;
    - « Prérequis » contient « requis » et compte comme marqueur d'exigence (#119) ;
    - « stage de fin d'études » n'est pas un indice.

## 2. Scripts à lancer (dans cet ordre)

Tous en lecture seule. Ils écrivent dans `audit_exports/`, qui est ignoré par git.

```bash
# A1 France Travail, critères de tes profils (quelques minutes par mode)
venv/bin/python scripts/audit_france_travail.py --user 1

# A2 La Bonne Alternance, export complet compris (fichier de plusieurs dizaines de Mo)
venv/bin/python scripts/audit_lba.py --user 1

# A3 Sirene (quota de 30 requêtes par minute : 5 à 10 min par mode)
venv/bin/python scripts/audit_sirene.py --user 1 --mode alternance
venv/bin/python scripts/audit_sirene.py --user 1 --mode stage

# C2 scraper, sur l'échantillon de 40 déjà exporté (30 s à 1 min par site)
venv/bin/python scripts/audit_scraper.py mesure

# B5 trace avec la vraie réponse du modèle (Ollama démarré)
venv/bin/python scripts/banc_ia/tracer_niveau.py --ids 13,119,12 --avec-ia
```

Une fois les annotations faites (format : `scripts/banc_ia/README.md`) :

```bash
venv/bin/python scripts/banc_ia/banc_analyse.py audit_exports/banc_reference.json --essais 3 --temperatures 0,0.1
venv/bin/python scripts/banc_ia/banc_lettre.py  audit_exports/banc_reference.json --max 10
venv/bin/python scripts/banc_ia/banc_emails.py  audit_exports/banc_emails_reference.json
```

Déjà générés ici, en lecture seule :
- `banc_offres_a_annoter.json` : 137 offres, dont 10 alternance, 100 job non analysées et 27 stage ;
- `banc_emails_a_annoter.json` : 9 adresses ;
- `banc_lettres.json` ;
- `scraper_echantillon.json` : 40 entreprises, dont 2 avec email, 14 traitées sans email et 24 pas encore traitées ;
- `trace_niveau.json` ;
- les paramètres France Travail de l'utilisateur 1.

Les trois bancs ont été essayés ici avec `ministral-3:3b` sur un jeu de test aux annotations factices. Ils tournent de bout en bout, mais ces sorties ne sont pas des résultats.

## 3. Diagnostic B5 : « stage ingénieur Bac+5 bien noté »

Profil stage de l'utilisateur 1 : Bac+2 (« BUT Informatique, 2e année en cours »), lu dans le niveau d'études.

Chemin de la décision :
1. Le modèle reçoit au plus 2000 caractères de la description.
2. Il rend une note et recopie un `niveau_requis`. On lui demande de ne pas compter le niveau dans la note.
3. `controler_extraits` vérifie ce niveau contre le texte (D98) et ne lance le secours D100 que si le modèle a répondu `non_precise`.
4. L'exigence vient du texte (D103) : `exige` seulement avec un marqueur explicite sans marqueur de souhait proche.
5. `exige` rend l'offre inéligible (note plafonnée à 3). `souhaite` retire 1 point pour deux crans d'écart, 2 au-delà.

Chaque offre ci-dessous a été rejouée avec les règles actuelles (`tracer_niveau.py`), pour chaque niveau que le modèle peut répondre.

| Offre | Indices lus par Python | Modèle répond `bac+5` | Modèle répond `non_precise` | Modèle répond `bac+2` (vu réellement) |
|---|---|---|---|---|
| #13 Stage Développeur Logiciel, en base 8 | « école d'ingénieur, master ou équivalent » : bac+5, souhaité (« ou équivalent ») | 10 → 8, Bien | 10 → 8, Bien (D100) | rejeté, `non_precise`, **10, Très bien** |
| #119 Développeur & Fiabilisation de données, en base 6 | « diplôme de niveau Bac +5 » au caractère 2070, après la coupe : invisible pour le modèle ; « Prérequis » lu comme exigence | inéligible, 3 | inéligible, 3 (D100) | rejeté, `non_precise`, **éligible, note du modèle gardée** (6 réellement) |
| #12 Ingénieur(e) Données R&D, en base inéligible (avant D103) | « dernière année d'école d'ingénieurs ou Master 2 (Bac+5) », sans marqueur | 10 → 8, Bien | 10 → 8, Bien | rejeté, **10** |

Pourquoi la note reste haute, par ordre de poids :
1. **Un niveau faux mais rejeté efface le niveau.** Le petit modèle recopie le niveau du profil (vu sur les 4 réponses réelles), ce qui coupe le secours D100.
2. **Sans marqueur explicite, Bac+5 n'est que « souhaité ».** D103 : -2 au plus, donc une offre notée 10 finit à 8. Une école d'ingénieur ou un Master 2 est en pratique inaccessible à un BUT2, mais aucune règle ne le dit.
3. **Le modèle ne pénalise pas le niveau dans sa note,** puisque le prompt le lui interdit.
4. Selon l'offre : indice au-delà des 2000 caractères ; « ou équivalents » de France Travail qui désarme « indispensable » ; « Bac+4/5 » lu bac+4 (-1 seulement).

Le titre « Stage Ingénieur… » n'est volontairement jamais un indice (D98). Les offres #14 à #17 (« Ingénieur/e … Défense », aucun niveau dans le texte) ont été notées 3 pour le domaine, pas pour le niveau.

## 4. Fichiers à me transmettre

- Après les scripts A et C :
  - `audit_exports/audit_france_travail_{alternance,job,stage}.json`
  - `audit_lba.json` (pas `lba_export_brut.json`, trop gros)
  - `audit_sirene_{alternance,stage}.json`
  - `scraper_mesure.json`
  - `emails_candidats.json`
  - `trace_niveau.json` (après `--avec-ia`)
- Pour l'annotation :
  - `banc_offres_a_annoter.json`, à rendre sous `banc_reference.json`
  - `banc_emails_a_annoter.json`, complété par `emails_candidats.json`, à rendre sous `banc_emails_reference.json`
- Les exports contiennent les descriptions des offres et les profils, sans identité (nom, email, téléphone, liens et pièces jointes retirés).
