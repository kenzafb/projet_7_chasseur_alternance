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
- **Remplacée** par D77 (phase 7) : IA locale, `IA_MODELE_ANALYSE`, `IA_MODELE_LETTRE`, `IA_MODELE_EXTRACTION`.

### D11. Plus jamais de résultat inventé par l'IA
- **Décision.** Aucun score, verdict ou lettre par défaut quand Mistral échoue. Erreur non récupérable (400, 401, 403, 404, 422) : arrêt immédiat du pipeline, message clair dans les logs et le bandeau. Erreur passagère épuisée (429, 5xx, réseau, réponse illisible) : l'offre est sautée. Dans les deux cas, l'offre n'est ni insérée, ni marquée vue, ni archivée : elle revient au lancement suivant.
- **Conséquence.** Sur les routes directes (lettre, réanalyse), rien n'est enregistré : 503 pour une erreur de configuration, 502 sinon.
- **Complétée** par D77 et D78 (phase 7) : IA injoignable bloquante ; réponse hors schéma redemandée une fois, puis offre sautée. Depuis D80, la recherche n'analyse plus : une offre sautée reste « non analysée » en base au lieu de ne pas être insérée.

### D12. Archivage « public spécifique » seulement pour les offres réservées
- **Décision.** La mention d'égalité des chances (« ouvert aux personnes en situation de handicap », « à compétences égales ») n'archive plus. Seules les tournures de réservation ou d'exigence explicites (« réservé aux », « exclusivement », « RQTH obligatoire », « vous devez être bénéficiaire de l'obligation d'emploi »...) archivent l'offre.
- **Raison.** Les trois offres archivées ainsi pendant la recette portaient toutes la mention standard.

### D13. Emails lus dans la page gardés quand Mistral échoue
- **Décision.** Si l'extraction par Mistral échoue, le scraper garde les emails trouvés par lecture directe de la page (regex, déobfuscation), notés non validés par l'IA (`emails_non_valides` dans `extra`). Une erreur non récupérable coupe l'IA pour le reste du lancement, avec un seul message.
- **Remplacée** par D81 (phase 7) : règles d'abord, l'IA pour les seules adresses douteuses.

### D14. Limites bornées par ce qui existe
- **Décision.** Le maximum du scraper est le nombre d'entreprises non traitées, celui de l'envoi le nombre d'entreprises avec email dont une adresse au moins n'a pas été contactée dans le mode courant. Le front l'affiche, le serveur l'applique (avec « demandé : X, ramené à Y », D6) et refuse en 400 un lancement sans rien à traiter.

## Phase 4b, points tranchés après le rapport (8 octobre 2026)

### D15. Emails non validés par l'IA : jamais envoyés automatiquement
- **Décision.** Les emails gardés sans validation par Mistral (D13) ne partent jamais d'eux-mêmes, même en mode test, et ne comptent pas dans le maximum d'envoi. Ils restent visibles dans la page Spontanées avec la mention « non validé ». L'utilisateur les valide à la main, une entreprise à la fois (`POST /api/spontanees/valider`), ou relance plus tard la validation par l'IA sur les entreprises concernées (`POST /api/spontanees/revalider`, limite « revalidations », 20 par défaut, 200 au plus, bornée par le nombre en attente).
- **Conséquence.** Une revalidation réussie remplace emails, téléphones et contact par ceux que l'IA retient ; un échec passager laisse l'entreprise en attente ; une erreur bloquante arrête la revalidation avec un seul message.
- **Complétée** par D81 (phase 7) : la validation se fait adresse par adresse ; une adresse validée par les règles part sans IA ; la revalidation repasse les seules adresses douteuses, sans relire le site.

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
- **Complétée** par D80 et D83 (phase 7) : la recherche n'appelle plus jamais l'IA, ANALYSE_IA reste l'interrupteur général ; sans IA, les règles de D81 valident encore les adresses de contact du domaine du site.

## Phase 5a, points tranchés après le rapport (8 octobre 2026)

### D20. Sans IA : archivage par mots-clés conservé, plafond d'offres propre
- **Décision.** Quand `ANALYSE_IA=false`, l'archivage par mots-clés reste appliqué (public réservé D12, école ou CFA, stage) ; seuls note basse et hors domaine disparaissent (D19). La limite d'offres par lancement a son propre plafond : 100 par défaut, 500 au plus (`LIMITES_LANCEMENT["sans_ia"]`), affichés dans l'interface à la place de ceux de l'analyse (30, 200).
- **Conséquence.** Même champ `max_analyses` pour la route ; valeur hors bornes ramenée et affichée (D6).
- **Plafond remplacé** par D80 (phase 7) : 100 par défaut, 500 au plus pour toute recherche, IA active ou non (`LIMITES_LANCEMENT["offres"]`, champ `max_offres`).

### D21. Analyse en différé des offres « non analysées » : travail futur
- **Décision.** Prévue pour l'arrivée du modèle local, non implémentée. En attendant, une offre `non_analysee` ne s'analyse qu'une à une, par le bouton « Analyser », IA active.
- **À faire** avec le modèle local : analyse en lot des offres `verdict = "non_analysee"`, avec archivage complet une fois l'analyse obtenue.
- **Réalisée** par D80 (phase 7).

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
- **France Travail remplacé** par D74 : branché dans le mode stage.

### D70. « Tous les secteurs » explicite, message avant lancement, tous les modes
- **Constat.** En job, domaine « indifférent » : « Récupérer » ne cherchait rien sur Sirene sans le dire avant le lancement, alors que l'interface affichait « indifférent ».
- **Décision.** Case explicite « tous les secteurs » dans la partie spontanées du profil, non cochée par défaut, avec la mention du volume. Quand ni domaine, ni secteur, ni cette case ne sont choisis, un message visible dans le profil et sur la page Spontanées avant tout lancement. Vaut pour tous les modes.

### D71. Étiquette « déjà contactée en <mode> » aussi pour les entreprises récupérées plus tard
- **Décision.** L'étiquette s'applique à toute entreprise dont une adresse figure dans les adresses contactées d'un autre mode (dont les contacts historiques importés), y compris une entreprise récupérée après l'import. Complète D65 et D66.

### D72. Nettoyage des adresses contactées exclues : par l'humain
- **Décision.** Les règles de `shared/referentiels/emails_exclus.txt` (D47) s'appliquent aussi aux adresses contactées importées (par exemple `…@sentry.wixpress.com`), par la commande de nettoyage existante (`scripts/nettoyer_emails_exclus.py`), lancée par l'humain. Complète D62.

## Phase 6b, résultats des scripts et points tranchés (9 octobre 2026)

`scripts/verifier_france_travail.py --stage` et `scripts/verifier_sirene.py --tous-secteurs` lancés par l'humain le 9 octobre 2026 (`docs/referentiels/france_travail/verification_stage.json`, `docs/referentiels/insee/verification_tous_secteurs.json`).

### D73. Points à valider de la phase 6b
- **Validés** (points 1 à 7 et 9 à 12 du rapport) : balises communes du mail et balises du stage réservées au stage, `{missions}` comprise ; durée arrondie à la semaine la plus proche, jours compris, au moins 1 ; dates en toutes lettres, `{duree_semaines}` sans le mot ; balise vide = envoi refusé avant le premier mail ; objet et trame par défaut du stage ; « tous les secteurs » cherché en dernier, en complément, mêmes tailles que les cœurs, exclusions conservées ; « Récupérer » refusé en job et en stage sans rien à chercher, lancé en alternance pour LBA ; « sans salarié » proposée en stage ; nettoyage par suppression des lignes de `emails_contactes` ; exclusion dès l'import de l'historique ; couleur verte du stage.
- **Point 8** : tranché par D75.

### D74. France Travail branché dans le mode stage (remplace D69 pour France Travail)
- **Constat.** `motsCles=stage` en Île-de-France : 73 offres, natures E1 55, E2 12, FS 6 (types CDI 37, CDD 34, MIS 2) ; le champ `alternance` des offres vaut vrai pour les 18 E2 et FS. Parmi les 20 intitulés d'exemple, trois désignent l'objet du poste (« Coordinateur de stages de formation », « Gestionnaire du service des stages », « Coordinateur en charge des ateliers, stages & restitution »).
- **Décision.** Recherche par `motsCles=stage`, domaines et secteurs du profil comme dans les autres modes ; natures E2 et FS (alternance) écartées ; seuls les intitulés où « stage » ou « stagiaire » désigne le poste sont gardés (en début d'intitulé, accolé à un tiret, après une barre oblique...), ceux où il désigne l'objet du poste sont écartés. Règles dans `shared/referentiels/intitules_stage.txt`, fichier de données à compléter, testées sur les 20 intitulés de l'essai. La page Offres du mode stage affiche ces offres « non analysées » comme les autres modes.
- **Conséquence.** En mode stage, l'archivage par mots-clés ne garde que « public réservé » : ni « stage » (le mot est attendu) ni « école ou CFA » (une école peut accueillir un stagiaire).

### D75. Départements et tailles des spontanées dans le profil job
- **Décision.** Le profil job a, comme l'alternance et le stage, les départements et les tailles des candidatures spontanées (avec l'option des effectifs inconnus), avec les mêmes valeurs par défaut que le stage : rien de coché, donc toute l'Île-de-France et toutes les tailles sauf « sans salarié », effectifs inconnus gardés. Clôt le point 7 de la phase 6a.

### D76. Volume de « tous les secteurs » mesuré
- **Décision.** `VOLUME_TOUS_SECTEURS` (`shared/naf.py`) affiche la mesure : 382 663 sièges actifs en Île-de-France hors « sans salarié », dont 67 755 à partir de 10 salariés (3 182 798 toutes tranches). La requête réelle, avec les activités exclues en ET, est acceptée par l'API (381 283).

## Phase 7 (IA locale avec Ollama), décisions du 14 octobre 2026

Décisions données par l'humain au lancement de la phase et mises en œuvre. Contexte : plus aucune IA extérieure ; Ollama tourne sur la machine (`http://localhost:11434`), sur processeur, avec `ministral-3:8b` (lecture 27 tokens/s, écriture 7 tokens/s) et `ministral-3:3b` (57 et 13 tokens/s), 12 Go de RAM visibles, un seul modèle chargé à la fois. Les choix faits pendant la mise en œuvre restent à valider dans `docs/PHASE_7_RAPPORT.md`.

### D77. IA interchangeable au format compatible OpenAI (remplace D10)
- **Complétée** par D85 (API native d'Ollama par défaut) et D86 (aucun retrait silencieux).
- **Décision.** `shared/ia.py` parle `chat/completions`, configuré par le `.env` : `IA_BASE_URL` (défaut `http://localhost:11434/v1`), `IA_API_KEY` (facultative), `IA_MODELE_ANALYSE`, `IA_MODELE_LETTRE`, `IA_MODELE_EXTRACTION` (défauts `ministral-3:8b`, `ministral-3:8b`, `ministral-3:3b`). Plus de SDK `mistralai`. Un seul appel à la fois dans tout le processus, délai d'attente long et réglable (`IA_DELAI_S`, 600 s par défaut). Serveur injoignable : arrêt du pipeline, « IA locale injoignable : vérifie qu'Ollama tourne », comme les autres erreurs bloquantes. Jamais de résultat inventé (D11).

### D78. Réponses structurées validées par Pydantic
- **Complétée** par D86 et D87 : un refus du schéma ou de la coupure de la réflexion est bloquant ; score borné en Python.
- **Décision.** Sortie JSON décrite par des modèles Pydantic (`shared/schemas_ia.py`), schéma imposé au serveur quand son API le permet (`response_format` de type `json_schema` ; un serveur qui le refuse est interrogé sans, la réponse restant validée). Une réponse invalide est redemandée une fois, puis l'offre est sautée et reste « non analysée ». Le mode de réflexion des modèles qui en ont un (Qwen notamment) est coupé dans la requête.

### D79. Prompts pour un petit modèle, un par mode
- **Décision.** Prompts plus courts, en français, schéma JSON écrit en toutes lettres, description de l'offre tronquée à une longueur réglable (`IA_LONGUEUR_DESCRIPTION`), seulement les champs utiles du profil. Un prompt d'analyse par mode, dont le mode stage (dates, missions visées, formation). Sens des prompts existants et règles d'archivage qui dépendent de l'analyse conservés.

### D80. Analyse en différé des offres en attente (réalise D21)
- **Décision.** La recherche insère toujours les offres « non analysées », sans attendre l'IA. Un pipeline « Analyser les offres en attente », par utilisateur et par mode, les traite des plus récentes aux plus anciennes, avec une limite par lancement, la progression dans le bandeau, un bouton d'arrêt et le temps restant estimé. Option du profil pour le lancer après chaque recherche.
- **Conséquence.** Migration 0013 (`profils.analyse_auto`, faux pour les profils existants).

### D81. Emails du scraper : règles d'abord, IA pour les cas douteux (remplace D13, complète D15)
- **Décision.** Des règles sans IA valident ou écartent d'office : domaine de l'adresse identique au domaine du site de l'entreprise, préfixes de contact ou de recrutement courants, liste d'exclusion existante (D47). L'IA (modèle d'extraction) ne sert qu'aux cas douteux ; sans IA, ils restent « non validés ». Règles dans un fichier de données facile à compléter (`shared/referentiels/validation_emails.txt`).
- **Complétée** par D88 à D90 (garde-fous de la validation d'office, envoi par adresse, adresses écartées par l'IA visibles).

### D82. Lettre de motivation à la demande
- **Décision.** Générée à la demande avec le modèle de lettre, avec un message d'attente dans l'interface.
- **Remplacée** par D106 : la lettre type est écrite par la personne, l'IA ne rédige que le paragraphe personnalisé.

### D83. ANALYSE_IA reste l'interrupteur général (complète D19)
- **Décision.** `ANALYSE_IA=false` : aucun appel à l'IA nulle part. `.env.example` et README décrivent l'installation d'Ollama, les modèles conseillés et `OLLAMA_MAX_LOADED_MODELS=1` pour les machines à peu de RAM.

### D84. Vérification de l'IA locale par un script lancé par l'humain
- **Décision.** `scripts/verifier_ia_locale.py` vérifie qu'Ollama répond, liste les modèles, analyse 3 vraies offres « non analysées » lues en lecture seule et valide un email douteux ; plusieurs modèles comparés sur les mêmes offres (`--modeles`), tableau du temps par offre, de la validité du JSON, du score et du verdict. Rien n'est écrit en base. Remplace `scripts/verifier_mistral.py`.

## Phase 7, corrections après le rapport (14 octobre 2026)

