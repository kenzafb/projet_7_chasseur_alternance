# Banc d'essai de l'IA (phase 15)

Rien ici ne modifie l'application ni la base : les exports ouvrent la base en lecture seule, les bancs n'écrivent que dans `audit_exports/` (ignoré par git).

## Étapes

1. Exporter (lecture seule) :
   `venv/bin/python scripts/banc_ia/exporter.py`
   produit `banc_offres_a_annoter.json`, `banc_emails_a_annoter.json` et `banc_lettres.json`.
2. Annoter à la main : remplir les blocs `attendu` (offres) et `attendu_valide` (emails), puis enregistrer sous `banc_reference.json` et `banc_emails_reference.json`.
3. Lancer les bancs :
   - analyse : `venv/bin/python scripts/banc_ia/banc_analyse.py audit_exports/banc_reference.json --essais 3 --temperatures 0,0.1`
   - lettre : `venv/bin/python scripts/banc_ia/banc_lettre.py audit_exports/banc_reference.json --max 10`
   - emails : `venv/bin/python scripts/banc_ia/banc_emails.py audit_exports/banc_emails_reference.json`
   - trace du niveau (sans IA, ou `--avec-ia`) : `venv/bin/python scripts/banc_ia/tracer_niveau.py --ids 13,119,12`

Pour comparer un modèle ou un prompt : `--modele <nom>`, `--prompt <fichier.py>` (le fichier définit `construire_messages(offre, profil, mode)` pour l'analyse, `construire_messages_paragraphe(offre, profil, mode, lettre_type)` pour la lettre, avec la signature de l'application).

## Format du jeu de référence des offres

```json
{
  "version": 1,
  "profils": {
    "1:stage": {"mode": "stage", "niveau_etudes": "Bac+2 (BUT Informatique, 2e année en cours)",
                "formation": "...", "missions": "...", "competences": ["..."], "recherche": {"domaines": ["M18"]},
                "date_debut": "2027-02-08", "date_fin": "2027-04-18", "duree_semaines": 10, "lettre_type": "..."}
  },
  "offres": [
    {
      "ref": "c7f4d4a4...", "id_base": 13, "mode": "stage", "profil": "1:stage",
      "source": "France Travail", "titre": "Stage Développeur Logiciel (H/F)", "entreprise": "...", "lieu": "...",
      "description": "texte complet de l'offre",
      "niveau_detecte": {"niveau": "bac+5", "exigence": "souhaite"},
      "niveaux_possibles_dans_le_texte": ["bac+4", "bac+5"],
      "app": {"score": 8, "verdict": "bon", "eligible": true, "statut": "envoye", "raison_archivage": "",
              "points_forts": ["..."], "points_faibles": ["..."], "domaine": "...", "resume": "..."},
      "attendu": {
        "eligible": false,
        "niveau_vise": "bac+5",
        "categorie": "Faible",
        "commentaire": "école d'ingénieur ou master : hors de portée d'un BUT2"
      }
    }
  ]
}
```

Le bloc `attendu` est le seul à remplir :

| Champ | Valeurs | Sens |
|---|---|---|
| `eligible` | `true`, `false`, `null` | La personne peut-elle candidater (niveau, durée, dates, alternance seulement) ? `null` : pas annotée. |
| `niveau_vise` | `bac`, `bac+2`, `bac+3`, `bac+4`, `bac+5`, `non_precise` | Niveau d'études que l'offre demande, d'après son texte (pas l'intitulé seul). |
| `categorie` | `Très bien`, `Bien`, `Moyen`, `Faible`, `Hors sujet` | Jugement d'ensemble pour ce profil. |
| `commentaire` | texte libre | Pourquoi, en une phrase. |

Correspondance avec l'application (`commun.categorie_du_resultat`) : inéligible ou note 0 à 2 = Hors sujet ; 3-4 Faible ; 5-6 Moyen ; 7-8 Bien ; 9-10 Très bien (mêmes seuils que `score_to_verdict`).

Les autres champs viennent de l'export et ne servent qu'à la lecture. On peut retirer des offres ou en ajouter (mêmes champs), et des profils fictifs.

## Format du jeu des emails

```json
{"version": 1, "emails": [
  {"entreprise_id": 18, "entreprise": "...", "site_web": "https://...", "url_scrapee": "https://...",
   "email": "contact@exemple.fr", "etat_app": "validee_regle", "contexte": "texte autour de l'adresse",
   "attendu_valide": true, "commentaire": "adresse de contact de l'entreprise"}
]}
```

`attendu_valide` : `true` si l'adresse permet de candidater auprès de cette entreprise, `false` sinon (autre organisme, annuaire, adresse technique, inventée). Les lignes de même `entreprise_id` forment une entreprise (un appel à l'IA). `scripts/audit_scraper.py mesure` produit aussi `emails_candidats.json` dans ce format, avec les adresses écartées par les règles.

## Mesures

- **Analyse** : exactitude de l'éligibilité, faux éligibles et faux inéligibles ; exactitude du niveau extrait (après contrôle Python) ; faux positifs de niveau (attendu Bac+4 ou plus, profil Bac+2 ou moins, éligible et note 7 ou plus) ; écart de rang moyen avec la catégorie attendue, part exacte, matrice de confusion ; écart type de la note sur les essais et offres dont la catégorie change ; temps par offre ; réponses invalides.
- **Lettre** : nombre de mots (consigne 60, maximum 80) ; part des phrases à la première personne ; tournures impersonnelles et inversion des rôles ; termes absents du profil, de l'offre et de la lettre type (indice de fait inventé, à relire) ; suites de 5 mots reprises de la lettre type ; markdown, tiret cadratin, esperluette, « expertise ».
- **Emails** : précision et rappel des règles seules, puis des règles avec l'IA, par essai ; faux positifs et faux négatifs nommés ; adresses dont la décision change d'un essai à l'autre.

## Ce que voit l'IA (phase 16, D189)

`voir_texte_ia.py` montre, pour chaque offre, le texte exact envoyé aux deux appels du prompt v2, la coupure de la description et le texte perdu. Base en lecture seule, `.env` jamais chargé en entier (seulement les `IA_*` avec `--analyser`). Exemple, les 5 offres de stage les plus longues, avec les deux appels :

    venv/bin/python scripts/banc_ia/voir_texte_ia.py --mode stage --offres 5 --analyser

Options : `--id` (une offre), `--user`, `--max-extraction`, `--max-jugement` (caractères lus par chaque appel), `--num-ctx` (remplace `IA_NUM_CTX` pour l'essai).
