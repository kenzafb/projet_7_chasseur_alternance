# Phase 7 : IA locale avec Ollama, rapport

Branche `phase-7-ia-locale`, 14 octobre 2026, créée depuis `main`. Non poussée, non fusionnée. Lus avant de commencer : `DECISIONS.md` (dont D10 à D21) et le README. Rien écrit dans `data/` ni `.env` : la migration 0013 a été essayée sur une copie de `data/chasseur_v2.db` dans le dossier temporaire de la session (empreinte de l'original identique avant et après). Aucun appel réseau ni appel à Ollama dans les tests, ni pendant le travail : le serveur d'IA est remplacé par une fausse IA. Décisions D77 à D84.

## Commits

| Commit | Contenu |
|---|---|
| 6af6b75 | IA interchangeable : client au format compatible OpenAI, Ollama par défaut, un seul appel à la fois, IA injoignable bloquante |
| 91bfdc6 | Réponses structurées : schéma JSON imposé, validation Pydantic, un nouvel essai, réflexion coupée |
| c4b456e | Prompts d'analyse pour un petit modèle, un par mode, mode stage compris |
| 91e4ec8 | Analyse en différé des offres en attente, option du profil, migration 0013 |
| 08b8dc5 | Validation des emails du scraper : règles d'abord, l'IA pour les seuls cas douteux |
| a6b68ad | Lettre à la demande avec le modèle de lettre, message d'attente, trame du stage |
| 3c5b7b3 | `scripts/verifier_ia_locale.py` : serveur, modèles, vraies offres, tableau comparatif |
| a0a2693 | README et `.env.example` : IA locale avec Ollama |
| c865442 | Décisions D77 à D84, recette, ce rapport |
| 957d895 | Corrections : API native d'Ollama par défaut, format OpenAI en alternative |
| 79e5516 | Corrections : aucun retrait silencieux, test de démarrage |
| 14cfc43 | Corrections : score borné en Python, emails jugés sur énumérations, meilleur contact |
| 1aed7bc | Corrections : garde-fous de la validation d'office, provenance de chaque adresse |
| 72f1080 | Corrections : adresses écartées par l'IA visibles et validables |
| b185736 | Corrections : limites de 30, toute la file, temps pour la vider, mots-clés avant l'IA |
| (dernier) | Décisions D85 à D92, README, ce rapport |

## À lancer par l'humain

Depuis la racine du projet, dans cet ordre :

```bash
git checkout phase-7-ia-locale
source venv/bin/activate

# 1. Dépendances : mistralai n'est plus utilisé, httpx passe dans requirements.txt
pip install -r requirements-dev.txt
pip uninstall -y mistralai          # facultatif

# 2. Sauvegarde, puis migration 0013 (profils.analyse_auto, rien d'autre)
cp data/chasseur_v2.db data/chasseur_v2.db.avant-0013
venv/bin/alembic upgrade head

# 3. Ollama : un seul modèle chargé à la fois (12 Go de RAM)
sudo systemctl edit ollama
#   ajouter, puis enregistrer :
#   [Service]
#   Environment="OLLAMA_MAX_LOADED_MODELS=1"
sudo systemctl restart ollama
ollama --version                    # à noter dans le retour
ollama list                         # ministral-3:8b et ministral-3:3b doivent y être

# 4. .env : recopier depuis .env.example la section IA
#    ANALYSE_IA=true
#    IA_API=ollama
#    IA_BASE_URL=http://localhost:11434      (sans /v1 : API native)
#    IA_MODELE_ANALYSE=ministral-3:8b
#    IA_MODELE_LETTRE=ministral-3:8b
#    IA_MODELE_EXTRACTION=ministral-3:3b
#    IA_DELAI_S=600
#    IA_NUM_CTX=8192
#    IA_KEEP_ALIVE=10m
#    (MISTRAL_*, MODELE_MISTRAL* et IA_FORMAT_JSON ne sont plus lus : à retirer)

# 5. Vérification de l'IA locale sur de vraies offres (lecture seule, rien n'est écrit)
venv/bin/python scripts/verifier_ia_locale.py
venv/bin/python scripts/verifier_ia_locale.py --mode alternance
venv/bin/python scripts/verifier_ia_locale.py --mode stage
venv/bin/python scripts/verifier_ia_locale.py --modeles ministral-3:8b,ministral-3:3b,qwen3.5:9b

# 6. Tests, puis l'application
systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q
uvicorn main:app --reload --port 5002
```

Le script commence chaque modèle par le test de démarrage : « Test de démarrage ... : N s » (chargement compris) veut dire que le schéma et la coupure de la réflexion sont respectés ; sinon le message dit lequel est refusé ou ignoré, et le modèle n'est pas essayé plus loin. Pour `qwen3.5:9b`, c'est là que le ticket Ollama #14645 se verrait. Ensuite, une à deux minutes par offre et par modèle avec `ministral-3:8b`. Sur la copie de la base, les offres en attente sont 8 en alternance, 100 en job et 8 en stage : sans `--mode`, les 3 plus récentes sont des offres de job. Aucune entreprise n'a d'email douteux en attente : le script prend un cas fictif, signalé comme tel. Merci de reporter le tableau obtenu et la version d'Ollama.

La recette (`docs/RECETTE.md`) a une étape 4 réécrite (vérification de l'IA locale), une étape 5 adaptée (la recherche n'analyse plus) et une étape 5 bis nouvelle (analyse des offres en attente). Avec les limites de D91, mettre 2 dans le champ « Au plus » de l'étape 5 bis reste valable.

## 1. IA interchangeable (D77)

- `shared/ia.py` envoie `POST <IA_BASE_URL>/chat/completions` avec `httpx` (une seule fonction de sortie réseau, `_poster`, remplacée par la fausse IA dans les tests). `IA_API_KEY` part en `Authorization: Bearer` seulement si elle est remplie. `lister_modeles()` lit `GET <IA_BASE_URL>/models`.
- Un verrou commun à tout le processus : un seul appel à la fois, tous utilisateurs et pipelines confondus. Une lettre demandée pendant une analyse attend la fin de l'offre en cours.
- Délais : 10 s pour ouvrir la connexion (au-delà : injoignable), `IA_DELAI_S` (600 s) pour la réponse.
- Erreurs : connexion impossible, `IAInjoignable` (bloquante), « IA locale injoignable : vérifie qu'Ollama tourne (IA_BASE_URL = ...) » ; 400, 401, 403, 404 et 422 bloquantes (404 : « installe-le (ollama pull <modèle>) ») ; erreur 500 d'Ollama qui parle de mémoire, bloquante (« Mémoire insuffisante... OLLAMA_MAX_LOADED_MODELS=1 ») ; autres 5xx et 429 passagères, retentées une fois après 5 s ; délai dépassé, passagère sans nouvel essai (il coûterait encore 10 minutes).
- `<think>...</think>` éventuel retiré de la réponse.
- `scripts/verifier_mistral.py`, `tests/test_limiteur_mistral.py` et le limiteur de débit (inutile en local) sont retirés ; `mistralai` quitte `requirements.txt`, `httpx` y entre.

## 2. Réponses structurées (D78)

- `shared/schemas_ia.py` : `AnalyseOffre` (score entier de 1 à 10, éligibilité, points forts, points faibles, domaine, résumé, tous obligatoires), `LettreIA` (bloc destinataire, paragraphe non vide), `ValidationEmail` (valide).
- `appeler_structure` envoie le schéma en `response_format` de type `json_schema` (Ollama le traduit en grammaire de sortie), lit l'objet JSON de la réponse (blocs de code et texte autour tolérés), le valide, le redemande une fois s'il est invalide, puis lève `ReponseInvalide` (passagère) : l'offre est sautée et reste « non analysée ».
- Réflexion coupée : `reasoning_effort: "none"` dans chaque requête, sauf `IA_REFLEXION=true`.
- Un paramètre facultatif (`reasoning_effort`, `response_format`) refusé par le serveur (400 ou 422 qui le nomme) est retiré pour ce serveur et ce modèle jusqu'au redémarrage, et la requête renvoyée aussitôt, sans compter d'essai. `IA_FORMAT_JSON=json` ou `aucun` pour un serveur qui ne sait pas contraindre sa sortie.

## 3. Prompts pour un petit modèle (D79)

- Un message système d'une phrase, puis : rôle, CANDIDAT (champs utiles du profil, chacun ramené à 400 caractères), OFFRE (titre, entreprise, lieu, description ramenée à `IA_LONGUEUR_DESCRIPTION`, 2000 caractères), règles d'inéligibilité, barème, consigne du domaine, et le schéma JSON écrit en toutes lettres. Environ 1700 caractères hors description, contre 3000 (alternance) à 4500 (job) avant.
- Plus d'identité (prénom, nom, ville) dans les prompts d'analyse : elle ne sert pas à noter.
- Alternance : niveau visé, formation, ce qu'elle apportera, compétences, expérience, trois projets au plus, langues, ce qu'il faut éviter, domaines. Règles inchangées sur le fond (hors domaine, niveau nettement supérieur, 3 ans d'expérience, poste senior sauf école ; « Hors domaine » écrit tel quel).
- Job : mêmes préférences qu'avant, « N'applique AUCUNE préférence que le profil n'exprime pas » gardé mot pour mot.
- Stage, nouveau : formation, établissement, missions visées, période en toutes lettres avec la durée en semaines, domaines. Inéligible si ce n'est pas un stage pour un étudiant, hors domaine, niveau nettement supérieur, ou dates incompatibles (durée minimale nettement plus longue, début après la fin de la période) ; dates absentes de l'offre sans pénalité.
- En mode stage, une offre d'école n'est plus archivée après analyse (D74 : une école peut accueillir un stagiaire) ; avant, l'analyse passait par le prompt d'alternance et archivait.

## 4. Analyse en différé (D80)

- La recherche n'appelle plus jamais l'IA : France Travail et LBA écrivent leurs offres « non analysées », archivées seulement par mots-clés (comme sans IA depuis D20), marquées vues. Limite `offres` : 100 par défaut, 500 au plus, champ `max_offres` (l'ancien `max_analyses` est refusé en 422 sur cette route).
- `POST /api/analyse` (mode obligatoire, corps `{max_analyses}`) : offres du mode au verdict `non_analysee` et non archivées, des plus récentes aux plus anciennes (date de publication, puis ordre d'insertion), au plus `analyses` par lancement (10 par défaut, 200 au plus, borné par le nombre en attente avec « demandé : X, ramené à Y »). Refus en 400 : IA désactivée, profil incomplet, rien en attente, analyse déjà en cours (tous modes confondus, comme les autres pipelines).
- Chaque analyse est écrite dès qu'elle est obtenue (score, verdict, éligibilité, points, domaine, résumé) avec l'archivage qui en dépend (note basse, hors domaine, école en alternance). Échec passager : l'offre reste en attente, la suivante est traitée. Erreur bloquante : arrêt, message dans le bandeau et les logs, rien d'écrit pour l'offre en cours.
- `POST /api/analyse/stop` : arrêt après l'offre en cours. `GET /api/analyse/statut` : état et nombre en attente. `/api/statut_pipelines` renvoie aussi `analyse`.
- Bandeau : « Analyse 3/10, environ 12 min restantes » et sa jauge ; temps restant : durée moyenne des offres déjà traitées fois le nombre restant. Les offres notées s'affichent au fil de l'eau. Le bouton « Arrêter » du bandeau arrête l'analyse si elle tourne, sinon le pipeline des spontanées.
- Page Offres : carte « N offre(s) en attente d'analyse » avec le modèle utilisé, la limite et le bouton ; sans IA, la carte le dit et n'a pas de bouton. Le bouton « Analyser » d'une offre affiche « Analyse en cours... (1 à 2 min) ».
- Profil, dans chaque mode : case « Analyser automatiquement les offres en attente après chaque recherche », colonne `profils.analyse_auto` (migration 0013, faux pour les profils existants). Après une recherche réussie, l'analyse part avec la limite par défaut ; sans IA, une ligne dans les logs et rien d'autre.

## 5. Validation des emails (D81)

- `shared/referentiels/validation_emails.txt`, fichier de données commenté : préfixes de contact ou de recrutement (contact, info, accueil, rh, recrutement, emploi, jobs, carrieres, candidature, stage, alternance...), préfixes écartés (dpo, rgpd, presse, legal, webmaster, noreply, facturation, support, newsletter...), messageries grand public (gmail.com, orange.fr, free.fr...). Un préfixe vaut pour la partie avant @ entière ou suivie de `.`, `-`, `_` ou d'un chiffre (`rh.paris@`, `contact2@`).
- Ordre : adresse de `emails_exclus.txt` (D47) ou préfixe écarté, écartée ; même domaine que le site (sous-domaines compris) et préfixe de contact, validée ; tout le reste est douteux (adresse nominative du domaine, autre domaine, messagerie grand public, site inconnu).
- Douteuse et IA active : le modèle d'extraction (`ministral-3:3b`) reçoit le nom de l'entreprise, le domaine du site, l'adresse et 200 caractères de texte de part et d'autre de l'adresse dans la page ; réponse `{"valide": true ou false}`. Vrai : validée ; faux : écartée (journalisée, plus gardée). Échec passager : l'adresse reste douteuse ; erreur bloquante : IA coupée pour la suite du lancement, un seul message. Sans IA : les douteuses restent « non validées ».
- Stockage : `emails_trouves` garde les validées puis les douteuses ; `extra.emails_douteux` les douteuses, `extra.contextes_emails` le texte qui les entoure ; `emails_non_valides` vaut vrai tant qu'il en reste. Une entreprise d'avant la phase 7 marquée non validée a toutes ses adresses douteuses.
- Envoi : seules les adresses validées partent, et ne comptent qu'elles dans le maximum d'envoi. Une entreprise qui a une adresse validée et une douteuse part vers la validée.
- « Relancer la validation IA » ne relit plus les sites : règles puis IA sur les seules douteuses, avec le texte gardé (vide pour les entreprises d'avant). La validation à la main valide toutes les douteuses de l'entreprise. La carte « Emails non validés » liste les douteuses et, en dessous, les adresses déjà validées.
- L'extraction des emails, téléphones et contact RH par l'IA (prompt de 2000 caractères de page plus 3000 de HTML) disparaît : la lecture directe trouve les emails, l'IA ne fait plus que trancher.

## 6. Lettre de motivation (D82)

- Prompt raccourci, schéma JSON explicite, consigne par mode ; règles de fond conservées (pas de « Je » en tête, rien d'inventé, écriture neutre, pas de superlatif, ni formation ni disponibilité).
- Le mode stage a sa trame par défaut (« Objet : Candidature pour un stage », dates renvoyées au CV) et son prompt (missions visées) : il retombait sur la trame d'alternance.
- La route reste synchrone. La fenêtre de la lettre affiche « Rédaction de la lettre par l'IA locale... N s », prévient qu'une analyse en cours la retarde, bloque la zone et les boutons ; fermée pendant la rédaction, la lettre est quand même enregistrée et la liste rechargée.

## 7. Interrupteur, `.env.example`, README (D83)

- `ANALYSE_IA=false` : aucun appel nulle part (dernier rempart dans `appeler_ia`), analyse en attente refusée, lettre et réanalyse refusées (503), revalidation refusée (400), analyse automatique non lancée. Les règles des emails s'appliquent toujours.
- `.env.example` : toutes les variables `IA_*`, et `ANALYSE_IA=true`.
- README : encadré sur l'IA locale, analyse en différé et validation des emails décrites, section « IA locale (Ollama) » (installation, modèles conseillés avec les vitesses mesurées, `OLLAMA_MAX_LOADED_MODELS=1` par `systemctl edit ollama`, script de vérification).

## 8. Script de vérification (D84)

- `scripts/verifier_ia_locale.py [--modeles a,b] [--offres 3] [--user ID] [--mode alternance|job|stage]`.
- Base ouverte en lecture seule par SQLite (`mode=ro`) : toute écriture serait refusée par SQLite lui-même (testé). Seule une base SQLite est prise en charge.
- Pour chaque modèle : un appel minimal (chargement mesuré à part, pour ne pas fausser la première offre), puis les mêmes offres et le même email, un seul essai par réponse (on mesure ce que le modèle répond du premier coup). Sans `--modeles` : modèle d'analyse pour les offres, d'extraction pour l'email.
- Code de sortie 0 si le serveur répond et qu'au moins une réponse est valide. `ANALYSE_IA=false` est ignoré pour ce test, avec un message.

## Tests

856 tests passent (784 au départ), sous `systemd-run --user --scope -p MemoryMax=2G`, en 50 secondes environ. La fausse IA (`tests/conftest.py`, fixture `ia`) remplace le serveur : elle enregistre chaque corps de requête et renvoie une réponse, une file de réponses, une erreur HTTP ou une exception réseau. Nouveaux fichiers : `test_ia.py` (client, erreurs, verrou, schémas, paramètres refusés), `test_analyse_differee.py`, `test_validation_emails.py`, `test_verifier_ia_locale.py`. Réécrits : les tests de la recherche (elle n'appelle plus l'IA), du scraper et de la revalidation des emails.

Non vérifié faute d'appel réel (interdit ici, c'est l'objet du script de l'étape 5) : que la version d'Ollama installée accepte `response_format` de type `json_schema` et `reasoning_effort` ; qu'elle les refuse ne bloque rien (ils sont retirés), mais la sortie ne serait plus contrainte.

## Limites

- La recherche limitée à 100 offres par lancement en remplit plus que l'IA n'en analyse : 100 offres à une à deux minutes chacune, c'est deux à trois heures. La file d'attente grossit vite, surtout en job (100 en attente sur la copie).
- Les pipelines vivent en mémoire : un redémarrage (ou `--reload` d'uvicorn après une modification de code) coupe l'analyse en cours ; les offres déjà écrites le restent, les autres attendent.
- L'estimation du temps restant ne tient pas compte d'une lettre qui passe entre deux offres, ni du chargement d'un autre modèle (validation des emails pendant une analyse) : sur 12 Go, chaque changement de modèle recharge des gigaoctets.
- Téléphones et contact RH ne sont plus relevés par le scraper (ils ne l'étaient plus depuis l'arrêt de l'IA en ligne).
- Une adresse écartée par l'IA n'est gardée nulle part (seulement dans les logs).

## Corrections après le rapport (D85 à D92)

- **API native d'Ollama par défaut** (`IA_API=ollama`) : `POST /api/chat` avec `"think": false` au premier niveau, le schéma dans `"format"`, `stream` faux, `options.num_ctx` (8192) et `options.temperature` (0,1 analyse et emails, 0,6 lettre) ; `keep_alive` au premier niveau, là où l'API le lit, et non dans `options` comme le demandait le retour ; liste des modèles par `/api/tags`. `IA_API=openai` garde l'ancien comportement. Une requête qui mêlerait `tools` et un format est refusée avant d'être envoyée.
- **Aucun mode dégradé** : le retrait automatique d'un paramètre refusé est supprimé ; un refus de `format` ou `think` (ou de leurs équivalents OpenAI) et un texte de réflexion dans une réponse (`message.thinking`, `reasoning_content`, `<think>`) sont des erreurs bloquantes. Test de démarrage (`shared.ia.verifier_demarrage`) avant le premier appel structuré de chaque modèle, au lancement de chaque analyse et dans le script ; réussi, il n'est pas refait dans le même processus.
- **Contrôles en Python** : score sans bornes dans le schéma, ramené à 0..10 par Pydantic (verdict « inéligible » de 0 à 2). Emails douteux jugés en un appel par entreprise : `valides` est une énumération des adresses douteuses, `meilleur_contact` une énumération des adresses trouvées ou null, tout revérifié en Python ; le meilleur contact n'est gardé que s'il est validé, et s'affiche dans la page Spontanées. Le prompt du stage ne parle plus d'alternance (écartée en code).
- **Validation d'office avec garde-fous** : `site_fiable` exige un site dont le domaine correspond au nom de l'entreprise (même règle que la recherche du site), qui n'est ni un annuaire, ni un sous-domaine d'hébergeur (`[hebergeurs]` : wixsite.com, wordpress.com, blogspot.com...), ni un fournisseur générique (`[fournisseurs_generiques]`, qui remplace `[domaines_messagerie]`). Provenance gardée par adresse (`extra.validation_emails`) et affichée : validée par règle, par l'IA, à la main, fournie par LBA, validée avant la phase 7, non validée, écartée par l'IA.
- **Adresses écartées par l'IA** : gardées (`extra.emails_ecartes_ia`), jamais envoyées, listées dans la carte « Emails non validés » avec « Valider quand même » ; `POST /api/spontanees/valider_adresse` valide une seule adresse (douteuse ou écartée). « Tout valider » reste pour l'entreprise entière.
- **Limites** : 30 offres par recherche et 30 analyses par lancement avec l'IA, 100 offres sans elle ; case « Toute la file (lancement de nuit) » ; la carte de la page Offres donne le temps pour vider la file (moyenne des analyses chronométrées dans le processus, 90 s par offre avant toute mesure, signalé comme tel). Les mots-clés d'archivage sont réappliqués juste avant l'IA.

Tests : 894 passent sous plafond mémoire.

## Points à valider

Les points 1 à 15 ci-dessous ont été tranchés le 14 octobre 2026 (D88 à D92) ; le point 6 est remplacé par D87. Nouveaux points :

16. **keep_alive** au premier niveau de la requête (l'API d'Ollama l'y lit) plutôt que dans `options`.
17. **Estimation de la file** : moyenne des 50 dernières analyses du processus (perdue au redémarrage), 90 s avant toute mesure.
18. **Test de démarrage** : refait à chaque redémarrage de l'application, une fois par modèle ; il vérifie la forme de la réponse, pas les valeurs (7, « ok »).
19. **Meilleur contact** : affiché seulement ; l'envoi part toujours vers toutes les adresses validées.

Points tranchés :

1. **Limites par défaut** : 100 offres par recherche (500 au plus) ; 10 analyses par lancement (200 au plus). Faut-il baisser celle de la recherche, ou monter celle de l'analyse ?
2. **Délai** : 600 s par réponse, sans nouvel essai après un délai dépassé ; une erreur 5xx retentée une fois après 5 s.
3. **File d'attente** : offres non analysées et non archivées seulement (celles archivées par mots-clés à l'insertion ne sont jamais analysées), tous statuts confondus, triées par date de publication.
4. **Archivage après analyse** : appliqué seulement si l'offre est encore « nouvelle » ; une offre déjà déplacée par l'utilisateur (en cours, envoyée...) garde son statut et reçoit sa note.
5. **Bouton « Analyser » d'une offre** : il écrit désormais le domaine et applique l'archivage complet, comme le pipeline (avant : école seulement, et pas le domaine).
6. **Score strict** : un score hors de 1 à 10 rend la réponse invalide (redemandée une fois), au lieu d'être ramené dans les bornes comme avant.
7. **Identité retirée des prompts d'analyse**, champs du profil ramenés à 400 caractères, trois projets au plus.
8. **Prompt du stage** et **trame par défaut de la lettre de stage** : à relire.
9. **Règles des emails** : une adresse nominative du domaine du site (`camille.martin@acme.fr`) est douteuse, pas validée d'office ; une adresse de messagerie grand public toujours douteuse ; au plus 5 adresses par entreprise soumises aux règles (les mieux notées, comme avant).
10. **Avis négatif de l'IA** : l'adresse est écartée définitivement (pas gardée pour une validation à la main) ; en cas de doute, la consigne demande « false ».
11. **Sans IA, les règles valident** : les adresses de contact du domaine du site partent désormais sans IA ni validation à la main ; avant (D19), toutes les adresses trouvées sans IA attendaient une validation.
12. **Validation par adresse** : une entreprise part vers ses adresses validées même s'il lui reste des douteuses (avant : tout ou rien par entreprise).
13. **Revalidation sans relire le site** ; pour les entreprises d'avant la phase 7, l'IA juge sans texte autour de l'adresse.
14. **`ANALYSE_IA=true` dans `.env.example`** ; le script de vérification ignore `ANALYSE_IA=false`.
15. **Modèles conseillés** : rester sur `ministral-3:8b` et `ministral-3:3b`, ou en changer après la comparaison du script.
