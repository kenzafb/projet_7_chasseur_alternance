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
