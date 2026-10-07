# Phase 3 : un compte d'envoi par utilisateur, rapport

Branche `phase-3-mails`, créée depuis `refonte-multiuser` (9ca038d), 8 octobre 2026. Non poussée, non fusionnée.
Règles suivies : rien écrit dans `data/` ni dans `.env` (`.env` ni lu ni modifié, date 00:43, antérieure à la branche ; aucun `__pycache__` dans `data/`). Aucun appel réseau réel : SMTP, DNS, Mistral, FT, LBA et INSEE sont simulés ou coupés dans les tests. Schéma modifié uniquement par migrations Alembic. `compileall -x 'venv/|data/'` propre, `node --check` propre sur les 8 modules JS.

## 1. Commits

| Commit | Thème |
|---|---|
| 4c246f5 | Compte d'envoi : modèle, migration 0003, chiffrement Fernet, module SMTP, routes, section du profil |
| 2cf0fde | Envoyeur : compte de celui qui lance, refus avant lancement, plafond quotidien, arrêt sur erreur de compte |
| 23f578b | Dédoublonnage des adresses par mode, migration 0004 |
| 04dbff4 | Contenus génériques : objet et trame par mode (migration 0005), prompts neutres, préférences job tirées du profil |
| 954a0df | Test transversal du mot de passe ; libellés de la page spontanées sans « IT » |
| d2b1311 | Correctif SMTP trouvé par un test : nom d'hôte transmis à TLS |
| (dernier) | Ce rapport |

## 2. Ce qui change pour l'utilisateur

**Compte d'envoi (Profil, section 09).** Commun aux deux modes, une ligne par utilisateur (`comptes_envoi`). Deux choix : Gmail (`smtp.gmail.com`, 465, SSL, identifiant = adresse ; les espaces du mot de passe d'application sont retirés) ou « Autre serveur » (hôte, port 465 ou 587, chiffrement SSL ou STARTTLS cohérent avec le port, identifiant facultatif, défaut l'adresse). Aucun autre préréglage. Un encadré explique le mot de passe d'application Gmail et la validation en deux étapes. Le champ mot de passe n'est jamais prérempli ; l'état affiché est « configuré, vérifié le JJ/MM/AAAA à HH:MM », « configuré, pas encore vérifié » ou « aucun compte ». Boutons : Enregistrer et tester, Tester la connexion, M'envoyer un mail de test, Supprimer. Modifier un paramètre de connexion (adresse, serveur, port, chiffrement, identifiant, mot de passe) retire la vérification ; changer le nom affiché la garde. Enregistrer sans mot de passe garde l'ancien.

**Routes** (toutes derrière `utilisateur_requis`) :
- `GET /api/compte_envoi` : `{disponible, raison, compte, plafond_jour, envois_du_jour}`, `compte` sans aucun champ de mot de passe (seulement `mot_de_passe_configure`, `verifie`, `verifie_le`).
- `POST /api/compte_envoi` : enregistre (Pydantic, `extra="forbid"`, `SecretStr`), 400 lisible sur adresse, port, hôte ou mot de passe manquant.
- `POST /api/compte_envoi/supprimer` : possible même sans clé.
- `POST /api/compte_envoi/tester` : connexion, chiffrement, authentification, déconnexion, aucun mail. Répond `{ok, message, compte}` ; succès = `verifie_le` posé, identifiants refusés = vérification retirée, serveur injoignable = vérification conservée. La vérification n'est posée que si le compte n'a pas été modifié pendant le test.
- `POST /api/compte_envoi/mail_test` : uniquement vers l'adresse de connexion de l'utilisateur (défaut) ou l'adresse d'expédition du compte ; toute autre adresse, liste comprise, est refusée en 400. Compte dans le plafond du jour.

**Clé de chiffrement.** `CLE_CHIFFREMENT` relue à chaque usage. Absente ou invalide : l'app démarre (avertissement en console), la section affiche le message, et enregistrer, tester, mail de test et envoi répondent 503 `{"erreur": "Envoi de mails désactivé : ..."}`. Clé changée après coup : 400 « saisis-le à nouveau ».

**Serveurs refusés** (option autre serveur, revérifiés à chaque connexion) : `localhost`, `*.localhost`, et tout nom ou IP qui résout vers une adresse de bouclage, privée, de lien local, réservée, multicast, non spécifiée ou non globale (IPv4, IPv6, IPv4 mappée en IPv6), y compris si une seule des adresses résolues l'est. Nom introuvable ou mal formé : 400. Ports autres que 465 et 587 : 400. La socket est ouverte vers l'IP vérifiée (pas de seconde résolution DNS entre la vérification et la connexion) tandis que TLS vérifie le certificat pour le nom d'hôte. STARTTLS est exigé sur 587 : sans lui, abandon avant d'envoyer le mot de passe.

**Envoi des candidatures spontanées.** `spontanees/envoyeur.py` n'utilise que le compte vérifié de l'utilisateur qui lance ; `GMAIL_SENDER` et `GMAIL_APP_PASSWORD` ont disparu du code et de `.env.example`. Avant tout lancement, `/api/spontanees/envoyer` refuse : 400 sans compte, 400 compte non vérifié, 400 plafond du jour déjà atteint, 503 sans clé ; aucun thread n'est créé. La route transmet enfin le mode courant (profil, objet, trame, pièces jointes et dédoublonnage du mode). Le mode test envoie à l'adresse du compte. Les pièces jointes sont lues une fois par lancement. Le mail est construit avec `EmailMessage` (en-têtes `Date` et `Message-ID`, nom affiché encodé, objet ramené à une ligne : pas d'injection d'en-tête).

**Plafond quotidien.** `PLAFOND_ENVOIS_JOUR` (défaut 50, réglable dans `.env`), par utilisateur et par jour calendaire de `FUSEAU_AFFICHAGE`, tous lancements et mails de test confondus, en plus de la limite par lancement (toujours 50 au plus). Table `compteurs_envoi` ; chaque envoi réserve sa place par une seule requête `INSERT ... ON CONFLICT DO UPDATE ... WHERE nombre < plafond` (deux envois simultanés ne peuvent pas le dépasser), rendue si le serveur refuse le mail. En l'atteignant, le pipeline sauvegarde, journalise « Plafond de N mails par jour atteint : arrêt, les envois reprendront demain. » et s'arrête normalement. Le compteur survit à la suppression du compte d'envoi.

**Erreurs SMTP pendant un envoi.** Identifiants refusés : arrêt immédiat après la première tentative, compte marqué non vérifié, sauvegarde, message « Authentification refusée par ... Vérifie le compte d'envoi dans ton profil, puis relance « Tester la connexion ». », état du pipeline « Erreur envoi : ... ». Serveur injoignable, TLS en échec ou expéditeur refusé : arrêt aussi (inutile d'insister sur les entreprises suivantes), vérification conservée. Destinataire ou message refusé : échec compté, passage à l'entreprise suivante.

