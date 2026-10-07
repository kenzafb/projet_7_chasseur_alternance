# Phase 2b : isolation complète entre utilisateurs, rapport

Branche `phase-2b-isolation`, créée depuis `refonte-multiuser` (44adad8), 8 octobre 2026. Non poussée, non fusionnée.
Règles suivies : rien écrit dans `data/` ni dans `.env` (listing de `data/` inchangé, `chasseur_v2.db` lu une seule fois en `mode=ro`, aucun `__pycache__` dans `data/`). Aucun appel à FT, LBA, INSEE, Mistral ou SMTP. Aucune route de pipeline appelée sur la vraie base. `compileall -x 'venv/|data/'` propre. Seul accès réseau : téléchargement de `pytest-timeout` par pip.

## 1. Commits

| Commit | Thème |
|---|---|
| 43d9025 | Dédoublonnage en base par utilisateur, insertions idempotentes |
| 51f1c93 | États, arrêt et logs des pipelines par utilisateur |
| 3724d61 | Limitation commune des appels Mistral |
| 3e4eb7b | PDF sécurisé, migration 0002, route de téléchargement protégée |
| 3e1d460 | Pièces jointes : bugs 8 et 9 |
| 8bcf733 | Dates : UTC en base, heure de Paris à l'affichage |
| fbd9ff9 | Tests : délai par test, threads bornés, plafond mémoire (suite à l'incident de 00:57) |
| c5e8a0f | Front via `api.js`, validation Pydantic de deux routes |
| (dernier) | Ce rapport |

## 2. Ce qui change pour l'utilisateur

**Dédoublonnage par utilisateur.** Les offres déjà vues sont dans `offres_vues` (user, mode), les adresses contactées dans `emails_contactes` (user, adresse en minuscules), via `database/dedup_db.py`. Une offre vue par A est proposée à B, une adresse contactée par A ne bloque pas B. `offres_vues_*.json` et `emails_deja_envoyes.json` ne sont plus ni lus ni écrits ; ils restent dans `data/`. Le bug 1 disparaît avec eux (chaque mode a ses lignes). Toutes les insertions passent par `database/insertion.py` (`INSERT ... ON CONFLICT DO NOTHING`, SQLite et PostgreSQL) : une candidature, une offre vue ou une adresse en double est ignorée sans erreur, même en cas d'insertions simultanées. Ce point de la phase 2a est donc réglé. `remplacer_candidatures`, inutilisée, est supprimée.

**Pipelines.** `shared/pipelines.py` remplace les quatre globales. États, événement d'arrêt et logs sont indexés par `user_id` et protégés par un verrou. `/api/logs`, `/api/statut_recherche`, `/api/spontanees/statut` et `/stats` ne renvoient que les données de l'utilisateur connecté. `/api/spontanees/stop` n'arrête que son propre pipeline et renvoie `en_cours` pour dire s'il y en avait un. Un utilisateur a au plus une recherche et une étape spontanée à la fois (test et marquage atomiques : vingt demandes simultanées donnent un seul démarrage) ; deux utilisateurs travaillent en parallèle. Les logs sont gardés en mémoire à raison de 200 lignes par utilisateur (`LOGS_MAX_PAR_UTILISATEUR`), les plus anciennes sont jetées. Le fetch affiche désormais aussi « Arrêté » quand on l'arrête.

**Mistral.** `shared/ia.py` contient un `Limiteur` commun au processus : au moins `MISTRAL_INTERVALLE_MIN_S` secondes entre deux appels, 2 par défaut, surchargeable dans le `.env`. Il s'applique à tous les utilisateurs, tous les pipelines et aussi aux retries. Chaque appelant réserve son créneau sous verrou, puis attend hors du verrou. La boucle LBA (bug 4) est donc espacée. Les pauses propres aux pipelines (10 s dans `analyser_offres`, 30 s dans le scraper) sont inchangées.

**PDF (bug 6, limite 4 de la phase 1).** Lettre, profil et champs de l'offre sont échappés (`html.escape`) : une balise s'imprime comme du texte. Le `url_fetcher` de WeasyPrint refuse toute ressource, qu'il s'agisse d'un fichier local, d'une URL réseau ou d'un `data:`. Le gabarit n'en utilise aucune (styles en ligne, polices système). Chaque PDF reçoit un nom unique, `lettres_pdf/user_<id>/lettre_<hex>.pdf`, écrit dans un temporaire puis renommé. Son chemin est gardé dans `candidatures.lettre_pdf`, et le PDF précédent de la même candidature est supprimé. `POST /api/telecharger_pdf` renvoie `{url, nom}` au lieu d'un chemin serveur. `GET /api/lettre_pdf/<ref>` cherche la candidature par `user_id` puis vérifie que le fichier est sous `user_<id>/` ; il sert le fichier en pièce jointe (`Lettre_Prenom_Nom_Entreprise.pdf`) et répond 404 pour le PDF d'un autre. Côté front, le PDF est téléchargé en vrai, via un blob (`api.telechargerPdf`).

**Pièces jointes.** Bug 8 : le nom est nettoyé (ASCII, sans dossier), raccourci à 60 caractères avant l'extension, qui est donc conservée, puis suffixé de 8 caractères hexadécimaux. Le fichier est ouvert en mode exclusif (`"xb"`), si bien que rien n'est jamais écrasé. Bug 9 : supprimer une pièce, ou la remplacer par une autre du même nom, n'efface le fichier que si aucun profil du même utilisateur, tous modes confondus, ne le référence encore.

**Dates.** En base, toute date est un instant UTC. La date d'une offre est l'horodatage de FT ou de LBA (`instant_depuis_api` : sans fuseau, c'est de l'UTC ; une date seule devient midi heure de Paris ; une date absente donne maintenant). Une date de candidature ou d'envoi est l'instant UTC de l'action. `vers_utc` refuse une date seule, et lit une heure sans fuseau dans `FUSEAU_AFFICHAGE` (Europe/Paris, configurable dans `shared/config.py` ou dans le `.env`), jamais dans le fuseau du serveur. La conversion n'a lieu qu'en sortie de la couche d'accès (`en_texte`) et pour l'affichage : date de la lettre, du PDF, heure des logs. Le suivi des envois est trié sur l'instant, plus sur le texte. Une date relue et non modifiée n'est plus réécrite par `sauvegarder_entreprises`. Formats échangés avec le front inchangés.

**Routes et front.** `profil.js`, `suivi.js` et `app.js` n'appellent plus `fetch` directement. Ils passent par `api.js`, enrichi de `profil`, `sauverProfil`, `mode`, `domaines`, `envoyerPiece` (multipart), `supprimerPiece`, `spSuivi` et `spSuiviStatut` : tout 401 renvoie donc vers `/login`. La bascule de mode de `base.html` le fait aussi. `/api/maj_statut` et `/api/offre/archivage` valident leur corps par Pydantic : statut parmi nouveau, en_cours, envoye, reponse, entretien, refus, archive ; raison parmi les 6 raisons connues ; champs en trop refusés ; archivage avec soit `desarchiver: true`, soit une raison. Tout corps invalide reçoit 422 `{"erreur": "Requête invalide : ...", "detail": [...]}`, que le front affiche.

## 3. Migration ajoutée

`alembic/versions/0002_lettre_pdf.py` (autogénérée puis relue) ajoute la colonne `candidatures.lettre_pdf` VARCHAR(255), nullable, en mode batch, sans toucher aux données existantes. Le downgrade retire la colonne. Aucune conversion de dates n'est nécessaire : les anciennes dates « minuit heure locale » écrites sous Paris restent affichées au bon jour. Vérifications : `alembic upgrade head`, puis `alembic check` (« No new upgrade operations detected »), puis `alembic current` = `0002 (head)` en ligne de commande sur une base temporaire. Un test monte une base en 0001 contenant des données jusqu'à 0002.

## 4. Incident mémoire de 00:57 : cause

Ce n'est **pas** le code applicatif. Le coupable est la première version de l'espion de `tests/test_pdf.py` :

```python
def espion(url, *args, **kwargs):
    demandees.append(url)
    return pdf.refuser_ressource(url)   # après monkeypatch, c'est espion lui-même
```

Une fois `pdf.refuser_ressource` remplacé par `espion`, la fonction s'appelle elle-même sans fin. Sur ce CPython 3.13.5, une fonction récursive qui prend `*args/**kwargs` n'atteint jamais `RecursionError`. Mesures : 999 appels puis erreur pour une fonction simple, plus de 50 000 appels sans erreur pour la même en version variadique, avec le même résultat sous `/usr/bin/python3`. Les frames de Python 3.13 sont allouées sur le tas, la récursion consomme donc de la mémoire jusqu'à l'OOM. Reproduit sous `systemd-run -p MemoryMax=1500M` : 1,4 Go en 3 s, la portée est tuée par l'OOM killer, sans `RecursionError` et sans même passer par WeasyPrint. Le test avait été corrigé à 00:58 (l'espion capture la vraie fonction avant le patch). Le `refuser_ressource` de l'application ne s'appelle pas lui-même. Le reste du code de la phase a été relu dans ce sens : limiteur, pipelines, logs bornés et événement d'arrêt ne contiennent ni récursion ni boucle sans borne.

