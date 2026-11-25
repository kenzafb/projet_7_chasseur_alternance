# Refonte de l'interface du Chasseur

Référence visuelle : les fichiers `*.dc.html` de ce dossier (maquettes faites sur un canevas de design, styles en ligne). Ils servent de modèle de rendu : on ne les copie pas tels quels, on reproduit leur apparence et leur comportement dans les gabarits Jinja et le CSS de l'app.

Les fichiers `Main`, `Liste`, `Tableau` et `Synthese` sont des pistes écartées, gardées pour mémoire. Les écrans à reproduire sont : `Connexion`, `Accueil`, `Offres`, `Candidatures`, `Profil`, `Entreprises`, `Lettre`, `TelAccueil`, `TelOffres`.

## Direction

Simple et lisible pour quelqu'un qui ne vient pas de l'informatique. Une action principale (couleur du mode) par écran. Des phrases courtes au lieu de bandeaux d'explication. Aucun réglage technique visible dans les pages (nombre max d'offres, modèle d'IA, file de nuit) : ils vont dans Paramètres, section « Réglages avancés ».

## Jetons

- Police : Instrument Sans (Google Fonts), 400 à 700. Plus de Space Grotesk ni de JetBrains Mono.
- Fond de page #F7F8F7 ; surfaces #FFFFFF ; bordures #E2E6E5 ; bordures de champs et boutons secondaires #D7DDDB ; fond neutre #EEF1F0.
- Texte #17201F ; texte secondaire #56625F ; texte tertiaire #3E4846.
- Action et accent : une couleur par mode, voir « Couleur par mode ».
- Réussite (validé, enregistré, complet, « Ce qui colle », note « Bien ») : texte #0B5A54 sur #E3F1EF, marque #0F766E (`--succes`, `--succes-texte`, `--succes-fond`). Vert dans tous les modes.
- Attention (à relancer, à compléter) : texte #7A4A00 sur #FCEFD8.
- Refus : texte #8A2E2E sur #F3E8E8.
- Note : 6 et plus vert (#0B5A54 sur #E3F1EF, dans tous les modes), 4 et 5 ambre, moins de 4 neutre (#46504E sur #EEF1F0), toujours accompagnée d'un mot (Bien, Moyen, Faible).
- Rayons : 10 px boutons et champs, 12 à 14 px cartes de liste, 16 à 20 px panneaux. Ombres très légères ou aucune.
- Contraste texte au moins 4,5:1. Zones cliquables d'au moins 44 px sur téléphone.

## Couleur par mode

Pour voir d'un coup d'œil dans quel mode on est. Les valeurs sont écrites une seule fois, dans `static/css/modes.css` ; partout ailleurs, les variables.

| Variable | Usage | Alternance (vert d'eau) | Stage (violet) | Job (terracotta) |
|---|---|---|---|---|
| `--accent` | bouton principal, lien, focus, onglet actif, logo | #0F766E | #534AB7 | #993C1D |
| `--accent-survol` | survol, texte sur fond doux | #0B5A54 | #3C3489 | #712B13 |
| `--accent-doux` | fond pâle : étiquettes, compteurs, offre sélectionnée | #E3F1EF | #EEEDFE | #FAECE7 |
| `--accent-moyen` | survol d'un fond pâle | #CFE7E3 | #DEDCFB | #F5DCD2 |
| `--accent-bordure` | bordure et piste de jauge sur fond pâle | #C6E2DE | #CECBF6 | #F2CDBE |

- Le mode vient de `<html data-mode="…">`, posé par le serveur. Sans mode (connexion, inscription, choix du mode) : couleur de l'alternance.
- Sélecteur de mode et page de choix : chaque mode garde sa propre couleur (`data-mode-btn`, `data-mode-lien`).
- Ne changent jamais avec le mode : réussite, attention, refus, notes et verdicts, lettres (PDF et aperçu).

Contrastes mesurés (formule WCAG, 4,5:1 au moins pour le texte) :

| Texte sur fond | Alternance | Stage | Job |
|---|---|---|---|
| `--accent` sur blanc, et blanc sur `--accent` | 5,47 | 6,93 | 6,96 |
| `--accent` sur le fond de page #F7F8F7 | 5,14 | 6,51 | 6,53 |
| `--accent` sur le fond neutre #EEF1F0 (sélecteur) | 4,82 | 6,10 | 6,12 |
| `--accent` sur `--accent-doux` | 4,72 | 6,00 | 6,03 |
| `--accent-survol` sur blanc | 8,06 | 10,27 | 10,21 |
| `--accent-survol` sur `--accent-doux` | 6,95 | 8,89 | 8,86 |
| `--accent-survol` sur `--accent-moyen` | 6,22 | 7,70 | 7,80 |
| `--texte-2` sur `--accent-doux` | 5,47 | 5,50 | 5,51 |

## Navigation

- En-tête blanc : logo (carré arrondi à la couleur du mode, cible blanche) et « Chasseur » ; sélecteur Alternance / Job / Stage en pilule, chaque mode dans sa couleur, point sur le mode ouvert ; menu Accueil, Offres, Candidatures, Entreprises à contacter, Mon profil, avec compteurs sur ce qui attend ; rond aux initiales pour Mon compte (Paramètres, déconnexion).
- Plus de barre latérale sombre ni de statistiques dans le menu.
- Téléphone : barre d'onglets en bas (Accueil, Offres, Candidatures, Plus), sélecteur de mode en haut à droite.

## Écrans

1. Connexion : panneau vert à gauche (logo, phrase d'accroche), formulaire à droite, lien « Oublié ? » près du mot de passe, création de compte avec code d'invitation.
2. Accueil (nouvelle page d'arrivée de chaque mode) : salutation et dates, bloc « À faire » (offres bien notées, candidatures à relancer, offres à noter), chacun avec un bouton vers le bon écran ; à côté, « Ta recherche en bref » et l'avancement du profil.
3. Offres : liste à gauche et volet de détail à droite.
   - Onglets À voir, Gardées, Écartées (Écartées remplace l'archivage manuel ; les archivages automatiques restent consultables).
   - Offre jamais ouverte : titre en gras et point vert ; elle devient « vue » à l'ouverture (nouveau champ à stocker).
   - Volet : note et verdict, Ce qui colle, Ce qui coince, l'offre en bref, lien vers l'annonce ; boutons Préparer ma lettre, J'ai postulé, Garder pour plus tard, Pas pour moi.
   - Bandeau discret « N offres pas encore notées » avec bouton.
4. Candidatures : tableau de suivi en colonnes Envoyée, Relancée, Entretien, Réponse ; chaque carte a un bouton pour l'étape suivante, Acceptée ou Refusée dans la dernière colonne, « Revenir à l'étape d'avant ». Pas de glisser-déposer obligatoire.
5. Mon profil : 5 parties (Toi, Ton stage ou équivalent selon le mode, Ton parcours, Ce que tu cherches, Tes documents), état complet ou à compléter pour chacune, bouton Partie suivante, compétences en étiquettes. Le contenu de chaque partie dépend du mode.
6. Entreprises à contacter : trois étapes (Trouver des entreprises, Trouver leurs emails, Envoyer ta candidature) ; bandeau du mode essai ; onglets Prêtes à envoyer, Via La Bonne Alternance, Sans contact, Déjà contactées.
7. Ma lettre : page dédiée (ou grande fenêtre) avec le paragraphe modifiable à gauche, l'aperçu fidèle au PDF à droite, paragraphe surligné, Proposer une autre version, Enregistrer, Télécharger le PDF.

## Vocabulaire

Spontanées → Entreprises à contacter ; Analyser les offres en attente → Noter les offres ; Scraper → Trouver leurs emails ; Points forts / faibles → Ce qui colle / Ce qui coince ; Archiver → Pas pour moi ; Bounce → Adresse invalide.
