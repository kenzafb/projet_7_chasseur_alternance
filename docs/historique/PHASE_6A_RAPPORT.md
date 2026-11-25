# Phase 6a : préparation du mode stage, rapport

Branche `phase-6a-modes`, 9 octobre 2026, créée depuis `refonte-multiuser`. Non poussée, non fusionnée. Lus avant de commencer : `DECISIONS.md` (dont D1 et D2, reportées « au mode stage »), `SPEC_SOURCES.md`, la fin du rapport 5d. Rien écrit dans `data/` ni `.env` ; `data/chasseur.db` et `data/emails_deja_envoyes.json` lus en lecture seule pour l'essai à blanc du point 3 (empreintes identiques avant et après). Aucun appel réseau dans les tests. L'IA reste coupée et rien de ce qui suit n'en dépend. Décisions D64 à D67.

## Commits

| Commit | Contenu |
|---|---|
| d0308b9 | Sirene : cœurs d'abord, effectifs inconnus en requête à part, répartition dans les logs |
| 6c803e1 | État d'envoi par entreprise et par mode, migration 0011 |
| 5a74cf2 | `scripts/importer_contacts_historiques.py` |
| 8a4b900 | Une URL par mode, page d'accueil, `/stage` « bientôt disponible », mode explicite pour l'API |
| (dernier) | README, décisions D64 à D67, ce rapport |

## À lancer par l'humain

Depuis la racine du projet, dans cet ordre :

```bash
git checkout phase-6a-modes

# 1. Sauvegarde, puis migration 0011 (déplace l'état d'envoi dans entreprises_modes)
cp data/chasseur_v2.db data/chasseur_v2.db.avant-0011
venv/bin/alembic upgrade head
venv/bin/alembic check

# 2. Historique des adresses contactées : classement seul, puis ce que l'import ferait pour le user 1
venv/bin/python scripts/importer_contacts_historiques.py --dry-run
venv/bin/python scripts/importer_contacts_historiques.py --dry-run --user 1

# 3. Import réel, groupe a seulement (défaut) ; ajouter b ou c seulement après lecture des exemples
venv/bin/python scripts/importer_contacts_historiques.py --user 1
# venv/bin/python scripts/importer_contacts_historiques.py --user 1 --groupes a,b

# 4. Relancer l'application, puis refaire l'essai Sirene (M18, limite 10)
uvicorn main:app --reload --port 5002
```

Pour l'étape 4 : ouvrir http://localhost:5002, choisir Alternance, page Spontanées, « Récupérer » avec une limite de 10. Les logs doivent montrer, pour chaque recherche, le groupe et le nombre d'établissements annoncés par Sirene, puis une ligne finale du type « Sirene : N nouvelles entreprises (X cœurs, Y transverses) ». Avec assez de cœurs, Y vaut 0.

