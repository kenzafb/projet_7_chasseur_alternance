# Phase 15, étape 2 : corrections des sources et du scraper

Branche `phase-15-audit-backend`. Rien dans `.env` ; `data/` lu en lecture seule seulement. Une seule écriture accidentelle (un fichier de test de 463 octets, supprimé aussitôt), qui a donné le garde-fou D164. Migration 0017, acceptée et lancée par l'utilisatrice. Tests sous `MemoryMax=2G` : 1390 passés.

## Mesures avant / après, point par point

### 1. France Travail, stage (D152)
- Avant : `motsCles=stage` et domaine M18 donnaient 9 offres gardées.
- Après : une requête « stage » et une « stagiaire », sans domaine, réunies et dédoublonnées, puis le même filtre d'intitulé. Résultat : 102 offres gardées, mesurées par l'utilisatrice.
- Reste vu : « Juriste Stagiaire dans le domaine… » est rejeté par `designe_un_stage`, aucune règle ne prévoyant « stagiaire » après le métier. Laissé tel quel, comme demandé.

### 2. France Travail, lieu « Île-de-France » sans département (D153)
- Avant : 680 offres job sur 19 719 (3,4 %) étaient rejetées comme hors IDF.
- Après : les 680 sont gardées, en zone « Île-de-France (non précisé) », filtrable dans la page Offres.

### 3. La Bonne Alternance et écoles (D154 à D156, D158, D163)
- **Niveau visé ± 1** : de 13 à 23 offres pour le profil Bac+2 (+10, toutes de niveau 6), marquées « niveau différent ». Les 10 exemples sont dans D154.
- **Offres déléguées** (`is_delegated`) : 456 en IDF, dont 337 (73,9 %) étaient archivées. Aucune ne l'est maintenant : elles sont marquées « Offre déposée par un organisme de formation » et filtrables.
- **Mots-clés école/CFA** : 62,1 % des offres LBA d'IDF étaient archivées, 0,1 % maintenant. En France Travail, ISCOD et Scholia restent écartés.
- **CAPIVISION** : marquée comme organisme de formation, jamais archivée.
- **Entreprises à fort potentiel** (D163) : 2 933 par la recherche par cercles, 3 888 par l'export, soit 955 en plus et aucune en moins. Elles viennent désormais de l'export, lu en flux, filtré sur l'IDF et stocké en fichier compact, rafraîchi au plus une fois par semaine.

### 4. Sirene (D159)
- Avant : sièges seulement. Sur 3 000 entreprises ayant un établissement non siège en IDF, 2 999 avaient leur siège hors d'IDF et n'étaient jamais trouvées.
- Après : établissements actifs d'IDF, une entrée par SIREN. Gain mesuré par l'utilisatrice : +711 entreprises cœurs et +548 transverses.
- Catégorie juridique enregistrée ; les administrations (7xxx) sont comptées, pas exclues.

### 5 à 7. Scraper et emails (D160 à D162, D165)
Mesure sur les 40 entreprises de l'échantillon, comparée à `scraper_reference.json` (27 tranchées). Les entreprises 28 à 40 ont été remesurées : au premier passage, la recherche web était en panne sans le dire, défaut corrigé.

**Sites, sur les 27 tranchés :**
- Justes : 12 avant, 12 après.
- Faux : 12 avant, 2 après.
  - Bellon SA → `fondationpierrebellon.org` (nom dans le titre).
  - Fermat → `olympic.fermat.edu.vn` (nom dans le titre).
- Non trouvés : 3 avant, 13 après. Cinq étaient justes avant, avec l'ancienne recherche : The Body Shop, Prodware, Puce et Plume, Cartadis, Murex.
  - Cause principale : le domaine officiel n'est jamais parmi les candidats essayés. Les 4 places de candidats sont prises par des pages tierces qui citent le nom (doctrine.fr, jobted, restaurantguru, usinenouvelle, infobel, xerfi, fusacq, clutch…), toutes refusées à la vérification.
  - Puce et Plume, CASD : aucun candidat à ce passage. Ils avaient été vérifiés à un passage précédent (SIRET dans les mentions légales).
  - Les résultats de la recherche varient d'un passage à l'autre : Neurones a été manqué à un passage, trouvé à un autre.
- Plus aucun annuaire ni agrégateur retenu. Avant : companyfrance, gnius.esante, centreservices, supinterim, lagazettefrance, e-pro, flamingtext…