**Dédoublonnage par mode.** Une adresse contactée pour une alternance peut l'être pour un job, pas deux fois pour une alternance. `lire_emails_contactes` et `ajouter_emails_contactes` prennent le mode (obligatoire). `data/emails_deja_envoyes.json` n'est pas importé.

**Contenus.**
- Objet du mail : nouveau champ « Objet » dans la section Email (`profils.email_objet`, par mode). Vide : « Candidature spontanée en alternance » ou « Candidature spontanée ». Trame vide : texte par défaut du mode, sans année ni rentrée, signé avec prénom, nom, téléphone et email du profil (l'ancien défaut n'était pas signé).
- Trame de lettre par défaut par mode (`LETTRES_PAR_DEFAUT`) : le mode job n'évoque plus l'alternance ; formulations sans accord de genre (« Avec sérieux, implication et l'envie d'apprendre » au lieu de « Sérieux(se), impliqué(e) », « Un entretien serait l'occasion » au lieu de « Je serais ravi(e) »).
- Prompt de lettre : « personne candidate », consigne explicite d'écriture neutre, exemples réels (ORMA INFORMATIQUE, Linux et Docker, Garage Numérique, « rigoureuse et habituée ») remplacés par une structure à crochets et un exemple sans genre. Mêmes règles qu'avant (pas de « Je » en tête, 350 caractères, rien d'inventé, pas de superlatifs). En mode job, le bagage réel du profil est désormais fourni, avec la même interdiction de parler technique sauf demande explicite de l'offre.
- Prompt d'analyse job : plus de préférence écrite en dur (jobs calmes, surveillance, gardiennage, billetterie, arrondissement préféré, téléconseil). Le critère n°1 devient l'adéquation aux préférences du profil (types de jobs acceptés et à éviter, disponibilité horaire, mobilité, durée, localisation, et les domaines préférés, qui n'étaient pas transmis jusqu'ici), avec consigne de n'en appliquer aucune autre. Barème 1 à 10, exigence de discrimination, règles de durée, localisation et accessibilité conservées ; ajout d'une règle sur les horaires et d'un repli quand le profil n'exprime aucune préférence.
- PDF : « Paris, le » devient « <ville du profil>, le » (ou « Le » sans ville) ; l'objet « Candidature, Alternance » par défaut devient « Candidature ».
- CLI : `--mode alternance|job` ajouté à l'envoyeur (défaut alternance, la ligne cron reste valide).

**Réponses 422.** Le gestionnaire commun ne renvoie plus `input` ni `ctx` dans `detail` (sinon un mot de passe mal formé, ou un champ en trop, aurait été renvoyé tel quel).

## 3. Migrations

| Révision | Contenu | Données existantes |
|---|---|---|
| 0003 | tables `comptes_envoi` (user_id UNIQUE, FK CASCADE, `mot_de_passe_chiffre` TEXT, `verifie_le`, `modifie_le`) et `compteurs_envoi` (UNIQUE user_id, jour) | aucune touchée |
| 0004 | `emails_contactes.mode` NOT NULL défaut `alternance` ; `uq_emails_contactes_user_id_email` remplacée par `uq_emails_contactes_user_id_mode_email` | lignes existantes en mode alternance ; le downgrade garde la plus ancienne ligne par (user, adresse) |
| 0005 | `profils.email_objet` VARCHAR(300) nullable | NULL, lu comme vide |

Autogénérées puis relues, mode batch. Vérifié en ligne de commande sur base temporaire : `upgrade head`, `alembic check` « No new upgrade operations detected », `alembic current` = `0005 (head)`, downgrade 0004 vers 0003 puis upgrade. `cryptography==46.0.6` ajouté à `requirements.txt` (déjà présent dans `venv/` comme dépendance).

## 4. Le mot de passe : où il passe

Saisi dans un champ `password` (`autocomplete="new-password"`), reçu en `SecretStr`, chiffré par Fernet avant le `commit`, déchiffré seulement par `compte_pour_envoi` pour `login()`. Aucune route ne le renvoie, aucun message n'est construit à partir d'une exception SMTP : chaque cas a son message écrit dans `shared/smtp.py` ; le seul texte serveur relayé (message refusé après DATA) est nettoyé du mot de passe en clair, en base64, et de la forme `\0identifiant\0mot de passe` d'AUTH PLAIN. Les tests utilisent un faux serveur dont les erreurs contiennent volontairement le mot de passe reçu.

## 5. Tests

Commande : `systemd-run --user --scope -p MemoryMax=2G venv/bin/python -m pytest -q`. Résultat : **246 passed** en 22 s, aucun avertissement (151 avant la phase, tous toujours verts). Adaptés : `test_dedoublonnage` (fixture d'envoi sur le faux SMTP avec comptes vérifiés, signature des fonctions de dédup avec mode), `test_schema` (la migration 0002 se compare à la tête courante au lieu de « 0002 »). `conftest.py` coupe aussi `socket.getaddrinfo` et fournit `FauxDNS`, `FauxServeurSmtp`, `cle_chiffrement`, `smtp_simule`, `compte_verifie`.

| Fichier | Couvre |
|---|---|
| `test_compte_envoi.py` (61) | chiffrement aller-retour, sel aléatoire, clé changée ; app qui tourne et 503 sans clé, avec clé vide ou invalide ; mot de passe absent des réponses et de la base en clair, espaces Gmail retirés, requis à la création puis conservé ; 422 sans mot de passe dans la réponse ; adresses invalides (dont injection de `Bcc`) ; isolation A/B ; suppression ; connexion réussie (IP vérifiée, TLS, aucun mail), STARTTLS, mauvais identifiants (sortie et logs sans mot de passe), serveur injoignable, échec d'authentification qui retire la vérification, modification qui la retire, configuration modifiée pendant le test non validée ; mail de test refusé vers trois autres adresses, accepté vers soi, en-têtes ; plafond appliqué au mail de test et rendu en cas d'échec ; sans compte ; 18 hôtes interdits (localhost, 127.0.0.1, 10.x, 172.16.x, 192.168.x, 169.254.x, 0.0.0.0, ::1, [::1], ::ffff:127.0.0.1, fe80::1, fd00::1, 100.64.x, multicast, réservé...) ; 6 noms qui résolvent vers une adresse interdite ; introuvable et mal formé ; 8 ports hors liste ; cohérence port et chiffrement ; DNS qui change après l'enregistrement ; préréglage Gmail qui ignore un serveur fourni ; balayage complet d'un mot de passe à travers tous les parcours et un pipeline arrêté ; vraie classe de connexion sans réseau (IP épinglée, certificat vérifié pour le nom d'hôte en SSL et en STARTTLS) |
| `test_envoyeur.py` (14) | A envoie avec ses identifiants et son adresse, jamais ceux de B, puis B avec les siens ; mode test vers l'adresse du compte ; plus aucune variable GMAIL dans le code ; refus sans compte, sans compte vérifié, sans clé (route et fonction, aucun thread, aucune connexion) ; lancement par la route avec le profil du mode courant ; plafond respecté sur deux lancements, arrêt journalisé, lancement suivant refusé, B non bloqué ; remise à zéro le lendemain ; défaut 50 et réglage par l'environnement ; arrêt propre sur erreur d'authentification (une seule tentative, rien de perdu, compteur rendu, logs sans mot de passe), y compris par la route ; arrêt sur serveur injoignable ; destinataire refusé puis entreprise suivante |
| `test_contenus.py` (12) | prompts de lettre et d'analyse des deux modes sans mention d'un utilisateur réel, sans accord imposé, sans année ; prompt de lettre neutre et fondé sur le bagage du profil ; analyse job qui contient chaque préférence du profil et plus aucune préférence en dur ; trames par défaut génériques, mode job sans alternance ; lettre générée avec la trame du mode ; lettre type du profil prioritaire ; objet et corps du profil, défauts signés ; objet du profil dans le mail réellement envoyé, sans en-tête injecté ; PDF sans lieu ni objet en dur ; code actif sans nom d'utilisateur réel |
| `test_dedoublonnage.py` (+2) | adresse acceptée en job après l'alternance, ignorée une seconde fois en alternance, en base et par l'envoyeur |
| `test_schema.py` (+1) | base en 0003 avec une adresse contactée montée en 0004 : mode alternance, unicité par mode, downgrade qui dédoublonne |

Autres vérifications : `uvicorn main:app --port 5099` sur base temporaire migrée, sans clé : démarrage avec l'avertissement, `/login` 200, `/api/compte_envoi` 401, `/static/js/compte_envoi.js` 200. Parcours dans un vrai navigateur et envoi réel non faits (aucun appel réseau autorisé).

**Défaut trouvé et corrigé par les tests (d2b1311).** `smtplib` ne pose le nom d'hôte (`_host`) que dans son constructeur. La connexion épinglée, construite sans hôte, aurait donc vérifié le certificat sans nom de serveur : en production, SSL comme STARTTLS auraient échoué à chaque connexion. Le faux serveur ne pouvait pas le voir ; le test sur la vraie classe l'a montré (il échoue sans le correctif).

## 6. Mentions propres à un utilisateur réel

Retirées du code actif : commentaires « rédigé par Kenza », « pas seulement Kenza », « rétrocompat Kenza », « DEUST Info » (`generateur.py`, `profil_db.py`, `domaines.py`, `models.py`) ; trame de mail « rentrée 2026 » ; exemples du prompt de lettre (ORMA INFORMATIQUE, Linux et Docker, Garage Numérique, « candidate », « rigoureuse et habituée ») ; préférences personnelles du prompt job ; « Paris, le » du PDF ; placeholders du profil (Kenza, Filali-Bouami, Paris 9e, DSP DevOps CNAM, DEUST IOSI, Garage Numérique, Bac+1 DevOps CNAM, septembre 2026, Windows/Active Directory, Java et POO, Linux et Docker, relation client télécom, Paris 9e de préférence) ; placeholder « Grabber » (nom d'un projet) dans `profil.js` ; « entreprises IT » de la page spontanées et du message de fetch (les codes NAF viennent des domaines du profil).

Restent, hors code actif ou sans lien avec une personne : `shared/profil.example.py` (fichier mort, gabarit générique avec « septembre 2026 ») ; `shared/profil.py` (non suivi, ignoré par git, plus lu) ; `archive/telegram_bot.py` ; `docs/` (rapports, état des lieux avec noms et emails) ; `tests/donnees/ancien_schema.sql` ; titre « Chasseur d'Alternance » de l'app et du gabarit `base.html` ; liste d'écoles et CFA de l'analyseur et géographie Île-de-France (choix du produit, pas d'une personne). `data/` n'a pas été parcouru.

## 7. Limites restantes

1. **Entreprises toujours communes aux deux modes.** Le fetch les crée en mode alternance et l'envoyeur les lit toutes ; `mail_envoye` est porté par l'entreprise. Une entreprise déjà contactée en alternance n'est donc jamais reproposée en job, même si son adresse le permettrait. Le dédoublonnage par mode ne joue que pour une même adresse partagée par plusieurs entreprises. Rendre `entreprises` vraiment par mode (fetch, stats, suivi, envoyeur) est un chantier à part.
2. Aucune limite de fréquence sur « Tester la connexion » : un utilisateur qui insiste avec de mauvais identifiants peut faire bloquer son compte par son fournisseur.
3. Gmail seul en préréglage ; un compte Google Workspace dont l'administrateur interdit les mots de passe d'application ne pourra pas envoyer. Pas d'OAuth.
4. Rotation de clé non prévue (pas de `MultiFernet`) : changer `CLE_CHIFFREMENT` oblige chacun à ressaisir son mot de passe. Perdre la clé a le même effet.
5. Connexion vers la première IP vérifiée seulement, sans repli sur les suivantes. L'EHLO annonce le nom de la machine (`getfqdn`).
6. Le compteur rend la place d'un mail refusé ; une coupure réseau pendant la transmission du message (mail peut-être parti) la rend aussi.
7. Mail de test autorisé vers l'adresse de connexion, qui n'est pas vérifiée à l'inscription (inscription sur invitation).
8. La section Lettre type n'est visible qu'en mode alternance : en mode job, seule la trame par défaut sert.
9. Les prompts d'analyse disent « le candidat » (masculin générique, sans effet sur les textes produits pour l'entreprise).
10. Hérité : threads et états en mémoire, perdus au redémarrage ; pas de limitation de débit sur `/login` ; pas de jeton CSRF.

## 8. À faire par l'humain

Après relecture et fusion de la branche, application arrêtée :

```bash
cd /home/kenza/Bureau/chasseur_alternance
source venv/bin/activate
pip install -r requirements.txt                          # cryptography (déjà dans venv/)
venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Dans `.env` :
- ajouter `CLE_CHIFFREMENT=<la clé affichée>` et la sauvegarder hors du serveur (sans elle, les mots de passe enregistrés sont perdus) ;
- retirer `GMAIL_SENDER=` et `GMAIL_APP_PASSWORD=` (plus lues ; le mot de passe d'application qui y figure peut être révoqué dans le compte Google une fois le nouveau compte d'envoi configuré) ;
- facultatif : `PLAFOND_ENVOIS_JOUR=50`.

Migration (si `DATABASE_URL` est déjà dans `.env`, le préfixe est inutile ; si la migration 0002 de la phase 2b n'a pas encore été appliquée, elle l'est au passage) :

```bash
cp data/chasseur_v2.db data/chasseur_v2_avant_phase3.db
DATABASE_URL=sqlite:////home/kenza/Bureau/chasseur_alternance/data/chasseur_v2.db alembic upgrade head
DATABASE_URL=sqlite:////home/kenza/Bureau/chasseur_alternance/data/chasseur_v2.db alembic current   # attendu : 0005 (head)
```

Puis chaque utilisateur configure son compte dans Profil, section Compte d'envoi, et clique « Enregistrer et tester » (Gmail : validation en deux étapes puis mot de passe d'application). La ligne cron `python -m spontanees.envoyeur --limite 50 --user 1` reste valide, mais échouera tant que le user 1 n'a pas de compte vérifié ; ajouter `--mode job` pour envoyer avec le profil job.

## 9. Points à valider

1. **Recontact d'entreprises (déjà signalé en 2b, toujours vrai).** Conformément à la consigne, `data/emails_deja_envoyes.json` (1085 adresses) n'est pas importé : le user 1 peut réécrire à des entreprises déjà contactées. Si la reprise est décidée, la signature a changé : `ajouter_emails_contactes(1, "alternance", adresses)`.
2. Plafond par défaut de 50 par jour : même valeur que le maximum par lancement, donc un cron quotidien de 50 passe encore, mais deux lancements le même jour non.
3. Arrêt aussi sur serveur injoignable ou expéditeur refusé, et pas seulement sur refus d'authentification.
4. Mail de test permis vers l'adresse de connexion ou l'adresse d'expédition (deux adresses de l'utilisateur), rien d'autre.
5. 503 pour l'absence de clé (problème de serveur), 400 pour l'absence de compte ou de vérification.
6. Mode job : bagage du profil ajouté au prompt de lettre, et domaines préférés ajoutés au contexte d'analyse.
7. Réponses 422 désormais sans `input` ni `ctx` pour toutes les routes.
8. Le compte d'envoi est unique pour les deux modes ; l'objet et la trame du mail, eux, sont par mode.
9. Ensuite : relire la branche, la fusionner dans `refonte-multiuser`, appliquer la section 8, pousser.
