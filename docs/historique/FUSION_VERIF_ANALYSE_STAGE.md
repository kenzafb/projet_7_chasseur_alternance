# Fusionner verif-analyse-stage dans main

La branche part de `main` (c07c6bb, fusion de `remise-a-zero`). Décisions : D201 à D209.

## Ce qui change à l'installation
- **Migration 0018** : deux colonnes vides dans `candidatures` (`code_rome`, `hors_sujet_car`). Sans elle, l'application échoue dès qu'elle lit une offre.
- **.env** : rien à changer.
- **Réseau** : rien de nouveau dans l'application. `completer_codes_rome.py` interroge l'API France Travail, une requête par offre.

Toutes les commandes se lancent dans le dossier du projet, **application arrêtée** jusqu'à la relance de l'analyse.

## 1. Sauvegarde

```bash
cp data/chasseur_v2.db ~/sauvegardes_chasseur/chasseur_v2_avant_0018_$(date +%F_%H%M).db
ls -lh ~/sauvegardes_chasseur/ | tail -2
```

## 2. Tests

```bash
git switch verif-analyse-stage && git status --short        # attendu : rien
systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q
```

Attendu : tout passe (1 sauté : l'ancienne base n'est plus dans `data/`).

## 3. Fusion et push

```bash
git switch main
git merge --no-ff verif-analyse-stage -m "Merge branch 'verif-analyse-stage'"
systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q
git push origin main
git push origin verif-analyse-stage        # facultatif : garder la branche sur GitHub
```

## 4. Migration 0018

```bash
venv/bin/alembic upgrade head
venv/bin/alembic current                   # attendu : 0018 (head)
```

## 5. Codes métier des offres déjà en base

1. Lecture seule :
   - `venv/bin/python scripts/completer_codes_rome.py`
   - Dernières lignes attendues : « N à remplir, N qui n'existent plus, … », puis « Lecture seule : rien n'est écrit ».
   - Beaucoup d'offres « en erreur » : relancer plus tard. Presque toutes « disparues » : ne pas appliquer, le signaler.
2. Écriture :
   - `venv/bin/python scripts/completer_codes_rome.py --appliquer`
   - Dernière ligne attendue : « N code(s) écrit(s) en une transaction. »
   - Une offre qui n'existe plus garde un code vide : elle ira aux autres règles, puis à l'IA.

## 6. Relance de l'analyse des stages

1. `venv/bin/uvicorn main:app --port 5002`, ouvrir http://localhost:5002, mode stage.
2. Page Offres : lancer l'analyse des offres en attente.
3. Attendu dans le journal : « archivée par les règles (hors informatique (code métier)), sans IA », « inéligible sans IA (…) », puis quelques offres notées.
   - Mesuré sur 50 offres, avec les codes : 88 s avec D203 (37 archivées par le code métier, 8 par les autres règles, 5 lues par l'IA), contre 1 244 s avant la branche. Non remesuré depuis D207, qui en archive 3 de plus par le code métier.
4. Les offres **déjà analysées** ne sont pas reprises par cette relance : « Faire noter à nouveau cette offre » applique le niveau, la durée et les dates, pas le code métier.

## 7. Tests à la main

Le compte d'envoi reste en mode essai.

1. **Mon profil, stage, « Ce que tu cherches »** (D201) : « Ce que tu préfères éviter » s'affiche avec ton texte ; modifier, enregistrer, recharger (F5) : il reste. M18 est coché.
2. **Offres écartées, filtre « Hors informatique (code métier) »** (D203) :
   - les stages RH, marketing et le stage UX y sont, avec la marque « Hors informatique (code métier) » ;
   - les trois « Développement RH » y sont (D207) ;
   - le stage simulateur n'y est pas : il est dans « Conditions non remplies » (4 mois).
3. **Offres écartées, « Conditions non remplies »** (D202, D204) : une offre Bac+5 affiche « Bac+5 souhaité, Bac+3 au plus en stage », la note « – » et « Écartée sans être notée ».
4. **Remettre dans À voir** une offre « Hors informatique » : elle revient dans À voir ; « Noter cette offre » la fait lire par l'IA si elle reste éligible. La relance de toute la file l'écarterait de nouveau.
5. **Recherche d'offres de stage** : une nouvelle offre hors informatique est écartée dès la récupération, sans IA. Une offre de plus de 10 000 caractères donne « Description France Travail coupée » dans le journal (D209).
6. **Mode alternance et mode job** : ouvrir les offres et en noter une ; le comportement ne change pas, sauf pour une offre que les règles écartent sans l'IA.

## Revenir en arrière

Application arrêtée : remettre la sauvegarde de l'étape 1 (`cp ~/sauvegardes_chasseur/chasseur_v2_avant_0018_….db data/chasseur_v2.db`) et revenir au `main` d'avant (`git switch --detach c07c6bb`).