**Emails gardés par entreprise** (règles seules, IA coupée pendant la mesure) :
- Avant : 47 adresses chez 20 entreprises, en majorité fausses (annuaires, autres organismes, `contact@monentreprise.fr`…).
- Après, validées d'office : 1 (`drh@degetel.com`).
- Après, douteuses, à trancher par l'IA ou à la main :
  - Degetel : 4 adresses d'agences (paris@, lille@, lyon@, benelux@) ;
  - Health Data Hub : dpd@ et hdh@ ;
  - Onisep : `servicejuridique@onisep.fr` ;
  - Factofrance : `reclamations-clients@factofrance.com` ;
  - Ithis : une adresse gmail ;
  - Fermat : `olympic@fermat.edu.vn`, sur le faux site.
- Formulaires de contact relevés sur 12 des 14 sites vérifiés.

**Temps et requêtes :**
- Temps moyen par entreprise : 76,3 s avant, 66,7 s après (47,1 s par site vérifié et lu).
- Requêtes par entreprise : 21,2 avant, 10,4 après.
- Réponses 404 : 594 sur 849 avant (adresses devinées), 27 sur 416 après.
- Pages interdites par robots.txt demandées : aucune après.

**Adresses déjà en base** (revalidation à blanc, `scripts/revalider_emails_en_base.py`) :
- Avant : 2 entreprises envoyables, 8 adresses.
- Après : 1 entreprise, 1 adresse (`contact@health-data-hub.fr`, sur le site vérifié). Les 5 adresses de France Université Numérique sont écartées : gabarit, mal formées, annuaire.
- Rien n'est écrit en base sans `--appliquer`.

**Banc des emails** (`banc_emails_reference.json`, 9 adresses) :
- Départ : précision 0,5 et rappel 1,0, l'IA retenant à chaque essai l'adresse companyfrance.
- Après : précision 1,0 et rappel 1,0 par les règles seules, sans appel à l'IA.

### 8. Test des noms réels (D157)
- La section « Autrice » du README et l'URL de clonage sont exclues du contrôle. Le test passe.

## Ajouts hors liste
- D164 : la suite de tests échoue si `data/` change (empreinte avant et après la session).
- D165 : jamais de page ni d'email d'un sous-domaine de préproduction ou de test. Ajouté après le site `prepod.fun.luniversitenumerique.fr` de France Université Numérique.

## Points à trancher
- **Preuve par le nom trop faible pour les noms d'un seul mot** : Fermat, Bellon et Ithis ont été retenus sur leur seul nom dans un titre. Proposition : exiger le SIREN quand le nom distinctif n'a qu'un mot.
- **Rappel de la recherche web** : 13 sites non trouvés sur 27. Pistes, à mesurer de nouveau sur l'échantillon :
  - essayer d'abord, sur toutes les requêtes, les domaines qui ressemblent au nom, puis seulement les pages tierces (aujourd'hui, ce tri ne se fait que dans une même page de résultats) ;
  - ajouter aux domaines interdits les agrégateurs vus : doctrine.fr, jobted, restaurantguru, usinenouvelle, infobel.fr, xerfi, fusacq, clutch ;
  - ajouter une requête « nom + site officiel » sans ville.

## Banc d'analyse (mesure de départ, prompt inchangé)
- Configuration : `ministral-3:3b`, prompt de l'application, température 0, 3 essais sur les 137 offres annotées (100 job, 27 stage, 10 alternance). Sortie : `audit_exports/banc_analyse_ministral-3_3b_20261122_214001.json`.
- Réponses invalides : aucune sur 411.
- Éligibilité juste : 66,2 %.
  - Faux éligibles : 45 offres. 34 en job sur les 36 inéligibles attendues : CACES, diplôme d'État ou expérience exigés, que les règles Python ne vérifient pas. Puis 7 en alternance et 4 en stage (école d'ingénieurs ou M2 demandés).
  - Faux inéligibles : 2 offres job.
- Niveau extrait après contrôle Python : 89,3 % juste.
- Faux positifs de niveau (Bac+4 ou plus attendu, éligible et noté 7 ou plus) : 1 offre, « Stage Développeur Logiciel » (le cas n° 13 de l'étape 1), aux 3 essais.
- Catégorie : 36,7 % exacte, écart moyen de 0,72 rang, 25 réponses à deux rangs ou plus.
  - Le modèle met rarement « Hors sujet » : 111 réponses « Faible » pour un « Hors sujet » attendu.
  - Il sous-note les offres moyennes : 56 réponses « Faible » pour un « Moyen » attendu.
- Stabilité : écart type de la note nul à température 0 ; 2 offres changent de catégorie d'un essai à l'autre.
- Temps : 22,4 s par offre en moyenne (médiane 21,9 s, maximum 63,6 s).
- Le premier lancement du banc avait été arrêté par le système, faute de mémoire. Relancé détaché, limité à 2 Go, il est allé au bout.
