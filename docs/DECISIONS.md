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
- **Remplacée** par D66 (phase 6a) : import par un script lancé par l'humain, groupe a par défaut.

### D2. Statut « contactée » porté par l'entreprise : dédoublonnage par mode incomplet, accepté
- **Décision.** `entreprises.mail_envoye` reste une propriété de l'entreprise, tous modes confondus. Le dédoublonnage par mode (`emails_contactes` unique sur utilisateur, mode, adresse) n'agit donc que sur les adresses partagées : une entreprise contactée en alternance n'est jamais reproposée en job.
- **Raison.** Rendre les entreprises vraiment par mode touche le fetch, le scraper, les statistiques, le suivi et l'envoyeur : chantier à part.
- **Conséquence.** Comportement inchangé en phase 4.
- **À refondre** pendant le mode stage : statut d'envoi par entreprise et par mode.
- **Remplacée** par D65 (phase 6a).

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
- **Remplacée pour LBA** par D37 (phase 5c) : LBA couvre tous les domaines, profil indifférent compris. **Remplacée pour Sirene** par D51 (phase 5d) : plus de défaut « informatique », secteurs choisis pour l'indifférent et les domaines sans correspondance.

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
- **Conséquence.** Les cercles au plafond d'entreprises sont redécoupés dans l'étape « Récupérer » des spontanées (qui s'arrête à la limite de nouvelles entreprises) ; la recherche d'offres ne redécoupe que pour les offres (et, depuis D46, ignore les entreprises).

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

### D41. Spontanées : La Bonne Alternance d'abord, puis Sirene (remplacée par D44)
- **Remplacée** par D44 après l'essai réel : plus de priorité de LBA sur Sirene.
- **Décision.** Validée : l'étape « Récupérer » interroge LBA d'abord, puis Sirene pour le reste de la limite de nouvelles entreprises. Les entreprises LBA (source `lba`, colonne `entreprises.source`, migration 0008) sont dédoublonnées par SIRET avec celles de Sirene (une entreprise Sirene retrouvée sur LBA passe en source `lba`), scrapées, envoyées et affichées en priorité. La recherche d'offres verse aussi dans les spontanées les entreprises qu'elle reçoit.

### D42. Valeurs de `parametres_lba.py` vérifiées
- **Décision.** `CODES_PAR_REQUETE` 100, `ACCEPTE_SANS_CODES` vrai, `RAYON_MAX_KM` 200 (201 refusé), `PLAFOND_PAR_SOURCE` 150, `PLAFOND_TOTAL_OFFRES` 450, coordonnées prises en compte (Paris et Cergy différents). L'exclusion `partners_to_exclude=France Travail` marche avec des codes métiers mais pas sans code (261 offres France Travail reçues) : le filtre par nom de partenaire reste indispensable.

### D43. France Travail : arrêt dès que le lot est plein
- **Décision.** Point reporté de la phase 5b : une recherche limitée à N offres arrête de télécharger dès N offres retenues (non vues, en Île-de-France, bonne taille, hors alternance en mode job), au lieu de lire toutes les tranches du découpage pour n'en garder que N. Pages lues des plus récentes aux plus anciennes, tranche de dates la plus récente d'abord. Les logs donnent le nombre de requêtes et l'arrêt anticipé ; le bilan « annoncé, récupéré, écart » de D31 n'est écrit que pour une recherche lue en entier.

## Phase 5c, points tranchés après le rapport et l'essai réel (9 octobre 2026)

### D44. Sirene et LBA ensemble, sans priorité ; trace des deux sources (remplace D41)
- **Décision.** Les entreprises de Sirene et de La Bonne Alternance sont traitées par le scraper et l'envoyeur, et affichées, dans l'ordre d'insertion, sans priorité de l'une sur l'autre. Dédoublonnage par SIRET conservé. Chaque entreprise garde la liste des sources qui l'ont trouvée (`entreprises.sources`, migration 0009, remplace `entreprises.source`) : une entreprise trouvée par les deux sources a `["sirene", "lba"]` (ou l'inverse, selon l'ordre de découverte), pour comparer les sources plus tard.
- **Interface.** Pastille par source sur chaque entreprise, filtres « Sirene » et « LBA ». Statistiques par source : entreprises, emails trouvés, mails envoyés, réponses (statut de suivi réponse, entretien ou refus), entretiens ; une entreprise des deux sources compte dans chacune, une ligne « les deux » les compte à part.
- **Étape « Récupérer ».** LBA a droit à la moitié de la limite de nouvelles entreprises (arrondie au-dessus), Sirene au reste, plus ce que LBA n'a pas utilisé.
- **Migration.** Les entreprises existantes reçoivent leur source d'avant ; celles passées de Sirene à « lba » sous D41 ne gardent que « lba ».

### D45. Effectif LBA « 0-0 » : inconnu (remplacée par D56)
- **Décision.** « 0-0 » (`parametres_lba.TAILLES_INCONNUES`) est traité comme un effectif inconnu : l'entreprise est gardée ou écartée selon l'option « inclure les effectifs inconnus » du profil.
- **Remplacée** par D56 : « 0-0 » est zéro salarié.

### D46. La recherche d'offres n'ajoute aucune entreprise
- **Décision.** Seule l'étape « Récupérer » des spontanées ajoute des entreprises LBA, avec sa limite. La recherche d'offres ignore les entreprises à fort potentiel (ni lues, ni redécoupées, ni signalées).

### D47. Adresses techniques ou factices jamais enregistrées
- **Constat.** Essai réel : `…@o4506196830715904.ingest.us.sentry.io` (suivi d'erreurs) et `votre@email.com` (exemple de formulaire) retenues par le scraper.
- **Décision.** Règles dans `shared/referentiels/emails_exclus.txt`, fichier de données à compléter : `@domaine` (domaine et sous-domaines : sentry.io, wixpress.com, example.com, domain.com...), `local@` (votre@, nom@, prenom.nom@...), adresse exacte. Appliquées par le scraper (adresse jamais retenue) et à l'enregistrement en base (scraper et LBA).
- **Conséquence.** Les adresses déjà en base ne sont pas nettoyées.

### D48. Rayon minimal et requêtes LBA réglables, durée dans les logs
- **Décision.** `LBA_RAYON_MIN_KM` (1 km) et `LBA_REQUETES_MAX` (300) restent dans `shared/config.py`. L'étape « Récupérer » écrit ces deux réglages au départ, puis le nombre de requêtes LBA faites et leur durée.

## Phase 5d (Sirene), décisions du 9 octobre 2026

Décisions de `docs/SPEC_SOURCES.md` (sections 0, 4 et 7), validées par l'humain et mises en œuvre dans cette phase. Les choix faits pendant la mise en œuvre restent à valider dans `docs/PHASE_5D_RAPPORT.md`.

### D49. Correspondance domaine vers NAF en fichier de données
- **Décision.** `shared/referentiels/correspondance_naf.json` : pour M18 et C15, secteurs cœurs (toutes tailles) et transverses (unités légales de 250 salariés et plus : tranche 32 et au-delà, ou catégorie ETI ou GE, taille lue sur l'unité légale), listes de la spec 4.1. Exclusions systématiques 68.32B, 41.10D, 66.19A, quelle que soit l'origine du code (domaine ou secteur choisi). Remplace les listes écrites à la main de `shared/domaines.py`.
- **NAF 2025.** Chaque code porte ses cibles NAF 2025 de la table officielle de l'INSEE (`Correspondances_NAFrev2-NAF2025.xlsx`, édition janvier 2026, copie en CSV dans `docs/referentiels/insee/`). Aucun code inventé ; pour une correspondance multiple, les cibles retenues pour le domaine sont marquées à valider.

### D50. NOMENCLATURE_NAF : bascule au 1er janvier 2027
- **Décision.** `shared.config.nomenclature_naf()` vaut `NAFRev2` jusqu'au 31 décembre 2026 et `NAF2025` à partir du 1er janvier 2027 (jour de Paris), relue à chaque recherche ; `NOMENCLATURE_NAF` du `.env` force l'une ou l'autre. Tant que le nom de la variable NAF 2025 de l'API n'est pas vérifié, une recherche en NAF 2025 se fait en NAF rév. 2, avec un message.

### D51. Filtres Sirene du profil (remplace D29 pour Sirene)
- **Tailles.** Celles du profil (communes avec France Travail et LBA), converties en tranches INSEE de l'unité légale (spec 4.2). Le « au moins 10 salariés » écrit en dur disparaît. NN et « effectifs inconnus » : corrigé par D55 ; profils existants : D60.
- **Départements.** Nouveau champ du profil d'alternance, choix multiple parmi les 8 départements d'Île-de-France ; remplace `SIRENE_DEPARTEMENTS`.
- **Secteurs.** Profil indifférent ou domaine sans correspondance : les secteurs choisis dans le profil (divisions NAF, le même champ que le filtre « secteur de l'employeur » de France Travail) sont cherchés, toutes leurs sous-classes. Plus de défaut « informatique » ; sans domaine couvert ni secteur, Sirene n'est pas interrogé, avec un message au lancement.
- **Sièges actifs**, pagination par curseur, requêtes et durée dans les logs.

### D52. Pas de doublon avec LBA
- **Décision.** Une entreprise déjà en base (même SIRET, trouvée par LBA ou par un lancement précédent) n'est pas dupliquée ; Sirene ajoute sa source (D44).

### D53. Points de l'API Sirene réunis en un seul endroit
- **Décision.** Variables de la requête, nombre de codes NAF et de départements par requête, syntaxe des unités sans tranche, taille de page et pauses sont lus dans `spontanees/parametres_sirene.py`, et nulle part ailleurs. `scripts/verifier_sirene.py`, lancé par l'humain, affiche les valeurs à y reporter.
- **En attendant.** Valeurs prudentes : un code NAF et un département par requête (comme avant), tranche « NN » seulement pour les inconnus, variable NAF 2025 inconnue.
- **À reconsidérer** dès que le script a tourné.

## Phase 5d, résultats de la vérification et points tranchés (9 octobre 2026)

`scripts/verifier_sirene.py` lancé par l'humain le 9 octobre 2026 (57 requêtes), détail dans `docs/referentiels/insee/verification_api.json`.

### D54. Valeurs de `parametres_sirene.py` vérifiées
- **Décision.** `NAF_PAR_REQUETE` 120 (OU exact sur 2 et 10 codes, 120 acceptés, 250 refusés en 414), `DEPARTEMENTS_PAR_REQUETE` 8 (OU exact), variable NAF 2025 `activitePrincipaleNAF25UniteLegale` (filtre, remplie dans toutes les réponses dès 2026 ; les autres noms essayés sont refusés). Absence de tranche : `-trancheEffectifsUniteLegale:*` acceptée (aucun résultat : les 19717 unités de la référence ont une tranche). Pagination toujours par curseur : `debut` est plafonné à 10000. La catégorie n'existe que sur l'unité légale.

### D55. NN : « sans salarié », distinct de « moins de 10 » (corrige D51)
- **Constat.** 857 sièges sur 1000 (Paris, 62.01Z) ont la tranche NN. Documentation des variables Sirene : « NN : Unité non employeuse (pas de salarié au cours de l'année de référence et pas d'effectif au 31/12) », distincte de 00 (salariés dans l'année, aucun au 31 décembre).
- **Décision.** Nouvelle taille « Sans salarié » (tranche NN), avec la mention « freelances, micro-entreprises, quasiment jamais d'alternant », proposée en alternance seulement. Elle n'est gardée que si elle est cochée : rien de coché veut dire toutes les tailles sauf elle. « Effectif inconnu » ne concerne plus que l'absence de tranche.

### D56. LBA « 0-0 » : sans salarié (remplace D45)
- **Constat.** LBA écrit les bornes de la tranche INSEE (« 6-9 » pour la tranche 03) ; « 0-0 » est donc zéro salarié. Les données versées ne comptent que 2 entreprises LBA (une « 0-0 », une « 6-9 ») : la lecture vient du format, pas d'un comptage.
- **Décision.** « 0-0 » (`parametres_lba.TAILLES_SANS_SALARIE`) est rangé en « sans salarié » ; effectif inconnu : taille absente.

### D57. Division en NAF 2025 : cible hors division seulement si unique
- **Décision.** Pour un secteur choisi (division rév. 2), une cible NAF 2025 hors de la division n'est gardée que si l'ancien code n'a qu'une cible (68.20A vers 55.90Y écarté ; 41.10A vers 68.12Y gardé).

### D58. Départements du profil appliqués aux entreprises LBA
- **Décision.** Le choix de départements des candidatures spontanées s'applique aussi aux entreprises à fort potentiel de LBA, d'après leur code postal.

### D59. Dédoublonnage par SIREN en plus du SIRET
- **Décision.** Un autre établissement d'une entreprise déjà en base (même SIREN), qu'il vienne de LBA ou de Sirene, n'est pas ajouté ; la source est notée sur l'entreprise existante. Complète D52.

### D60. Profils existants : ancien réglage de Sirene pré-coché
- **Décision.** Aucune taille cochée : toutes (sauf « sans salarié », D55) ; aucun département coché : les 8. Les profils d'alternance existants sans choix reçoivent l'ancien réglage par la migration 0010 : 10 salariés et plus pour les tailles des candidatures spontanées (D63), départements 75, 92, 93, 94. Les tailles des offres ne sont pas touchées.

### D61. Correspondance NAF et secteurs : validés
- **Décision.** Validés tels quels : cibles NAF 2025 des correspondances multiples (60.20H, 26.40Y, 55.90Y écartées), cibles uniques qui élargissent (46.50Y, 95.10Y, 71.12Y, 68.12Y), secteurs choisis utilisés seulement pour l'indifférent et les domaines sans correspondance.

### D62. Nettoyage des adresses exclues déjà en base : par l'humain
- **Décision.** `scripts/nettoyer_emails_exclus.py` applique les règles de D47 aux entreprises déjà en base (liste seulement, `--appliquer` pour écrire). Lancé par l'humain.

### D63. Tailles des offres et tailles des candidatures spontanées séparées
- **Constat.** Un seul réglage de taille filtrait à la fois les offres et les entreprises des spontanées ; or une petite entreprise qui publie une offre d'alternance veut recruter, l'écarter serait une perte.
- **Décision.** Deux réglages dans le profil d'alternance : tailles des offres (`tailles`, `taille_inconnue` ; France Travail, toutes par défaut, aucune pré-coche par migration) et tailles des candidatures spontanées (`tailles_spontanees`, `taille_inconnue_spontanees` ; Sirene et entreprises LBA, « sans salarié » proposée ici seulement, pré-cochées à 10 salariés et plus pour les profils existants par la migration 0010). Lecture de D55 validée : rien de coché dans les spontanées veut dire toutes les tailles sauf « sans salarié ».


## Phase 6a (préparation du mode stage), décisions du 9 octobre 2026

Décisions données par l'humain au lancement de la phase et mises en œuvre. Les choix faits pendant la mise en œuvre restent à valider dans `docs/PHASE_6A_RAPPORT.md`.

### D64. Sirene : les cœurs remplissent la limite, les transverses complètent
- **Constat.** Essai réel M18, limite de 10 : 5 entreprises, toutes transverses, 0 cœur. Cause : la clause des effectifs inconnus était mise en OU avec les tranches, `(tranche:(...) OR -tranche:*)` ; en Lucene, une clause `-x` dans un OU exclut au lieu d'ajouter, donc toute unité qui a une tranche était écartée. Les transverses, sans cette clause, remplissaient seuls la limite. L'API simulée des tests lisait ce OU comme une union, d'où des tests verts.
- **Décision.** La limite se remplit dans l'ordre du plan : cœurs, secteurs choisis, transverses seulement pour compléter. Les unités sans tranche sont cherchées par une requête à part (`-trancheEffectifsUniteLegale:*` en ET), jamais dans un OU. L'API simulée suit la sémantique Lucene.
- **Logs.** Pour chaque recherche : groupe, établissements annoncés par Sirene, nouvelles ; à la fin, répartition de tous les groupes du plan, zéros compris.

### D65. État d'envoi par entreprise et par mode (remplace D2)
- **Décision.** Une entreprise reste unique par utilisateur (SIRET, puis SIREN) ; ses données publiques (site, emails, téléphones, contact, validation des emails) sont communes à tous les modes et ne sont scrapées qu'une fois. La sélection pour un mode, l'envoi, sa date, les destinataires et le statut de suivi sont propres à chaque mode (table `entreprises_modes`, migration 0011). Les données existantes passent en mode alternance.
- **Interface.** La page Spontanées et le suivi n'affichent que les entreprises du mode courant, avec l'étiquette « déjà contactée en <autre mode> le <date> » quand c'est le cas ; l'envoi n'est jamais bloqué par un contact dans un autre mode.

### D66. Historique des adresses contactées importé par un script (remplace D1)
- **Décision.** `scripts/importer_contacts_historiques.py`, lancé par l'humain, classe les 1085 adresses de `data/emails_deja_envoyes.json` d'après l'ancienne base `data/chasseur.db` (lecture seule) : (a) dans une entreprise marquée envoyée, (b) dans une entreprise non marquée envoyée, (c) absente (probablement des mails personnels ou autres, le fichier venant du dossier Envoyés de Gmail). `--dry-run` d'abord ; import réel avec `--user` et le choix des groupes, a seulement par défaut, comme contactées en mode alternance ; les entreprises correspondantes de la nouvelle base sont marquées « déjà contactées en alternance ».
- **Conséquence.** En alternance, ces adresses ne sont plus visées. En job ou en stage, rien n'est bloqué : seulement l'étiquette de D65.
- **Essai à blanc du 9 octobre 2026** (sans `--user`) : 798 adresses en a, 11 en b, 276 en c.

### D67. Une URL par mode, mode explicite pour l'API
- **Décision.** `/alternance`, `/job` et `/stage`, et une page d'accueil où l'on choisit son mode. Le mode vient de l'URL et non plus de la session : deux onglets dans deux modes différents ne se gênent pas. L'API reçoit le mode explicitement (paramètre `mode`). Les anciennes URL redirigent. `/stage` affiche une page « bientôt disponible » (phase 6b). Isolation entre utilisateurs et protection de toutes les routes inchangées.
- **Page `/stage` « bientôt disponible » remplacée** par D68 (phase 6b) : le mode stage est ouvert.

## Phase 6b (mode stage), décisions du 9 octobre 2026

Décisions données par l'humain au lancement de la phase et mises en œuvre. Les choix faits pendant la mise en œuvre restent à valider dans `docs/PHASE_6B_RAPPORT.md`.

### D68. Mode stage ouvert sur /stage, avec son profil propre
- **Décision.** `/stage` est un mode comme les autres (fin de la page « bientôt disponible » de D67). Profil du mode : dates de début et de fin du stage, durée en semaines calculée et affichée, établissement et formation (texte libre), missions visées (texte libre), lien vers un portfolio, pièces jointes, objet et trame du mail de candidature spontanée, domaines, secteurs, tailles et départements des spontanées comme en alternance. Rien sur la convention.
- **Balises.** Au minimum `{date_debut}`, `{date_fin}`, `{duree_semaines}`, `{etablissement}`, `{formation}`, `{portfolio}` dans l'objet et la trame, en plus des balises existantes. Objet et trame par défaut génériques, valables pour n'importe quel utilisateur, qui annoncent un stage conventionné avec ses dates et sa durée.
- **Conséquence.** Migration 0012 (colonnes du profil). Les balises et la règle de durée retenues sont dans le rapport.

### D69. Sources du mode stage : Sirene seulement pour l'instant
- **Décision.** Candidatures spontanées par Sirene comme en alternance (cœurs et transverses, tailles, départements). Pas de LBA (alternance uniquement). France Travail : essai `motsCles=stage` en Île-de-France ajouté à `scripts/verifier_france_travail.py` (nombre d'offres, types et natures de contrat, 20 intitulés) ; France Travail n'est pas branché dans le mode stage tant que l'humain n'a pas lu le résultat. La page Offres du mode stage dit que les offres ne sont pas encore disponibles.
- **À reconsidérer** après lecture de `docs/referentiels/france_travail/verification_stage.json`.

### D70. « Tous les secteurs » explicite, message avant lancement, tous les modes
- **Constat.** En job, domaine « indifférent » : « Récupérer » ne cherchait rien sur Sirene sans le dire avant le lancement, alors que l'interface affichait « indifférent ».
- **Décision.** Case explicite « tous les secteurs » dans la partie spontanées du profil, non cochée par défaut, avec la mention du volume. Quand ni domaine, ni secteur, ni cette case ne sont choisis, un message visible dans le profil et sur la page Spontanées avant tout lancement. Vaut pour tous les modes.

### D71. Étiquette « déjà contactée en <mode> » aussi pour les entreprises récupérées plus tard
- **Décision.** L'étiquette s'applique à toute entreprise dont une adresse figure dans les adresses contactées d'un autre mode (dont les contacts historiques importés), y compris une entreprise récupérée après l'import. Complète D65 et D66.

### D72. Nettoyage des adresses contactées exclues : par l'humain
- **Décision.** Les règles de `shared/referentiels/emails_exclus.txt` (D47) s'appliquent aussi aux adresses contactées importées (par exemple `…@sentry.wixpress.com`), par la commande de nettoyage existante (`scripts/nettoyer_emails_exclus.py`), lancée par l'humain. Complète D62.
