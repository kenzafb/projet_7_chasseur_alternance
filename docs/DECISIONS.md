# Décisions prises hors du code

Ce fichier garde la trace des choix tranchés par l'humain (produit, données, risques acceptés) qui ne se lisent pas dans le code ou que le code seul ne justifie pas. Il complète les rapports de phase : un rapport propose, ce fichier enregistre ce qui a été décidé.

**Règle.** Au début de chaque phase, lire ce fichier et ne rien changer au comportement lié à une décision sans nouvelle décision. À la fin de chaque phase, y ajouter les décisions prises pendant la phase (et seulement celles validées : les propositions restent dans la section « Points à valider » du rapport jusqu'à ce qu'elles soient tranchées). Une décision remplacée n'est pas effacée : elle est marquée « remplacée par » avec un renvoi.

Format : identifiant, date, phase, décision, raison, conséquence dans le code, quand la reconsidérer.

## Phase 3 (compte d'envoi par utilisateur), décisions du 8 octobre 2026

### D1. Historique des adresses déjà contactées non importé
- **Décision.** Les 1085 adresses de `data/emails_deja_envoyes.json` (ancien dédoublonnage global, antérieur au multi-utilisateur) ne sont pas importées dans `emails_contactes`.
- **Raison.** Le fichier n'est rattaché à aucun utilisateur ni à aucun mode ; l'importer pour le user 1 en mode alternance serait une supposition.
- **Conséquence.** Le user 1 peut réécrire à une entreprise déjà contactée avant la refonte. Le fichier reste dans `data/`, ni lu ni écrit. Si l'import est décidé : `ajouter_emails_contactes(1, "alternance", adresses)`.
- **À reconsidérer** au moment du mode stage.

### D2. Statut « contactée » porté par l'entreprise : dédoublonnage par mode incomplet, accepté
- **Décision.** `entreprises.mail_envoye` reste une propriété de l'entreprise, tous modes confondus. Le dédoublonnage par mode (`emails_contactes` unique sur utilisateur, mode, adresse) n'agit donc que sur les adresses partagées : une entreprise contactée en alternance n'est jamais reproposée en job.
- **Raison.** Rendre les entreprises vraiment par mode touche le fetch, le scraper, les statistiques, le suivi et l'envoyeur : chantier à part.
- **Conséquence.** Comportement inchangé en phase 4.
- **À refondre** pendant le mode stage : statut d'envoi par entreprise et par mode.

### D3. Plafond quotidien de 50 mails par utilisateur conservé
- **Décision.** `PLAFOND_ENVOIS_JOUR` vaut 50 par défaut (réglable dans `.env`), par utilisateur et par jour calendaire de Paris, tous lancements et mails de test confondus.
- **Raison.** Protéger la réputation du compte d'envoi de chacun.
- **Conséquence.** Un cron quotidien de 50 passe ; deux lancements le même jour s'arrêtent au cinquantième mail. Les mails du mode test de la phase 4 comptent aussi (ce sont de vrais mails).

### D4. Arrêt du pipeline d'envoi aussi sur serveur injoignable : validé
- **Décision.** Le pipeline d'envoi s'arrête sur identifiants refusés, mais aussi sur serveur injoignable, échec TLS ou expéditeur refusé ; seul un destinataire ou un message refusé fait passer à l'entreprise suivante.
- **Raison.** Insister sur les entreprises suivantes ne servirait à rien et pourrait faire bloquer le compte.
- **Conséquence.** Comportement inchangé en phase 4.

## Phase 4 (préparation du test réel), décisions du 8 octobre 2026

### D5. Le mode test envoie à l'adresse d'expédition : validé
- **Décision.** En mode test, chaque candidature spontanée part vers l'adresse d'expédition du compte d'envoi, le vrai destinataire dans l'objet, et non vers l'adresse de connexion.
- **Raison.** C'est une boîte dont l'utilisateur détient forcément le mot de passe ; l'adresse de connexion n'est pas vérifiée à l'inscription.

### D6. Valeurs de limite hors bornes ramenées, valeur appliquée affichée
- **Décision.** Une limite de lancement hors bornes est ramenée dans les bornes (pas de refus en 400), mais la valeur réellement appliquée est montrée à l'utilisateur : dans la confirmation de lancement de l'interface et dans les logs du pipeline (« demandé : X, ramené à Y »).
- **Conséquence.** Le front n'arrondit plus lui-même : il envoie la valeur saisie et affiche celle que renvoie le serveur.

