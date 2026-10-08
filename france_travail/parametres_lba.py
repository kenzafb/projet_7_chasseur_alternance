"""
france_travail/parametres_lba.py
================================
Seul endroit qui dépend des points de l'API de La Bonne Alternance encore
à vérifier sur la vraie API (SPEC_SOURCES.md, section 7). Le reste du code
lit ces valeurs, sans rien supposer d'autre.

Pour les trancher, lancer (clé LBA_API_KEY dans le .env) :

    venv/bin/python scripts/verifier_lba.py

puis reporter ici les valeurs que le script affiche à la fin.

Valeurs vérifiées sur la vraie API le 9 octobre 2026 (détail dans
docs/referentiels/lba/verification_api.json, décisions D36 à D42).
"""

URL_RECHERCHE = "https://api.apprentissage.beta.gouv.fr/api/job/v1/search"

# ─── Paramètres de la recherche ───────────────────────────────────────────────
PARAM_CODES = "romes"          # codes métiers (ROME, 5 caractères), séparés par des virgules
PARAM_LATITUDE = "latitude"
PARAM_LONGITUDE = "longitude"
PARAM_RAYON = "radius"         # en kilomètres

# Codes métiers acceptés dans une requête (au-delà : plusieurs requêtes,
# résultats réunis et dédoublonnés). 100 codes acceptés, plus non essayé.
CODES_PAR_REQUETE = 100

# L'API accepte une recherche sans code métier : un profil « indifférent »
# cherche sur LBA sans code (décision D37).
ACCEPTE_SANS_CODES = True

# Rayon maximal accepté (km) : 201 refusé (« expected number to be <=200 »).
RAYON_MAX_KM = 200

# Niveau de diplôme : jamais envoyé à l'API (target_diploma_level filtre,
# mais écarte les offres sans niveau indiqué : 1 offre sur 3 au niveau 6).
# Filtre après récupération sur ce champ, offres sans niveau gardées (D38).
CHAMP_NIVEAU_OFFRE = "offer.target_diploma.european"

# Offres déjà relayées depuis France Travail : exclues à la source par ces
# paramètres, puis par le libellé du partenaire (toute offre dont le
# partenaire contient l'un de ces textes, casse et accents ignorés, est
# écartée). Le second filtre est indispensable : l'exclusion marche avec
# des codes métiers (28 offres France Travail retirées), mais une recherche
# sans code renvoie quand même 261 offres France Travail.
PARAMS_EXCLUSION = {"partners_to_exclude": "France Travail"}
PARTENAIRES_FRANCE_TRAVAIL = ("france travail", "pole emploi")

# ─── Plafond ──────────────────────────────────────────────────────────────────
# Résultats au plus dans une réponse : 150 par source (partenaire d'offres,
# ou entreprises à fort potentiel), 450 offres en tout (sans code : 150
# offres LBA + 261 France Travail + 39 autres = 450). Les entreprises sont
# à 150 sur presque tous les cercles (seul Cergy à 10 km en donne 98).
# Une réponse au plafond est peut-être tronquée : son cercle est redécoupé
# (france_travail.scraper_lba).
PLAFOND_PAR_SOURCE = 150
PLAFOND_TOTAL_OFFRES = 450

# ─── Structure des réponses ───────────────────────────────────────────────────
CLE_OFFRES = "jobs"
CLE_ENTREPRISES = "recruiters"   # entreprises à fort potentiel d'embauche

# Champ du libellé de partenaire d'une offre (chemin pointé)
CHAMP_PARTENAIRE = "identifier.partner_label"

# Champs d'une entreprise à fort potentiel : premier chemin pointé non vide.
# Sur 4148 entreprises lues : SIRET, nom, adresse, effectif (workplace.size,
# « 0-0 », « 6-9 »...), NAF et apply.url toujours présents ; aucun email ni
# téléphone (les entreprises passent par le scraper) ; apply.recipient_id
# dans 772 (identifiant de la candidature directe, gardé sans être branché).
CHAMPS_ENTREPRISE = {
    "siret":       ["workplace.siret"],
    "nom":         ["workplace.brand", "workplace.name", "workplace.legal_name"],
    "raison_sociale": ["workplace.legal_name"],
    "adresse":     ["workplace.location.address"],
    "effectif":    ["workplace.size"],
    "code_naf":    ["workplace.domain.naf.code"],
    "libelle_naf": ["workplace.domain.naf.label"],
    "site_web":    ["workplace.website"],
    "email":       ["apply.email", "contact.email", "workplace.email"],
    "telephone":   ["apply.phone"],
    "candidature_id":  ["apply.recipient_id"],    # identifiant de candidature directe (API non branchée)
    "candidature_url": ["apply.url"],
    "identifiant": ["identifier.id"],
}


def lire(objet, chemin: str):
    """Valeur d'un chemin pointé (« workplace.location.address »), None si absente."""
    valeur = objet
    for cle in chemin.split("."):
        if not isinstance(valeur, dict):
            return None
        valeur = valeur.get(cle)
    return valeur


def premier(objet, chemins: list[str]):
    """Première valeur non vide parmi des chemins pointés."""
    for chemin in chemins:
        valeur = lire(objet, chemin)
        if valeur not in (None, "", [], {}):
            return valeur
    return None