Retour arrière de la migration si besoin : `venv/bin/alembic downgrade 0010` (l'état du mode alternance revient dans `entreprises` ; celui des autres modes est perdu), ou recopier la sauvegarde.

## 1. Sirene : cœurs d'abord (D64)

Le plan des recherches était déjà dans l'ordre cœurs, secteurs, transverses ; la limite s'arrêtait bien au premier groupe qui la remplissait. Le défaut était ailleurs : avec « effectifs inconnus » coché (le défaut), la clause de taille des cœurs valait `(trancheEffectifsUniteLegale:(11 OR ...) OR -trancheEffectifsUniteLegale:*)`. En Lucene, `-x` dans un OU est une exclusion (MUST_NOT), pas une alternative : la clause garde ce qui a une tranche de la liste ET n'a pas de tranche, c'est-à-dire rien. Les cœurs rendaient 0, les transverses (sans cette clause) remplissaient seuls la limite. La vérification de la phase 5d avait essayé `-trancheEffectifsUniteLegale:*` seule (acceptée, aucun résultat), jamais dans un OU ; l'API simulée lisait ce OU comme une union.

Corrigé :
- `filtre_tailles` ne rend plus que les tranches ; `filtre_inconnus` rend la clause d'absence, employée par une requête à part en ET (cœurs puis cœurs « effectif inconnu », secteurs de même). Elle ne coûte qu'une requête (404 attendu : D54 n'a trouvé aucune unité sans tranche).
- `tests/faux_sirene.py` suit la sémantique Lucene : une clause `-x` dans un OU exclut. Un test vérifie que l'ancienne clause ne rend rien.
- Logs : « Sirene, cœurs : 8 établissements annoncés, 8 nouvelles » par recherche, et une répartition finale qui nomme tous les groupes du plan, zéros compris (« 10 nouvelles entreprises (8 cœurs, 2 transverses) »).

## 2. État d'envoi par entreprise et par mode (D65)

**Schéma (migration 0011).** Nouvelle table `entreprises_modes` : `entreprise_id` et `user_id` (suppression en cascade), `mode`, `selectionnee_le`, `mail_envoye`, `mail_envoye_le`, `statut_suivi`, `mail_destinataires`, `mail_note`, `historique` ; unique sur (entreprise, mode). `entreprises` perd `mode`, `mail_envoye`, `mail_envoye_le`, `statut_suivi` ; `mail_destinataires` et `mail_note` quittent `extra`. Chaque entreprise existante reçoit une ligne en mode alternance avec son état. Ordre imposé par SQLite : la recopie de table du mode batch d'Alembic supprime l'ancienne table `entreprises`, ce qui, clés étrangères actives, viderait `entreprises_modes` par cascade ; la migration modifie donc `entreprises` avant de créer la nouvelle table (et après l'avoir lue au retour arrière). Toute future migration qui recopie `entreprises` devra en tenir compte (commentaire dans la migration).

**Code.** `database/entreprises_db.py` : lectures et écritures par mode (`lire_entreprises`, `calculer_stats`, `compter_a_scraper`, `lire_a_valider`, `lire_entreprises_envoyees`, `modifier_statut_suivi`, `sauvegarder_entreprises`), le mode `alternance` par défaut comme `profil_db` et `candidatures_db`. Le format des dicts ne change pas pour l'envoyeur et le scraper, qui reçoivent le mode. Ajout d'entreprises (Sirene et LBA) : une entreprise déjà connue dans un autre mode (même SIRET, puis SIREN, ou identifiant LBA) n'est pas dupliquée, elle est sélectionnée dans le mode avec ses données déjà scrapées. « Récupérer » lit le profil du mode ; LBA n'est interrogé que dans les modes qui l'utilisent (alternance).

**Étiquette.** `contacts_autres_modes` : pour chaque entreprise, un contact par autre mode, soit un envoi enregistré dans ce mode, soit une de ses adresses déjà dans `emails_contactes` de ce mode ; date la plus ancienne connue. Affichée dans la page Spontanées et le suivi (« déjà contactée en alternance le 29/05/2026 »). L'envoyeur ne la regarde pas.

## 3. Import de l'historique (D66)

`scripts/importer_contacts_historiques.py` :
- **Classement** d'après l'ancienne base, ouverte en lecture seule : une adresse appartient à une entreprise si elle est dans ses emails trouvés ou dans les destinataires de son mail. Groupe a : au moins une entreprise envoyée (date : le plus ancien envoi, heure locale de l'ancienne application) ; b : seulement des entreprises non envoyées ; c : aucune. `--dry-run` affiche les effectifs et 5 exemples par groupe (avec les entreprises et la date).
- **Import** (`--user`, `--groupes`, a par défaut) : adresses dans `emails_contactes` en mode alternance (date de l'ancien envoi pour a, inconnue sinon) ; entreprises de l'utilisateur marquées si elles ont le SIRET ou le SIREN d'une ancienne entreprise qui contient l'adresse, ou l'adresse parmi leurs emails. Marquage : ligne alternance `mail_envoye`, `historique`, destinataires, note « contactée avant la refonte (historique) » ; une entreprise déjà envoyée par l'application n'est pas touchée. Relançable sans doublon.
- **Refus** : `--user` absent pour l'import réel, groupe inconnu, utilisateur introuvable, ancienne base absente, ou `DATABASE_URL` qui désigne l'ancienne base (c'est le défaut sans `.env`).
- **Essai à blanc réel** (sans `--user`, donc sans lire la nouvelle base) : 1085 adresses ; a 798, b 11, c 276.

## 4. Une URL par mode (D67)

- **Pages.** `/` : choix du mode (Alternance, Job, Stage « bientôt disponible »). `/alternance` et `/job` : l'application, `<html data-mode>` posé par le serveur, titre du mode, bascule de mode devenue des liens (la page courante, `#profil` par exemple, est gardée). `/stage` : page « bientôt disponible ».
- **API.** Dépendance `mode_requis` sur chaque route qui lit ou écrit des données d'un mode (24 routes sur 23 chemins, dont `/api/mode`) : paramètre `mode` obligatoire, 400 s'il manque, s'il est inconnu ou s'il vaut `stage`. Le front l'ajoute à chaque appel `/api/` (`avecMode` dans `api.js`, lien des pièces jointes compris) ; l'URL du PDF de lettre le contient. `POST /api/mode` (bascule en session) supprimé ; `mode_courant` retiré de `auth/securite.py`. Sans mode : compte d'envoi, logs, état des pipelines, arrêt, référentiels, validation manuelle des emails (donnée commune aux modes).
- **Anciennes URL.** Inscription : redirection vers `/alternance?bienvenue=1` ; `/?bienvenue=1` y redirige aussi. Liens `/#candidatures` : la page d'accueil les renvoie vers la même page dans le mode de l'ancienne session (alternance à défaut).
- **Pipelines.** Toujours un seul de chaque type par utilisateur, tous modes confondus (plafond quotidien et compte d'envoi communs). L'état garde le mode du lancement ; un second lancement est refusé avec « (mode job) », et le bandeau d'un autre onglet signale un traitement en cours dans l'autre mode.
- **Protection.** `utilisateur_requis` reste la dépendance du routeur, résolue avant le mode : sans session, 401 ou redirection vers `/login` sur toutes les routes, mode donné ou non. `test_routes_protegees` couvre les nouvelles pages et vérifie l'inventaire des routes du mode.

## Tests

`systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q` : **709 passed** (660 au début de la phase). Chaque commit de thème passe seul. Nouveaux ou adaptés :
- `test_sirene.py` : clauses de taille et d'absence séparées, plan (cœurs, cœurs effectif inconnu, transverses), essai réel reproduit (8 cœurs puis 2 transverses pour une limite de 10 ; 5 cœurs et 0 transverse pour une limite de 5), ancienne clause sans résultat.
- `test_etat_par_mode.py` (9) : entreprise unique et données communes, envoi propre au mode et étiquette sans blocage, adresse contactée dans un autre mode, routes par mode, isolation du suivi, Sirene en job reprenant une entreprise de l'alternance, LBA et limite, migration 0011 montée et retour arrière, cascade.
- `test_importer_contacts_historiques.py` (5) : classement et essai à blanc, import du groupe a (SIREN, suivi « historique », étiquette en job, plus de visée en alternance, relance sans doublon), groupes b et c et entreprise déjà envoyée, refus, ancienne base intacte.
- `test_modes_url.py` (5) et `test_routes_protegees.py` : accueil, pages des modes, `/stage`, anciennes URL, deux onglets dans deux modes sur la même session, pipeline d'un autre mode signalé ; chaque route du mode refusée sans mode, avec `stage` ou un mode inconnu, et fermée sans session.
- Client de test `ClientDeMode` (`tests/conftest.py`) : comme le front, ajoute le mode de l'onglet aux appels `/api/` ; les anciens `client.post("/api/mode", ...)` deviennent `client.mode = "job"`.

Essai de l'application sur une base temporaire (hors `data/`) : inscription, `/`, `/alternance`, `/job`, `/stage`, `/?bienvenue=1`, API sans et avec mode, `alembic check` propre. `node --check` propre sur tous les modules. L'interface n'a pas été vérifiée dans un navigateur.

## Limites

- **Profil job et Sirene.** « Récupérer » en mode job lit le profil job, qui n'a dans l'interface ni départements ni tailles des candidatures spontanées : toute l'Île-de-France, toutes les tailles sauf « sans salarié ». Les domaines du profil job servent comme en alternance.
- **Un pipeline de chaque type par utilisateur.** Deux onglets ne se gênent pas pour lire et écrire, mais une recherche (ou une étape des spontanées) lancée dans un mode bloque le même type de lancement dans l'autre jusqu'à la fin.
- **Étiquette par adresse partagée.** Une adresse générique commune à plusieurs entreprises (un groupe, par exemple) étiquette toutes celles qui la portent.
- **Ancien mode en session.** Il ne sert plus qu'aux anciens liens `/#page` ; il disparaîtra avec les sessions existantes.

## Points à valider

1. **Entreprise connue dans un autre mode = nouvelle pour ce mode** : sélectionnée dans le mode et comptée dans la limite de « Récupérer », données scrapées reprises.
2. **Contacts « historique »** : comptés à part (`historiques`) et non dans « Envoyés » ni dans la répartition par source ; affichés dans le suivi d'alternance avec la mention « historique », jamais « à relancer ».
3. **Import, correspondance des entreprises** : par SIRET ou SIREN des anciennes entreprises qui contiennent l'adresse, ou par l'adresse elle-même ; une entreprise sélectionnée seulement en job reçoit quand même une ligne alternance « historique ».
4. **Dates de l'ancienne base** lues comme heure de Paris (l'ancienne application écrivait `datetime.today()`).
5. **Validation des emails commune aux modes** : valider à la main dans un mode vaut pour les autres.
6. **Pipelines par utilisateur et par mode** plutôt que par utilisateur, si deux lancements en parallèle dans deux onglets sont souhaités (le plafond quotidien resterait commun).
7. **Départements et tailles des spontanées dans le profil job** (aujourd'hui absents de l'interface, défauts appliqués).