Retour de l'humain après une recherche sur les modèles locaux et Ollama en octobre 2026 : points 1 à 4 du compte rendu tranchés, et deux constats sur l'API (le format compatible OpenAI n'a pas de paramètre documenté pour couper la réflexion ; le ticket Ollama #14645 rapporte que `format` est ignoré pour Qwen3.5 quand la réflexion est coupée).

### D85. API native d'Ollama par défaut (complète D77)
- **Décision.** `IA_API=ollama` (défaut) : `POST /api/chat`, `"think": false` au premier niveau de la requête, schéma JSON dans `"format"`, `stream` faux, `options.num_ctx` (`IA_NUM_CTX`, 8192) et `options.temperature` (0,1 pour l'analyse et les emails, 0,6 pour la lettre). `keep_alive` (`IA_KEEP_ALIVE`, 10 min) est envoyé au premier niveau, où l'API d'Ollama le lit (pas dans `options`). `IA_API=openai` garde le format compatible OpenAI comme alternative. Jamais `tools` et `format` dans la même requête.

### D86. Aucun retrait silencieux, test de démarrage (complète D78)
- **Décision.** Un serveur qui refuse le schéma ou la coupure de la réflexion, ou qui renvoie un texte de réflexion malgré elle : erreur bloquante avec un message clair, jamais de nouvel essai sans le paramètre. Test de démarrage (requête courte, petit schéma, réponse qui doit être l'objet JSON tel quel sans texte de réflexion) avant le premier appel structuré de chaque modèle, au lancement de chaque analyse et dans `scripts/verifier_ia_locale.py`. Échec : arrêt avec le message, pas d'analyse dégradée. `IA_FORMAT_JSON` disparaît.

### D87. Contrôles en Python, pas confiés au modèle
- **Décision.** Score sans bornes dans le schéma (Ollama ignore minimum et maximum), ramené à 0..10 en Python. Emails : un appel par entreprise ; adresses retenues et « meilleur contact » contraints par des énumérations construites à partir des adresses trouvées dans la page (ou null), revérifiés en Python. Les règles d'éligibilité vérifiables en code restent en Python et ne sont pas demandées au modèle : type et nature de contrat (filtres France Travail du mode, alternance écartée en job et en stage, intitulés du stage), lieu (Île-de-France), niveau visé des offres LBA. Les dates des offres, texte libre, restent jugées par le modèle.

### D88. Validation d'office des emails avec garde-fous (point 1 du compte rendu, complète D81)
- **Décision.** Acceptée, seulement si le domaine de l'adresse est celui du site de l'entreprise, que ce site a été retenu parce que son domaine correspond au nom de l'entreprise (ni annuaire, ni sous-domaine d'hébergeur) et que le domaine n'est pas un fournisseur générique (free.fr, orange.fr, wanadoo.fr, sfr.fr, laposte.net, gmail.com, outlook, hotmail, yahoo, icloud, wix... ; sections `[fournisseurs_generiques]` et `[hebergeurs]` du fichier de règles). Sinon l'adresse est douteuse : IA ou validation manuelle. L'interface indique pour chaque adresse comment elle a été validée (règle, IA, à la main).

### D89. Envoi par adresse (point 2 du compte rendu)
- **Décision.** Validé : une entreprise part vers ses adresses validées, même s'il lui reste des adresses douteuses.

### D90. Avis négatif de l'IA visible (point 3 du compte rendu)
- **Décision.** Pas d'écart définitif invisible : l'adresse est gardée, jamais envoyée, affichée « écartée par l'IA » avec un bouton pour la valider quand même.

### D91. Limites avec l'IA, toute la file, mots-clés d'abord (point 4 du compte rendu, complète D80)
- **Décision.** Quand ANALYSE_IA est vrai : 30 offres par défaut par recherche et 30 analyses par lancement, plus une option « analyser toute la file » pour un lancement de nuit. La taille de la file en attente et le temps estimé pour la vider sont affichés. Les règles d'archivage par mots-clés passent avant l'IA. Sans IA, 100 offres par recherche (D20).

### D92. Autres points du rapport de la phase 7 : propositions gardées
- **Décision.** Points 2 à 9 et 13 à 15 du rapport validés tels que proposés : délai de 600 s sans nouvel essai après un délai dépassé, 5xx retentée une fois ; file des offres non analysées et non archivées, par date de publication ; archivage après analyse seulement pour une offre encore « nouvelle » ; bouton « Analyser » avec domaine et archivage complet ; identité retirée des prompts d'analyse, champs ramenés à 400 caractères, trois projets au plus ; prompt et trame par défaut du stage ; adresse nominative du domaine et fournisseur générique toujours douteux, 5 adresses au plus par entreprise ; revalidation sans relire le site ; `ANALYSE_IA=true` dans `.env.example`, script de vérification qui ignore `ANALYSE_IA=false` ; modèles `ministral-3:8b` et `ministral-3:3b` jusqu'à la comparaison du script. Le point 6 (score strict de 1 à 10) est remplacé par D87 (score ramené à 0..10 en Python).

### D93. Points 16 à 19 du rapport de la phase 7 : validés
- **Décision.** `keep_alive` envoyé au premier niveau de la requête, où l'API d'Ollama le lit ; temps pour vider la file estimé sur la moyenne des 50 dernières analyses du processus, 90 s par offre avant toute mesure ; test de démarrage refait à chaque redémarrage de l'application, une fois par modèle, sur la forme de la réponse seulement ; meilleur contact affiché seulement, l'envoi partant vers toutes les adresses validées.
- **En attente** : tableau de `scripts/verifier_ia_locale.py` et version d'Ollama, renvoyés par l'humain.

## Phase 7, comparaison avec un jugement humain (14 octobre 2026)

`scripts/verifier_ia_locale.py` lancé par l'humain avec `OLLAMA_IGPU_ENABLE=1` (Radeon 660M utilisée) : quatre modèles, dont `ministral-3:3b`, `ministral-3:8b` et `qwen3.5:9b`, passent le test de démarrage avec un JSON valide, environ 30 s par offre. Sur trois offres de stage jugées par l'humain pour un profil BUT2 de 10 semaines (février à avril) : O1 (Orange, 6 mois dès janvier 2027, Bac+5 ingénieur exigé), inéligible, notée 5 à 8 par les quatre modèles ; O2 (Bac+5 exigé), notée 7 et 9 par le 8b et le 9b.

### D94. Critères bloquants décidés en Python, plus par le modèle (complète D79 et D87)
- **Décision.** Le schéma de l'analyse ajoute des champs extraits de l'offre, sans jugement : `niveau_requis` (énumération bac, bac+2, bac+3, bac+4, bac+5, non_precise), `duree_mois` (nombre ou null), `date_debut_offre` (texte ou null), `alternance_seulement` (booléen). L'éligibilité qui en dépend est décidée en Python (`shared/eligibilite.py`) : niveau requis supérieur au niveau du profil d'au moins deux crans ; en mode stage, durée de l'offre supérieure à celle du profil de plus de 4 semaines, ou début de l'offre incompatible avec les dates du profil. Une offre inéligible a son score plafonné à 3, son verdict « inéligible » et la raison écrite (« Bac+5 exigé, profil Bac+2 », « 6 mois demandés, 10 semaines disponibles »). Une information non précisée ne rend jamais inéligible. Le prompt ne demande plus au modèle de juger le niveau ni les dates, et demande des notes étalées (8 à 10 réservés aux offres qui correspondent vraiment au profil et aux missions visées).
- **Niveau du profil.** Champ `niveau_etudes`, proposé désormais dans les trois modes ; vide, déduit de la formation quand c'est sans ambiguïté (BUT1 = bac, BUT2 = bac+2 en cours, BUT3 = bac+3) ; sinon le profil affiche un avertissement qui demande de le remplir.
- **Choix de mise en œuvre** (points 2 à 5 validés le 14 octobre 2026 ; point 1 remplacé par D95). En alternance, le niveau visé sert avant la formation quand `niveau_etudes` est vide ; Licence et Master sont lus comme le BUT (L1 = bac, L2 = bac+2, L3 = bac+3, M1 = bac+4, M2 = bac+5) ; deux niveaux différents dans la formation, ou « BTS » seul, sont ambigus. `alternance_seulement` rend inéligible en job et en stage. Mois de début sans année : non précisé ; début à date précise jusqu'à 7 jours avant le début du profil : accepté. Toute offre inéligible est archivée (« note basse »), quel que soit son score. La raison s'affiche en tête des points faibles (pas de nouvelle colonne en base). `scripts/verifier_ia_locale.py` affiche niveau requis, durée et raison d'inéligibilité.

### D95. Offre inéligible archivée « inéligible » (remplace le point 1 des choix de D94)
- **Décision.** Une offre inéligible (critère établi en Python ; depuis D99, jamais par le jugement du modèle) est archivée avec la raison distincte `ineligible`, et non plus `note_basse` (gardée pour l'archivage à la main et les offres déjà archivées). Son motif est visible sur la carte de l'offre (« Inéligible : Bac+5 exigé, profil Bac+2 » ; le cas « jugée inéligible par l'IA » est supprimé par D99), les archives ont un filtre « Inéligible », et un bouton « Remettre dans les offres actives » la désarchive.

### D96. Compétences, projets et expérience dans les trois modes, avertissement s'ils manquent
- **Constat.** Le profil du mode stage n'affichait ni compétences, ni projets, ni expérience, alors que les colonnes existent : l'IA jugeait les offres de stage sur la formation et les missions visées seulement.
- **Décision.** Les cartes « Compétences techniques » et « Projets » (même interface qu'en alternance) sont affichées dans les trois modes ; le stage a son champ « Expérience », le job gardait le sien. Le prompt d'analyse du stage cite niveau d'études, formation, missions visées, compétences, expérience et projets ; celui du job ajoute les projets ; la lettre cite les projets dans tous les modes. Si compétences, projets ou expérience sont vides, le profil l'indique : sans eux, l'IA juge à l'aveugle.
- **Conséquence.** Compétences et projets restent propres à chaque mode (une ligne de profil par mode) : à saisir aussi dans le profil stage et le profil job.

## Phase 7, résultats sur 8 offres de stage et test des lettres (14 octobre 2026)

### D97. Lettre : ministral-3:8b, première personne, rien d'inventé, texte brut
- **Constat.** Comparaison à l'aveugle (`--lettre`) : `ministral-3:8b` nettement le meilleur ; `qwen3.5:9b` écrit à la deuxième personne (« votre maîtrise de Linux vous permettrait »), `qwen3.5:4b` inverse les rôles (« Orange SA vous attire »), `ministral-3:3b` met des astérisques markdown et cite des outils absents de l'offre et du profil.
- **Décision.** `IA_MODELE_LETTRE=ministral-3:8b` (défaut inchangé). Le prompt de lettre impose la première personne (la personne candidate parle au recruteur), aucune mise en forme markdown, seulement des compétences et outils présents dans le profil ou l'offre, et pas de mot comme « expertise » pour un profil en formation. En Python, toute mise en forme markdown résiduelle est retirée (`generateur.sans_markdown`).

### D98. Valeurs extraites contrôlées contre le texte de l'offre, niveau exigé ou souhaité (complète D94)
- **Constat.** Sur 8 offres de stage : `duree_mois` vaut 2,5 pour presque toutes les offres et chez tous les modèles, c'est-à-dire la durée du profil (10 semaines), recopiée. « Étudiant(e) en informatique (école d'ingénieur, master ou équivalent) » (OHana) a été lu « Bac+5 exigé » et l'offre écartée, alors que c'est la plus adaptée. `qwen3.5:9b` a déclaré « Bac+5 exigé » quatre offres titrées « Ingénieur/e ... » dont le texte ne dit rien du niveau.
- **Décision.** Le prompt sépare nettement le profil et le texte de l'offre ; les champs extraits viennent uniquement du texte de l'offre, null ou non précisé sinon. En Python, chaque valeur est contrôlée contre la description (`controler_extraits`) : `duree_mois` gardée seulement si l'offre contient une durée correspondante (nombre suivi de mois ou semaines, à un demi-mois près ; les lignes « Expérience : » ajoutées par France Travail ne comptent pas) ; `niveau_requis` seulement si la description contient un indice correspondant (Bac+N, Master, M1, M2, école ou diplôme d'ingénieur, licence, bachelor, BTS, DUT, BUT en majuscules, bac) ; le mot « ingénieur » seul et l'intitulé du poste ne sont jamais des indices ; `date_debut_offre` seulement si le mois et l'année figurent dans l'offre. Sinon la valeur devient non précisée et ne peut pas rendre l'offre inéligible.
- **Exigence.** Nouveau champ `niveau_exigence` (exige, souhaite, non_precise). « ou équivalent », « idéalement », « de préférence », « souhaité », « apprécié », « un plus » près de l'indice de niveau donnent `souhaite`, même si le modèle a répondu `exige`. Seul `exige` rend inéligible ; `souhaite` baisse le score de 1 point (deux crans d'écart) ou 2 (davantage) et ajoute « Bac+5 souhaité, profil Bac+2 » aux points faibles. Cas testés : OHana souhaité, éligible ; MOSS (« dernière année d'école d'ingénieurs ou en Master 2 (Bac+5) ») exigé, inéligible ; quatre intitulés « Ingénieur/e ... » : non précisé. Le script affiche la colonne de l'exigence.

## Phase 7, résultats après D97 et D98 (14 octobre 2026)

Sur les 8 offres de stage : O1, O2 et O8 inéligibles pour de bonnes raisons, O3 éligible (8/10), plus aucun Bac+5 inventé.

### D99. Le modèle ne décide plus jamais de l'inéligibilité (complète D94, modifie D95)
- **Constat.** `ministral-3:3b` a déclaré inéligibles quatre offres sans aucune règle vérifiable, dont une qui correspond au profil : elle aurait été archivée à tort.
- **Décision.** Le schéma de l'analyse n'a plus de champ d'éligibilité, et le verdict déduit du score ne peut valoir qu'excellent, bon, moyen ou faible. Une offre n'est inéligible, et archivée « inéligible », que par les règles Python de `shared/eligibilite.py`. Le cas « jugée inéligible par l'IA » de D95 disparaît. Ce que le modèle juge encore (hors domaine, expérience exigée, poste senior, types de jobs à éviter) ne fait que baisser la note ; « Hors domaine » garde son archivage propre (raison `hors_domaine`, inchangée).

### D100. Niveau requis de secours lu par Python (complète D98)
- **Constat.** OHana (« école d'ingénieur, master ou équivalent ») ressort en `non_precise` chez les deux modèles retenus, alors qu'elle doit donner bac+5, souhaité.
- **Décision.** Si le modèle répond `non_precise` mais que la description contient un indice de niveau reconnu par le contrôle Python (Bac+N, Master, M2, école ou diplôme d'ingénieur...), le niveau et l'exigence détectés par Python sont utilisés (`niveau_detecte`), et la substitution est notée dans `extraits_ecartes`. Chaque indice vaut son niveau le plus haut (« Master » = bac+5) ; avec plusieurs indices (« BTS ou licence »), le plus bas, celui qui suffit. Exigence : souhaite si un marqueur (« ou équivalent »...) est proche d'un indice, exige sinon. De même, un niveau donné par le modèle avec une exigence `non_precise` devient exigé, sauf marqueur de souhait.

### D101. Modèles par défaut : ministral-3:3b pour l'analyse et les emails, ministral-3:8b pour la lettre (complète D77)
- **Décision.** `IA_MODELE_ANALYSE=ministral-3:3b`, `IA_MODELE_LETTRE=ministral-3:8b`, `IA_MODELE_EXTRACTION=ministral-3:3b`, dans `shared/config.py`, `.env.example` et le README.
- **Mesures** (`scripts/verifier_ia_locale.py`, machine de l'humain, 12 Go de RAM, octobre 2026). Sur processeur : `ministral-3:8b` lit 27 tokens/s et écrit 7 tokens/s (une à deux minutes par offre), `ministral-3:3b` lit 57 et écrit 13 tokens/s. Avec `OLLAMA_IGPU_ENABLE=1`, la Radeon 660M est utilisée (`qwen3.5:9b` à 100 % sur le GPU) : environ 30 s par offre. Les quatre modèles essayés (`ministral-3:3b`, `ministral-3:8b`, `qwen3.5:4b`, `qwen3.5:9b`) passent le test de démarrage avec un JSON valide. Analyse : avant D94, les quatre notaient 5 à 9 des offres de stage inéligibles et divergeaient fortement (O2 : 2, 0, 7 et 9) ; après D94, D97 à D100, sur 8 offres de stage, O1, O2 et O8 sont inéligibles pour de bonnes raisons et O3 éligible (8/10), sans Bac+5 inventé ; les critères bloquants ne dépendant plus du modèle, le plus rapide suffit pour noter et recopier. Lettre, comparaison à l'aveugle : `ministral-3:8b` nettement le meilleur ; `qwen3.5:9b` écrit à la deuxième personne, `qwen3.5:4b` inverse les rôles, `ministral-3:3b` met du markdown et cite des outils absents (D97).
- **À reconsidérer** si une prochaine comparaison humaine montre des notes de `ministral-3:3b` trop éloignées du jugement humain sur les offres éligibles.

## Phase 7, retour de recette sur l'analyse (14 octobre 2026)

### D102. Le hors domaine jugé par le modèle n'archive plus (suite de D99)
- **Constat.** « Stage Ingénieur/e Système » a été archivée hors domaine alors que c'est de l'informatique. Une offre archivée à tort est une erreur invisible ; une offre mal notée ne l'est pas.
- **Décision.** Un domaine « Hors domaine » répondu par le modèle ne fait plus que baisser la note, comme ses autres critères ; il reste affiché comme catégorie de l'offre. Archivent automatiquement les seules règles Python : l'éligibilité de `shared/eligibilite.py`, et l'archivage par mots-clés déjà en place (public réservé, école ou CFA, stage ; D12, D20, D74). La raison `hors_domaine` reste disponible pour l'archivage à la main.

### D103. Niveau « exigé » seulement avec un marqueur explicite (corrige D100 et D98)
- **Décision.** Même principe que D102 : un niveau détecté sans mot d'exigence explicite vaut « souhaite », pas « exige ». L'exigence est décidée en Python à partir du texte, jamais par le modèle seul : « exige » seulement si un marqueur clair (exigé, obligatoire, impératif, impérativement, requis, indispensable) est proche de l'indice de niveau et qu'aucun marqueur de souhait (« ou équivalent », « idéalement »...) ne l'adoucit. Seul « exige » rend inéligible ; « souhaite » baisse la note de 1 à 2 points (D98).
- **Conséquence acceptée.** MOSS (« dernière année d'école d'ingénieurs ou en Master 2 (Bac+5) », sans marqueur d'exigence) devient éligible, avec une note baissée de 2 points.

### D104. Points forts tirés du profil seulement
- **Constat.** `ministral-3:3b` attribue à la candidate des compétences absentes de son profil (« C/C++/Qt », « VoIP ») dans les points forts.
- **Décision.** Le prompt d'analyse précise qu'un point fort ne cite que des compétences, projets ou expériences écrits dans le profil, jamais une compétence demandée par l'offre que le profil ne cite pas ; si rien ne correspond, il le dit (« Aucune compétence du profil ne correspond à l'offre »). Pas de contrôle Python : un test vérifie le prompt construit.

### D105. « J'ai postulé » sur les offres : le statut « envoye » existant, une seule notion de « postulé »
- **Constat.** Une offre n'avait qu'une action, l'archivage. Les statuts existaient déjà : `nouveau`, `en_cours` (lettre générée), `envoye`, `reponse`, `entretien`, `refus` (page « Mes candidatures »), `archive` ; et la colonne `date_candidature` depuis la migration 0001. L'application n'envoie aucun mail pour une offre : seules les candidatures spontanées partent par l'envoyeur, sur les entreprises (`entreprises_modes.mail_envoye`, une autre notion, celle d'un mail envoyé).
- **Décision.** Pas de nouveau statut ni de migration : « postulée » est le statut `envoye`, affiché « Postulée », avec `date_candidature`. Sur l'offre : bouton « J'ai postulé » avec la date du jour (heure de Paris), modifiable, date future refusée ; « Changer la date » et « Annuler la candidature » (retour à `nouveau`, date effacée) ; une offre en entretien, réponse ou refus garde son suivi quand on change la date. Postuler sur une offre archivée la désarchive. « Désarchiver » (« Remettre dans les offres actives » pour une offre inéligible) existait déjà. Page Offres : filtre « Toutes les offres / À traiter / Postulées », les postulées triées par date de candidature, la plus récente d'abord ; le compteur « À postuler » ne compte plus les offres postulées. Isolation par utilisateur et par mode, comme les autres routes.

### D106. Lettre : lettre type de la personne, l'IA n'écrit que le paragraphe personnalisé (remplace D82)
- **Décision.** La candidate ne veut plus de lettre générée en entier. Elle écrit sa lettre type dans le profil (section « Lettre de motivation type », désormais dans les trois modes, une par mode ; bouton « Partir d'un exemple »). Balises : `{entreprise}`, `{poste}`, `{date}` et `{contact_entreprise}` (bloc destinataire : entreprise puis lieu), remplacées en Python ; `{paragraphe}`, obligatoire, rédigé par `IA_MODELE_LETTRE`. `{paragraphe_entreprise}`, ancien nom, reste accepté, comme les lettres types déjà écrites. Le paragraphe : 3 à 5 phrases à la première personne sur ce qui l'attire dans cette entreprise et ce poste et le lien avec un élément réel de son profil, appuyé sur le texte de l'offre, sans formule de politesse, sans redire la lettre type (qui est fournie au modèle sans ses balises), sans markdown, sans tiret cadratin ni esperluette (retirés aussi en Python), sans le mot « expertise ».
- **Interface.** « Préparer la lettre » rédige le paragraphe, affiché et modifiable ; « Régénérer le paragraphe » ; « Insérer dans ma lettre type » assemble la lettre en Python et l'enregistre (une offre « nouvelle » passe « en cours », une offre postulée garde son statut). Sans IA, le paragraphe s'écrit à la main et s'insère de même. Sans lettre type, ou sans `{paragraphe}` : message clair qui renvoie au profil, aucune génération complète en secours. Routes `POST /api/lettre/paragraphe` (rien d'enregistré) et `POST /api/lettre/assembler`, à la place de `/api/generer_lettre`.
- **Script.** `scripts/verifier_ia_locale.py --lettre` compare à l'aveugle ce paragraphe, avec la lettre type du profil (sinon l'exemple du mode, signalé).

## Phase 7, retour de recette sur D105 et D106 (14 octobre 2026)

### D107. Un seul tableau de suivi par mode : offres postulées et spontanées envoyées (complète D105)
- **Constat.** Deux tableaux coexistaient : « Mes candidatures » filtrait en mémoire les offres déjà chargées par la page Offres (statuts envoye à refus), « Spontanées envoyées » lisait les entreprises par `/api/spontanees/suivi`, avec ses propres statuts (à relancer, bounce). Le premier n'était recalculé qu'au rechargement complet de la page : une offre marquée « J'ai postulé » n'y apparaissait pas tout de suite, et les spontanées n'y figuraient jamais.
- **Décision.** Une seule page « Candidatures » par mode, lue par `GET /api/suivi` : chaque ligne vient de sa table d'origine (candidatures pour une offre, entreprises_modes pour une spontanée), rien n'est recopié. Colonnes : entreprise, poste, type (offre ou spontanée), date de candidature, statut, lien vers l'offre ou le site et contact. Statuts existants repris pour les deux types : envoye (« Postulée » pour une offre, « Envoyée » pour une spontanée), a_relancer, reponse, entretien, refus, et bounce pour les spontanées seulement ; « À relancer » est calculé pour les deux après 7 jours sans changement. Le statut se change depuis le tableau (`POST /api/suivi/statut`), écrit dans la table d'origine. Le tableau se met à jour dès « J'ai postulé » ou son annulation. La page « Spontanées envoyées » disparaît (son ancienne adresse ouvre la nouvelle) ; ses routes restent pour compatibilité.

### D108. Entreprise inconnue : balises laissées visibles dans la lettre, à compléter (complète D106)
- **Décision.** Si le nom de l'entreprise de l'offre vaut « Inconnue » (ou est vide, ou une autre valeur de masquage de France Travail), `{entreprise}` et `{contact_entreprise}` ne sont pas remplacées : elles restent dans la lettre assemblée. La fenêtre de la lettre les surligne dans un aperçu, avec le message « Nom de l'entreprise inconnu, à compléter », et l'aperçu suit la saisie jusqu'à ce qu'elles soient remplacées. La formule « À l'attention du service recrutement » n'est plus mise d'office.

### D109. Paragraphe personnalisé : court, à la première personne, sans rien redire de la lettre type (complète D106)
- **Constat.** Sur l'offre IPv6, le paragraphe était impersonnel (« correspondent aux intérêts portés vers », « renforcent une capacité »), reprenait Arch et le Chasseur, déjà dans la lettre type, et inventait des liens.
- **Décision.** Le modèle reçoit la lettre type entière, sans ses balises, avec la consigne de ne citer aucun fait, projet ou expérience qui y figure déjà. Paragraphe de 2 ou 3 phrases, 60 mots au plus, à la première personne (je, me, mon) ; tournures impersonnelles interdites. Contenu : ce qui attire la personne précisément dans cette mission ou cette entreprise, d'après le texte de l'offre, et pourquoi cela rejoint ce qu'elle vise (missions visées en stage, types de jobs en job, domaines et ce que la formation apporte en alternance) ; pas de liste de compétences ; aucun intérêt ni compétence absents du profil.
- **Contrôle Python.** Au-delà de 80 mots, le paragraphe est redemandé une fois ; encore trop long, il est gardé avec un avertissement affiché dans la fenêtre de la lettre. `scripts/verifier_ia_locale.py --lettre` affiche le nombre de mots de chaque paragraphe et le dépassement.

### D110. Une candidature n'est suivie que dans Candidatures (complète D105 et D107)
- **Décision.** Une offre postulée sort de la page Offres, qui n'affiche plus que les offres à traiter (nouveau, en cours), compteurs compris ; le filtre « À traiter / Postulées » de D105 est retiré. Date de candidature et « Annuler » se font dans le tableau Candidatures ; annuler remet l'offre dans la page Offres. Même logique pour les spontanées : la liste de la page Spontanées ne montre plus que les entreprises pas encore envoyées (filtre « Envoyés » retiré), les envoyées ne sont plus que dans le tableau.

### D111. Couleur du statut sur le menu fermé seulement
- **Décision.** Dans le tableau Candidatures, la couleur du statut (fond, bordure, texte) ne s'applique qu'au menu fermé ; les options de la liste déroulante gardent le texte et le fond neutres de l'application. L'application n'a pas de thème sombre : rien d'autre à vérifier.


## Phase 8, bascule NAF 2025 (12 novembre 2026)

### D112. Code NAF des entreprises dans les deux nomenclatures (complète D49 et D50)
- **Constat.** Seul le code de la période de l'établissement (`activitePrincipaleEtablissement`, en NAF rév. 2) était enregistré, même pour une recherche en NAF 2025 ; une entreprise trouvée avant le 1er janvier 2027 n'aurait eu aucun code NAF 2025.
- **Décision.** Deux colonnes `entreprises.naf_rev2` et `entreprises.naf_2025` (migration 0014), remplies quelle que soit la nomenclature active. Sirene : code de la période et `activitePrincipaleNAF25Etablissement`, à défaut ceux de l'unité légale. Les deux nomenclatures n'ont aucun code en commun : chaque code se classe par la table de l'INSEE, ce qui marche aussi quand la période passera en NAF 2025. Un code manquant est déduit de l'autre seulement quand la table n'en donne qu'un ; sinon il reste vide. LBA : « 6201Z » lu comme 62.01Z. Une entreprise déjà en base que Sirene ou LBA retrouve voit ses codes manquants complétés. `secteur` et `extra.code_naf` gardent le code brut de la source.
- **Entreprises existantes.** Migration 0014 : `naf_rev2` tiré de `secteur` ou de `extra.code_naf`, `naf_2025` de la table quand la cible est unique ; vide pour une correspondance multiple, jusqu'à ce que Sirene retrouve l'entreprise. Migration lancée par l'humain après sauvegarde de la base.

### D113. Repli si l'API refuse la variable NAF 2025 (complète D50 et D54)
- **Constat.** Rien n'est vérifié pour l'après-bascule : `activitePrincipaleUniteLegale` portera sans doute les codes NAF 2025, et `activitePrincipaleNAF25UniteLegale` pourrait disparaître.
- **Décision.** Une recherche en NAF 2025 refusée par l'API (400) est refaite une fois avec la variable de repli (`VARIABLE_NAF_REPLI` de `parametres_sirene.py` : `activitePrincipaleUniteLegale`), avec les mêmes codes NAF 2025. Acceptée, elle sert aux recherches suivantes du lancement ; refusée aussi, la recherche est abandonnée comme toute recherche en erreur. Le journal donne la variable du plan, le refus, le repli et, dans le bilan, les variables employées.
- **Vérification.** `scripts/verifier_sirene.py`, section 7 : sur 100 sièges de Paris sans filtre d'activité, valeurs de `nomenclatureActivitePrincipaleUniteLegale` et nomenclature réelle des codes de `activitePrincipaleUniteLegale` et de la période (classés par la table de l'INSEE), puis la variable de repli avec 62.10Y. Si la variable NAF25 ne filtre plus et que le repli filtre, le script propose le repli dans `VARIABLE_NAF`. À relancer par l'humain après le 1er janvier 2027.

### D114. NOMENCLATURE_NAF documentée dans `.env.example`
- **Décision.** `NOMENCLATURE_NAF=` est livrée vide dans `.env.example`, avec ce que veut dire chaque valeur : vide, la nomenclature suit la date (bascule au 1er janvier 2027, heure de Paris, D50) ; `NAFRev2` ou `NAF2025` la forcent ; une valeur inconnue est ignorée. Le forçage sert à essayer la NAF 2025 avant la bascule ou à revenir en arrière après ; les deux codes des entreprises (D112) sont enregistrés dans tous les cas.

### D115. Table de correspondance INSEE : édition d'octobre 2026 (complète D49)
- **Décision.** `docs/referentiels/insee/correspondance_naf_rev2_naf2025.csv` vient de l'édition d'octobre 2026 (« TABLE COMPLETE - octobre 2026 », modifiée le 27 octobre 2026), convertie au format de l'édition de janvier : six colonnes, espaces et retours à la ligne ramenés à un espace, ligne sans code NAF rév. 2 écartée (46.89Y, « pas de correspondance déterminée »). 1241 lignes au lieu de 1223 ; aucun code créé ni supprimé dans l'une ou l'autre nomenclature ; 22 correspondances ajoutées, 4 retirées, toutes hors des codes de la correspondance.
- **Correspondance (M18, C15, exclusions).** Aucune cible ni aucun type ne change ; codes retenus inchangés. Intitulé NAF 2025 de 68.32G et 66.19G (« détentrices de » devient « support de ») mis à jour. 61.90Z : la fourniture d'un accès téléphonique et internet dans des installations ouvertes au public passe de 61.90Y à 61.20Y, après les 200 caractères gardés du contenu ; noté dans la note de l'entrée. Les codes NAF 2025 des secteurs choisis par division (D57) sont identiques.

### D116. Repli si la variable NAF 2025 est acceptée mais vide (complète D113)
- **Constat.** Après la bascule, `activitePrincipaleNAF25UniteLegale` pourrait rester acceptée mais ne plus être remplie : pas de refus (400), donc pas de repli D113, et toutes les recherches à 0.
- **Décision.** En NAF 2025, une recherche avec la variable NAF25 qui réussit avec 0 résultat au total est refaite une fois avec la variable de repli (`activitePrincipaleUniteLegale`) et les mêmes codes. Le repli trouve des résultats : il sert pour le reste du lancement, avec au journal « variable NAF25 vide, repli utilisé » et les deux totaux. Les deux à 0 (ou le repli refusé) : le 0 est gardé, sans erreur, avec une ligne au journal. Dès qu'une recherche avec la variable NAF25 a donné des résultats dans le lancement, la variable est remplie et un 0 n'est plus mis en doute (pas de requête de plus).

## Phase 9, copie de profil entre modes (12 novembre 2026)

### D117. Copie de sections du profil depuis un autre mode : sections et règles
- **Constat.** Chaque mode a sa ligne dans `profils`, avec toutes les colonnes ; la page Profil n'en montre qu'une partie selon le mode. Deux colonnes changent de sens : `langues` est « Langues » en alternance et « Atouts / compétences » en job (absente en stage) ; `niveau_etudes` est « actuel » en alternance et en stage, « obtenu » en job. `portfolio` n'est affiché qu'en stage.
- **Sections copiables** (`shared/copie_profil.py`), chacune limitée aux champs affichés avec le même sens dans les deux modes : identité (prénom, nom, email, téléphone, ville), liens (LinkedIn, GitHub), formation et niveau d'études actuel (entre alternance et stage seulement), expérience, compétences, projets, lettre type, email de candidature spontanée (objet et message).
- **Jamais copiés.** Propres au mode : critères de recherche (domaines, filtres, réglages des spontanées), dates, établissement et missions du stage, niveau visé, ce que la formation apporte, critères à éviter, champs du job, analyse automatique. Sens différent : langues, niveau d'études du job. Portfolio : affiché dans un seul mode.
- **Aperçu.** Pour chaque section, valeur actuelle (mode de la page) et valeur copiée, champ par champ. Une section remplie et différente dans le mode cible doit être nommée dans `ecraser`, sinon la copie est refusée sans rien écrire ; une section identique ne demande rien. Email : une balise inconnue du mode cible ({date_debut} du stage vers l'alternance) rend la section impossible à copier, avec le message de `verifier_balises`.
- **Isolation.** Le mode de la page est la cible, la source un autre mode ; les deux profils sont lus par l'utilisateur de la session, aucun identifiant n'est reçu. Copie en une transaction : tout ou rien. Routes `GET /api/profil/copie/sections`, `POST /api/profil/copie/apercu`, `POST /api/profil/copie`.

### D118. Pièces jointes copiées par référence partagée (complète D117)
- **Constat.** Les pièces jointes sont stockées par mode (`profils.pieces_jointes`, liste de {nom, fichier}), mais les fichiers sont déjà faits pour être partagés : un envoi écrit toujours un fichier neuf au nom unique (jamais un fichier existant réécrit), et un fichier n'est effacé du disque que quand plus aucun mode de l'utilisateur ne le référence (`fichiers_references`, bug 9).
- **Décision.** La copie met dans le mode cible les mêmes références que dans la source, sans dupliquer les fichiers. C'est le plus sûr : rien ne peut diverger ni rester orphelin. Supprimer la pièce dans un mode la laisse dans l'autre, et la remplacer dans un mode écrit un nouveau fichier sans toucher à l'autre. Une duplication aurait doublé le disque et ajouté une écriture de fichier qui peut échouer à moitié, sans rien protéger de plus.
- **Écrasement.** Comme les autres sections : la liste du mode cible est remplacée, après confirmation si elle était remplie. Les fichiers qu'elle seule référençait sont effacés du disque après la copie ; ceux encore utilisés par un autre mode restent.

### D119. Interface « Copier depuis un autre mode » (complète D117 et D118)
- **Décision.** Sur la page Profil des trois modes, un bouton « Copier depuis un autre mode » dans le bandeau d'accueil ouvre une fenêtre en trois étapes : mode source (les deux autres modes), sections copiables de ce mode vers celui de la page (cases), puis aperçu. Une source sans profil enregistré le dit et ne propose rien.
- **Aperçu.** Une carte par section, champ par champ : valeur actuelle et valeur copiée côte à côte (l'une sous l'autre sur téléphone). Une section déjà remplie ici et différente porte « déjà rempli ici : sera écrasé » et une case « Remplacer ce qui est rempli ici par la valeur copiée » : « Copier » reste désactivé tant qu'une de ces cases n'est pas cochée, et le pied de la fenêtre dit lesquelles manquent. Une section identique porte « identique : rien ne change ». Une section impossible (balise de l'email inconnue du mode) est en rouge avec le message, et n'est pas envoyée.
- **Après la copie.** La fenêtre se ferme, le profil est rechargé depuis la base et la barre d'enregistrement affiche les sections copiées. La fenêtre prévient que des modifications pas encore enregistrées sur la page seront remplacées.

### D120. Portfolio dans la carte Identité, copié avec les liens (complète D117)
- **Décision.** Le champ portfolio quitte la carte « Ton stage » pour la carte Identité, commune aux trois modes, après GitHub. La section « Liens » de la copie entre modes devient « LinkedIn, GitHub, portfolio ».
- **Données.** Aucune migration ni reprise : `profils.portfolio` existe déjà sur la ligne de chaque mode. La valeur du profil de stage reste sur sa ligne et s'affiche au même endroit qu'avant pour le stage, dans la carte Identité ; en alternance et en job le champ est vide jusqu'à saisie ou copie.
- **Inchangé.** La balise `{portfolio}` de l'email de candidature spontanée reste propre au mode stage (D74 et suivantes) : l'étendre aux autres modes serait une décision à part.

### D121. Copie refusée tant que le profil a des modifications non enregistrées (remplace le rappel de D119)
- **Constat.** La copie recharge le profil depuis la base : une saisie pas encore enregistrée était perdue, avec un simple rappel dans la fenêtre.
- **Décision.** Au chargement et après chaque enregistrement réussi, la page garde ce que « Enregistrer » enverrait (tous les champs du mode, compétences, projets, domaines, options de recherche). Au clic sur « Copier depuis un autre mode », si le formulaire diffère, la fenêtre ne s'ouvre pas : un message « Enregistre d'abord tes modifications » s'affiche sous le bouton, avec « Enregistrer puis copier » et « Annuler ». « Enregistrer puis copier » enregistre comme le bouton habituel (mêmes contrôles) et n'ouvre la fenêtre que si l'enregistrement a réussi ; sinon le message dit que l'enregistrement est impossible. Pièces jointes et compte d'envoi, enregistrés dès leur saisie, ne comptent pas.

## Phase 10, compte et Paramètres (12 novembre 2026)

### D122. Page Paramètres : mot de passe, email de connexion, compte d'envoi
- **Page.** « Paramètres » dans le menu « Mon compte », sous Profil, la même dans les trois modes (aucun paramètre « mode » lu par ses routes). Trois cartes : email de connexion, mot de passe, compte d'envoi.
- **Mot de passe.** Ancien mot de passe obligatoire, nouveau selon les règles de l'inscription (`verifier_nouveau_mot_de_passe`, 10 caractères minimum), confirmation identique, différent de l'actuel. `POST /api/compte/mot_de_passe`.
- **Autres sessions déconnectées.** La session est un cookie signé, sans état côté serveur. Le cookie porte désormais, avec l'id, une empreinte du mot de passe : HMAC par SECRET_KEY du hash, jamais le hash (le cookie est lisible). Une session dont l'empreinte ne correspond plus est fermée à la requête suivante. Changer le mot de passe rouvre la session courante avec la nouvelle empreinte : elle reste ouverte, toutes les autres sont fermées. Sans migration. Conséquence : les sessions ouvertes avant cette version n'ont pas d'empreinte et sont fermées une fois (chacun se reconnecte une fois).
- **Email de connexion.** Mot de passe obligatoire, format vérifié, mis en minuscules, refusé s'il est déjà pris. `POST /api/compte/email`. L'email de contact des profils et l'adresse du compte d'envoi ne changent pas.
- **Compte d'envoi.** Sa carte quitte le Profil pour Paramètres ; mêmes champs, mêmes routes `/api/compte_envoi/*`. Le chiffrement Fernet n'est pas touché : sa clé est `CLE_CHIFFREMENT`, globale, indépendante de l'email et du mot de passe de connexion. Les messages qui renvoyaient à « Profil, section Compte d'envoi » renvoient à Paramètres.

### D123. Mot de passe oublié, version locale : mot de passe temporaire donné par l'administratrice
- **Script.** `scripts/reinitialiser_mot_de_passe.py <email>`, lancé par l'administratrice sur la base de DATABASE_URL, avec confirmation (`--oui` pour s'en passer). Il tire un mot de passe temporaire aléatoire (`secrets`, 4 groupes de 4 caractères sans 0/O/1/l/I, environ 92 bits), enregistre son hash, met `users.mot_de_passe_temporaire` à vrai et l'affiche une seule fois à l'écran. Il n'est écrit nulle part ailleurs : ni journal, ni fichier ; perdu, on relance le script. Le hash change : toutes les sessions du compte sont fermées (D122).
- **Connexion suivante.** Avec le mot de passe temporaire, la connexion mène à `/mot-de-passe-temporaire` : temporaire, nouveau mot de passe (règles de l'inscription), confirmation. Tant que ce n'est pas fait, toute page de l'espace y redirige et toute route `/api/` répond 403. Une fois changé, l'indicateur repasse à faux et la session continue.
- **Page de connexion.** Lien « Mot de passe oublié ? » vers une page qui dit de contacter l'administratrice.
- **Migration 0015** (`users.mot_de_passe_temporaire`, faux pour les comptes existants), à lancer par l'humain après sauvegarde. `ADD COLUMN` direct, sans `batch_alter_table` : sur SQLite, la recréation de `users` effaçait en cascade profils, candidatures et entreprises (constaté par le test de la migration 0002 jusqu'à head, corrigé avant tout commit). La migration 0014 déjà lancée a été vérifiée sur une base de test : `entreprises_modes` intacte.

### D124. À préparer pour l'hébergement : lien de réinitialisation par email (non codé)
- **Aujourd'hui.** App en local, 3 comptes, pas d'adresse d'envoi propre à l'app : le mot de passe oublié passe par l'administratrice (D123). Les comptes d'envoi SMTP sont ceux des utilisateurs, pour leurs candidatures : jamais pour des mails de l'app.
- **Adresse d'envoi de l'app.** Un compte SMTP ou un service transactionnel propre à l'app (`noreply@<domaine>`), configuré dans le `.env` (hôte, port, identifiant, mot de passe), avec SPF, DKIM et DMARC sur le domaine pour ne pas finir en indésirables. Distinct des comptes d'envoi des utilisateurs.
- **URL publique.** Une variable `URL_PUBLIQUE` (https obligatoire, `COOKIE_SECURE=true`) pour construire le lien ; jamais déduite de l'en-tête Host de la requête (empoisonnement du lien).
- **Jeton.** Aléatoire (`secrets.token_urlsafe(32)`), à usage unique, valable 30 minutes. Table dédiée (user_id, empreinte SHA-256 du jeton, expire_le, utilise_le) : seul le hash est stocké, le jeton n'apparaît que dans le mail. Une nouvelle demande invalide les jetons précédents du compte ; un changement de mot de passe aussi. Jeton expiré, déjà utilisé ou inconnu : même message neutre.
- **Demande.** Page « Mot de passe oublié » avec un champ email ; réponse identique que le compte existe ou non (pas de révélation des comptes), délai constant ; limite de demandes par adresse et par IP (par exemple 3 par heure).
- **Réinitialisation.** Le lien ouvre une page qui demande le nouveau mot de passe (règles de l'inscription) ; à l'enregistrement : hash mis à jour, jeton consommé, toutes les sessions fermées (empreinte, D122), `mot_de_passe_temporaire` à faux. Mail de notification « ton mot de passe a été changé » à l'adresse du compte.
- **Journaux.** Ni jeton, ni lien, ni mot de passe dans les logs ; seulement « demande pour le compte n », « réinitialisation faite pour le compte n ».
- **Le script de D123 reste** comme recours de l'administratrice.

### D125. Balise {portfolio} dans les emails et les lettres des trois modes (complète D120)
- **Emails.** `{portfolio}` passe des balises du stage aux balises communes : objet et message du mail de candidature spontanée, dans les trois modes. Comme toute balise du mail, vide dans le profil, elle bloque l'envoi avant le premier mail, avec le message qui renvoie au profil. Les autres balises du stage (dates, durée, établissement, formation, missions) restent propres au stage.
- **Lettres.** `{portfolio}` rejoint les balises de la lettre type (contrôle côté serveur et côté page), remplacée par le portfolio de la carte Identité. Vide : la balise reste dans la lettre assemblée, surlignée avec « Portfolio vide dans le profil (carte Identité), à compléter », comme l'entreprise inconnue (D108) ; la lettre n'est pas bloquée, la personne la complète avant le PDF.
- **Aides du profil** (lettre type, email) mises à jour.

## Phase 11, candidature via La Bonne Alternance (12 novembre 2026)

### D126. Pas d'API de candidature LBA : pages de candidature du site
- **Décision.** L'API de candidature de La Bonne Alternance (jobApply, api.apprentissage.beta.gouv.fr) n'est pas utilisée : l'accès en production demande une habilitation, la documentation exclut l'usage individuel ou personnel, et elle ne couvre que les offres publiées. Les candidatures passent par les pages du site labonnealternance.apprentissage.beta.gouv.fr, ouvertes par la personne dans son navigateur ; l'app ne soumet rien elle-même.
- **Remplace** la proposition de SPEC_SOURCES section 3 (« LBA propose une API qui transmet directement une candidature »), et l'identifiant `apply.recipient_id` reste noté sans servir à un envoi.

### D127. Vérifier quelles pages LBA ont un formulaire de candidature
- **Constat.** Les trois pages d'entreprises connues (WETRADELOCAL, GRANITE, LEHIBOU CYBERSECURITY, `apply.url` fourni par l'API) mènent à la bonne entreprise mais affichent « Nous n'avons pas de contact pour cette entreprise » : aucun formulaire. `apply.recipient_id` n'est présent que pour 772 entreprises sur 4148 (vérification du 9 octobre 2026). Hypothèse : seules celles-là ont un formulaire.
- **Décision.** `scripts/verifier_lba.py`, section 9, sort 3 pages d'entreprises avec `apply.recipient_id` et 3 sans, et jusqu'à 3 `apply.url` d'offres par partenaire (lues dans les réponses déjà reçues, aucune requête de plus), avec le nombre d'offres sans `apply.url`. L'humain les ouvre ; si l'hypothèse est contredite, les règles des boutons (D129) sont ajustées.

### D128. Jamais de lien LBA construit au hasard (point 5)
- **Constat.** Sans `apply.url`, le scraper construisait pour une offre `…/emploi/<identifiant>`, format jamais observé. Pour les entreprises, l'API fournit `apply.url` dans 4148 cas sur 4148, au format `/emploi/recruteurs_lba/<SIRET>/<slug>` ; ouverte avec un slug quelconque, la page montre la même entreprise : elle ne dépend que du SIRET.
- **Décision.** `shared/lba.py` décide seul. Offre : page de candidature seulement si elle vient de LBA et que son `apply.url` (gardée dans `lien`) est une page `https://labonnealternance.apprentissage.beta.gouv.fr/emploi/<type>/<identifiant>[/<slug>]` ; une `apply.url` de partenaire hors du site n'en est pas une. Plus de repli : sans `apply.url`, l'offre n'a pas de lien. Les liens inventés déjà en base (`/emploi/<id>`, un seul segment) ne sont plus renvoyés à la page (masqués à la lecture, sans migration). Entreprise trouvée par LBA : son `apply.url` si elle a ce format et le même SIRET, sinon la page construite d'après ce format à partir d'un SIRET valide de 14 chiffres ; sans SIRET valide, rien.

### D129. Boutons « Postuler sur La Bonne Alternance » (point 2)
- **Offres.** Une offre LBA dont la page de candidature est connue (D128) porte « Postuler sur La Bonne Alternance », qui ouvre cette page dans un nouvel onglet, dans le bloc où se trouve « J'ai postulé ». L'API renvoie `page_lba` (vide sinon). Offre de partenaire hors du site LBA : seulement le lien habituel « Voir l'offre ».
- **Entreprises des spontanées** trouvées par LBA, selon la réponse de l'humain à D127 (option 1) : « Postuler sur La Bonne Alternance » seulement si LBA a un contact (`apply.recipient_id`, gardé dans `extra.lba.candidature_id`), car c'est la condition supposée du formulaire ; sinon un simple lien « Voir sur La Bonne Alternance » (page d'information, « pas de contact »). L'API renvoie `lba` : {url, formulaire}, ou rien pour une entreprise que LBA n'a pas trouvée ou sans URL déterminable.
- **À ajuster** si la vérification de D127 contredit l'hypothèse.

### D130. « J'ai postulé » à côté du bouton La Bonne Alternance (point 3)
- **Offres.** « Postuler sur La Bonne Alternance » est placé dans le bloc qui porte déjà la date et « J'ai postulé » (D105) : au retour, l'offre passe « Postulée » à la date choisie (aujourd'hui par défaut), comme toute offre.
- **Entreprises.** À côté du bouton, une date (aujourd'hui par défaut, jamais dans le futur) et « J'ai postulé » (`POST /api/spontanees/postule_lba`) : l'entreprise passe « Envoyée » dans le mode, sans email ni destinataire, avec la note fixe « Candidature sur La Bonne Alternance » (`mail_note`, sans migration). Elle quitte la liste des spontanées à traiter et entre dans le tableau Candidatures, avec la page LBA comme lien et « La Bonne Alternance » comme contact. Refusé pour une entreprise d'un autre utilisateur, déjà envoyée, ou sans formulaire LBA (D129). L'envoyeur ne la contacte plus (déjà envoyée).
- **Pas d'annulation** depuis la liste pour l'instant : le statut se change dans le tableau Candidatures.

### D131. Entreprises LBA sans email : candidature par la page LBA, plus « bloquées » (point 4)
- **Constat.** Une entreprise sans email portait « non trouvé » et « ignoré », et la liste n'affichait que les 30 premières entreprises non envoyées : une entreprise LBA arrivée après pouvait ne jamais apparaître.
- **Décision.** Une entreprise sans email dont la page LBA a un formulaire (D129) porte le statut « à postuler sur LBA » et « pas d'email : via LBA » dans la colonne email, avec le bouton et « J'ai postulé » (D130). Elle est toujours listée, après les 30 premières (au plus 30 de plus), et un filtre « À postuler sur LBA » les isole ; l'API donne leur nombre (`a_postuler_lba`). Sans formulaire LBA, rien ne change : « ignoré » et un simple lien « Voir sur La Bonne Alternance ».
- **Au passage.** Le bandeau d'aide des spontanées renvoie au compte d'envoi dans Paramètres (oubli de D122).

## Phase 12, audit (12 novembre 2026)

### D132. Lot 1 de l'audit : liens sûrs, descente de 0014, journal de France Travail
- **Liens externes (bloquant B1).** Le lien d'une offre (`origineOffre.urlOrigine` de France Travail, `apply.url` de LBA) arrivait tel quel dans un `href` : un lien `javascript:` reçu d'une API s'exécutait au clic (vérifié dans Chrome pendant l'audit). Désormais seuls les liens http(s) sont gardés : `shared/liens.py` (`lien_http`) à la récupération (France Travail : repli sur la page de l'offre, LBA : pas de lien), à la lecture des offres déjà en base, et pour le site d'une entreprise dans le suivi ; la page vérifie encore (`lienSur` de `api.js`) et échappe le lien. Le nom d'une pièce jointe est échappé dans le profil.
- **Migration 0014 (bloquant B2).** Sa descente recréait la table `entreprises` (`batch_alter_table`) et effaçait en cascade `entreprises_modes`. Elle retire maintenant les deux colonnes directement (`DROP COLUMN`). La montée, déjà appliquée, ne change pas. `tests/test_migrations.py` monte puis descend chaque migration sur une base remplie (une ligne par table) et vérifie qu'aucune ligne ne se perd ; il échoue avec l'ancienne 0014.
- **Journal de France Travail.** Un jeton refusé ne recopie plus la réponse brute de l'API : statut HTTP et code d'erreur OAuth seulement, dans le journal du pipeline. France Travail injoignable au moment du jeton : message dans le journal au lieu d'une exception. Requête du jeton avec un délai (15 s). Les `print` des pipelines de `france_travail/scraper.py` passent par le journal ; ceux de l'aperçu en ligne de commande restent.

### D133. Lot 2 de l'audit : erreurs de l'interface et navigation
- **Lettre.** « Enregistrer » dans la fenêtre de la lettre : un échec affiche « Lettre non enregistrée : <message> » et la fenêtre reste ouverte avec le texte, au lieu de rien dire.
- **Offres.** Archiver, changer de raison ou désarchiver : un échec affiche le message et recharge la liste. Un échec du chargement des offres affiche « Offres non chargées » avec la raison, au lieu d'une liste vide qu'on pouvait prendre pour « aucune offre ».
- **Navigation.** Un clic dans le menu crée une entrée d'historique : Précédent et Suivant du navigateur, ou une ancre modifiée à la main, changent de page (`hashchange`). L'ancienne ancre `#spontanees-suivi` mène toujours à Candidatures.

### D134. Lot 3 de l'audit : origine des requêtes, déconnexion en POST, connexion, téléversement
- **Origine.** Le cookie de session est en SameSite=Lax, mais pour localhost tous les ports sont « le même site » : une autre application ouverte sur localhost pouvait poster vers le Chasseur avec la session (formulaire, téléversement multipart ; les routes JSON refusaient déjà tout corps qui n'est pas du JSON). Middleware `auth/origine.py` : une requête POST, PUT, PATCH ou DELETE dont l'en-tête Origin (à défaut Referer) désigne un autre hôte que l'en-tête Host est refusée en 403. Sans Origin ni Referer (scripts, client de test), elle passe. Derrière un proxy, le Host transmis doit rester celui du site (à vérifier à l'hébergement).
- **Déconnexion.** `/logout` n'accepte plus que POST (GET : 405) : les liens deviennent des boutons de formulaire, même apparence (barre latérale des trois modes, page de choix du mode, page du mot de passe temporaire).
- **Connexion.** Un email inconnu vérifie un hash factice : même durée qu'un mauvais mot de passe, rien ne dit si le compte existe. Au plus 5 échecs par email et adresse IP en 15 minutes ; au-delà, « Trop d'essais : réessaie dans N min » (429), même avec le bon mot de passe. Compteurs en mémoire, remis à zéro par une réussite ou un redémarrage.
- **Téléversement.** Le fichier est lu jusqu'à la limite + 1 octet, jamais en entier avant le contrôle des 5 Mo. Nom d'une pièce jointe : 100 caractères au plus (refusé au-delà s'il est saisi, raccourci s'il vient du nom du fichier).

### D135. Lot 4 de l'audit : pipelines terminés dans leur test, tests d'audit dans la suite
- **Pipelines.** Un pipeline lancé pendant un test (thread « lancer » de `main.py`) pouvait continuer après le test, une fois les API simulées et la barrière réseau retirées, et tenter un vrai accès réseau (observé pendant l'audit). Fixture `pipelines_termines` de `tests/conftest.py` : à la fin de chaque test, elle attend ces threads (20 s au plus, sinon le test échoue), avant que monkeypatch ne défasse quoi que ce soit.
- **Tests ajoutés.** `tests/test_isolation_toutes_routes.py` : B appelle chacune des routes de l'API (plus de 50) avec les identifiants de A ; aucune donnée de A ne change ni n'apparaît chez B, aucune réponse 500. `tests/test_cas_limites.py` : profil vide, offre sans titre, entreprise ni description dans les trois modes, IA en panne, corps de requête de mauvais type sur chaque route POST : toujours une erreur avec un message, jamais de 500. `tests/test_migrations.py` (D132) complète l'ensemble. Une nouvelle route est couverte d'office par les deux premiers.

### D136. Lot 5 de l'audit : code mort retiré, outils d'analyse
- **Bot Telegram.** Abandonné pour l'instant : `archive/telegram_bot.py` est supprimé (dernière version dans l'historique git, commit 3986177 et avant, à récupérer si le projet reprend). Les variables `TELEGRAM_*`, `FLASK_BASE_URL` et `GOOGLE_CLOUD_PROJECT` n'étaient lues que par lui.
- **Routes retirées**, plus appelées par la page : `/api/statut_recherche` et `/api/spontanees/statut` (même information dans `/api/statut_pipelines`), `/api/spontanees/suivi` et `/api/spontanees/suivi/statut` (remplacées par `/api/suivi` et `/api/suivi/statut` depuis D107). Les tests passent par les routes restantes.
- **Fonctions et constantes retirées** : `rediger_paragraphe` (seuls les tests l'appelaient, ils passent par `rediger_paragraphe_verifie`), `labels_modes`, `NIVEAUX_REQUIS`, `COMMANDE_GENERATION`, `TRANCHE_SANS_SALARIE` (la tranche « NN » est dans `shared/tailles.py`), l'attribut `non_explores` du collecteur LBA, un import et une variable inutilisés. `LettreIA` passe dans `tests/test_ia.py`, seul à s'en servir. `MANUELLE` remplace le littéral « manuelle » répété dans `database/entreprises_db.py`. `get_session` est gardée (dépendance FastAPI de session de base).
- **CSS** de l'ancien tableau Kanban et de la pastille de score (`kanban`, `kcol*`, `kcard*`, `kempty`, `score-pill`, `sc-*`, `pj-item__file`) retiré.
- **Outils** : `ruff` et `vulture` dans `requirements-dev.txt` (développement seulement). `vulture` ne signale plus que `get_session` et des faux positifs (colonnes SQLAlchemy, champs Pydantic).

### D137. Lot 6 de l'audit : documentation remise à jour
- **README.** Installation de zéro sur Fedora (dnf : Python 3.13, Pango, Cairo), tableau des variables d'environnement, Ollama avec son service systemd, lancement par le venv, tests et analyse du code (`ruff`, `vulture`), tableau des scripts lancés à la main. Fonctionnalités à jour : tableau Candidatures unique, « J'ai postulé » qui sort l'offre de la page Offres, candidature sur La Bonne Alternance, copie de profil, Paramètres, mot de passe temporaire, balise `{portfolio}`, contrôle de l'origine, migrations testées. Retirés : filtre « Postulées », archive Telegram, améliorations faites ou abandonnées (Paramètres, mot de passe oublié, bot Telegram, API de candidature LBA).
- **`.env.example`.** Compte d'envoi dans Paramètres ; `DATABASE_URL` à renseigner (le défaut est l'ancienne base) ; `FUSEAU_AFFICHAGE` ajoutée : toutes les variables lues par le projet y sont.
- **`docs/RECETTE.md`.** Compte d'envoi dans Paramètres, section 03 ; plus de page « Spontanées envoyées », le tableau Candidatures la remplace.
- **`docs/SPEC_SOURCES.md`, section 3.** La proposition d'API de candidature LBA renvoie à D126 (écartée) et aux pages du site (D127 à D131).

### D138. Lot L : lettre et PDF, entreprise inconnue, nom du fichier, mise en page Word (remplace D108)
- **Entreprise inconnue** (nom absent, « Inconnue », « non renseigné »...). `{contact_entreprise}` devient « À l'attention du service recrutement » et `{entreprise}` « votre entreprise », dans la lettre comme dans son PDF : plus de balise laissée à compléter ni de surlignage jaune. La fenêtre de la lettre affiche une simple information, en gris : « Contact de l'entreprise inconnu : la lettre est adressée au service recrutement. Tu peux modifier cette ligne. », et, si la lettre type emploie `{entreprise}`, « Nom de l'entreprise inconnu : la lettre parle de « votre entreprise ». Tu peux modifier ce passage. » (aussi à la réouverture d'une lettre enregistrée). Textes et règle dans `shared/offres.py`, communs à la page et au PDF. Le portfolio vide reste « à compléter » (D125).
- **Même texte dans la page et dans le PDF.** Le PDF reprend la lettre telle qu'elle est affichée, paragraphe par paragraphe, sans en retirer l'en-tête : le bloc destinataire, la ligne de date et la ligne « Objet » de la lettre sont mis en page à leur place. Seulement si la lettre type n'en a pas (elle commence à « Madame, Monsieur »), le PDF les ajoute, avec les mêmes règles : destinataire de `contact_entreprise`, date du jour (« <Ville>, le ... »), objet « Candidature : <intitulé> ». Aucun tiret cadratin produit.
- **Mise en page** (celle d'une lettre Word) : coordonnées en haut à gauche (prénom et nom en gras, ville, téléphone, email, LinkedIn, GitHub, portfolio), destinataire en dessous à droite, date puis objet en gras, corps aligné à gauche et non justifié, aucun trait, marges de 2,5 cm, 11 pt. Police : Inter (paquet Fedora `rsms-inter-fonts`), libre et proche d'Aptos, prise sur le système et embarquée dans le PDF ; à défaut Carlito, puis Liberation Sans. Le PDF ne charge toujours aucune ressource.
- **Nom du fichier** : `Lettre_de_motivation_<Prénom>_<Nom>.pdf`, suivi de `_<Entreprise>` seulement si son nom est connu ; accents gardés, tout autre caractère que lettres, chiffres et tirets remplacé par « _ ».

## Phase 12, série 2 (12 novembre 2026)

### D139. Lot 7 de l'audit : dossiers configurables, base par défaut, get_session retirée
- **Dossiers.** `DATA_DIR` (défaut `data/`), `UPLOADS_DIR` (défaut `DATA_DIR/uploads`) et `LETTRES_PDF_DIR` (défaut `lettres_pdf/`) se règlent dans le `.env` ; chemin relatif : depuis la racine du projet. Utile pour l'hébergement, et pour des essais sur des données temporaires sans toucher à `data/`. Les chemins enregistrés en base restent relatifs à ces dossiers.
- **Base par défaut.** Sans `DATABASE_URL`, la base est `DATA_DIR/chasseur_v2.db`, celle que conseillent le README et `.env.example`, et non plus `data/chasseur.db`, l'ancienne base mono-utilisateur. Une installation qui renseigne `DATABASE_URL` (le cas normal) ne voit aucun changement. Le garde-fou des tests refuse désormais toute base du dossier `data/` du projet.
- **`get_session`** (`database/connexion.py`) retirée : jamais appelée, l'application ouvre ses sessions par `SessionLocal`.

### D140. Lot 8 de l'audit : pwdlib à la place de fastapi-users
- **Constat.** `fastapi-users` ne servait qu'à `PasswordHelper`, une enveloppe de `pwdlib` (`PasswordHash((Argon2Hasher(), BcryptHasher()))`), et tirait d'autres dépendances (PyJWT, email-validator, makefun).
- **Décision.** `auth/securite.py` construit le même `PasswordHash` avec `pwdlib` directement : nouveaux hashs en argon2id (mêmes paramètres, m=65536, t=3, p=4), hashs argon2 et bcrypt acceptés en vérification. `fastapi-users` quitte `requirements.txt` ; `pwdlib`, `argon2-cffi` et `bcrypt` restent épinglés.
- **Preuve.** `tests/test_hachage.py` : un hash argon2id créé par `PasswordHelper().hash` de fastapi-users 15.0.5 et un hash bcrypt, gardés en constantes, sont acceptés (et refusés avec un autre mot de passe) ; un compte qui porte le hash fastapi-users se connecte par `/login` ; là où fastapi-users est encore installé, compatibilité croisée dans les deux sens. L'application démarre et hache avec l'import de `fastapi_users` bloqué.
- **Comptes existants.** Rien n'est réécrit en base. Après mise à jour, chaque compte doit encore se connecter avec son mot de passe actuel ; l'empreinte de session (D122) ne change pas, les sessions ouvertes restent valides. `pip uninstall fastapi-users` est facultatif (rien ne l'importe plus).

### D141. Retouches du lot L : objet, en-tête, police (complète D138)
- **Objet.** Même taille que le corps (11 pt, fixée explicitement), en gras seulement. Mesure sur le PDF : l'objet et le corps avaient déjà la même hauteur de ligne ; c'est le gras très épais d'Inter qui le faisait paraître plus grand. Un test compare désormais la hauteur de l'objet et celle du corps dans le PDF généré.
- **En-tête.** Nom, ville, téléphone et email seulement : LinkedIn, GitHub et portfolio quittent l'en-tête du PDF. La lettre affichée dans la page n'en a jamais ajouté (elle ne contient que le texte de la lettre type). `{portfolio}` reste une balise de la lettre type, à écrire soi-même dans le texte.
- **Police.** Carlito (paquet Fedora `google-carlito-fonts`, mêmes métriques que Calibri), repli Liberation Sans, à la place d'Inter. Marges inchangées (2,5 cm). README à jour.

## Phase 13, réorganisation (12 novembre 2026)

### D142. Arborescence lisible, sans changement de comportement
- **Routes.** `main.py` ne garde que la création de l'application, les middlewares, la gestion des erreurs, le journal d'accès et l'inclusion des routeurs. Les routes vivent dans `routes/` par domaine (pages, profil, parametres, offres, analyse, lettre, candidatures, spontanees, documentation), avec `routes/commun.py` (gabarits, états des pipelines, mode de la requête, limites, routeur privé). Mêmes chemins, mêmes noms de fonction, même schéma OpenAPI : comparés à l'enregistrement fait avant tout changement, diff vide à chaque étape.
- **Paquets.** `france_travail/` (qui contenait aussi LBA, l'analyse, la lettre et le PDF) devient `offres/` (`france_travail.py`, `la_bonne_alternance.py`, `parametres_france_travail.py`, `parametres_lba.py`, `recherche.py`, `analyse.py`, `analyse_differee.py`, `pages_lba.py` venu de `shared/lba.py`) et `lettres/` (`redaction.py`, `pdf.py`). Dans `spontanees/`, `recuperation.py`, `recherche_emails.py`, `envoi.py`. `shared/` garde son nom. Commandes en ligne : `python -m spontanees.recuperation`, `spontanees.recherche_emails`, `spontanees.envoi`.
- **Fonctions longues.** Découpées sans risque : `api_recherche` et `ajouter_entreprises_lba`. Laissées, avec la raison dans le commit de l'étape 3 : la boucle d'envoi, le scraper d'emails, la boucle Sirene avec repli NAF, le script de vérification de l'IA.
- **Qualité.** `ruff` configuré dans `pyproject.toml`, sans erreur ; `print` remplacés par le journal (`shared/journal.py`) hors `scripts/`. Aucune migration, même base.

## Phase 14, refonte de l'interface (12 novembre 2026)

Référence : `docs/maquettes/DESIGN.md` et les maquettes `*.dc.html` (reproduites dans les gabarits et le CSS, pas copiées). Huit lots, un commit et une décision chacun.

### D143. Lot 1 : jetons et en-tête
- **Jetons.** Instrument Sans (400 à 700) remplace Space Grotesk, Inter et JetBrains Mono. Couleurs, rayons et ombres de DESIGN.md dans `base.css` (`--fond`, `--texte`, `--accent`, `--attention`, `--refus`...). Plus de couleur par mode (bleu, orange, vert) : un seul accent vert, le mode se voit au point du sélecteur. Les anciens noms de variables (`--signal`, `--encre`, `--txt-faint`...) pointent vers les nouveaux jetons, pour que les pages pas encore refaites restent lisibles ; chaque lot les fait disparaître de sa page. `--txt-faint` (#9AA3AD, 2,6:1) prend la valeur du texte secondaire : tout texte est au moins à 4,5:1.
- **En-tête.** La barre latérale sombre, son repli et ses statistiques disparaissent. En-tête blanc : logo, sélecteur Alternance / Job / Stage en pilule (`aria-current`), menu principal en vrais liens (`#offres`...) avec `aria-current="page"`, rond aux initiales (prénom et nom du profil du mode, sinon l'email) qui ouvre Mon compte : Paramètres et Se déconnecter (toujours en POST, D134). Le menu s'ouvre et se ferme au clavier (Entrée, Échap qui rend le focus, sortie du focus), et un lien d'évitement mène au contenu.
- **Compteurs.** Seulement sur ce qui attend, masqués à zéro : Candidatures compte celles à relancer ; Offres compte les offres à traiter jusqu'au lot 3, où il comptera les offres pas encore vues. Entreprises à contacter : compteur masqué jusqu'au lot 6.
- **Tête de page.** Titre, phrase courte et action principale verte remplacent la barre du haut et les encarts « guide » (dont la croix n'était pas un bouton). Le badge de la barre du haut disparaît. La recherche dans la page ne s'affiche que là où il y a une liste. Le titre de l'onglet suit la page.
- **Statistiques de la barre latérale.** Emails trouvés, envoyés et taux d'envoi passent sur la page Entreprises à contacter, en attendant sa refonte (lot 6).
- **Téléphone.** Provisoire jusqu'au lot 8 : en-tête sur une ligne (logo seul, nom lu par les lecteurs d'écran), menu défilant en dessous, liens de 44 px de haut.

### D144. Lot 2 : Accueil et complétude du profil
- **Page d'arrivée.** Chaque mode s'ouvre sur l'Accueil (`#accueil`, aussi pour une ancre inconnue) : salutation selon l'heure de Paris (Bonjour de 5 h à 18 h, Bonsoir sinon) et prénom du profil, rappel de la recherche (dates du stage, début de l'alternance, durée du job), « À faire », « Ta recherche en bref » et l'avancement du profil. L'ancienne page de choix du mode (`/`) garde son rôle sous le nom `choix_mode.html`.
- **Une requête.** `GET /api/accueil` agrège : la meilleure offre à voir notée 6 ou plus (« N offres te correspondent bien » s'il y en a plusieurs), les candidatures à relancer (une : son entreprise et sa date ; plusieurs : leur nombre), les offres à noter avec le temps estimé (rien sans IA), puis offres à regarder (ni gardées, ni écartées, ni postulées), candidatures envoyées et réponses reçues (réponse, entretien, refus, acceptée). La première tâche porte l'action verte ; « Les noter » lance la même notation que la page Offres.
- **Complétude.** `shared/completude_profil.py`, cinq parties et une ligne par partie incomplète. Toi : prénom, nom, email, téléphone, ville. Stage : dates de début et de fin, école, formation, missions visées ; alternance : formation visée (niveau visé), rythme, date de début ; job : disponibilités et durée. Parcours : 3 compétences au moins, et un projet ou une expérience. Ce que tu cherches : un domaine ou « indifférent », un département ; la taille des entreprises à contacter est un conseil, jamais un manque. Documents : un CV (au moins une pièce jointe : rien ne distingue un CV des autres pièces) et une lettre type avec `{paragraphe}`.
- **Deux clés du JSON `recherche`, sans migration.** `rythme` (texte, nouveau champ de la carte alternance) et `domaines_indifferent`, vrai seulement quand la personne coche « Indifférent » elle-même : jusque-là, des domaines vides voulaient dire aussi bien un choix qu'un oubli. Ni l'une ni l'autre ne change la recherche. Le champ « Disponibilité » de l'alternance s'appelle « Date de début ».

### D145. Lot 3 : Offres avec volet, Gardées et Écartées, réglages avancés, migration 0016
- **Liste et volet.** Liste à gauche (note dans un carré coloré, titre, lieu, « il y a N jours »), détail à droite : note sur 10 avec un mot (Bien de 6 à 10, Moyen à 4 et 5, Faible en dessous, « Pas notée » sinon), conditions remplies ou motif d'inéligibilité, Ce qui colle, Ce qui coince, l'offre en bref, lien vers l'annonce et vers La Bonne Alternance. Actions : Préparer ma lettre (verte), J'ai postulé (date modifiable), Garder pour plus tard, Pas pour moi ; « Faire noter à nouveau » reste en lien discret. Après une action, l'offre suivante de l'onglet s'ouvre et une phrase confirme. Les mieux notées en haut, les offres pas encore notées à la fin. Sur téléphone (900 px et moins), la liste puis le détail en plein écran avec « Retour à la liste ».
- **Vue.** Nouvelle colonne `candidatures.vue` : une offre jamais ouverte est en gras avec un point vert (et « pas encore vue » pour les lecteurs d'écran) ; elle devient vue à l'ouverture (`POST /api/offre/vue`). Le compteur Offres du menu compte les offres à voir pas encore vues. La migration met les offres existantes à vu, sinon tout l'historique paraîtrait nouveau. Sans rapport avec la table `offres_vues` (dédoublonnage des recherches).
- **Gardées et Écartées.** Gardée : nouveau statut `gardee`, posé et retiré par `/api/maj_statut` ; plutôt qu'une colonne, parce qu'À voir, Gardée, Écartée et Postulée s'excluent. L'analyse n'écarte jamais une offre gardée (elle n'archive que les offres « nouveau »). Écartée : l'archivage existant, raison « manuel » pour « Pas pour moi » ; l'onglet Écartées montre aussi les archivages automatiques, filtrables « par toi » ou « par le Chasseur » avec la raison en clair. Remettre dans À voir : `en_cours` si une lettre est prête, sinon `nouveau`. Les onglets sont des boutons à `aria-pressed`. Les compteurs du haut de l'ancienne page (nouvelles, note moyenne, à postuler, lettres) disparaissent : l'Accueil donne ce qui compte.
- **Réglages avancés.** Nouvelle colonne JSON `profils.reglages`, propre à chaque mode, réglée dans Paramètres (`GET` et `POST /api/reglages`, chaque valeur bornée par le serveur, enregistrée dès qu'elle change). Lot 3 : offres ajoutées au plus par recherche, offres notées au plus à chaque fois, « noter toute la file d'un coup », noter après chaque recherche (la colonne `analyse_auto` existante, qui quitte la page profil), et le modèle d'IA affiché. Un lancement sans valeur demandée prend le réglage du mode, sinon le défaut de `config.LIMITES_LANCEMENT` ; les plafonds des entreprises à contacter s'y ajoutent au lot 6. La page Offres ne garde qu'un bandeau « N nouvelles offres pas encore notées » avec « Les noter ».
- **Migration 0016.** Une seule pour la refonte : `candidatures.vue` (booléen, faux par défaut, vrai pour les lignes existantes) et `profils.reglages` (JSON, `{}` par défaut). Testée en montée et en descente sans perte de lignes, et sur la base de démonstration.

### D146. Lot 4 : Candidatures en colonnes
- **Tableau.** Quatre colonnes : Envoyée (envoyée, à relancer), Relancée, Entretien, Réponse (réponse en attente, acceptée, refusée, adresse invalide). Chaque carte : type (Offre ou Entreprise), étiquette « À relancer » ou l'issue, poste, entreprise, date d'envoi ; un bouton vert pour l'étape suivante (J'ai relancé, J'ai un entretien, J'ai eu la réponse), Acceptée ou Refusée dans Réponse, « Revenir à l'étape d'avant ». De vrais boutons, aucun glisser-déposer ; le focus revient sur la carte déplacée et une phrase annonce le changement. Une colonne vide dit ce qui y arrivera. Quatre colonnes sur grand écran, deux en dessous de 1100 px, une sur téléphone.
- **Rien ne disparaît.** Dans « Plus » de chaque carte : changer d'étape vers n'importe laquelle (l'ancien menu de statut), date de candidature d'une offre, contact, lien, lettre, « Je n'ai pas postulé » (ancien « Annuler », l'offre revient dans Offres). Filtre « Afficher » : offres et entreprises, offres seulement, entreprises seulement. Les filtres par statut disparaissent, les colonnes les remplacent. Le bouton « Actualiser » aussi : la page se recharge à chaque ouverture.
- **Deux statuts, sans migration.** `relancee` et `acceptee` rejoignent les statuts de suivi des offres et des spontanées (`STATUTS_SUIVI`, routes, statistiques : une acceptée compte comme réponse). « À relancer » reste calculé : une candidature encore envoyée 7 jours après. Un changement de date de candidature garde l'étape atteinte. « Bounce » s'affiche « Adresse invalide ».

### D147. Lot 5 : Mon profil en cinq parties
- **Parties.** Toi, la partie du mode (Ton stage, Ton alternance, Ton job), Ton parcours, Ce que tu cherches, Tes documents. Une seule affichée à la fois, choisie dans la liste de gauche (`aria-current="step"`, le focus va au titre de la partie) ou par « Partie suivante : … » ; toutes restent dans la page, et « Enregistrer » (vert, collant en bas du panneau sur grand écran) enregistre tout le profil, comme avant. Chaque partie porte son état (Complet, À compléter), la ligne de ce qui manque et, pour Ce que tu cherches, le conseil sur la taille des entreprises : servis par `GET /api/profil/completude` (règles de D144), rafraîchis après chaque enregistrement.
- **Rangement des champs.** Toi : coordonnées, portfolio, LinkedIn, GitHub. Stage : dates, durée, école, formation, niveau actuel, missions visées. Alternance : formation visée, rythme, date de début, ce que la formation apporte. Job : durée, dates, horaires, mobilité. Parcours : compétences en étiquettes, projets, et selon le mode formation, niveau, expérience, langues ou atouts. Ce que tu cherches : domaines, tailles, départements, secteurs, ce que tu préfères éviter, types de jobs, lieu préféré. Documents : CV et pièces jointes, lettre type, objet et message du mail aux entreprises. Les balises de la lettre et du mail sont dans des encarts dépliables. Aucun champ ne disparaît : un test vérifie, mode par mode, que chaque champ éditable avant la refonte est dans un bloc de son mode.
- **Accessibilité.** Le retrait d'une compétence et d'un projet sont de vrais boutons, nommés (« Retirer Python ») ; le texte des étiquettes est échappé ; le focus revient au champ de saisie après un retrait. La fenêtre de copie depuis un autre mode est un `dialog` nommé. Libellés à 14 px, aides à 13 px, champs de 44 px de haut, partout dans l'application.

### D148. Lot 6 : Entreprises à contacter
- **Trois étapes.** Trouver des entreprises (« En trouver d'autres » une fois la base remplie), Trouver leurs emails, Envoyer ta candidature (bouton vert, grisé s'il n'y a personne à qui écrire). Chaque étape dit où on en est en une phrase (trouvées, dont La Bonne Alternance ; emails trouvés, joignables par La Bonne Alternance, à chercher ; prêtes à recevoir ta candidature), avec sa progression et « Arrêter » pendant qu'elle tourne. Plus de bouton dans la tête de page : chaque étape a le sien.
- **Entreprises.** Onglets Prêtes à envoyer, Via La Bonne Alternance (Postuler sur La Bonne Alternance, J'ai postulé avec sa date), Sans contact, Déjà contactées (lues dans le suivi, avec leur étape et un lien vers Candidatures), plus un menu Source (Sirene, La Bonne Alternance) qui remplace les anciens filtres par source. Comme avant, les entreprises listées sont les 30 prochaines à traiter et celles à postuler sur La Bonne Alternance. Les adresses à vérifier restent dans un encadré, validables une à une ou par l'IA (« Faire revoir par l'IA »). Le compteur du menu donne les entreprises prêtes à envoyer.
- **Mode essai.** Bandeau « Mode essai : les mails arrivent dans ta propre boîte » avec « Passer en envoi réel », qui coupe le mode test du compte d'envoi par la route existante, après confirmation.
- **Réglages avancés.** Les plafonds (nouvelles entreprises, entreprises dont chercher les emails, mails envoyés, entreprises revues par l'IA) quittent la page pour Paramètres, avec le maximum disponible affiché ; un lancement sans valeur demandée prend le réglage du mode (D145).
- **Chiffres et vocabulaire.** Taux d'envoi et tableau par source dans « Tes chiffres » (dépliable, vrai tableau). Scraper → Trouver leurs emails, Récupérer → Trouver des entreprises (y compris dans les messages du serveur), validée avant la phase 7 → adresse validée, non validée → à vérifier, Mode test → Mode essai dans cette page.

### D149. Lot 7 : page Ma lettre
- **Page dédiée.** La fenêtre de la lettre (D106) devient une page (`#lettre`), ouverte par « Préparer ma lettre » ou « Voir ma lettre » depuis Offres et Candidatures. Barre du haut : retour à la page d'origine, poste visé, Enregistrer, Télécharger le PDF (vert). À gauche, le paragraphe pour cette offre, modifiable, « Proposer une autre version » (rédaction par l'IA, avec son temps écoulé), les informations d'entreprise inconnue (D138) et de portfolio à compléter (D125), « Modifier toute la lettre » (la lettre entière, pour cette offre seulement : c'est alors elle qui est enregistrée et mise en PDF, avec un retour possible à la lettre type) et « Modifier ma lettre type » (partie Tes documents du profil).
- **Aperçu fidèle au PDF.** `POST /api/lettre/apercu` renvoie, sans rien enregistrer, le HTML même du PDF (`construire_html`) avec une page A4 dessinée et le paragraphe surligné, seul dans son bloc ou à l'intérieur ; avant la première rédaction, sa place est montrée. Il s'affiche dans un cadre isolé (`sandbox` sans scripts), mis à l'échelle de la colonne, et se met à jour pendant la frappe. Le PDF n'en est pas changé : un test vérifie qu'il ne prend ni la police livrée ni le surlignage.
- **Police.** Carlito (licence OFL 1.1), les quatre styles, est livrée telle quelle dans `static/fonts/carlito/` avec sa licence (`OFL.txt`), et déclarée en `@font-face` dans l'aperçu seulement (URL versionnées) : l'aperçu est le même sur tout appareil. Fichiers non convertis (pas de WOFF2), pour ne pas créer de version modifiée d'une police à nom réservé ; le navigateur ne les charge que sur cette page. Le PDF garde la police installée par dnf.
- **Enregistrer** insère le paragraphe dans la lettre type (route existante, l'offre passe « en cours ») ou enregistre la lettre entière modifiée ; « Télécharger le PDF » enregistre d'abord. Un échec laisse la page telle quelle avec le message (D133).

### D150. Lot 8 : connexion, inscription et version téléphone
- **Pages hors session.** Connexion, inscription, mot de passe oublié, mot de passe temporaire et choix du mode partagent un gabarit (`auth_base.html`) et une feuille versionnée (`static/css/auth.css`) à la place de leurs styles en ligne : panneau vert à gauche (logo, phrase d'accroche), formulaire à droite, « Oublié ? » à côté du mot de passe, création de compte avec code d'invitation. Champs, noms et routes inchangés ; chaque champ a son libellé. Les deux verts pâles de la maquette sur le panneau (4,4:1 et 4,0:1) sont remplacés par un blanc à peine teinté (5,0:1). Sur téléphone, le panneau se réduit à la marque et la phrase.
- **Téléphone (720 px et moins).** En-tête court : logo, « Chasseur », mode ouvert en pilule qui déplie les trois modes. Barre d'onglets fixe en bas : Accueil, Offres, Candidatures (avec leurs compteurs), Plus, qui ouvre Entreprises à contacter, Mon profil, Paramètres et Se déconnecter (fermeture par Échap, clic ailleurs ou choix, focus rendu au bouton). Cibles d'au moins 44 px. Les tâches de l'Accueil deviennent des lignes entièrement cliquables avec un chevron ; le détail d'une offre prend tout l'écran, sans la tête de page.
- **Compteurs** mis à jour en un seul endroit (`majCompteur`, `api.js`) pour le menu et la barre d'onglets.
- **Nettoyage.** Les anciens noms de variables (D143) sont remplacés par les jetons partout et retirés ; les règles CSS des écrans remplacés (carte d'offre, tableau de suivi en lignes, viseur, compteurs du haut, fenêtre de la lettre, cartes de l'ancien pipeline) sont supprimées. Un test vérifie qu'aucun ancien nom ne revient.
- **README** à jour (Accueil, Offres, Ma lettre, Candidatures en colonnes, profil en cinq parties, réglages avancés, 16 migrations).

### D151. Destinataire de la lettre calé sur la marge droite (complète D141)
- Le bloc destinataire (« À l'attention du service recrutement », ou nom puis adresse de l'entreprise) n'est plus décalé par une marge gauche de 55 % : il occupe la largeur du corps et son texte est aligné à droite, chaque ligne finissant au bord droit du corps de la lettre. Ni largeur fixe ni marge en pourcentage. Même HTML pour l'aperçu et le PDF (`lettres/pdf.py`) ; la date reste à gauche.
- Vérifié pour une entreprise connue (trois lignes) et une inconnue : dans la mise en page WeasyPrint du PDF (test qui mesure chaque ligne, écart nul au bord droit) et dans l'aperçu du navigateur (écart nul).

### D152. Stage France Travail : « stage » et « stagiaire », sans filtre de domaine (phase 15)
- **Requêtes.** Une requête par mot-clé, `motsCles=stage` puis `motsCles=stagiaire` (`VALEURS_PAR_REQUETE["motsCles"] = 1`), réunies et dédoublonnées par identifiant comme toute collecte ; puis les filtres d'avant, inchangés : Île-de-France, alternance (E2, FS) écartée, `designe_un_stage` sur l'intitulé. L'audit de l'étape 1 avait montré que « stage » seul ratait les offres dont l'intitulé dit « stagiaire ».
- **Domaines.** Le mode stage n'envoie plus les domaines du profil à France Travail (`ft_sans_domaine`) : la liste est courte (73 offres en IDF le 9 octobre 2026 avec « stage » seul, avant tout domaine) et 15 % des offres n'ont aucun domaine. Les domaines restent dans le prompt : l'IA met « Hors domaine » et une note basse, sans jamais archiver (D99, D102). Les secteurs d'activité, choisis explicitement, restent un filtre.
- **Mesure.** `scripts/audit_france_travail.py --mode stage --user N`, section `avant_apres_D152` : offres gardées avec l'ancienne recherche (« stage » et domaines du profil) et la nouvelle, ajoutées et perdues, exemples.

### D153. Offres France Travail de la région sans département gardées (phase 15)
- **Constat** (audit du 22 novembre 2026, mode job) : 680 offres sur 19719 (3,4 %) ont pour lieu « Île-de-France » (649), « Ile-de-France » (23) ou « Île-de-France - … » (« Télétravail à 100% », « Région Parisienne »...), sans code commune. `detecter_zone` attendait « NN - » et les rejetait comme hors IDF alors que la recherche porte sur `region=11`.
- **Règle.** Un lieu dont la partie avant « - » est « Île-de-France », accents et casse ignorés, est gardé avec la zone `ZONE_IDF_NON_PRECISE` = « Île-de-France (non précisé) » ; le libellé d'origine reste le lieu affiché. Le menu Lieu de la page Offres propose cette zone ; « Toute l'Île-de-France » la montre. Même règle pour l'adresse d'une offre LBA sans code postal.
- **Mesure.** Les 680 libellés rejetés de l'audit sont tous gardés (contrôle hors ligne sur `audit_france_travail_job.json`) ; aucun en alternance (56 offres) ni en stage. Relancer `scripts/audit_france_travail.py` : `hors_idf` doit tomber à 0.

### D157. Signature du README hors du contrôle des noms réels (phase 15)
- `test_code_actif_sans_mention_d_un_utilisateur_reel` échouait depuis le README réécrit (019e0c4) : la section « Autrice » et l'adresse du dépôt à cloner (`github.com/kenzafb/projet_7_chasseur_alternance`) nomment l'autrice, volontairement. Le test retire du README cette section (jusqu'au titre suivant) et cette adresse exacte, puis cherche les noms comme avant dans tout le reste ; un test vérifie que rien d'autre n'est retiré. Le code actif reste contrôlé sans exception.

### D154. La Bonne Alternance : niveau adjacent gardé et marqué ; migration 0017 (phase 15)
- **Règle.** `filtrer_niveau` garde le niveau visé, les offres sans niveau (D38) et désormais les niveaux adjacents (visé ± 1, `ECART_NIVEAU_GARDE`), marqués `niveau_different` : une offre « BTS à Master » n'est codée qu'à un seul niveau. Plus d'un niveau d'écart : écartée comme avant. L'IA note ensuite l'offre normalement.
- **Marques.** Nouvelle colonne `candidatures.marques` (JSON, `[]` par défaut, migration 0017, lignes existantes intactes, testée en montée et en descente), clés de `shared/marques.py`. La page Offres les affiche sous le titre (« Niveau différent du tien ») et propose un filtre « Particularités ».
- **Mesure** (export du 22 novembre 2026, profil alternance Bac+2, 37 offres d'IDF de ses codes métiers hors France Travail) : 13 offres gardées avant, 23 après (+10, toutes de niveau 6). Exemples : Alternant Développeur et Maintenance Informatique (FM France), Apprenti Data Ingénieur (SPIE), Assistant·e Product Owner CRM (Etam), Apprenti Analyste Gouvernance Cybersécurité (SCOR)...

### D155. La Bonne Alternance : offre déléguée à un organisme de formation gardée et marquée (phase 15)
- `is_delegated` (OpenAPI : « offer management is delegated to a partner school » ; nom, SIRET et adresse sont alors ceux de l'organisme) devient la marque `organisme_formation`, affichée « Offre déposée par un organisme de formation » et filtrable (« Sans les offres d'organismes de formation », « Déposées par un organisme de formation »). Une offre marquée n'est jamais écartée « École ou CFA », même si elle nomme un organisme vérifié.
- **Mesure** (export, IDF) : 456 offres déléguées sur 2407, dont 337 (73,9 %) étaient archivées par les mots-clés ; aucune maintenant.

### D156. École ou CFA : seuls les organismes vérifiés écartent, les mots génériques sont des indices (phase 15)
- **Liste.** `shared/referentiels/organismes_formation.txt` : « + nom » pour un organisme vérifié (ISCOD, Scholia, Studi, Aureis...), « ? mot » pour un indice (cfa, école, organisme de formation, centre de formation, la plateforme, business school). Comparaison sans accents ni casse, sur des mots entiers : « studi » ne trouve plus « studio », « nexa » plus « Nexans », « igs » plus « designs » ; « h3 », qui trouvait « 9h30 », est retiré ; « Groupe IGF », jamais trouvé (majuscules), l'est enfin.
- **Indices.** Cherchés dans le titre et le nom de l'entreprise seulement (dans la description, « école » et « CFA » sont dans presque toutes les offres d'alternance), affichés « Indice d'école ou de CFA : « cfa » », sans effet sur l'archivage.
- **Mesure.** Export LBA, offres d'IDF non déléguées : 1211 sur 1951 (62,1 %) archivées avant, 1 (0,1 %) après. Audit France Travail du 22 novembre, mode alternance : 12 offres sur 56 avant ; ISCOD et Scholia (10) le restent. En base, les 2 offres écartées « École ou CFA » le restent. Cas à trancher : les offres de CAPIVISION titrées « IGF ... - ALT », qui recrutent pour l'école IGF, ne sont plus écartées (tranché : voir ci-dessous).

- **Intermédiaires d'écoles** (complément) : « = nom » dans le fichier, CAPIVISION pour commencer. Une offre qui les nomme n'est ni archivée ni mêlée aux offres normales : elle reçoit la marque `organisme_formation` (« Offre déposée par un organisme de formation »), comme une offre LBA déléguée, et se filtre de même.

### D158. Entreprises à fort potentiel : l'export complet évalué, pas encore branché (phase 15)
- `scripts/audit_lba_export.py` lit l'export déjà téléchargé en flux (824 Mo, 420627 objets, 57 s, moins de 2 Go). Pour le profil alternance (codes M18, départements 75, 92, 93, 94) : 11201 entreprises « recruteurs_lba » en IDF pour ses codes, 3888 après les filtres de taille et de départements du profil, contre 8 entreprises LBA en base. Ni site ni email dans l'export, comme dans la recherche.
- La recherche de l'application avait reçu 8980 entreprises en 300 requêtes (382 s) et s'était arrêtée sur `LBA_REQUETES_MAX`, cercles au plafond de 150. La comparaison SIRET par SIRET avec la recherche se lance avec `--recherche` (clé et réseau). L'export n'est pas branché tant que ce gain n'est pas validé : téléchargement de 824 Mo une fois par jour, deux appels par minute, URL valable deux minutes.

### D159. Sirene : établissements actifs d'Île-de-France, une entrée par entreprise (phase 15)
- **Constat** (audit du 22 novembre 2026) : la recherche ne lisait que les sièges (`etablissementSiege:true`). Sur 3000 entreprises ayant un établissement actif non siège en IDF, 2999 avaient leur siège hors d'IDF : jamais trouvées. 161521 établissements actifs non sièges en IDF, toutes activités.
- **Requête.** `periode(etatAdministratifEtablissement:A)` à la place du siège, avec comme avant `etatAdministratifUniteLegale:A`, le NAF, la tranche d'effectif et la catégorie de l'unité légale, et le code postal de l'établissement. `periode()` trouve aussi un établissement actif autrefois et fermé aujourd'hui : la période courante est contrôlée à la réception, et un établissement fermé est écarté et compté.
- **Une entrée par entreprise.** Dans un lancement, un seul établissement par SIREN, avec son adresse francilienne : le premier reçu, remplacé par le siège s'il arrive ensuite et qu'il est en IDF. Les SIREN déjà en base restent dédoublonnés comme avant (D59). `extra` garde `siege` et `categorie_juridique`.
- **Administrations.** La catégorie juridique de l'unité légale est enregistrée ; les 7xxx (personnes morales de droit public) sont comptées dans les logs (« dont N administrations publiques »), pas exclues.
- **Mesure** : `scripts/audit_sirene.py`, section `avant_apres_D159` (clé INSEE) : entreprises distinctes avant et après, gagnées, part des 7xxx, exemples.

### D160. Scraper : site de l'entreprise identifié puis vérifié, sinon aucun email (phase 15)
- **Sources, dans l'ordre** (`spontanees/site_officiel.py`) : site déjà vérifié lors d'un passage précédent ; site fourni par La Bonne Alternance (`workplace.website`, désormais gardé dans `extra.lba.site_web`) ; site donné par une offre France Travail (`entreprise.url`) ou LBA de l'utilisateur au même nom (ligne « Site de l'entreprise : » ajoutée à la description de l'offre, sans migration, lue par `sites_des_offres`) ; puis la recherche web, au plus 4 domaines. Le site déjà en base, trouvé par l'ancienne recherche, n'est plus repris tel quel.
- **Vérification.** Un candidat n'est retenu que si l'accueil ou les mentions légales (lien réel de l'accueil ou du sitemap) portent le SIREN, seul, dans un SIRET ou dans le numéro de TVA ; à défaut, le nom de l'entreprise (nom commercial ou raison sociale, sans forme juridique ni parenthèses, avec un mot distinctif d'au moins 4 lettres) dans le titre du site ou dans les mentions légales. Un sous-domaine est aussi essayé sur son domaine parent (support.lexmark.com, puis lexmark.com). Sinon « site non vérifié » : aucun email gardé, entreprise traitée, état affiché dans Entreprises à contacter.
- **Domaines interdits.** `shared/referentiels/domaines_interdits.txt` remplace `DOMAINES_ANNUAIRES` : annuaires et registres (companyfrance, societe.com, pappers, pagesjaunes...), annonces légales, fiches d'un autre organisme (gnius.esante.gouv.fr), réseaux sociaux, emploi, moteurs de recherche, blogs. Jamais candidats.
- **Enregistré** dans `extra` : `site_verifie` (url, domaine, source, preuve, date ; `{"verifie": false}` sinon) et `essais_site` (candidats essayés, raison du refus).
- **Recherche web filtrée** : un résultat n'est vérifié que si son domaine ressemble au nom ou si son titre ou son extrait cite le nom ou le SIREN ; un moteur dégradé renvoyait des sites sans rapport (jeux, paroles, films) qui épuisaient les candidats.
- **Mesure** : `scripts/audit_scraper.py mesure` compare à `audit_exports/scraper_reference.json` (juste, faux, manqué) ; chiffres dans le rapport de l'étape 2.
- **Échecs de la recherche web jamais silencieux** (complément) : toute erreur du moteur est journalisée, suivie de la même pause qu'un refus pour excès de requêtes et d'un nouvel essai, puis comptée (« N en échec » en fin de lancement, `recherche_web_en_echec` dans la mesure). À la mesure du 22 novembre, une panne silencieuse avait laissé 13 entreprises de suite sans aucun candidat.
- La nouvelle tentative de site « non fiable » (FIX 11) disparaît : `fiable` valait toujours vrai, elle ne se déclenchait jamais.

### D161. Scraper : lecture par les liens réels, robots.txt, plafond de pages, formulaires de contact (phase 15)
- `spontanees/lecture_site.py` : pages lues parmi les liens réels de l'accueil et du sitemap (robots.txt, puis /sitemap.xml), par catégorie : contact, recrutement et carrières, mentions légales, à propos. Plus d'adresses devinées (« /contact », « /careers »... : 594 réponses 404 sur 849 requêtes à l'audit).
- robots.txt respecté comme le dit la RFC 9309 (règles de « ChasseurBot », sinon « * ») : page interdite jamais demandée ; robots.txt indisponible (4xx, 403 compris) : tout est permis ; erreur du serveur (5xx) ou site injoignable : rien.
- Au plus `MAX_PAGES` = 8 pages HTML par site, vérification comprise, pause de 0,6 à 1,5 s entre deux pages.
- Formulaires de contact ou de candidature (champ message ou fichier ; ni recherche, ni connexion, ni lettre d'information) enregistrés dans `extra.formulaires_contact` ; une entreprise sans email en montre le lien (« Ouvrir le formulaire de contact »).

### D162. Emails : domaine du site vérifié exigé, adresses factices et mal formées écartées ; revalidation (phase 15)
- **Règles** (`shared/validation_emails.classer`, avec le site vérifié) : écartée d'office une adresse de la liste d'exclusion (complétée des gabarits vus en base : monentreprise, votreentreprise, masociete...), mal formée (partie locale ou domaine mal écrits, extension ni à deux lettres ni dans la section `[extensions]` : « info+dpo@companyfrance.fr.nous »), à préfixe écarté, sans site vérifié, ou d'un autre domaine que le site vérifié. Validée d'office : domaine du site vérifié et préfixe de contact. Douteuse (l'IA ou la personne tranche) : même domaine mais adresse nominative, ou messagerie grand public trouvée sur le site vérifié. Avant, une adresse d'un autre domaine était douteuse et l'IA la validait (contact@health-data-hub.fr sur gnius.esante.gouv.fr, info+dpo@companyfrance.fr).
- **Revalidation** sans rien envoyer : `scripts/revalider_emails_en_base.py`, lecture seule par défaut ; `--verifier-sites --recherche` cherche le site maintenant ; `--appliquer` écrit (adresses écartées retirées de `emails_trouves`, gardées dans `extra.emails_ecartes_revalidation`). Une adresse fournie par La Bonne Alternance est gardée ; une entreprise déjà contactée n'est pas touchée. La revalidation par l'IA (« Faire revoir par l'IA ») suit les mêmes règles, avec le site vérifié enregistré.

### D163. Entreprises à fort potentiel de La Bonne Alternance tirées de l'export complet (phase 15)
- **Mesure** (`scripts/audit_lba_export.py --recherche`, 22 novembre 2026, profil alternance M18, départements 75, 92, 93, 94) : 3888 entreprises après les filtres du profil par l'export, 2933 par la recherche par cercles, 955 en plus, aucune en moins. Les entreprises viennent désormais de l'export ; la recherche par cercles ne sert plus qu'aux offres (et à la comparaison de l'audit).
- **Lecture en flux** (`offres/export_lba.py`) : l'export (environ 820 Mo, offres et recruteurs mêlés) n'est jamais chargé en entier ni écrit tel quel. Il est décodé objet par objet pendant la réception, et seules les entreprises « recruteurs_lba » d'Île-de-France sont gardées, normalisées comme celles de la recherche, avec leurs codes métiers, dans `DATA_DIR/lba_recruteurs_idf.jsonl.gz` (JSON Lines compressé, quelques Mo). Un seul fichier pour tous les profils : les codes métiers du profil (indifférent : tous), puis la taille et les départements des spontanées, filtrent à la relecture, ligne à ligne, et les entreprises passent à la base une à une.
- **Rafraîchissement** au plus une fois tous les 7 jours (`FRAICHEUR_JOURS`), à la première étape « Trouver des entreprises » qui en a besoin ; un seul téléchargement à la fois. Export injoignable ou clé refusée : l'ancien fichier sert, avec un message ; sans fichier ni clé, aucune entreprise LBA pour ce lancement.
- La limite et le partage avec Sirene (D44) ne changent pas. Les tests redirigent le fichier vers un dossier temporaire.

### D164. Garde-fou : la suite de tests échoue si data/ change (phase 15)
- Après l'incident de D163 (un test avait écrit un fichier factice dans le vrai `data/`, supprimé aussitôt), `tests/conftest.py` prend l'empreinte de `data/` et de `DATA_DIR` s'il est ailleurs (chemin, taille, date de modification de chaque fichier) au début et à la fin de la session. Un fichier créé, modifié ou supprimé fait échouer la suite (code de sortie 1) avec la liste des écarts. Vérifié avec un test temporaire qui écrivait dans un `DATA_DIR` de travail : code 1 et écart listé ; sans lui, code 0.

### D165. Jamais de page ni d'email d'un sous-domaine de préproduction ou de test (phase 15)
- **Constat** : à la mesure du 22 novembre 2026, le site vérifié de France Université Numérique était `prepod.fun.luniversitenumerique.fr` (son SIRET y figure, mais c'est une préproduction).
- **Règle** (`shared/liens.py`) : un sous-domaine dont une étiquette, hors domaine principal, vaut preprod, pre-prod, prepod, staging, dev, test, tests, recette, qa ou demo (suivi ou non d'un chiffre ou d'un tiret : staging2, recette-v2) est de préproduction. Jamais lu : un candidat, un lien de l'accueil ou du sitemap, une page à lire est remplacé par la même adresse sur le domaine principal (étiquettes jusqu'à la dernière de préproduction retirées : prepod.fun.x.fr devient fun.x.fr) ; une page redirigée vers une préproduction est refusée. Une adresse email d'un tel domaine est écartée (« domaine de préproduction ou de test ») ; un site vérifié enregistré en préproduction compte sur son domaine principal. « test.fr » ou « developpement.acme.fr » ne sont pas concernés.

### D166. Scraper, sources sûres : site de l'export LBA par SIREN, site des offres France Travail (phase 15, étape 3)
- Avant toute recherche, le scraper essaie, dans l'ordre : le site déjà vérifié, le site La Bonne Alternance (celui de l'entreprise LBA, sinon celui de l'export pour son SIREN), puis le site donné par une offre France Travail ou LBA au même nom (D160). Tous passent par la même vérification (SIREN ou nom).
- L'export LBA garde désormais, en le lisant, `{SIREN: workplace.website}` de toutes ses entrées (`DATA_DIR/lba_sites_par_siren.json`). Constat sur l'export du 22 novembre 2026 : 328 offres et aucun recruteur ont un site, soit 140 SIREN, dont aucun dans l'échantillon de 40. Le gain attendu est donc faible ; la source coûte une lecture de fichier.
- Pour France Travail, `entreprise.url` est déjà mis dans la description de l'offre (D160). L'audit des champs du 23 novembre 2026 montre qu'aucune des 796 offres lues n'en donne : source sans effet aujourd'hui, gardée au cas où l'API le fournirait.

### D167. Scraper, autres noms de l'entreprise : sigle, dénominations usuelles, enseignes (phase 15, étape 3)
- La récupération Sirene garde le sigle, les trois dénominations usuelles de l'unité légale, les enseignes et la dénomination usuelle de l'établissement (`extra.autres_noms`).
- Une entreprise qui ne les a pas (déjà en base, ou venue de LBA) les reçoit une fois de l'API publique Recherche d'entreprises (données Sirene, sans clé, seul le SIREN est envoyé), puis les garde ; si l'API ne répond pas, ils seront redemandés.
- Ces noms servent à prouver le site (nom dans le titre ou les mentions légales) et ajoutent une requête de recherche chacun (trois au plus).
- TIDF : ni sigle ni enseigne dans Sirene. « Toshiba Île-de-France » n'y figure pas, donc cette règle ne le trouve pas.

### D169. Éligibilité par Python à partir des exigences structurées des offres (phase 15, étape 3)
- **Constat** (banc de départ, 137 offres annotées) : 45 offres faussement éligibles, dont 34 en job sur 36 inéligibles attendues. Elles exigent un CACES, un diplôme d'État ou de l'expérience, ce qu'aucune règle Python ne regardait ; et un niveau « (indispensable) » restait souhaité à cause de « ou équivalents ».
- **Offres France Travail.** Les champs structurés sont ajoutés en lignes à la fin de la description, jamais coupées (seule la description libre est raccourcie) :
  - `Permis : B - Véhicule léger (exigé|souhaité)` ;
  - `Expérience : 2 An(s) (exigée|souhaitée)`, d'après `experienceExige` (E, S, D) ;
  - `Formation : … (indispensable|souhaitée)` ;
  - `Compétence : … (indispensable|souhaitée)`.

  Les noms et valeurs réels de ces champs restent à vérifier avec `scripts/audit_champs_france_travail.py` (clé France Travail). Déjà vus en base : les libellés d'expérience (« 2 An(s) », « 6 Mois », « Débutant accepté », « Expérience exigée »), les formations et les compétences avec leur exigence.
- **Offres LBA.** Les fourchettes d'expérience de `access_conditions` (« 1-2 ans », « 3-5 ans ») deviennent la même ligne d'expérience exigée. Les textes génériques du métier (« Cet emploi est accessible avec un CAP… », 1 897 offres sur 12 507) ne sont pas repris : ils décrivent le métier, pas l'offre.
- **Profil.** Nouveaux champs dans la partie « Ton parcours », communs aux trois modes et copiables (section « Permis, expérience en mois et certifications »), rangés dans `profils.recherche` (pas de migration) :
  - permis en cases (référentiel France Travail, plus « Aucun permis ») ;
  - expérience totale en mois ;
  - certifications en étiquettes, avec suggestions (CACES R489, SSIAP 1, carte professionnelle de sécurité, BAFA, PSC1) et saisie libre.
- **Règles** (`shared/exigences.py`, appelées par `raisons_ineligibilite`) :
  - permis exigé que le profil n'a pas (« aucun » ou d'autres codes) : inéligible ; permis non renseigné : ne bloque pas ;
  - formation exigée d'un niveau supérieur à celui du profil : inéligible ;
  - diplôme d'État exigé (en toutes lettres ou par sigle, avec un mot d'exigence), absent de la formation et des certifications : inéligible, sauf en alternance où c'est souvent le diplôme préparé ;
  - expérience exigée : en job, si elle dépasse celle du profil (non renseignée : ne bloque pas) ; en alternance, deux ans ou plus, ce n'est pas une alternance ;
  - certification exigée (CACES, SSIAP, carte professionnelle de sécurité, BAFA, PSC1, SST, habilitation électrique, HACCP, FIMO/FCO ; « CASES », coquille vue en base, compte pour CACES), absente du profil : inéligible. Rapprochement par famille de certification, pas par catégorie.
- Le modèle n'en décide pas : il n'extrait que ce que Python ne lit pas (niveau, durée et dates écrits en texte libre). Une offre d'avant D169, sans ces lignes, garde les règles d'avant.

### D168. Scraper : domaines devinés d'après le nom, avant toute recherche web (phase 15, étape 3)
- Après les sources sûres (D166) et avant la recherche web, le scraper essaie jusqu'à 8 domaines devinés : le nom simplifié (sans forme juridique ni mots de liaison : « Groupe Puce et Plume » donne puceplume), mots collés puis séparés d'un tiret, avec .fr, .com, .eu et .io, puis le sigle et les autres noms (D167). Chacun est essayé aussi avec « www. ».
- Ils sont vérifiés comme les autres candidats : SIREN, SIRET ou numéro de TVA, sinon nom dans le titre ou les mentions légales (avec, pour un nom d'un seul mot, le SIREN obligatoire : D172).
- **Redirection suivie** (complément, constaté à la mesure du groupe 2) : un domaine deviné qui redirige vers un autre domaine (cartadis.fr vers cartadis.com, prodware.fr vers prodwaregroup.com, theatredelaville.fr vers theatredelaville-paris.com) est vérifié, lu et retenu sur le domaine d'arrivée. Avant, le lecteur restait sur le domaine de départ : les mentions légales du vrai site n'étaient pas lues, et le site retenu ne correspondait pas au domaine des emails.
- Sans moteur de recherche, donc sans limite de requêtes. Un domaine qui n'existe pas échoue tout de suite et n'est pas noté parmi les essais. Seuls les noms d'au moins 4 caractères avec un mot distinctif sont devinés.

### D171. Scraper, recherche web : 8 candidats, domaines interdits écartés avant de compter, requête sans ville (phase 15, étape 3)
- **Constat** (mesure de l'étape 2) : pour Murex, Cartadis, Prodware ou The Body Shop, le domaine officiel n'apparaissait jamais parmi les 4 candidats essayés ; les places étaient prises par des pages tierces qui citent le nom (doctrine.fr, jobted, usinenouvelle, infobel, xerfi, fusacq, clutch…).
- **Règles.** Un domaine interdit est écarté avant d'être compté : seuls les candidats possibles prennent une place, et il y en a désormais 8 au lieu de 4. Une requête « "nom" site officiel », sans ville, s'ajoute après la première. Les agrégateurs vus à la mesure entrent dans `domaines_interdits.txt`.

### D172. Nom d'un seul mot distinctif : SIREN obligatoire sur le site (phase 15, étape 3)
- **Constat** : Fermat (olympic.fermat.edu.vn), Bellon (fondationpierrebellon.org) et Ithis (ithishospital.com) avaient été retenus sur leur seul nom dans un titre.
- **Règle.** La preuve par le nom (titre du site ou mentions légales) n'est acceptée que pour un nom qui a au moins deux mots distinctifs (4 lettres ou plus, ni généraux, ni formes juridiques, ni nombres). Sinon il faut le SIREN, le SIRET ou le numéro de TVA. Cela vaut aussi pour les autres noms (D167) : « Toshiba Île-de-France » n'a qu'un mot distinctif.
- **Effet attendu** : moins de faux, mais certains sites justes trouvés par le titre seul (Neurones, WeTradeLocal, Degetel…) exigent maintenant leur SIREN dans les mentions légales. La mesure le dira.

### D170. Prompt d'analyse v2 : extraction sans le profil, jugement en un mot, Python note et plafonne (phase 15, étape 3)
- **Constats** (banc de départ) : la catégorie n'est juste qu'à 36,7 % ; le modèle met rarement « Hors sujet » et sous-note les offres moyennes ; à l'étape 1, il recopiait le niveau du profil au lieu de celui de l'offre, et ne voyait que 2 000 caractères.
- **Appel 1, extraction** (`offres/analyse_v2.py`) : il ne voit pas le profil et lit la description entière (jusqu'à 8 000 caractères). Il donne niveau et exigence, durée, date de début, alternance seulement, années d'expérience exigées, permis exigé, certifications exigées, diplôme d'État exigé. Python contrôle chaque valeur contre le texte (D98). Les exigences retrouvées dans le texte deviennent des lignes structurées, jugées par les mêmes règles que D169.
- **Appel 2, jugement** : avec le profil, sur la description raccourcie (`IA_LONGUEUR_DESCRIPTION`), un mot parmi Très bien, Bien, Moyen, Faible et Hors sujet, chacun défini. L'arbre de décision est ordonné :
  1. hors sujet (domaine, postes à éviter, ce n'est pas le bon contrat) ;
  2. adéquation des missions ;
  3. réserves, en descendant d'un cran une seule fois.

  Niveau, durée, dates, permis et certifications ne comptent pas : ils sont vérifiés à part.
- **Python** convertit le mot en note (Très bien 9, Bien 7, Moyen 5, Faible 3, Hors sujet 1), décide l'éligibilité (plafond 3 si inéligible) et plafonne : un niveau souhaité deux crans ou plus au-dessus du profil donne Moyen au plus, à la place du malus de 1 à 2 points de v1.
- **Mesure** (D, `scripts/banc_ia/decouper.py`) : le jeu annoté est coupé en deux moitiés fixes (graine 15, réparties par mode), 69 offres de réglage et 68 de test. Le prompt ne s'ajuste que sur la moitié réglage. La moitié test sert à la mesure finale seulement : v1 contre v2 avec ministral-3:3b, puis v2 avec ministral-3:8b. Les bancs lisent les seules variables `IA_*` du `.env`. `banc_analyse.py --version v1|v2`.
- **Réglage** (moitié réglage seulement, ministral-3:3b, 1 essai, 69 offres) :

  | Passage | Éligibilité | Catégorie exacte | Écart moyen |
  |---|---|---|---|
  | 1 | 87 % | 26 % | 1,14 rang |
  | 2 | 87 % | 36 % | 0,88 rang |
  | 3 | 87 % | 49 % | 0,61 rang |

  1. Arbre tel que conçu : le modèle met « Hors sujet » partout où le poste n'est pas dans les types de jobs qui conviennent.
  2. Étape 1 resserrée : Hors sujet seulement pour ce que le profil écarte explicitement ; en cas de doute, étape 2.
  3. Le modèle doit recopier la phrase du profil qui impose Hors sujet (`hors_sujet_car`) ; Python ne garde Hors sujet que si elle vient d'un champ d'exclusion (types de jobs à éviter, ce qu'il préfère éviter, domaines recherchés hors job), sinon Faible.
- **Mesure finale** (moitié test, 68 offres jamais regardées avant, 1 essai, température 0, variables `IA_*` du `.env`) :

  | | v1, 3b | v2, 3b | v2, 8b |
  |---|---|---|---|
  | Éligibilité juste | 60,3 % (26 faux éligibles) | 72,1 % (18) | 70,6 % (19) |
  | Faux inéligibles | 1 | 1 | 1 |
  | Niveau extrait juste | 86,8 % | 89,7 % | 86,8 % |
  | Faux positifs de niveau | 0 | 0 | 0 |
  | Catégorie exacte | 32,4 % | 51,5 % | 55,9 % |
  | Écart moyen | 0,76 rang | 0,63 rang | 0,56 rang |
  | Réponses à 2 rangs ou plus | 4 | 8 | 6 |
  | Temps par offre | 23,3 s | 23,8 s | 50,2 s |
  | Réponses invalides | 0 | 0 | 0 |
- **Décision** : v2 devient le prompt de l'application (`IA_VERSION_ANALYSE`, défaut `v2`, `v1` pour revenir), avec ministral-3:3b. Le 8b gagne un peu en catégorie mais double le temps. Les tests d'avant restent épinglés sur v1, v2 a les siens.

### D173. Nom d'un seul mot : site accepté sans SIREN si le domaine est le nom et si l'adresse Sirene y figure (phase 15, étape 3)
- **Constat** (D172) : la règle « SIREN obligatoire pour un nom d'un seul mot distinctif » écartait Fermat et Bellon, mais aussi 7 sites justes (WeTradeLocal, AMUE, Theatre de la Ville, Degetel, Cartadis, Lexmark, Murex), dont les mentions légales n'affichent ni SIREN, ni RCS, ni TVA.
- **Règle.** Un tel site est accepté sans SIREN aux deux conditions suivantes ; sinon, SIREN toujours obligatoire :
  1. le domaine principal (sans sous-domaine ni extension) est exactement le nom distinctif simplifié (cartadis.com pour CARTADIS, lexmark.com pour LEXMARK INTERNATIONAL) ;
  2. l'accueil, la page contact (lien réel de l'accueil, une page de plus) ou les mentions légales portent le code postal ou la voie (au moins 8 caractères) d'une adresse Sirene de l'entreprise : l'établissement francilien en base, ou le siège donné par l'API Recherche d'entreprises (gardé dans `extra.adresse_siege`, même appel que D167).
- **Mesure** (groupe 4, mêmes recherches en cache) :
  - 14 justes, 2 faux, 11 non trouvés, contre 12, 2 et 13 avec D172 strict ;
  - Degetel et Cartadis retrouvés par leur code postal ;
  - Fermat et Bellon ne reviennent pas ;
  - 42,2 s par entreprise.
- Preuve enregistrée : `domaine_adresse`, avec ce qui a été trouvé et où (« domaine au nom de l'entreprise et code postal 94120 dans la page contact »).

### D174. Job : expérience exigée inéligible seulement au-delà de 12 mois d'écart (phase 15, étape 3)
- **Constat** (remesure avec le profil rempli) : 5 offres job exigeant 1 ou 2 ans d'expérience, annotées éligibles (« vente en magasin, accepté par le profil »), étaient écartées pour un profil de 3 mois.
- **Règle.** En job, l'offre est inéligible seulement si l'expérience exigée dépasse celle du profil de plus de 12 mois. Sinon elle reste éligible, plafonnée à Moyen (5), avec « Expérience demandée : 1 an » en tête de Ce qui coince (`shared/exigences.reserves`, appliqué par `appliquer_eligibilite`, en v1 comme en v2). La règle de l'alternance (2 ans ou plus) ne change pas.

### D175. Aucun permis et permis exigé, toute catégorie : inéligible (phase 15, étape 3)
- **Constat** (remesure) : pour 3 offres « Conducteur de bus », v2 extrayait « permis C » alors que le texte demande une autre catégorie ; le contrôle contre le texte rejetait la valeur, et l'offre restait éligible pour un profil sans permis.
- **Règle.** Quand l'extraction donne un permis exigé dont la catégorie n'est pas retrouvée dans le texte, mais que le texte parle bien de permis, une ligne « Permis : * - catégorie non lue (exigé) » est ajoutée. Un profil « Aucun permis » est alors inéligible (« permis exigé, tu n'as pas de permis »), comme pour toute catégorie lue. Un profil qui a un permis n'est pas écarté sur une catégorie incertaine ; un permis non renseigné ne bloque jamais.

### D176. Expérience écrite en lettres et en fourchettes (phase 15, étape 3)
- **Constat** (remesure) : pour 2 offres « Conseiller en gestion de patrimoine », v2 extrayait 3 ans d'expérience, mais le contrôle contre le texte, qui cherchait « 3 ans », rejetait la valeur.
- **Règle** (`shared/exigences.annees_dans_texte`) : le texte porte une durée d'expérience écrite en chiffres ou en lettres (un à dix), seule ou en fourchette (« 3 à 5 ans », « 3-5 ans » : la borne basse), avec ou sans « minimum » ou « au moins » (« 2 ans minimum », « au moins deux années »). L'extraction est gardée si son nombre d'années figure parmi celles-là.

### D177. Bac+5 exigé : stage de fin d'études, dernière année d'école d'ingénieurs ou de master, M2 (phase 15, étape 3)
- **Constat** (remesure) : 3 offres Bac+5 (un stage de fin d'études en école d'ingénieurs, deux alternances) restaient éligibles pour un profil Bac+2. Aucun mot d'exigence n'était écrit à côté du niveau, donc D103 les classait « souhaité » (plafond Moyen).
- **Règle** (`shared/eligibilite.BAC5_EXIGE`) : « stage de fin d'études », « dernière année d'école d'ingénieurs », « dernière année de master » (ou du cycle ingénieur) et « M2 » (« Master 2 ») valent Bac+5 exigé, même sans mot d'exigence et même avec « ou équivalent ». Les autres indices suivent toujours D103 : « idéalement en école d'ingénieurs (Bac+5) » reste souhaité. Les tests MOSS, qui encodaient l'ancienne lecture de « dernière année d'école d'ingénieurs ou Master 2 », sont mis à jour.

### D178. Alternance : diplôme préparé à plus d'un niveau au-dessus du niveau visé, inéligible (phase 15, étape 3)
- **Constat** (remesure) : une alternance Product Owner préparant un Bac+4/5 (ISCOD) restait éligible pour un profil qui vise un DEUST (Bac+2).
- **Règle.** En alternance, le niveau de l'offre (extrait puis contrôlé contre le texte) est celui du diplôme préparé. S'il dépasse de plus d'un cran le niveau visé du profil (champ « Niveau visé »), l'offre est inéligible (« diplôme préparé Bac+5, niveau visé Bac+2 »), qu'il soit exigé ou souhaité. Un cran au-dessus reste toléré (comme le niveau adjacent de D154). Un niveau visé non renseigné ne bloque pas.

### D179. Job : poste confirmé, senior ou expérimenté, traité comme le poste senior de l'alternance (phase 15, étape 3)
- **Constat** (remesure) : « Responsable commercial confirmé » restait éligible en job ; la règle « poste senior » n'existait que dans le prompt de l'alternance. Avec v2, un « Hors sujet » sans phrase du profil redescend à Faible, donc elle ne tenait plus non plus en alternance.
- **Règle** (`shared/exigences.poste_senior`, appliquée par Python) : en job et en alternance, un intitulé qui contient « confirmé », « senior » ou « expérimenté » (et leurs accords) rend l'offre inéligible (« poste confirmé ou senior »), comme l'annotation la classe. « Responsable » seul ne compte pas. Exception reprise de l'alternance : une offre déposée par un organisme de formation (marque `organisme_formation`) n'est pas concernée.
- Choix à confirmer : la règle de l'alternance donnait une note basse (0 à 2) ; ici l'offre devient inéligible, ce qui revient à la même catégorie (« Hors sujet ») et suit l'annotation.

**Point 8 de la remesure, métiers qualifiés sans exigence écrite** (frigoriste, technicien CVC, gestion locative) : aucune règle, décision de l'utilisatrice ; ils restent jugés par l'IA.

### D180. M2 exigé seulement après « en », « de », « niveau », « étudiant(e) », « préparez » (phase 15, étape 3)
- **Constat** (remesure après D177) : l'offre « Adjoint en scolarité », dont les missions citent les « dossiers d'entrée en Master 1 et Master 2 », devenait inéligible pour un profil Bac+1.
- **Règle.** « M2 » ou « Master 2 » reste un indice de niveau Bac+5. Il ne vaut exigé que précédé, à quelques mots près, de « en », « de », « niveau », « étudiant(e) », « préparez » ou « préparant », un article pouvant s'intercaler (« préparez un M2 », « étudiant en M2 », « niveau Master 2 »). Sinon D103 s'applique. « Stage de fin d'études » et « dernière année d'école d'ingénieurs ou de master » restent exigés (D177).

### D181. Annotation : « Assistant(e) administratif(ve) polyvalent(e) », 2 ans exigés, inéligible (phase 15, étape 3)
- Dans le jeu de référence (`banc_reference.json`) et la moitié test, l'offre job qui exige 2 ans d'expérience passe en attendu inéligible. Elle est cohérente avec D174 : 21 mois d'écart pour un profil de 3 mois, au-delà des 12 tolérés. Les autres offres qui exigent 1 an gardent leur annotation éligible (plafond Moyen par D174). Comme pour le CACES (point 2 de la remesure précédente), c'est l'annotation qui change, pas une règle.

### D182. Permis implicite pour les métiers de conduite (phase 15, étape 3)
- **Constat** (remesure) : 3 offres « Conducteur de bus » restaient éligibles pour un profil « Aucun permis » ; leur description stockée ne dit pas « permis ».
- **Règle.** `shared/referentiels/metiers_conduite.txt` liste les métiers de conduite : conducteur ou conductrice de bus, de car, d'autocar ou de poids lourd, conducteur PL, SPL ou routier, chauffeur et chauffeuse (y compris chauffeur-livreur et VTC), ambulancier et ambulancière. Un intitulé qui en contient un, sur des mots entiers et sans tenir compte des accents ni du pluriel, vaut « permis exigé, catégorie non lue ». Un profil « Aucun permis » est inéligible ; un profil qui a un permis ne l'est pas ; un permis non renseigné ne bloque pas. « Conducteur de travaux » et « chauffagiste » ne sont pas concernés.

### D183. Expérience exigée sans durée, poste « débutant accepté » : aucun changement (phase 15, étape 3)
- « Expérience : Expérience exigée » sans durée (Conseiller en gestion de patrimoine) ne rend pas inéligible : sans durée écrite, la règle job (D174) ne s'applique pas.
- « Responsable commercial Clients Directs Ouest », dont le titre ne dit pas « confirmé » et dont le texte indique « Débutant accepté », reste éligible. Ces offres restent comptées faux éligibles dans le banc : décision de l'utilisatrice.

### D184. Étiquettes du profil : la suggestion choisie et la saisie en cours sont gardées (phase 16)
Une certification choisie dans la liste suggérée remplissait le champ sans touche Entrée : aucune étiquette n'était créée et « Enregistrer » envoyait une liste vide (le serveur, lui, enregistrait bien). Désormais une valeur égale à une suggestion devient une étiquette dès qu'elle est choisie, une saisie non validée le devient quand on quitte le champ, et `collecter()` compte la saisie en cours (compétences et certifications). Test : enregistrer puis relire par l'API dans les trois modes (`tests/test_profil_parcours.py`).

### D185. « Ton parcours » : permis aligné sur les autres champs, aides sous le titre (phase 16)
- Permis : le fieldset perd le cadre du navigateur (titre au-dessus, sans trait) ; les cases prennent le style des domaines (bords arrondis, case cochée surlignée). « Aucun permis » coché décoche et désactive (grise) les autres cases, comme « Indifférent » pour les domaines : pour cocher un permis, on décoche d'abord « Aucun permis ».
- Certifications et compétences : la liste d'étiquettes vide est masquée, et le titre, l'aide et le champ sont regroupés comme un champ simple (5 px au lieu des 18 px qu'imposait l'espacement des blocs).
- Texte d'aide : partout sous le titre, au-dessus du champ (14 aides déplacées qui étaient sous le champ) ; dans les blocs composés (projets, documents, domaines, mail), l'aide est collée à son titre.

### D186. Revalidation des emails en base : examen en lecture seule, écriture en une transaction à la fin (phase 16)
- Avant : `--appliquer` ouvrait une session d'écriture pour tout le parcours, réseau compris, et ne commitait qu'à la fin ; un Ctrl+C sautait le commit (rien d'écrit, `autoflush=False` et aucune fonction appelée n'écrit en base), mais ce n'était garanti que par cette structure.
- Désormais : l'examen (sites, recherche web, décisions) se fait toujours sur la base ouverte en lecture seule ; Ctrl+C pendant l'examen affiche « rien n'a été écrit en base » (code 130). L'écriture vient ensuite, en une seule transaction courte. Une entreprise dont les adresses ont changé entre-temps, ou contactée entre-temps, n'est pas touchée.
- Constat sur la base après le `--appliquer` interrompu du 25/11 (comparaison en lecture seule avec `chasseur_v2_avant_revalidation_2026-11-25_0132.db`) : entreprises, candidatures, emails contactés, profils identiques ; seuls changent le mode essai du compte d'envoi de l'utilisateur 1 (activé) et le compteur d'envois du 25/11 (2 envois), sans lien avec le script : le script n'écrit ni l'un ni l'autre (vraisemblablement l'étape 12 du guide, envoi en mode essai).

### D187. Recherche web : plusieurs moteurs avec repli, arrêt après des échecs d'affilée (phase 16)
- Diagnostic (25/11) : ddgs 9.12.1, moteur non forcé (`backend="auto"` : Wikipédia et Grokipédia d'abord, puis les autres moteurs dans un ordre aléatoire, deux en parallèle), région `us-en`. Rythme : 3 à 6 s entre deux requêtes, 45 s de pause toutes les 15, et après un refus, 90 s d'attente puis un nouvel essai. Après le lancement interrompu, DuckDuckGo et Mojeek renvoient un captcha, Brave un 429.
- Règle : les moteurs de `RECHERCHE_BACKENDS` (.env) sont essayés un par un, dans l'ordre, région `fr-fr` ; le suivant seulement si le précédent refuse ou ne trouve rien. Défaut : `brave, mojeek, duckduckgo, yahoo, yandex`. Un nom inconnu est ignoré et journalisé.
- Mesure (`scripts/mesurer_moteurs_recherche.py`, 25 entreprises de référence qui ont un site, première requête du scraper, adresse bloquée) : Brave, Mojeek, DuckDuckGo et Google refusent les 25 requêtes (0,5 s chacune) ; Yahoo répond 15 fois (site officiel 3 fois), Yandex 22 fois (2 fois). Un moteur bloqué coûte moins d'une seconde : les moteurs habituels restent en tête, Yahoo et Yandex servent de repli. Mesure à refaire hors blocage pour départager les premiers.
- Après 5 requêtes d'affilée sans réponse d'aucun moteur, la recherche web s'arrête pour le lancement (journalisé) ; plus aucune attente de 90 s ; les autres sources du site restent essayées. Le lancement suivant la réautorise.
- Aucune API payante.

### D188. Site officiel d'après Wikidata, avant toute recherche web (phase 16)
- `spontanees/wikidata.py` interroge query.wikidata.org (SPARQL, public, gratuit, sans clé) : l'élément qui porte le SIREN (P1616) et son site officiel (P856). Seuls les SIREN sont envoyés, par lots de 100 au début d'un lancement, avec un User-Agent qui nomme le client sans contact personnel. Une panne ne bloque rien.
- Ordre des sources du site : déjà vérifié, Wikidata, LBA, offres, domaines devinés, recherche web. Un site trouvé par Wikidata compte comme vérifié dès que son accueil se lit (preuve « site officiel déclaré dans Wikidata pour le SIREN »), sans SIREN ni nom à trouver sur le site ; illisible, la source suivante est essayée.
- Mesure (`scripts/mesurer_wikidata.py`, 40 entreprises de `scraper_reference.json`) : 7 ont un site dans Wikidata, 6 justes (France Université Numérique, Onisep, Amue, Neurones, PAP, Murex), 1 non tranché (« PARIS HOTEL DE VILLE », bred.fr : la référence n'a pas de site), aucun faux. 33 absentes de Wikidata.
- Les tests ne l'appellent jamais (conftest coupe `requests` du module).

### D189. Ce que voit l'IA : num_ctx jamais trop petit, description coupée signalée (phase 16)
- Caractères de description lus (v2) : extraction 8 000 (`LONGUEUR_EXTRACTION`), jugement `IA_LONGUEUR_DESCRIPTION` (2 000 dans ton .env). Dans ta base, la description la plus longue fait 5 035 caractères : l'extraction lit toujours tout ; le jugement coupe 137 offres sur 267 (5 sur 10 en alternance, 44 sur 130 en job, 88 sur 127 en stage).
- Mesure (`voir_texte_ia.py --analyser --num-ctx 16384`, 5 offres de stage les plus longues, ministral-3:3b) : extraction 1 583 à 1 687 tokens lus, environ 100 écrits ; jugement 1 559 à 1 581 lus, jusqu'à 253 écrits ; 4,1 à 4,3 caractères par token. Ton `IA_NUM_CTX=4096` suffit aux limites actuelles. Modèle chargé avec 16 384 : 3,3 Go.
- Règle : avant chaque appel à Ollama, le prompt est estimé à 3 caractères par token (prudent), plus 1 024 tokens de réponse, arrondi au millier ; num_ctx envoyé = le plus grand de `IA_NUM_CTX` et de cette estimation, plafonné à 16 384. Avec tes réglages, 4 096 reste envoyé (pas de rechargement du modèle). `prompt_eval_count` et `eval_count` de chaque réponse sont lus (`shared.ia.dernier_appel`) ; une fenêtre pleine (lus + écrits à moins de 32 tokens de num_ctx) est journalisée.
- Description coupée : ligne « ✂️ Description coupée pour l'IA » dans le journal (caractères lus par chaque appel), et, dans le détail de l'offre, l'étiquette « Description longue : l'IA en a lu les 2 000 premiers caractères sur 3 412 pour la note » (marque `description_coupee:<lus>` dans `candidatures.marques`, mise à jour à chaque analyse, sans migration).
- `scripts/banc_ia/voir_texte_ia.py` : texte exact des deux appels, coupure et texte perdu ; `--analyser` lance les appels et affiche catégorie, prompt_eval_count et num_ctx.

### D190. Entreprises à contacter : origine affichée, filtre par origine, transverses facultatives (phase 16)
- Chaque entreprise dit pourquoi elle est là, calculé à la lecture (code NAF rév. 2 ou 2025 de l'entreprise comparé aux secteurs du profil actuel, colonne `sources`), sans migration : « Informatique » (cœur de métier, libellé court ajouté à `correspondance_naf.json` ; « Immobilier » pour C15), « Grande entreprise, service informatique interne » (transverse), « La Bonne Alternance, recrute des alternants dans ton métier », « Secteur choisi dans ton profil », « Tous les secteurs », ou « Sirene, hors des secteurs actuels de ton profil » si le profil a changé depuis. Une entreprise trouvée par les deux sources affiche les deux.
- Le filtre « Source » devient « Origine » : ton secteur, grandes entreprises (service interne), La Bonne Alternance, autres. Les entreprises déjà contactées, sans origine calculée, restent affichées.
- Profil, options de recherche : « Inclure les grandes entreprises qui ont un service interne de ton domaine » (cochée par défaut, `recherche.inclure_transverses`). Décochée, « Trouver des entreprises » ne cherche plus les transverses sur Sirene (journalisé) ; celles déjà trouvées restent, filtrables.

### D191. Grandes entreprises : candidature sur leur site carrières (phase 16)
- Grande entreprise : 500 salariés et plus (tranche Sirene ou LBA lue dans `extra.taille`), ou catégorie GE (`shared.tailles.grande_entreprise`).
- Sur le site vérifié (Wikidata en premier, D188), le scraper retient la page carrières parmi les liens « recrutement » de l'accueil puis du sitemap : d'abord un lien qui dit carrières, careers, recrutement, jobs, nous rejoindre, rejoignez-nous ou join us, sinon le premier (stage, alternance, talents). Gardée dans `extra.page_carrieres` pour toute entreprise.
- Pour une grande entreprise sans email avec cette page : onglet « Sur leur site carrières » et bouton « Postuler sur leur site carrières » (nouvel onglet), au lieu de « Sans contact » ; journal « 💼 Grande entreprise, candidature sur son site carrières » au lieu de « Aucun email » ; bilan du lancement « N grandes entreprises à contacter sur leur site carrières ». Une page carrières sur un autre domaine (plateforme de recrutement) n'est pas suivie.

### D192. Nom affiché : dénomination de l'unité légale d'abord, établissement ou enseigne ensuite (phase 16)
- Constat : « PARIS HOTEL DE VILLE » a le SIREN 552091795, celui de BRED BANQUE POPULAIRE ; bred.fr (Wikidata, D188) est donc juste. Le nom affiché venait de l'export LBA (`workplace.brand` ou `name`, sans `legal_name`).
- La fiche de l'annuaire Recherche d'entreprises (déjà demandée pour les autres noms, D167) donne aussi `nom_raison_sociale`, gardée dans `extra.denomination` ; pour Sirene, la dénomination est `denominationUniteLegale` (déjà en base). Le scraper la demande quand elle manque.
- Entreprises à contacter : « BRED BANQUE POPULAIRE · PARIS HOTEL DE VILLE » (dénomination, puis nom d'établissement ou enseigne s'il diffère) ; la liste des emails à valider montre la dénomination.
- Entreprises déjà en base : `scripts/completer_denominations.py` (lecture seule par défaut, `--appliquer` écrit en une transaction à la fin). Sur ta base : 18 entreprises LBA sans dénomination, 18 trouvées (dont BRED, FML YR BEAUTE pour Yves Rocher, LEO TSOU SAS pour Le Ju).

### D193. L'IA lit la description entière ; plafond de sécurité ; un seul num_ctx pour l'analyse (phase 16)
- Décision de l'utilisatrice : plus de coupure réelle. Les deux appels de la v2 (et la v1) lisent la description entière. `IA_LONGUEUR_DESCRIPTION` devient un plafond de sécurité (défaut 20 000 caractères) : s'il coupe, c'est journalisé (« Plafond de sécurité atteint ») et l'étiquette « Description longue » apparaît ; sinon rien. La lettre garde sa limite de 2 000 caractères (`LONGUEUR_DESCRIPTION_LETTRE`), inchangée.
- Un seul num_ctx pour les deux appels, calculé pour le plus grand prompt possible (profil maximal, description au plafond, tous modes, 3 caractères par token, 1 024 de réponse) : 10 240 avec le plafond de 20 000, jamais plus de 16 384.
- Mesure du rechargement (`voir_texte_ia.py --analyser`, 5 offres de stage les plus longues, modèle déchargé au départ, `load_duration` d'Ollama) : avant, num_ctx par appel (extraction 4 096, jugement 5 120), le modèle est rechargé à chaque appel (2,6 à 3,6 s), 41,6 s par offre ; après, num_ctx 10 240 pour les deux, un seul chargement au premier appel, 35,6 s par offre ; mêmes catégories. Mémoire : 2,7 Go (5 120), 3,0 Go (10 240).
- Banc, moitié test (68 offres, v2, ministral-3:3b, 1 essai, température 0), contre la v2 du 23/11 (2 000 caractères, num_ctx 4 096) : éligibilité juste 0,897 -> 0,882 (faux éligibles 7 -> 8, faux inéligibles 0 -> 0) ; catégorie exacte 54,4 % -> 54,4 % ; écart moyen 0,57 -> 0,57 rang ; temps moyen 21,97 -> 26,45 s (offres de moins de 2 000 caractères, texte identique : 20,5 -> 24,6 s ; plus longues : 24,7 -> 29,9 s). Six offres changent de catégorie ou d'éligibilité : 3 vers l'attendu (Secrétaire-assistant médical et conducteur de bus, Assistant acheteur, Stage développeur web full-stack), 3 s'en éloignent (Architecte logiciel, devenu éligible : l'extraction lit « bac+3 souhaité » au lieu de « bac+5 exigé » sur le même texte ; CACES 3 préparateur, Hors sujet -> Faible, toujours inéligible ; Chargé de gestion locative, Hors sujet -> Moyen). Deux de ces changements portent sur des offres de moins de 2 000 caractères, au texte inchangé : ils viennent du changement de num_ctx, pas de la longueur.
- Ton .env contient `IA_LONGUEUR_DESCRIPTION=2000` : tant que la ligne y est, elle reste le plafond et coupe à 2 000. La retirer (ou mettre 20000).

### D194. Analyse : num_ctx unique de 4 096, relevé seulement si besoin (phase 16)
- Remplace le num_ctx de 10 240 de D193, dimensionné pour le plafond théorique : plus grand prompt mesuré 2 271 tokens, réponse 265 au plus.
- Les deux appels d'une offre reçoivent le même num_ctx, 4 096 (pas de rechargement entre eux). Si le plus grand des deux prompts estimés (3 caractères par token) plus 512 tokens de réponse n'y tient pas, il est relevé au millier supérieur pour cette offre (16 384 au plus), avec une ligne « num_ctx porté de 4096 à N » dans le journal. Les offres de ta base (5 035 caractères au plus) restent à 4 096.
- Banc de contrôle (68 offres, v2, ministral-3:3b, 1 essai, température 0, description entière), comparé à la v2 du 23/11 (2 000 caractères, num_ctx 4 096) et au banc de D193 (num_ctx 10 240) :
  - éligibilité juste : 0,897 / 0,882 / **0,897** (faux éligibles 7 / 8 / 7, faux inéligibles 0 / 0 / 0) ;
  - catégorie exacte : 54,4 % / 54,4 % / **54,4 %** ; écart moyen 0,57 / 0,57 / **0,57** ;
  - temps moyen : 21,97 / 26,45 / **25,88 s** ; offres de 2 000 caractères ou moins : 20,5 / 24,6 / 23,8 s ; plus longues : 24,7 / 29,9 / 29,7 s.
  - Offres qui changent face au 23/11 : quatre, toutes de plus de 2 000 caractères (effet de la description entière) : Secrétaire-assistant médical et conducteur de bus (Moyen -> Hors sujet, attendu Hors sujet), Assistant acheteur (Hors sujet -> Moyen, attendu Moyen), Stage développeur web full-stack (Bien -> Très bien, inéligible, attendu Bien), Chargé de gestion locative (Hors sujet -> Moyen, attendu Hors sujet inéligible). Architecte logiciel et CACES 3 reviennent à leur résultat du 23/11.
  - Les offres courtes, au texte et au num_ctx identiques au 23/11, prennent encore 3,3 s de plus : ce surcoût ne vient pas du num_ctx (cause non établie : état de la machine ou d'Ollama).

### D195. Alternance : diplôme préparé lu par Python, sans dépendre de l'IA (phase 16)
- Constat : « Architecte logiciel » écrit « Dans le cadre de la préparation du titre Architecte des Systèmes d'Information - Bac+5, niveau 7, nous recherchons […] un(e) alternant(e) » et « Vous êtes titulaire d'un Bac+3 en informatique […] et souhaitez poursuivre vos études en Bac+5 ». Pas de mot d'exigence près de « Bac+5 » : c'est le diplôme préparé (règle D178), pas un niveau exigé. Le contrôle Python acceptait la lecture « bac+3 » de l'IA puisque le texte cite aussi un Bac+3.
- Règle : `shared.eligibilite.niveau_prepare` lit le niveau d'un indice placé dans les 100 caractères qui suivent « préparation », « préparer », « préparez », « préparant », « prépare » ou « poursuivre vos études en », dans la même phrase. En alternance, D178 prend le plus haut niveau entre celui de l'IA et celui-ci.
- Vérification sur les 137 offres annotées (`banc_reference.json`, Python seul) : la règle se déclenche 2 fois (Product Owner / QA et Architecte logiciel), toutes deux inéligibles attendues ; aucun faux inéligible. Hors alternance, elle ne s'applique pas.

### D196. Références des bancs : seule scraper_reference.json est versionnée (ménage)
- `audit_exports/` est ignoré par git : aucune référence n'était versionnée.
- `scraper_reference.json` (entreprises, SIREN, sites officiels : données publiques) passe dans `scripts/references/`, versionné ; `audit_scraper.py`, `mesurer_wikidata.py` et `mesurer_moteurs_recherche.py` le lisent là par défaut (`audit_commun.REFERENCES`).
- Non versionnées, laissées dans `audit_exports/` : `banc_reference.json`, `banc_reglage.json`, `banc_test.json`, `banc_test_profils_a_jour.json` (profils complets des utilisateurs 1, 3, 4 et 5, état des candidatures) et `banc_emails_reference.json` (adresse nominative d'un tiers). Les scripts qui les lisent les reçoivent en argument : rien à changer.

### D197. Lettres PDF rangées dans DATA_DIR/lettres_pdf (ménage)
- Défaut de `LETTRES_PDF_DIR` : `DATA_DIR/lettres_pdf` au lieu de `lettres_pdf/` à la racine ; une valeur dans le `.env` reste prioritaire.
- La base stocke le chemin relatif à ce dossier (`candidatures.lettre_pdf`, « user_<id>/lettre_<hex>.pdf ») : aucune migration, seuls les fichiers bougent.
- `scripts/deplacer_lettres_pdf.py` : lecture seule par défaut (4 fichiers de user_1 à déplacer chez toi), `--appliquer` déplace, sous-dossiers compris, sans jamais écraser un fichier déjà présent ; application arrêtée.

### D198. Pièces jointes : fichiers sans nom répété ni suffixes empilés (ménage)
- Constat : le nom reçu par l'entreprise est le nom affiché de la pièce plus « .pdf » (`charger_pieces_jointes`), déjà propre (forme « Programme_X.pdf »). Le nom répété est celui des fichiers sur disque importés de l'ancienne application le 14/10 (forme « Programme_X_Programme_X.pdf », ou « Lettre_…_Lettre_…(tronqué) » sans extension), recopiés tels quels par l'import de l'ancienne base.
- Téléversement : la base du fichier perd un suffixe unique déjà présent (« _1a2b3c4d », fichier retéléversé) et une répétition (« A_A », ou « A_<début de A> » d'au moins 10 caractères) avant d'ajouter son suffixe unique.
- `scripts/renommer_pieces_jointes.py` : lecture seule par défaut ; `--appliquer` renomme les fichiers hérités et met à jour les chemins de tous les profils qui les citent, en une transaction (fichiers remis en place si l'écriture échoue), sans jamais écraser un fichier. Chez toi : 2 fichiers renommés ; le CV de stage (suffixe `_cd87164d`) garde son nom, le nom sans suffixe étant pris par l'autre CV.
- CV joints : en alternance, le CV du 14/10 (162 818 octets, nom sans suffixe) ; en stage, un autre fichier, celui du 12/11 (347 748 octets, suffixe `_cd87164d`) ; en job, aucun.

### D199. docs/ rangé, sorties de vérification hors de docs/ (ménage)
- Rapports `PHASE_*` et guides de fusion dans `docs/historique/` (liens de DECISIONS.md et RECETTE.md mis à jour) ; l'état des lieux du 7 octobre y devient `ARCHITECTURE_2026-10-07.md`, et `docs/ARCHITECTURE_ACTUELLE.md` est réécrit d'après le code (phases 15, 16 et ménage).
- `verification_*.json` et `test_pagination.json` ne sont lus par aucun code de l'application : ce sont les sorties des scripts de vérification des API (`verification_stage.json` sert aussi de jeu d'essai à `tests/test_intitules_stage.py`). Ils passent dans `scripts/verifications/<source>/` (versionné), où ces scripts écrivent désormais ; `docs/referentiels/` ne garde que les référentiels lus par le code (France Travail, table NAF de l'INSEE).
- `audit_exports/` (hors git) : 22 fichiers gardés (références, entrées des scripts, dernières mesures citées par D173 à D194), 34 déplacés dans `audit_exports/archives/` (dont l'export LBA brut, 787 Mo).
- `data/chasseur.db` et `data/emails_deja_envoyes.json` ne sont plus lus par l'application ; seuls `scripts/importer_contacts_historiques.py` (défauts de --source et --fichier, import ponctuel déjà fait) et un test de garde-fou du schéma de l'ancienne base (sauté si le fichier est absent) les citent. Ils peuvent être archivés.

### D200. Remise à zéro d'un utilisateur : scripts/remettre_a_zero.py
- `--utilisateur` obligatoire, lecture seule par défaut (base en `mode=ro`) : lignes et fichiers qui seraient effacés, table par table et mode par mode, et ce qui est gardé. Effacé, tous modes : `candidatures`, `offres_vues`, `entreprises`, `entreprises_modes`, PDF de `LETTRES_PDF_DIR/user_<id>/`. Gardé : tout le reste (profils et réglages, pièces jointes, compte et compteurs d'envoi, `emails_contactes`, fichiers partagés).
- Anti-doublon : l'envoi lit aussi `entreprises_modes.mail_destinataires`, effacé ici. Les adresses d'un envoi absentes de `emails_contactes` y sont recopiées, dans leur mode, avant l'effacement. Une candidature par le formulaire LBA n'a pas d'adresse : rien ne la retient, le script la compte.
- `--appliquer` refuse si l'application tourne (`main:app` ou `main.py` lancé depuis le projet) ou si un autre processus a la base ouverte, d'après `/proc` (absent : refus). Une seule transaction, `BEGIN IMMEDIATE` ; l'empreinte des lignes à garder (autres utilisateurs, tables gardées) est comparée avant et après l'effacement, et tout est annulé si elle change. Les PDF ne sont supprimés qu'ensuite (ni liens, ni autres fichiers) ; refus si `LETTRES_PDF_DIR` et `UPLOADS_DIR` se recouvrent.

### D201. Stage : champ « Ce que tu préfères éviter », envoyé au jugement
- Constat : en stage, `criteres_eviter` était admis comme preuve d'un « Hors sujet » (`CHAMPS_EXCLUSION`), mais n'était ni affiché dans « Mon profil » ni envoyé à l'IA.
- Même colonne qu'en alternance (pas de migration), propre au mode (jamais copiée). Profil, « Ce que tu cherches » : « Ce que tu préfères éviter ». Remplie, elle part dans le contexte du stage (« Préfère éviter », v1 et v2) et l'étape 1 du jugement v2 en fait un motif de hors sujet, comme en alternance ; vide, le prompt est inchangé.
- Mesure (4 offres RH, marketing, comptabilité, jugement seul, température 0,1, champ rempli en mémoire ; 2 passages, décision finale relevée au second) : « Hors sujet » 4/4, mais la phrase citée vient encore des missions visées 3 fois sur 4 et Python rétrograde ces 3 offres en « Faible ». Le champ ne suffit donc pas seul.

### D202. Stage : niveau minimal au-dessus de Bac+3 = inéligible
- Demande : stages de 1re ou 2e année, 3e au plus. En mode stage, si `niveau_detecte` (Python, borne basse d'une fourchette) dépasse Bac+3, exigé ou souhaité, l'offre est inéligible (« Bac+5 souhaité, Bac+3 au plus en stage »). Sans niveau écrit, rien ne bloque. Un profil déjà au-dessus de Bac+3 garde son propre niveau comme plafond. La règle d'avant (deux crans au-dessus, exigé) reste.
- Banc (27 stages) : 19 touchées, toutes annotées Bac+4 ou plus ; 12 déjà annotées inéligibles, 7 écartées en plus (dont la n° 13, Bien, et la n° 137, Moyen : accepté).

### D203. Stage : code métier ROME enregistré, hors informatique archivé
- `romeCode` est donné par l'API pour chaque offre (audit du 23/11 : 600/600 job, 56/56 alternance, 140/140 stage). Il est enregistré à la récupération dans `candidatures.code_rome` (migration 0018, vide pour les lignes existantes).
- Mode stage : code connu hors de M18, ou cartographie et météo (M1808, M1809, M1888, M1890, M1891, M1893), archivé sans IA avec la raison `hors_informatique` et la marque « Hors informatique (code métier) », filtrable dans les écartées. Gardée si l'intitulé contient un mot informatique entier ; code inconnu : gardée. Règle dans `shared/metiers_informatique.py`, appliquée à la récupération et avant l'analyse ; le bouton « Faire noter à nouveau » n'en dépend pas.
- Un profil de stage qui a choisi des domaines sans M18 n'est pas concerné ; avec M18 et d'autres domaines, ceux-ci sont gardés.
- Mesure sur les 50 offres de la base (codes lus sur les pages publiques à l'étape précédente, la base n'en avait pas) : 37 archivées, 13 gardées dont 7 par leur intitulé (trois offres « Développement RH » en profitent). Banc : 1 Hors sujet écarté (n° 123), aucun autre.

### D204. Règles Python avant l'IA
- Ordre : mots-clés et code métier, puis `raisons_sans_ia` (exigences structurées, niveau, niveau maximal en stage, diplôme préparé en alternance, durée et début en stage quand Python les lit seul), puis l'IA si l'offre reste éligible. Une offre écartée ainsi a le verdict `ineligible`, ses raisons dans « Ce qui coince », et pas de note (`score` vide, affiché « – »).
- Durée et début lus seulement dans une tournure sûre (« stage de 6 mois », « durée : 4 à 6 mois » : borne basse, « à partir de janvier 2027 ») ; une durée plus courte ailleurs, une souplesse (« flexible », « ou février ») ou un mois de la période du profil dans le texte laissent l'offre à l'IA.
- Banc (137 offres), règles Python seules : aucun faux inéligible en job (3 écartées) ni en alternance (5) ; en stage 19 écartées, dont les 7 de D202.
- Temps mesuré, les 50 offres de stage, une à une, hors base : avant 1 244 s (50 offres lues par l'IA, 24,9 s chacune) ; après 88 s (37 écartées par le code métier, 8 par les règles, 5 lues par l'IA, 17,7 s chacune). Codes métier fournis à la mesure : les 50 lignes de la base n'en ont pas. Sans eux, l'IA lirait 16 offres sur 50, qui ont pris 373 s dans la mesure « avant ». Profil modifié par l'utilisatrice entre les deux mesures (M18 recoché, « à éviter » rempli) : cela touche le prompt de jugement, pas les offres écartées.
- `analyser_offre(regles_d_abord=False)` pour les scripts qui mesurent le modèle (`verifier_ia_locale`, `tracer_niveau`) ; les bancs appellent directement la v2.

### D205. Champs de l'IA gardés jusqu'à la base
- `points_forts` n'était pas perdu : vide parce que le modèle n'en donne pas pour une offre hors sujet (vérifié sur la réponse brute). Un test couvre le trajet.
- `hors_sujet_car` était perdu entre la réponse et la base : gardé dans `candidatures.hors_sujet_car` (migration 0018), même quand Python rétrograde le Hors sujet en Faible ; « aucune » donne vide.
- Missions visées comme preuve de Hors sujet en stage : mesuré, **non codé** (condition non remplie). Profil du banc (M18, anciennes missions) : aucun changement (5 justes, 6 faux, moitié test 2 et 4). Profil actuel (domaines indifférents) : 0 gardé avant, après 5 justes et 11 faux (moitié test 2 et 6), dont le stage C++ (n° 17), le front-end (n° 137) et les stages cyber (n° 127, 130).

### D206. Description LBA : plafond IA_LONGUEUR_DESCRIPTION, coupure journalisée
- La récupération LBA coupait à 5 000 caractères en silence. Elle garde maintenant la description sous le plafond de l'IA (20 000 par défaut), et une coupure est journalisée. Les offres déjà en base ne changent pas.

### D207. Titre informatique : « développement » pas compté devant certains mots
- Complète D203 : « développement » ne compte pas s'il est suivi de « RH », « des ressources humaines », « commercial » (et ses accords), « business », « durable », « personnel » ou « des compétences ». Un autre mot informatique du titre garde toujours l'offre.
- Mesure sur les 50 offres de stage (codes des pages publiques) : 40 archivées au lieu de 37 ; les 3 « Développement RH » le sont, le stage simulateur reste gardé.

### D208. scripts/completer_codes_rome.py
- Offres France Travail sans `code_rome` : une requête à l'API par identifiant (lu dans le lien, vérifié contre `ref_offre`), seul `code_rome` est écrit. Lecture seule par défaut ; `--appliquer` refuse si l'application est lancée (avant et après les requêtes) et écrit en une transaction. Offre disparue (204, 404 ou 410), sans code, en erreur ou au lien d'un site partenaire : laissée telle quelle et comptée. Accès refusé : rien n'est écrit.
- Les codes de réponse d'une offre disparue n'ont pas été vérifiés sur la vraie API (identifiants non lus) : dans tous les cas le code reste vide.

### D209. Description France Travail : coupure journalisée
- La limite de 10 000 caractères reste ; pour chaque nouvelle offre coupée, une ligne dans le journal de la recherche (longueur et caractères gardés).

### D210. Une couleur d'accent par mode
- Alternance inchangée (#0F766E), stage violet (#534AB7), job terracotta (#993C1D). Valeurs dans `static/css/modes.css`, chargé par `base.html` et `auth_base.html` ; le reste du CSS n'utilise que les variables. Tableau et contrastes dans DESIGN.md.
- Plusieurs états empruntaient l'accent (note « Bien », ✓ « Ce qui colle », messages de réussite, « validée », « complet », confirmation de lancement). Ils ont leurs propres variables `--succes*`, vertes dans tous les modes.
- Champ `couleur` de `shared/modes.py` (bleu, orange, vert) supprimé, ainsi que dans la réponse de `/api/mode` : l'interface n'en lisait que le mode. La couleur d'un mode n'est plus écrite que dans `modes.css`.
- Remplace D143 sur ce point (« un seul accent vert »).

### D211. Job : niveau maximal demandé et expérience par domaine
- Deux réglages du profil job (« Ton parcours »), dans `profils.recherche` (pas de migration), appliqués avant l'IA (D204) puis à nouveau sur ce qu'elle extrait. Une offre déjà notée ne change pas sans « Faire noter à nouveau ».
- **Niveau maximal demandé par l'offre** (`niveau_max_offre`, sans limite par défaut) : niveau minimal demandé, exigé ou souhaité, au-dessus = inéligible, « Niveau demandé trop élevé ». Sans niveau écrit : passe. Lecture de `niveau_detecte` complétée pour le job (`niveau_minimal_job`) : CAP/BEP et « sans diplôme » comptent dans la borne basse (« CAP ou BTS » passe avec Bac), « 500 m2 » n'est plus un M2 ni « licence IV » une licence.
- **Niveau lu seulement dans une phrase de recrutement**, dans les trois modes (`_de_recrutement`) : mots de la demande (niveau, titulaire, diplômé, formation, profil, vous êtes ou avez, étudiant, requis, souhaité), plus exigé, obligatoire, indispensable, minimum, idéalement, « préparez », école, université, études, césure, nécessaires pour ne rien perdre ; ou ligne qui commence par le diplôme (« - BTS SIO »). Un diplôme objet d'une mission (examens, auditions, jury, scolarité, dossiers, brochures) est ignoré si rien ne s'adresse au candidat dans la phrase. `niveau_prepare` (D195) garde sa propre fenêtre. Comparaison avant et après : sur les 137 offres annotées, seule la n° 99 du job (Adjoint en scolarité) change ; sur les 107 stages de la base, `niveau_detecte` ne change pas. Modifie un test de D180 (même texte, plus lu du tout).
- **Mon expérience par domaine** (`experience_domaines`, domaine et mois). Offre qui exige de l'expérience : éligible si le domaine exigé est un des miens et la durée tenue dans ce domaine (« Expérience exigée dans un autre domaine », « Expérience exigée trop longue »), sans les 12 mois de D174. Domaine non précisé (rien, ou « poste similaire ») : celui de l'intitulé s'il est reconnu, sinon durée comparée au plus long de mes domaines. « Débutant accepté » et « souhaitée » passent, même si l'IA extrait une exigence. Un domaine écrit mais inconnu du référentiel est un autre domaine. « Expérience exigée » sans durée : seul le domaine compte.
- Liste remplie : remplace D174 en job, plafond Moyen compris. Liste vide : D174, sur `experience_mois`, gardé sans être affiché en job. Le champ reste affiché en stage et en alternance ; aucune règle ne l'y utilise.
- Domaine de l'offre : ligne France Travail (`experienceLibelle`), sinon `experience_exigee_domaine` (extraction v2), gardé seulement si le texte l'écrit tel quel près du mot « expérience ». Correspondance en Python par `shared/referentiels/domaines_experience.txt` (20 domaines, synonymes en mots entiers).
- Mesure, banc (100 offres job), Bac et relation client 3 mois, règles Python seules : textes tels quels, sans « (exigée) » (exportés avant D169), niveau 9 offres, expérience : seules les lignes « Expérience exigée » comptent. Lignes « N An(s) / N Mois » comptées exigées (audit du 23/11 : `experienceExige` vaut D ou E, jamais S) : niveau 9, expérience 36, ensemble 37 offres, dont 22 annotées éligibles. L'intitulé change la raison de 20 offres et en écarte 2 de plus par l'expérience (n° 62 Manutentionnaire ; n° 87 Gestionnaire de bases de données, déjà écartée par le niveau). Base : aucune offre job le 25/11, rien à mesurer.
- Extraction, `ministral-3:3b`, les 40 offres du banc qui exigent de l'expérience : éligibilité finale identique avec l'ancien et le nouveau prompt, 0 changement ; 1 offre écartée en plus après l'IA dans les deux cas (n° 88). Le modèle donne un domaine presque toujours, d'où le contrôle contre le texte (23 gardés sur 40). Un exemple dans le prompt était recopié : retiré. Stage et alternance non mesurés.
- Stage, règle mesurée, **non codée** (à décider) : expérience exigée supérieure à `experience_mois` (3) = inéligible. Banc (27 stages) : 0 écartée (« 0 An(s) » ou sans durée). Base (107) : 13 écartées (12 à « 1 An(s) », 1 à « 6 Mois »), toutes déjà archivées.

### D212. Stage et alternance : expérience exigée au-delà de celle du profil = inéligible
- Suite de la mesure de D211. En stage et en alternance, une offre qui exige plus que « Expérience professionnelle, en mois » est inéligible, « Expérience exigée trop longue », avant l'IA sur la ligne France Travail, puis sur ce qu'elle extrait. Débutant accepté, expérience souhaitée, « 0 An(s) » et « Expérience exigée » sans durée passent. Champ vide : pas de règle. Le job ne change pas (D211).
- Alternance : la règle des 2 ans (D169) reste pour un champ vide ou un profil de 2 ans et plus, sans doublon de raison.
- Après l'IA, une durée extraite qui n'est écrite que dans une phrase de souhait n'est plus comptée exigée (`texte_sans_souhait`, tous modes) : 0 changement sur les 68 extractions enregistrées du banc.
- Texte d'aide du champ : l'offre qui exige davantage est écartée ; vide, jamais pour ça.
- Vérification, profil à 3 mois. Stage (27) : 0 écartée. Alternance (10), textes tels quels : 0 avant l'IA ; lignes « (exigée) » remises : 4 écartées, dont 1 en plus des autres règles, la n° 8 (Technicien systèmes et réseaux, « 1 An(s) »), annotée Bien : **un faux écart** au regard de l'annotation, conforme à la règle. Son texte libre ne parle pas d'expérience. Après l'IA, 18 extractions enregistrées de stage et d'alternance : mêmes offres. Base : 13 stages sur 107, tous déjà archivés.