Garde-fous ajoutés : `pytest-timeout==2.4.0` dans `requirements-dev.txt`, avec `timeout = 30` et la méthode `signal` dans `pytest.ini` (vérifié : un test bloqué échoue seul et les suivants tournent). Tous les tests à threads passent par `en_parallele` (`tests/conftest.py`) : barrière avec délai, `join` borné, threads démons, échec explicite si un thread survit. Les faux pipelines attendent au plus 5 s, et la fixture attend la fin des threads lancés par les routes avant de retirer les faux. Le README donne la commande sous plafond mémoire. Un délai seul n'aurait pas suffi ici : 10 Go sont atteints bien avant 30 s, c'est le plafond qui protège la machine.

## 5. Tests

Commande : `systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q`. Résultat : **151 passed** en 15 s, aucun avertissement (87 avant la phase, tous toujours verts ; deux adaptés : la date seule de `test_schema` devient un instant, et le nom du PDF de `test_lettre` devient l'URL de téléchargement plus le fichier dans `user_<id>/`).

| Fichier | Couvre |
|---|---|
| `test_dedoublonnage.py` | Offre vue par A proposée à B ; modes séparés (bug 1) ; recherche complète pour A et B ; plus de fonctions JSON ; adresse contactée par A ne bloque pas B (SMTP simulé) ; doublons de candidature, offre vue, adresse (casse) ignorés ; 8 insertions simultanées, une seule réussit, aucune erreur |
| `test_pipelines.py` | A et B lancent une recherche en même temps : chacun ne voit que ses logs et son état, second lancement refusé ; A arrête son scraper, celui de B continue avec son message ; arrêt sans pipeline ; recherche et spontanées ensemble ; logs bornés ; démarrage atomique |
| `test_limiteur_mistral.py` | 4 threads × 3 appels : écart minimal entre appels respecté ; retries limités aussi ; l'analyse utilisée par la boucle LBA passe par le limiteur |
| `test_pdf.py` | Lettre, profil et offre piégés (img `file:///etc/passwd`, script, link, `@import`) échappés ; aucune ressource demandée ; HTML brut : les 4 ressources (fichier, http, https, `url()` CSS) refusées, PDF quand même produit ; homonymes ; téléchargement du propriétaire (en-têtes, `%PDF`) ; PDF de B refusé à A, chemins détournés en 404 ; régénération qui remplace l'ancien fichier |
| `test_pieces_jointes.py` | Nom de plus de 300 caractères ramené sous 73 en gardant `.pdf` ; noms piégés nettoyés ; deux fichiers de même nom coexistent ; suppression en alternance qui garde le fichier encore utilisé en job, puis suppression effective ; remplacement |
| `test_dates.py` | Pour TZ = UTC, Los Angeles, Tokyo, Kiritimati (UTC+14) et Paris : mêmes valeurs brutes en base et mêmes dates affichées, y compris les jours de changement d'heure ; date de candidature = instant UTC ; date seule refusée ; horodatages des API ; tri du suivi pendant l'heure doublée d'octobre |
| `test_validation.py` | 7 corps invalides pour chaque route en 422 sans effet, cas valides, corps non JSON |
| `test_schema.py` | `+1` : base en 0001 avec données montée en 0002, `alembic check` propre |

Autres vérifications : `uvicorn main:app --port 5099` sur une base temporaire migrée donne `/login` 200, `/` 303, `/api/logs` 401, `/api/lettre_pdf/x` 401. `node --check` passe sur les 7 modules JS. Le parcours dans un navigateur réel n'a pas été fait.

## 6. Limites restantes

1. **Threads perdus au redémarrage** (non corrigé, comme demandé) : états, logs et threads vivent dans la mémoire du processus. Un redémarrage, ou chaque modification de fichier sous `uvicorn --reload`, tue les pipelines en cours sans trace. Plusieurs workers uvicorn auraient chacun leurs états, et le limiteur Mistral ne vaut que par processus (une CLI lancée à côté ne le partage pas). Il faudra une vraie file de tâches avant tout déploiement multi-worker.
2. Les offres FT sont marquées vues avant leur analyse (comportement inchangé) : un plantage en cours de run perd celles qui n'ont pas été analysées.
3. Le nombre d'utilisateurs présents en mémoire n'est pas borné (200 lignes de log chacun) ; c'est négligeable à l'échelle actuelle.
4. Supprimer un utilisateur efface ses lignes par cascade, mais pas ses fichiers (`uploads/user_N`, `lettres_pdf/user_N`).
5. Les anciens `lettres_pdf/Lettre_*.pdf` à la racine ne sont plus servis ni nettoyés.
6. La mention « Paris, le » du PDF reste codée en dur, indépendamment de `FUSEAU_AFFICHAGE`.
7. L'intervalle Mistral de 2 s est une valeur raisonnable, pas une mesure ; il est à ajuster selon le palier du compte.
8. Toujours hérité des phases précédentes : compte Gmail partagé, pas de limitation de débit sur `/login`, pas de jeton CSRF.

## 7. À faire par l'humain

`data/chasseur_v2.db` est aujourd'hui en révision `0001`, avec 3 users, 4 profils et aucune autre ligne (lu en `mode=ro`). Après fusion de la branche, et application arrêtée :

```bash
cd /home/kenza/Bureau/chasseur_alternance
source venv/bin/activate
pip install -r requirements-dev.txt                  # pytest-timeout (déjà dans venv/)
cp data/chasseur_v2.db data/chasseur_v2_avant_2b.db  # sauvegarde
DATABASE_URL=sqlite:////home/kenza/Bureau/chasseur_alternance/data/chasseur_v2.db alembic upgrade head
DATABASE_URL=sqlite:////home/kenza/Bureau/chasseur_alternance/data/chasseur_v2.db alembic current   # attendu : 0002 (head)
```

Le préfixe `DATABASE_URL=` est inutile si cette ligne figure déjà dans le `.env`. Facultatif dans le `.env` : `MISTRAL_INTERVALLE_MIN_S=2` et `FUSEAU_AFFICHAGE=Europe/Paris` (valeurs par défaut).

## 8. Points à valider

1. **Risque de recontacter des entreprises.** `emails_contactes` est vide dans `chasseur_v2.db`, et les 1085 adresses de `data/emails_deja_envoyes.json` ne sont plus lues. Si le user 1 relance fetch, scraper et envoi, il réécrira à des entreprises déjà contactées. Je recommande de les reprendre, une seule fois, après la migration (l'opération est idempotente) :
   `DATABASE_URL=sqlite:////home/kenza/Bureau/chasseur_alternance/data/chasseur_v2.db python -c "import json; from database.dedup_db import ajouter_emails_contactes; print(ajouter_emails_contactes(1, json.load(open('data/emails_deja_envoyes.json'))))"`
   Les `mail_destinataires` des entreprises de l'ancienne base (users 1 et 3) ne sont pas repris non plus. Cette commande n'a pas été lancée : elle écrit dans `data/`.
2. Offres vues : la mémoire repart de zéro. Au premier run, chaque utilisateur se verra reproposer les offres FT encore en ligne, ce qui coûte des appels Mistral une fois.
3. Ordre de grandeur du limiteur (2 s) et maintien, ou non, des pauses propres de 10 s et 30 s, désormais en partie redondantes.
4. Statuts acceptés par `/api/maj_statut` : la liste inclut `nouveau`, `en_cours` et `archive`, en plus des 4 statuts du front.
5. Les PDF s'accumulent à raison d'un fichier par candidature (le précédent est supprimé) ; faut-il aussi une purge par âge ?
6. Ensuite : relire la branche, la fusionner dans `refonte-multiuser`, appliquer la migration (section 7), pousser.
