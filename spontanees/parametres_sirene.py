"""
spontanees/parametres_sirene.py
===============================
Seul endroit qui dépend des points de l'API Sirene (INSEE, version 3.11)
encore à vérifier sur la vraie API (SPEC_SOURCES.md, section 7). Le reste
du code lit ces valeurs, sans rien supposer d'autre.

Pour les trancher, lancer (clé INSEE_API_KEY dans le .env) :

    venv/bin/python scripts/verifier_sirene.py

puis reporter ici les valeurs que le script affiche à la fin.

Valeurs prudentes, NON VÉRIFIÉES (phase 5d, 9 octobre 2026) : celles de
la requête utilisée avant la phase (une valeur de NAF et un département
par requête, tranche lue sur l'unité légale), le reste rendu inoffensif
s'il est faux (voir chaque valeur).
"""

URL_RECHERCHE = "https://api.insee.fr/api-sirene/3.11/siret"
ENTETE_CLE = "X-INSEE-Api-Key-Integration"

# ─── Variables de la requête (syntaxe Lucene de l'API) ────────────────────────
# Code NAF de l'unité légale par nomenclature (shared.naf.nomenclature_naf).
# None pour NAF2025 : nom de la variable inconnu ; la recherche reste alors
# en NAF rév. 2 avec un message dans les logs (Sirene affiche les deux
# codes pendant 2026).
VARIABLE_NAF = {
    "NAFRev2": "activitePrincipaleUniteLegale",
    "NAF2025": None,
}
# Tranche d'effectif et catégorie d'entreprise, lues sur l'unité légale
# (SPEC_SOURCES 4.1 : la taille d'une agence se lit sur son groupe)
VARIABLE_TRANCHE = "trancheEffectifsUniteLegale"
VARIABLE_CATEGORIE = "categorieEntreprise"
VARIABLE_CODE_POSTAL = "codePostalEtablissement"

# Effectif inconnu : valeur « non renseigné » de la tranche. ABSENTS_PAR :
# clause qui ajoute les unités sans tranche du tout (None : non demandées,
# faute de syntaxe vérifiée ; elles sont alors perdues quand un filtre de
# taille est appliqué).
TRANCHE_NON_RENSEIGNEE = "NN"
ABSENTS_PAR = None

# Valeurs réunies par OU dans une requête. 1 : une requête par valeur
# (comme avant la phase).
NAF_PAR_REQUETE = 1
DEPARTEMENTS_PAR_REQUETE = 1

# ─── Pagination ───────────────────────────────────────────────────────────────
PAR_PAGE = 1000          # résultats par page (maximum documenté)
PAUSE_S = 0.5            # entre deux requêtes
ATTENTE_429_S = 10       # quota dépassé : pause puis nouvelle tentative
