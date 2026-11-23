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
- Offres écartées pour des exigences que le profil ne remplit pas (« Conditions non remplies ») :
  - permis exigé, quelle que soit la catégorie pour un profil « Aucun permis » ;
  - formation au-dessus du profil ;
  - diplôme d'État ;
  - Bac+5 exigé, y compris « stage de fin d'études », « dernière année d'école d'ingénieurs ou de master », « M2 » ;
  - en alternance, diplôme préparé à plus d'un niveau au-dessus du niveau visé ;
  - expérience exigée : en job, au-delà de 12 mois de plus que la sienne ; en alternance, deux ans ou plus ;
  - certification (CACES, SSIAP…) absente ;
  - en job et en alternance, poste « confirmé », « senior » ou « expérimenté ».
- En job, une expérience demandée jusqu'à 12 mois au-dessus de la sienne n'écarte pas l'offre : note plafonnée à Moyen, « Expérience demandée : 1 an » dans Ce qui coince.

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

Dans le dossier du projet, sur la branche `phase-15-audit-backend`. Le compte d'envoi reste en mode essai jusqu'à l'étape 11 : aucun mail ne part ailleurs que dans ta boîte.

1. **Branche et état.**
   - `git switch phase-15-audit-backend && git status --short` : rien à commiter.
   - `venv/bin/alembic current` : affiche `0017 (head)`.
2. **Suite de tests.**
   - `systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q`
   - Attendu : tout passe, sans section « data/ modifié par les tests » à la fin.
3. **Réglage du prompt.**
   - `grep -n "^IA_VERSION_ANALYSE" .env || echo "absent : v2 par défaut"`
4. **Démarrer l'application.**
   - `venv/bin/uvicorn main:app --port 5002`, puis ouvrir http://localhost:5002 et se connecter.
   - Les trois modes (alternance, stage, job) s'ouvrent, aucune erreur dans le terminal.
5. **Mon profil, en mode job.**
   - Partie « Ton parcours » : les cases du permis, l'expérience en mois et les certifications montrent tes valeurs (aucun permis, 3, aucune certification).
   - Cocher B : « Aucun permis » se décoche. Recocher « Aucun permis » : B se décoche.
   - Ajouter « CACES R489 » par la liste suggérée, enregistrer, recharger la page (F5) : les valeurs restent.
   - Remettre tes vraies valeurs et enregistrer.
6. **Copie entre modes.**
   - En mode alternance : « Copier depuis un autre mode », source job, section « Permis, expérience en mois et certifications ». Confirmer.
   - Partie « Ton parcours » : les trois champs sont recopiés ; les domaines de recherche de l'alternance n'ont pas changé.
7. **Recherche d'offres.**
   - **Stage** : lancer « Chercher des offres ». Le terminal affiche deux requêtes France Travail (`motsCles=stage`, `motsCles=stagiaire`), sans domaine. Des offres « Stagiaire … » apparaissent.
   - **Job** : lancer une recherche. Dans Offres, « Filtrer », menu Lieu, choisir « Île-de-France, lieu non précisé » : des offres apparaissent (sinon aucune ce jour-là, sans erreur).
   - **Alternance** : lancer une recherche, puis « Filtrer », menu Particularités. Essayer « Niveau différent du tien » et « Déposées par un organisme de formation ». L'étiquette apparaît sous le titre dans le détail de l'offre.
8. **Note des offres (prompt v2).**
   - En job, ouvrir une offre non notée, puis « Noter cette offre ». La note arrive en une trentaine de secondes ; « Ce qui colle » et « Ce qui coince » sont remplis.
   - Bandeau « N nouvelles offres pas encore notées », « Les noter » sur quelques offres : la progression avance, sans erreur.
   - Ouvrir une offre qui demande « 1 an d'expérience » : elle reste éligible, notée Moyen au plus, avec « Expérience demandée : 1 an » en tête de Ce qui coince.
   - Une offre qui demande « 2 ans » ou plus affiche « Conditions non remplies : … d'expérience exigés, profil 3 mois ».
   - Une offre « … confirmé » ou « … senior » affiche « Conditions non remplies : poste confirmé ou senior ».
   - Facultatif, pour comparer :
     - ajouter `IA_VERSION_ANALYSE=v1` dans `.env`, redémarrer (Ctrl+C puis la commande de l'étape 4), noter une offre ;
     - retirer la ligne et redémarrer.
9. **Trouver des entreprises (export LBA).**
   - En alternance, page « Entreprises à contacter », « Trouver des entreprises » avec un petit plafond (10).
   - Le premier lancement télécharge l'export : quelques minutes, ligne « export du … en cours de lecture (en flux, IDF seulement) » dans les logs.
   - Pendant ce temps, dans un autre terminal : `free -h` (la mémoire disponible ne s'effondre pas).
   - Ensuite : `ls -lh data/lba_recruteurs_idf.jsonl.gz data/lba_recruteurs_idf.json data/lba_sites_par_siren.json`
   - Relancer « Trouver des entreprises » : il ne retélécharge pas (pas de ligne « en cours de lecture »).
10. **Trouver leurs emails.**
    - Sur la même page, « Trouver leurs emails » avec un plafond de 5.
    - Dans les logs, pour chaque entreprise : « 🌐 https://… [source, preuve] », ou « ❌ Site non vérifié ».
    - Onglet « Sans contact » : « Site non vérifié… » ou « Ouvrir le formulaire de contact » (le lien s'ouvre dans un nouvel onglet).
    - Aucune adresse d'annuaire (companyfrance, societe.com…) dans les adresses gardées.
11. **Adresses déjà en base.**
    - Lecture seule : `venv/bin/python scripts/revalider_emails_en_base.py --verifier-sites --recherche`. Lire le bilan : 2 entreprises avant, 1 après, 1 adresse gardée (contact@health-data-hub.fr).
    - S'il te convient : arrêter l'application (Ctrl+C), puis `venv/bin/python scripts/revalider_emails_en_base.py --verifier-sites --recherche --appliquer`, puis la relancer (étape 4).
    - « Entreprises à contacter » : France Université Numérique n'est plus prête à envoyer.
12. **Envoi en mode essai.**
    - Le bandeau « Mode essai : les mails arrivent dans ta propre boîte » est affiché.
    - « Envoyer ta candidature » à 1 entreprise : le mail arrive dans ta boîte, à une adresse validée seulement.
13. **Arrêt.**
    - Ctrl+C dans le terminal de l'application.

## Fusion, une fois les tests passés

```bash
git switch main
git merge --no-ff phase-15-audit-backend -m "Merge branch 'phase-15-audit-backend'"
systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q
```
