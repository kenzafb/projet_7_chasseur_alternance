# Phase 15 : préparer la fusion de phase-15-audit-backend dans main

`main` (019e0c4) est un ancêtre de la branche : la fusion se fait sans conflit (avance rapide possible, ou fusion avec commit, comme pour la phase 14).

## Migrations
- **0017** (`candidatures.marques`, JSON, `[]` par défaut, lignes existantes intactes) : la seule de la phase, déjà lancée chez toi.
- Aucune autre migration. Les nouveaux champs du profil (permis, expérience en mois, certifications) sont rangés dans la colonne JSON `profils.recherche`, et ceux des entreprises (site vérifié, autres noms, adresse du siège, formulaires de contact, catégorie juridique) dans `entreprises.extra`.
- Sur une autre installation : `venv/bin/alembic upgrade head` avant de lancer l'application.

## Fichiers et réglages nouveaux
- `.env` : `IA_VERSION_ANALYSE` (défaut `v2` ; `v1` pour revenir à l'ancien prompt). Rien d'autre à ajouter.
- `DATA_DIR` : à la première étape « Trouver des entreprises » qui en a besoin, l'application télécharge l'export LBA, le lit en flux et écrit :
  - `lba_recruteurs_idf.jsonl.gz` (quelques Mo) ;
  - `lba_recruteurs_idf.json` (date de l'export) ;
  - `lba_sites_par_siren.json`.

  Il est rafraîchi au plus une fois par semaine et demande `LBA_API_KEY`.
- Le scraper appelle l'API publique Recherche d'entreprises (sans clé, le SIREN seulement) une fois par entreprise qui n'a pas encore ses autres noms.

## Changements visibles pour les utilisatrices

**Offres**
- Une offre France Travail rattachée à la région sans département (« Île-de-France ») n'est plus écartée : zone « Île-de-France (non précisé) », dans le menu Lieu.
- Stage : recherche par « stage » et « stagiaire », sans filtre de domaine (environ 102 offres gardées au lieu de 9) ; une offre hors des domaines est mal notée, jamais écartée.
- Alternance (LBA) :
  - offres d'un niveau adjacent gardées, avec l'étiquette « Niveau différent du tien » ;
  - offres déposées par un organisme de formation (et CAPIVISION) gardées, avec l'étiquette « Offre déposée par un organisme de formation » ;
  - nouveau filtre « Particularités ».
- Écoles et CFA : seuls les organismes vérifiés écartent une offre. « CFA », « école »… dans le titre ou le nom de l'entreprise ne font qu'afficher un indice. Beaucoup moins d'offres d'alternance écartées.
- Note des offres, prompt v2 :
  - deux appels à l'IA au lieu d'un, pour le même temps (environ 24 s par offre) ;
  - le résultat est un mot (Très bien, Bien, Moyen, Faible, Hors sujet), traduit en note ;
  - les notes changent pour les offres notées à nouveau, pas pour celles déjà notées.
- Offres écartées pour des exigences que le profil ne remplit pas (« Conditions non remplies ») : permis exigé, formation au-dessus du profil, diplôme d'État, expérience exigée supérieure à la sienne (job), deux ans ou plus en alternance, certification (CACES, SSIAP…) absente.

**Mon profil**
- Partie « Ton parcours », dans les trois modes : permis de conduire (cases, avec « Aucun permis »), expérience professionnelle en mois, certifications (étiquettes avec suggestions).
- Nouvelle section copiable entre modes : « Permis, expérience en mois et certifications ».

**Entreprises à contacter**
- Les entreprises à fort potentiel de La Bonne Alternance viennent de l'export complet : bien plus d'entreprises (3 888 contre 2 933 pour le profil mesuré). Le premier lancement télécharge l'export et dure plus longtemps.
- Sirene : les établissements franciliens dont le siège est ailleurs sont trouvés (+711 entreprises cœurs, +548 transverses à la mesure).
- Trouver leurs emails :
  - site retenu seulement s'il porte le SIREN, le nom, ou, pour un nom d'un seul mot, le nom dans le domaine et l'adresse ; sinon « Site non vérifié », et aucun email ;
  - pages lues par les liens réels, robots.txt respecté, 8 pages au plus ;
  - formulaire de contact affiché (« Ouvrir le formulaire de contact ») quand il n'y a pas d'email.
- Emails : seules les adresses du domaine du site vérifié sont gardées (ou une messagerie grand public trouvée sur le site, à valider). Les adresses factices, mal formées ou d'un sous-domaine de test sont écartées.

## À tester dans l'application avant de fusionner

Avec ton compte, dans l'ordre ; rien n'envoie de mail tant que le compte d'envoi est en mode essai.

1. **Démarrage** : l'application démarre, les trois modes s'ouvrent, aucune erreur dans les logs.
2. **Mon profil**, en job puis en stage :
   - remplir permis, expérience et certifications, enregistrer, recharger : les valeurs restent ;
   - « Aucun permis » décoche les autres cases ;
   - copie de la section « Permis, expérience en mois et certifications » d'un mode vers un autre.
3. **Recherche d'offres**, dans chaque mode :
   - le stage ramène des offres « stagiaire » ;
   - une offre « Île-de-France (non précisé) » apparaît et se filtre par le menu Lieu ;
   - en alternance, les étiquettes « Niveau différent du tien » et « Offre déposée par un organisme de formation » et le filtre « Particularités » fonctionnent.
4. **Noter des offres** (bouton « Noter cette offre », puis « Les noter » sur quelques offres) :
   - les notes arrivent, sans erreur ;
   - une offre qui exige un CACES ou de l'expérience au-delà de la tienne passe en « Conditions non remplies » avec la raison ;
   - si besoin, `IA_VERSION_ANALYSE=v1` dans `.env` et redémarrage pour comparer.
5. **Trouver des entreprises** (mode alternance) :
   - le premier lancement télécharge l'export LBA (quelques minutes, message dans les logs), le second ne le refait pas ;
   - des entreprises LBA et Sirene arrivent ;
   - la mémoire reste raisonnable pendant le téléchargement.
6. **Trouver leurs emails** sur 5 à 10 entreprises :
   - logs « 🌐 site [source, preuve] » ou « Site non vérifié » ;
   - des formulaires de contact affichés ;
   - aucune adresse d'annuaire ni d'un autre domaine retenue.
7. **Adresses déjà en base** :
   - `venv/bin/python scripts/revalider_emails_en_base.py --verifier-sites --recherche` (lecture seule), puis, si le rapport te convient, `--appliquer` ;
   - les 2 entreprises aux adresses fausses ne sont plus envoyables.
8. **Envoi en mode essai** d'une candidature spontanée vers ta propre boîte : seules les adresses validées partent.
9. **Suite de tests** : `systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q`. Elle passe, et le garde-fou de `data/` ne signale rien.
