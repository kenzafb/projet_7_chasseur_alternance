# Phase 4b : correctifs de la recette réelle, rapport

Branche `phase-4-recette`, 8 octobre 2026. Non poussée, non fusionnée. Lus avant de commencer : `DECISIONS.md`, `PHASE_4_RAPPORT.md`. Rien écrit dans `data/` ni `.env` ; `data/chasseur_v2.db` lue en lecture seule (`mode=ro`), elle est en révision 0006. Aucun appel réseau dans les tests. Pas de migration.

## Commits

| Commit | Contenu |
|---|---|
| cc92398 | Décisions de la phase 4 : mode test d'office à la création d'un compte (D7), limite appliquée affichée dans la confirmation et les logs (D6), D5 et D8 validées |
| 0bebf5a | Correctifs de la recette (points 1 à 6), tests, décisions D9 à D14, `.env.example`, README, recette |
| (dernier) | Ce rapport |

## Ce qui change

1. **Modèles Mistral.** `shared.config.modele_mistral(usage)` : `MODELE_MISTRAL_ANALYSE`, `_LETTRE` ou `_EXTRACTION`, sinon `MODELE_MISTRAL`, sinon `mistral-medium-latest` (analyse, lettre) et `mistral-small-latest` (extraction). Relu à chaque appel ; `appeler_mistral(..., usage=...)`. L'usage du SDK a été vérifié contre la documentation livrée avec mistralai 2.4.9 (`from mistralai.client import Mistral, errors`, `chat.complete`, `models.list()`, `errors.MistralError.status_code`, `httpx.RequestError` pour le réseau) : déjà conforme, seule la gestion d'erreurs reposait sur le texte de l'exception. `scripts/verifier_mistral.py` liste les modèles de la clé, appelle chaque modèle configuré (5 tokens) et affiche OK ou l'erreur expliquée ; code de sortie 1 en cas d'échec.
2. **Plus de résultat inventé.** Les deux `except` de l'analyseur qui renvoyaient score 5 et « Erreur analyse » sont supprimés ; une réponse sans score entier lève une erreur passagère. `ErreurIABloquante` (400, 401, 403, 404, 422 ; message dédié pour le 403 d'abonnement, le 401 et le 404) arrête la recherche : état « Erreur : ... », log « Recherche arrêtée », LBA comprise. `ErreurIAPassagere` (429, 5xx, réseau, après retries ; réponse illisible) fait sauter l'offre avec un log. Une offre n'est marquée vue qu'après analyse et écriture (`chercher_offres(marquer=False)`, marquage une à une), donc une offre en échec n'est ni insérée, ni vue, ni archivée. Lettre : plus de lettre sans paragraphe ; réanalyse et lettre répondent 503 (configuration) ou 502 sans rien enregistrer ; la fenêtre de lettre se ferme sur une alerte au lieu d'afficher « Erreur : » dans le texte. Le front affiche l'erreur d'un pipeline terminé dans le bandeau jusqu'à un clic.
3. **Règle « public spécifique ».** Avant : archivage dès que la description (texte de l'offre FT, description de l'entreprise, ou description LBA) contenait « boeth », « maazi » ou « situation de handicap », indépendamment de l'analyse ; la mention standard « ce poste est ouvert aux personnes en situation de handicap » suffisait donc, et une analyse échouée (score 5 inventé) n'empêchait rien. Après : `reserve_public_specifique` ne retient que des tournures de réservation ou d'exigence (réservé, exclusivement, uniquement ou seulement aux ; destinée aux ; poste ou offre BOETH ou RQTH ; RQTH obligatoire, exigée, requise ; vous devez être bénéficiaire ou titulaire), sur la description et le titre. « maazi » est abandonné (sens inconnu, aucune occurrence légitime trouvée).
4. **Scraper.** `scraper_et_extraire(ia=...)` : si Mistral échoue, les emails lus dans les pages (mailto, regex, déobfuscation, mêmes filtres et score qu'avant) sont gardés avec `emails_non_valides` (dans `extra`, relu) et le log « (non validés par l'IA) ». Erreur bloquante : un seul message, IA coupée pour le reste du lancement, plus aucun appel.
5. **Limites bornées.** `/api/spontanees/stats` renvoie `a_scraper` et `a_envoyer` (même critère que les pipelines : `a_scraper`, `adresses_nouvelles`, dédoublonnage du mode courant). Le front ajuste le maximum des champs et l'affiche (« max 3, 3 disponibles », « aucune entreprise à contacter ») ; le serveur borne la limite (« demandé : X, ramené à Y ») et refuse en 400 un lancement sans rien à traiter.
6. **Mail de test** vers l'adresse d'expédition uniquement ; l'adresse de connexion est refusée.

