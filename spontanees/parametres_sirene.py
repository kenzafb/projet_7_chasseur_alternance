"""
spontanees/parametres_sirene.py
===============================
Seul endroit qui dépend des points de l'API Sirene (INSEE, version 3.11)
encore à vérifier sur la vraie API (SPEC_SOURCES.md, section 7). Le reste
du code lit ces valeurs, sans rien supposer d'autre.

Pour les trancher, lancer (clé INSEE_API_KEY dans le .env) :

    venv/bin/python scripts/verifier_sirene.py

puis reporter ici les valeurs que le script affiche à la fin.

Valeurs vérifiées sur la vraie API le 9 octobre 2026 (détail dans
docs/referentiels/insee/verification_api.json, décision D54).
"""

URL_RECHERCHE = "https://api.insee.fr/api-sirene/3.11/siret"
ENTETE_CLE = "X-INSEE-Api-Key-Integration"

# ─── Variables de la requête (syntaxe Lucene de l'API) ────────────────────────
# Code NAF de l'unité légale par nomenclature (shared.config.nomenclature_naf).
# activitePrincipaleNAF25UniteLegale filtre (19101 pour 62.10Y à Paris) et
# est rempli dans 100 réponses sur 100 dès 2026 ; les quatre autres noms
# essayés sont refusés.
VARIABLE_NAF = {
    "NAFRev2": "activitePrincipaleUniteLegale",
    "NAF2025": "activitePrincipaleNAF25UniteLegale",
}
# Tranche d'effectif et catégorie d'entreprise, lues sur l'unité légale
# (SPEC_SOURCES 4.1 : la taille d'une agence se lit sur son groupe)
VARIABLE_TRANCHE = "trancheEffectifsUniteLegale"
VARIABLE_CATEGORIE = "categorieEntreprise"
VARIABLE_CODE_POSTAL = "codePostalEtablissement"

# « NN » : unité non employeuse (aucun salarié dans l'année de référence
# ni au 31 décembre), documentation des variables Sirene ; 857 sièges sur
# 1000 à Paris en 62.01Z. Taille « sans salarié », pas un effectif inconnu
# (D55). Effectif inconnu : unité sans tranche du tout, ajoutée par
# ABSENTS_PAR ; syntaxe acceptée (404, aucun résultat : les 19717 unités de
# la référence ont toutes une tranche, 2819 connues + 16898 NN).
TRANCHE_SANS_SALARIE = "NN"
ABSENTS_PAR = "-trancheEffectifsUniteLegale:*"

# Valeurs réunies par OU dans une requête : OU exact (somme des valeurs
# seules) pour 2 et 10 codes, 120 codes acceptés, 250 refusés (414,
# en-tête trop long) ; deux départements exacts, les huit tiennent.
NAF_PAR_REQUETE = 120
DEPARTEMENTS_PAR_REQUETE = 8

# ─── Pagination ───────────────────────────────────────────────────────────────
# Toujours par curseur : « debut » est plafonné à 10000 (« valeur maximale
# pour le paramètre debut: 10000 »), le curseur n'a pas de limite.
PAR_PAGE = 1000          # résultats par page
PAUSE_S = 0.5            # entre deux requêtes
ATTENTE_429_S = 10       # quota dépassé : pause puis nouvelle tentative
