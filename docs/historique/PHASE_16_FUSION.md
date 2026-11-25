# Phase 16 : fusionner phase-16-correctifs dans main

`main` (ce932a0, fusion de la phase 15) est un ancêtre de la branche : la fusion se fait sans conflit.

## Ce qui change à l'installation
- **Aucune migration.** Les nouvelles données sont rangées dans les colonnes JSON existantes : `entreprises.extra` (`denomination`, `page_carrieres`), `candidatures.marques` (`description_coupee:<lus>`), `profils.recherche` (`inclure_transverses`).
- **.env** :
  - `IA_LONGUEUR_DESCRIPTION` est maintenant un plafond de sécurité : 20000 (déjà fait chez toi), ou supprimer la ligne ;
  - `RECHERCHE_BACKENDS` est facultatif (défaut `brave, mojeek, duckduckgo, yahoo, yandex`) ;
  - rien d'autre.
- **Réseau** : le scraper interroge Wikidata (query.wikidata.org, SIREN seulement) avant toute recherche web.

## Avant la fusion

Dans le dossier du projet, application arrêtée.

1. **Branche et état.**
   - `git switch phase-16-correctifs && git status --short` : rien à commiter.
2. **Suite de tests.**
   - `systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q`
   - Attendu : tout passe.
3. **Sauvegarde de la base**, à faire avant d'écrire quoi que ce soit :
   - `cp data/chasseur_v2.db ~/sauvegardes_chasseur/chasseur_v2_avant_phase16_$(date +%F_%H%M).db`
   - `ls -lh ~/sauvegardes_chasseur/ | tail -2`

## Fusion et push

```bash
git switch main
git merge --no-ff phase-16-correctifs -m "Merge branch 'phase-16-correctifs'"
systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q
git push origin main
git push origin phase-16-correctifs        # facultatif : garder la branche sur GitHub
```

## Dénominations des entreprises déjà en base (D192)

Application arrêtée (pas d'uvicorn lancé), après la sauvegarde.

1. Lecture seule, pour voir ce qui sera écrit :
   - `venv/bin/python scripts/completer_denominations.py`
   - Attendu : environ 18 entreprises, dont « PARIS HOTEL DE VILLE -> BRED BANQUE POPULAIRE ».
2. Écriture, en une transaction à la fin (un Ctrl+C avant n'écrit rien) :
   - `venv/bin/python scripts/completer_denominations.py --appliquer`
   - Dernière ligne attendue : « Écrit en une transaction. »

## Tests à la main après la fusion

Démarrer : `venv/bin/uvicorn main:app --port 5002`, ouvrir http://localhost:5002 et se connecter. Le compte d'envoi reste en mode essai.

1. **Mon profil, partie « Ton parcours »** (D184, D185) :
   - le permis s'affiche en cases arrondies, sans cadre gris ;
   - cocher « Aucun permis » grise les autres cases ; le décocher les rend cochables ;
   - choisir « SSIAP 1 » dans la liste suggérée des certifications : l'étiquette apparaît aussitôt ;
   - enregistrer, recharger (F5) : elle reste.
2. **Mon profil, « Ce que tu cherches »** (D190) : la case « Inclure les grandes entreprises qui ont un service interne de ton domaine » est cochée par défaut.
3. **Entreprises à contacter** (D190, D191, D192) :
   - chaque entreprise porte son origine : « Informatique », « Grande entreprise, service informatique interne » ou « La Bonne Alternance, recrute des alternants dans ton métier » ;
   - le menu « Origine » filtre la liste ;
   - en alternance, la BRED s'affiche « BRED BANQUE POPULAIRE · PARIS HOTEL DE VILLE » ;
   - un onglet « Sur leur site carrières » existe (vide tant que le scraper n'a pas relu de grande entreprise).
4. **Trouver leurs emails** (D187, D188), plafond de 5 :
   - les logs affichent une ligne « Wikidata : N site(s) officiel(s) trouvé(s) pour M SIREN » ;
   - si les moteurs refusent, des lignes « Recherche web en échec (brave : … ; mojeek : …) » apparaissent, puis au plus une ligne « ⛔ Recherche web arrêtée pour ce lancement », sans attente de 90 s.
5. **Note des offres** (D193, D194, D195) :
   - « Noter cette offre » sur une offre de stage longue : la note arrive ;
   - le terminal n'affiche ni « Plafond de sécurité atteint » ni « num_ctx porté » (les offres font moins de 20 000 caractères) ;
   - aucune étiquette « Description longue » dans le détail ;
   - pendant la notation, dans un autre terminal, `ollama ps` affiche CONTEXT 4096.
   - En alternance, une offre qui prépare un Bac+5 (« préparation du titre … Bac+5 ») avec un niveau visé Bac+2 affiche « Conditions non remplies : diplôme préparé Bac+5, niveau visé Bac+2 ».
6. **Arrêt** : Ctrl+C.