### D7. Mode test activé à la création d'un compte d'envoi
- **Décision.** Un compte d'envoi créé est en mode test ; l'utilisateur le décoche pour envoyer pour de vrai. Les comptes existant avant la migration 0006 ne changent pas (mode test coupé).
- **Raison.** Aucun mail ne doit partir vers une entreprise avant un choix explicite.
- **Conséquence.** Réenregistrer ou modifier un compte existant ne touche pas au mode test.

### D8. Les mails du mode test comptent dans le plafond quotidien : validé
- **Décision.** Ce sont de vrais mails, envoyés par le vrai serveur : ils consomment le plafond du jour (D3) comme les autres.

## Phase 4b (correctifs de la recette réelle), décisions du 8 octobre 2026

### D9. Mail de test du compte d'envoi vers l'adresse d'expédition seulement
- **Décision.** « M'envoyer un mail de test » part vers l'adresse d'expédition du compte, comme le mode test (D5) ; plus vers l'adresse de connexion, qui est désormais refusée.

### D10. Modèles Mistral configurables par usage
- **Décision.** `MODELE_MISTRAL_ANALYSE`, `MODELE_MISTRAL_LETTRE`, `MODELE_MISTRAL_EXTRACTION`, sinon `MODELE_MISTRAL`, sinon les défauts : `mistral-medium-latest` pour l'analyse et la lettre, `mistral-small-latest` pour l'extraction d'emails.
- **Raison.** Recette : `mistral-large-latest` refusé en 403 (code 1910, modèle hors de l'abonnement de la clé).

### D11. Plus jamais de résultat inventé par l'IA
- **Décision.** Aucun score, verdict ou lettre par défaut quand Mistral échoue. Erreur non récupérable (400, 401, 403, 404, 422) : arrêt immédiat du pipeline, message clair dans les logs et le bandeau. Erreur passagère épuisée (429, 5xx, réseau, réponse illisible) : l'offre est sautée. Dans les deux cas, l'offre n'est ni insérée, ni marquée vue, ni archivée : elle revient au lancement suivant.
- **Conséquence.** Sur les routes directes (lettre, réanalyse), rien n'est enregistré : 503 pour une erreur de configuration, 502 sinon.

### D12. Archivage « public spécifique » seulement pour les offres réservées
- **Décision.** La mention d'égalité des chances (« ouvert aux personnes en situation de handicap », « à compétences égales ») n'archive plus. Seules les tournures de réservation ou d'exigence explicites (« réservé aux », « exclusivement », « RQTH obligatoire », « vous devez être bénéficiaire de l'obligation d'emploi »...) archivent l'offre.
- **Raison.** Les trois offres archivées ainsi pendant la recette portaient toutes la mention standard.

### D13. Emails lus dans la page gardés quand Mistral échoue
- **Décision.** Si l'extraction par Mistral échoue, le scraper garde les emails trouvés par lecture directe de la page (regex, déobfuscation), notés non validés par l'IA (`emails_non_valides` dans `extra`). Une erreur non récupérable coupe l'IA pour le reste du lancement, avec un seul message.

### D14. Limites bornées par ce qui existe
- **Décision.** Le maximum du scraper est le nombre d'entreprises non traitées, celui de l'envoi le nombre d'entreprises avec email dont une adresse au moins n'a pas été contactée dans le mode courant. Le front l'affiche, le serveur l'applique (avec « demandé : X, ramené à Y », D6) et refuse en 400 un lancement sans rien à traiter.

## Phase 4b, points tranchés après le rapport (8 octobre 2026)

### D15. Emails non validés par l'IA : jamais envoyés automatiquement
- **Décision.** Les emails gardés sans validation par Mistral (D13) ne partent jamais d'eux-mêmes, même en mode test, et ne comptent pas dans le maximum d'envoi. Ils restent visibles dans la page Spontanées avec la mention « non validé ». L'utilisateur les valide à la main, une entreprise à la fois (`POST /api/spontanees/valider`), ou relance plus tard la validation par l'IA sur les entreprises concernées (`POST /api/spontanees/revalider`, limite « revalidations », 20 par défaut, 200 au plus, bornée par le nombre en attente).
- **Conséquence.** Une revalidation réussie remplace emails, téléphones et contact par ceux que l'IA retient ; un échec passager laisse l'entreprise en attente ; une erreur bloquante arrête la revalidation avec un seul message.

### D16. Code HTTP 400 de Mistral bloquant : validé
- **Décision.** 400 rejoint 401, 403, 404 et 422 : arrêt immédiat du pipeline (D11).

### D17. Mot-clé « maazi » retiré de la règle « public spécifique »
- **Décision.** Retiré (fait en phase 4b, confirmé) ; seules les tournures de réservation de D12 archivent.

### D18. Nettoyage des 5 candidatures issues d'analyses échouées : par l'humain
- **Décision.** L'humain lance lui-même la commande de `docs/PHASE_4B_RAPPORT.md` (section « Avant de relancer la recette ») ; le code n'y touche pas.

## Phase 5a (préparation de l'étude des sources), décisions du 8 octobre 2026

### D19. Interrupteur ANALYSE_IA : travail sans IA
- **Décision.** `ANALYSE_IA` dans le `.env`, vrai par défaut. À `false` : aucun appel à Mistral nulle part (`appeler_mistral` lève `IADesactivee` sans appeler, en dernier rempart). La recherche insère les offres France Travail et LBA avec le verdict `non_analysee`, sans score (NULL) ni points ni résumé, et les marque vues normalement ; aucun archivage fondé sur l'analyse (note basse, hors domaine). L'interface affiche « non analysée » à la place du viseur ; génération de lettre, réanalyse et revalidation des emails sont désactivées avec un message clair (refus serveur : 503 pour lettre et réanalyse, 400 pour la revalidation). Le scraper ne fait que la lecture directe, emails notés non validés comme en cas d'échec de l'IA (D13), donc jamais envoyés automatiquement (D15). Un bandeau discret signale que l'IA est désactivée. `scripts/verifier_mistral.py` n'appelle rien.
- **Raison.** Le compte Mistral ne permet plus l'API ; un modèle local viendra plus tard. On étudie France Travail, LBA et Sirene sans IA.
- **Conséquence.** La limite « analyses » borne aussi le nombre d'offres ajoutées sans analyse. Une offre non analysée pourra être analysée par le bouton « Analyser » quand l'IA reviendra. Les offres non analysées sont triées après les autres.
- **À reconsidérer** à l'arrivée du modèle local (analyse en lot des offres `non_analysee`).

## Phase 5a, points tranchés après le rapport (8 octobre 2026)

### D20. Sans IA : archivage par mots-clés conservé, plafond d'offres propre
- **Décision.** Quand `ANALYSE_IA=false`, l'archivage par mots-clés reste appliqué (public réservé D12, école ou CFA, stage) ; seuls note basse et hors domaine disparaissent (D19). La limite d'offres par lancement a son propre plafond : 100 par défaut, 500 au plus (`LIMITES_LANCEMENT["sans_ia"]`), affichés dans l'interface à la place de ceux de l'analyse (30, 200).
- **Conséquence.** Même champ `max_analyses` pour la route ; valeur hors bornes ramenée et affichée (D6).

### D21. Analyse en différé des offres « non analysées » : travail futur
- **Décision.** Prévue pour l'arrivée du modèle local, non implémentée. En attendant, une offre `non_analysee` ne s'analyse qu'une à une, par le bouton « Analyser », IA active.
- **À faire** avec le modèle local : analyse en lot des offres `verdict = "non_analysee"`, avec archivage complet une fois l'analyse obtenue.

## Phase 5b (domaines et France Travail), décisions du 8 octobre 2026

Décisions de `docs/SPEC_SOURCES.md` (sections 0, 1 et 2), validées par l'humain et mises en œuvre dans cette phase. Les choix faits pendant la mise en œuvre restent à valider dans `docs/PHASE_5B_RAPPORT.md`.

### D22. Domaines du profil en codes France Travail
- **Décision.** Le profil stocke des codes de la nomenclature France Travail : grands domaines (une lettre, « C ») et domaines (trois caractères, « M18 »), choix multiple ; `[]` signifie « indifférent ». L'interface montre les 14 grands domaines, chacun affinable par ses domaines. Les listes viennent des référentiels versionnés (`docs/referentiels/france_travail/`, plus `shared/referentiels/grands_domaines.json` pour les libellés des lettres), plus de `shared/domaines.py` écrit à la main.
- **Migration.** `informatique` devient `M18`, `immobilier` devient `C15` (migration 0007, données seulement).
- **Conséquence.** Un profil sans domaine cherche désormais tous les domaines sur France Travail (avant : informatique par défaut). En mode job, les domaines filtrent la recherche (avant : simple préférence pour l'analyse).

### D23. Filtres France Travail par mode
- **Décision.** Alternance : `natureContrat` E2 et FS (contrat de professionnalisation ajouté), aucun filtre de qualification. Job : `typeContrat` CDD, MIS, SAI, filtre `qualification=0` retiré (il écartait les offres « X », 61 % du total en IDF). Domaines du profil dans les deux modes. Options : secteur de l'employeur (88 divisions NAF) dans les deux modes ; thèmes 13 (saisonniers) et 17 (sans diplôme ni expérience) en mode job, décochés par défaut. Stage : aucune recherche France Travail (le mode n'existe pas encore).

### D24. Rien de tronqué en silence : découpage adaptatif (découpage remplacé par D31)
- **Décision.** Au-delà de 3150 offres par requête (150 par page, début au plus 3000, mesuré le 8 octobre 2026), la requête est redécoupée par département d'IDF, puis par domaine, puis par fenêtre de publication, avec dédoublonnage par identifiant. Une troncature ou une perte restante est écrite dans les logs du pipeline.

### D25. Taille d'entreprise filtrée après récupération
- **Décision.** L'API ne filtrant pas la taille, les offres sont filtrées après récupération selon la tranche d'effectif de l'établissement, avec l'option « garder les offres sans information ». Tailles proposées (communes avec Sirene, section 4.2 de la spec) : moins de 10 (avertissement « moins de chances d'accueillir un alternant »), 10 à 49, 50 à 249, 250 à 4999, 5000 et plus.

### D26. Points de l'API à vérifier réunis en un seul endroit
- **Décision.** Nom des paramètres de domaine, nombre de valeurs acceptées par requête, champ de tranche d'effectif et début des fenêtres de dates sont lus dans `france_travail/parametres_api.py`, et nulle part ailleurs. `scripts/verifier_france_travail.py`, lancé par l'humain, affiche les valeurs à y reporter.
- **En attendant.** Valeurs prudentes : une requête par valeur, `grandDomaine` pour les lettres, `domaine` pour les codes, `trancheEffectifEtab`.
- **À reconsidérer** dès que le script a tourné.

## Phase 5b, points tranchés après le rapport (8 octobre 2026)

### D27. Profils d'alternance sans domaine : restent « indifférent », bandeau d'invitation
- **Décision.** Pas de migration vers M18 : un profil d'alternance sans domaine cherche tous les domaines sur France Travail (D22). Tant que la liste est vide, un bandeau dans le profil d'alternance invite à choisir des domaines ; il disparaît dès qu'un domaine est coché.
- **Conséquence.** Le mode job n'a pas de bandeau : indifférent y est le défaut voulu.

### D28. Domaines filtrants en mode job : validé
- **Décision.** En mode job, les domaines cochés filtrent la recherche France Travail (D22, D23), ils ne sont plus une simple préférence pour l'analyse.

### D29. LBA et Sirene avec un domaine non couvert : comportement conservé, signalé au lancement
- **Décision.** Jusqu'aux phases 5c et 5d, LBA et Sirene ne cherchent que M18 et C15 ; profil indifférent : ancien défaut, informatique ; domaine sans correspondance : non cherché ; aucun domaine couvert : source ignorée. En plus des logs, la confirmation de lancement dans l'interface nomme les domaines non couverts (recherche d'offres pour LBA, récupération des entreprises pour Sirene), champ `avertissement` de la réponse.
- **À reconsidérer** en 5c (LBA) et 5d (Sirene), quand les correspondances seront tirées des référentiels.
- **Remplacée pour LBA** par D37 (phase 5c) : LBA couvre tous les domaines, profil indifférent compris. Toujours valable pour Sirene jusqu'à la phase 5d.

### D30. « Garder les offres sans information de taille » cochée par défaut : validé
- **Décision.** `taille_inconnue` vaut vrai tant que l'utilisateur ne la décoche pas (D25).

## Phase 5b, résultats de la vérification de l'API (8 octobre 2026)

`scripts/verifier_france_travail.py` lancé par l'humain le 8 octobre 2026, détail dans `docs/referentiels/france_travail/verification_api.json`.

### D31. Découpage par date de création seulement (remplace le découpage de D24)
- **Constat.** Découper par domaine ou par département perd des offres : la somme des 14 grands domaines fait 56979 sur 66929 (offres sans domaine), celle des 8 départements 64031 sur 66929 (offres sans département).
- **Décision.** Au-delà de 3150 offres, la requête est découpée uniquement par date de création : période coupée en deux, récursivement, tant qu'une tranche dépasse le plafond, jusqu'à l'heure. Départements et domaines ne servent qu'aux filtres choisis par l'utilisateur, jamais au découpage. L'étape « valeur » disparaît. Le principe de D24 reste : rien n'est tronqué en silence.
- **Fenêtre.** La fenêtre complète arrêtée à maintenant (UTC) ramenait 66709 offres sur 66929. L'écart vaut environ deux heures d'offres (17458 en 7 jours, une centaine par heure) : l'API lit vraisemblablement les dates en heure de Paris. La fenêtre finit désormais à maintenant plus 24 h (`MARGE_FIN_FENETRE_HEURES`) ; les deux moitiés partagent leur borne (offre à la borne lue deux fois, dédoublonnée, quelle que soit l'inclusion des bornes). Le script compare désormais les fins « maintenant », « plus 3 h » et « plus la marge » au total sans dates, pour confirmer la cause.
- **Bilan.** Après chaque recherche découpée, les logs donnent le total annoncé par l'API, le nombre d'offres distinctes récupérées et l'écart (attendu : quelques offres publiées ou retirées pendant la recherche).

### D32. Valeurs de `parametres_api.py` vérifiées
- **Décision.** `grandDomaine` pour les lettres, `domaine` pour les codes (`domaine=M` refusé). Valeurs par requête : `natureContrat` 2, `typeContrat` 3, `grandDomaine` 5 (listes acceptées, OU) ; `domaine`, `theme` 1 (listes refusées) ; `secteurActivite` 1 en attendant D33. Tranche d'effectif : `trancheEffectifEtab`, présente dans 287 offres sur 300, toutes reconnues. Complète D26.

### D33. secteurActivite : essai à exactement deux valeurs
- **Constat.** La liste de cinq secteurs est refusée avec « 2 chaînes de caractères séparées par des virgules ».
- **Décision.** Le script essaie aussi exactement deux valeurs (`62,68`). La valeur reste 1 jusqu'à ce nouveau passage du script.
- **Note.** Le premier passage avait déjà fait un essai à deux valeurs (1289 offres, soit 614 + 675), jugé « incohérent » à cause d'un défaut du script (comparaison aux totaux des cinq valeurs), corrigé.

### D34. Offres écartées par la taille non marquées vues ; secteur employeur en alternance : validés
- **Décision.** Une offre écartée par le filtre de taille n'est pas marquée vue : elle revient si l'utilisateur change de taille. Le secteur de l'employeur est proposé en option dans les deux modes, vide par défaut.

## Phase 5b, seconde vérification de l'API (8 octobre 2026)

### D35. Fuseau des dates confirmé ; secteurActivite à deux valeurs
- **Fuseau.** L'API lit `minCreationDate` et `maxCreationDate` en heure de Paris malgré le « Z » : fenêtre finissant à maintenant (UTC) 66790 offres, finissant à maintenant plus 3 h 66932, le total sans dates. La marge de fin de 24 h de D31 est conservée (elle couvre l'heure d'hiver comme l'heure d'été). Découpage exact : les deux moitiés font 56937 + 9995 = 66932.
- **secteurActivite.** Deux valeurs acceptées (`62,68` : 1289 = 614 + 675), cinq refusées : `VALEURS_PAR_REQUETE["secteurActivite"]` passe à 2. Clôt D33.

## Phase 5c (La Bonne Alternance), décisions du 9 octobre 2026

`scripts/verifier_lba.py` lancé par l'humain le 9 octobre 2026 (32 requêtes), détail dans `docs/referentiels/lba/verification_api.json`. Décisions 1 à 6 données par l'humain après lecture du résultat.

### D36. Cercles au plafond redécoupés, rayon réduit
- **Constat.** Les entreprises à fort potentiel sont plafonnées à 150 par requête sur tous les cercles essayés, de 10 à 200 km, seul Cergy à 10 km en donne 98. Les offres : 150 par source et 450 en tout (sans code métier : 150 offres LBA, 261 France Travail, 39 autres).
- **Décision.** Recherche autour de 19 centres à rayon réduit (`LBA_CENTRES`, 8 km pour Paris, 10 km en petite couronne, 18 à 25 km en grande couronne). Un cercle dont la réponse atteint le plafond est redécoupé en sept cercles de rayon moitié qui le recouvrent entièrement, jusqu'à 1 km (`LBA_RAYON_MIN_KM`), puis le lot de codes métiers en deux ; les cercles encore au plafond sont écrits dans les logs. Au plus 300 requêtes par recherche (`LBA_REQUETES_MAX`), parcourues en largeur (tous les centres avant les redécoupages).
- **Conséquence.** Les cercles au plafond d'entreprises sont redécoupés dans l'étape « Récupérer » des spontanées (qui s'arrête à la limite de nouvelles entreprises) ; la recherche d'offres ne redécoupe que pour les offres et écrit dans les logs les cercles au plafond d'entreprises laissés tels quels.

### D37. Profil « indifférent » : LBA sans code métier
- **Décision.** L'API accepte une recherche sans code : un profil sans domaine cherche sur LBA sans code au lieu d'être ignoré. Les autres profils envoient tous les métiers de `metiers.json` des domaines choisis, par lots de 100 (100 codes acceptés en une requête). Remplace D29 pour LBA.

### D38. Niveau de diplôme filtré après récupération
- **Constat.** `target_diploma_level` filtre (les autres noms essayés sont ignorés), mais écarte les offres sans niveau indiqué : au niveau 6, 1 offre sur les 3 de la référence.
- **Décision.** Le niveau n'est jamais envoyé à l'API. Le niveau visé du profil (texte libre) est converti en niveau européen 3 à 7 ; après récupération, les offres d'un autre niveau (`offer.target_diploma.european`) sont écartées et celles sans niveau gardées. Niveau visé vide ou non reconnu : aucun filtre, signalé dans les logs.

### D39. Entreprises LBA sans email : par le scraper ; identifiant de candidature gardé
- **Constat.** Aucun email ni téléphone sur 4148 entreprises lues ; `apply.recipient_id` présent dans 772.
- **Décision.** Les entreprises LBA passent par le scraper comme celles de Sirene. `apply.recipient_id` est gardé (`extra.lba.candidature_id`) pour la future candidature directe, qui n'est pas branchée. Si LBA fournit un jour un email, il est gardé et noté `extra.emails_lba`.

### D40. Taille du profil appliquée aux entreprises LBA
- **Décision.** `workplace.size` est toujours présent (« 0-0 », « 6-9 »...) : les entreprises LBA sont filtrées par les tailles cochées du profil d'alternance, avec l'option « garder les tailles inconnues ».

### D41. Spontanées : La Bonne Alternance d'abord, puis Sirene
- **Décision.** Validée : l'étape « Récupérer » interroge LBA d'abord, puis Sirene pour le reste de la limite de nouvelles entreprises. Les entreprises LBA (source `lba`, colonne `entreprises.source`, migration 0008) sont dédoublonnées par SIRET avec celles de Sirene (une entreprise Sirene retrouvée sur LBA passe en source `lba`), scrapées, envoyées et affichées en priorité. La recherche d'offres verse aussi dans les spontanées les entreprises qu'elle reçoit.

### D42. Valeurs de `parametres_lba.py` vérifiées
- **Décision.** `CODES_PAR_REQUETE` 100, `ACCEPTE_SANS_CODES` vrai, `RAYON_MAX_KM` 200 (201 refusé), `PLAFOND_PAR_SOURCE` 150, `PLAFOND_TOTAL_OFFRES` 450, coordonnées prises en compte (Paris et Cergy différents). L'exclusion `partners_to_exclude=France Travail` marche avec des codes métiers mais pas sans code (261 offres France Travail reçues) : le filtre par nom de partenaire reste indispensable.

### D43. France Travail : arrêt dès que le lot est plein
- **Décision.** Point reporté de la phase 5b : une recherche limitée à N offres arrête de télécharger dès N offres retenues (non vues, en Île-de-France, bonne taille, hors alternance en mode job), au lieu de lire toutes les tranches du découpage pour n'en garder que N. Pages lues des plus récentes aux plus anciennes, tranche de dates la plus récente d'abord. Les logs donnent le nombre de requêtes et l'arrêt anticipé ; le bilan « annoncé, récupéré, écart » de D31 n'est écrit que pour une recherche lue en entier.
