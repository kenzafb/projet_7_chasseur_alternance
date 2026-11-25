# Architecture actuelle : le Chasseur

État au 25 novembre 2026, après les phases 15 et 16 et le ménage (branche `menage`). L'état des lieux du 7 octobre, d'avant la refonte, est dans `docs/historique/ARCHITECTURE_2026-10-07.md`. Les raisons de chaque choix sont dans `docs/DECISIONS.md` (D1 à D209).

## 1. En bref
- Application web FastAPI multi-utilisateurs : `venv/bin/uvicorn main:app --port 5002`. Pages Jinja et modules JavaScript, sans framework.
- Trois modes par utilisateur : alternance, job et stage. Chaque mode a son profil, ses offres, ses entreprises et son suivi.
- Base SQLite par SQLAlchemy 2, schéma tenu par Alembic (migrations 0001 à 0018). Les données hors dépôt sont dans `DATA_DIR` (défaut `data/`).
- IA locale par Ollama (`ministral-3:3b` pour l'analyse et les emails, `ministral-3:8b` pour la lettre) ; un serveur compatible OpenAI est possible (`IA_API`).

## 2. Arborescence
```
main.py                 Application : middlewares (session, contrôle de l'origine), routeurs, pages d'erreur
auth/                   Connexion, inscription par code d'invitation, mot de passe (hash, temporaire), compte
routes/                 Un routeur par page : accueil, offres, analyse, candidatures, lettre, profil,
                        spontanees, parametres, pages, documentation ; commun.py (gabarits, pipelines, mode)
database/               models.py (schéma), connexion.py, couches d'accès par table (*_db.py),
                        dates.py (UTC en base, Paris à l'affichage), schema.py (alembic depuis Python)
offres/                 Recherche d'offres et analyse par l'IA
  france_travail.py       API Offres d'emploi v2, critères du profil (shared/criteres.py)
  la_bonne_alternance.py  Offres LBA (mode alternance), pages_lba.py (liens de candidature fiables)
  export_lba.py           Export complet LBA lu en flux, cache gz compact, rafraîchi chaque semaine (D163)
  recherche.py            Pipeline de recherche : offres insérées « non analysées »
  analyse.py              Règles communes, prompt v1, éligibilité appliquée, marques
  analyse_v2.py           Prompt v2 : extraction sans le profil puis jugement en un mot (D170, D193, D194)
  analyse_differee.py     Analyse des offres en attente, dans un thread
  parametres_*.py         Seuls endroits qui dépendent des points vérifiés sur les vraies API
lettres/                redaction.py (paragraphe écrit par l'IA dans la lettre type), pdf.py (WeasyPrint)
spontanees/             Candidatures spontanées
  recuperation.py         « Trouver des entreprises » : export LBA puis Sirene (cœurs, secteurs, transverses)
  site_officiel.py        Identification du site : déjà vérifié, Wikidata, LBA, offres, domaines devinés, recherche web
  wikidata.py             SIREN (P1616) -> site officiel (P856), par lots (D188)
  recherche_emails.py     « Trouver leurs emails » : moteurs ddgs avec repli (D187), lecture du site, page carrières (D191)
  lecture_site.py         Lecture polie d'un site : robots.txt, liens réels, sitemap, 8 pages au plus
  noms_entreprise.py      Autres noms et dénomination de l'unité légale (annuaire Recherche d'entreprises, D167, D192)
  envoi.py                Envoi des candidatures par le compte SMTP de l'utilisateur, plafond quotidien
shared/                 Règles sans IA et outils communs
  config.py               .env, dossiers (DATA_DIR, UPLOADS_DIR, LETTRES_PDF_DIR), réglages IA
  ia.py                   Client d'IA unique : schéma JSON imposé, num_ctx, compteurs de tokens (D189)
  eligibilite.py          Niveau, durée, dates, diplôme préparé en alternance (D178, D195)
  exigences.py            Permis, expérience, certifications, diplôme d'État lus dans les champs structurés (D169)
  validation_emails.py    Tri des adresses : règles d'abord, l'IA seulement pour les douteuses
  naf.py, domaines.py     Domaines du profil -> codes NAF Sirene ; origine d'une entreprise (D190)
  marques.py              Étiquettes des offres (niveau différent, organisme de formation, description longue)
  metiers_informatique.py  Stage : code métier ROME hors informatique (D203)
  referentiels/           Données versionnées : correspondance NAF, domaines interdits, métiers de conduite...
templates/, static/     Pages Jinja (partials par page) ; JS en modules ES, un par page ; CSS en trois fichiers
alembic/                Migrations 0001 à 0018
scripts/                Outils lancés à la main, jamais par l'application
  audit_*.py, mesurer_*.py  Mesures de la phase 15 et 16 (lecture seule, sorties dans audit_exports/)
  banc_ia/                Bancs de l'IA (analyse, emails, lettre), voir_texte_ia.py
  verifier_*.py, explorer_france_travail.py  Vérification des API ; sorties dans scripts/verifications/
  references/             Références annotées sans donnée personnelle (scraper_reference.json)
  *.py de maintenance     Lecture seule par défaut, --appliquer pour écrire (revalider_emails_en_base,
                          completer_denominations, renommer_pieces_jointes, deplacer_lettres_pdf, remettre_a_zero,
                          completer_codes_rome...)
tests/                  pytest, sous systemd-run MemoryMax=2G ; aucun appel réseau ni à la vraie base
docs/                   DECISIONS.md, CONFIGURATION.md, SPEC_SOURCES.md, RECETTE.md, ce fichier,
                        referentiels/ (référentiels France Travail et table NAF de l'INSEE, lus par le code),
                        historique/ (rapports de phase, guides de fusion, ancien état des lieux)
```

Hors dépôt (ignorés par git) :
- `data/` : base `chasseur_v2.db`, `uploads/user_<id>/` (pièces jointes), `lettres_pdf/user_<id>/` (D197), cache de l'export LBA ;
- `audit_exports/` : sorties des mesures, références à données personnelles, `archives/` ;
- `.env` : secrets et réglages (modèle : `.env.example`, documenté dans `docs/CONFIGURATION.md`).

## 3. Base de données
Tables :
- `users` ;
- `profils`, un par utilisateur et mode, avec `recherche` en JSON : critères, permis, expérience en mois, certifications, `inclure_transverses` ;
- `candidatures` : offres, avec `marques` en JSON ;
- `entreprises` et `entreprises_modes` ; `extra` en JSON contient site vérifié, autres noms, dénomination, page carrières, formulaires ;
- `offres_vues` et `emails_contactes` : dédoublonnage par utilisateur ;
- `comptes_envoi` (mot de passe SMTP chiffré) et `compteurs_envoi`.

Toute requête filtre par `user_id`. Les chemins de fichiers sont stockés relativement à leur dossier (`UPLOADS_DIR`, `LETTRES_PDF_DIR`).

## 4. Flux principaux
- **Offres** : France Travail, plus LBA en alternance → filtres sans IA (zone, intitulés de stage, organismes de formation) → insertion « non analysée » → analyse différée.
- **Analyse v2** :
  - extraction sur la description entière, sans le profil ;
  - jugement en un mot, avec le profil ;
  - même `num_ctx` (4 096) pour les deux appels ;
  - Python décide ensuite l'éligibilité (exigences, niveau, diplôme préparé), la note et les plafonds.
- **Candidatures spontanées** :
  1. Trouver des entreprises : export LBA, puis Sirene.
  2. Trouver leurs emails : site vérifié (Wikidata en premier, recherche web en dernier, arrêt après 5 échecs d'affilée), puis lecture polie du site. Les adresses passent les règles, puis l'IA si elles sont douteuses. La page carrières est notée pour les grandes entreprises.
  3. Envoyer : compte SMTP de l'utilisateur, mode essai, plafond quotidien.
- **Lettre** : lettre type du profil avec balises ; l'IA écrit le paragraphe personnalisé (2 000 caractères de description) ; PDF WeasyPrint.

## 5. Phases 15 et 16 en une ligne chacune
- **Phase 15** :
  - audit des sources et du scraper ;
  - export LBA complet et Sirene hors siège ;
  - site vérifié avant tout email ;
  - prompt v2 ;
  - exigences sans IA (permis, expérience, certifications, métiers de conduite) ;
  - bancs de l'IA en deux moitiés fixes.
- **Phase 16** :
  - profil « Ton parcours » réparé ;
  - revalidation des emails en tout ou rien ;
  - moteurs de recherche avec repli, puis Wikidata ;
  - l'IA lit la description entière, et ce qu'elle voit est mesurable (`voir_texte_ia.py`) ;
  - origine des entreprises, page carrières des grandes entreprises, dénomination de l'unité légale ;
  - diplôme préparé lu par Python.
- **Ménage** :
  - références versionnées sans donnée personnelle ;
  - lettres PDF dans `DATA_DIR` ;
  - noms de pièces jointes sans répétition ;
  - `audit_exports/` et `docs/` rangés.