## Candidatures « public spécifique » de `data/chasseur_v2.db`

Trois, aucune légitime : CAF de Paris « Développeur Applicatif - Alternance » (user 1) et deux offres IN'LI (user 3). Toutes portent la mention d'égalité des chances (« ce poste est ouvert aux personnes en situation de handicap », « ouvert, à compétences égales, aux candidatures de personnes en situation de handicap ») et toutes ont un score 5 « Erreur analyse » inventé. Plus largement, les **5 candidatures** de la base (user 1 : 3, user 3 : 2) viennent d'analyses échouées, et leurs offres sont marquées vues (7 lignes) : elles ne reviendront pas d'elles-mêmes.

## Tests

`systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q` : **398 passed** (325 à la fin de la phase 4). Nouveaux : `test_mistral.py` (33 : modèles par défaut, commun, par usage, chaque usage sur son modèle ; 5 codes bloquants, 4 passagers, réseau ; messages ; pas de retry sur bloquante, retries sur passagère ; réponses sans score ; recherche arrêtée sur 403 et 401 sans rien insérer ni marquer, offres revenues une fois Mistral rétabli ; offre passagère sautée puis reprise ; échec jamais archivé ; LBA sautée ; réanalyse et lettre sans rien enregistrer ; script de vérification), `test_archivage.py` (25, dont les trois textes réels), `test_scraper_sans_ia.py` (4). Ajoutés : mode test à la création et migration 0006 (D7), valeur ramenée journalisée et affichée (D6), limites bornées (5), mail de test (D9). Adaptés, parce qu'ils reposaient sur le score inventé ou sur un lancement à vide : la recherche complète de `test_dedoublonnage`, l'analyse LBA de `test_limiteur_mistral` (vraie réponse d'analyse), les routes de scraper et d'envoi de `test_limites` et `test_pipelines` (entreprises créées), le mail de test de `test_compte_envoi`. `alembic check` propre, `compileall` et `node --check` propres.

## Limites restantes

- Codes 400 rangés parmi les bloquants (une requête mal formée échouerait pour chaque offre).
- Les erreurs passagères de l'extraction gardent la politique de retry historique : jusqu'à 20 tentatives, 300 s d'attente au plus chacune.
- Les emails non validés par l'IA partent à l'envoi comme les autres ; ils ne sont distingués que dans les logs et en base.
- La règle d'archivage reste fondée sur des tournures : une réservation formulée autrement passera, à surveiller dans l'onglet Offres.
- `verifier_mistral.py` et les modèles n'ont pas été essayés contre la vraie API.

## Avant de relancer la recette

1. `venv/bin/python scripts/verifier_mistral.py` ; corriger `.env` si un usage est en échec.
2. Nettoyer les 5 candidatures inventées, sinon leurs offres ne reviendront pas (application arrêtée, après sauvegarde) :
   ```bash
   cp data/chasseur_v2.db data/chasseur_v2_avant_phase4b.db
   venv/bin/python -c "import sqlite3; c=sqlite3.connect('data/chasseur_v2.db'); refs=c.execute(\"select user_id, mode, ref_offre from candidatures where resume_analyse='Erreur analyse'\").fetchall(); c.executemany('delete from offres_vues where user_id=? and mode=? and ref_offre=?', refs); c.execute(\"delete from candidatures where resume_analyse='Erreur analyse'\"); c.commit(); print(len(refs), 'candidatures retirées')"
   ```
3. Relancer `docs/RECETTE.md` à partir de l'étape 0 (vérification Mistral ajoutée en 0.4).

## Points à valider

Tranchés après le rapport : décisions D15 à D18 de `docs/DECISIONS.md` (400 bloquant, emails non validés jamais envoyés automatiquement avec validation manuelle ou relance de l'IA, « maazi » retiré, nettoyage par l'humain).


1. 400 traité comme bloquant.
2. Emails non validés par l'IA envoyés comme les autres, ou mis de côté jusqu'à validation.
3. Abandon du mot-clé « maazi ».
4. Nettoyage proposé ci-dessus des 5 candidatures inventées (et des offres vues correspondantes).
