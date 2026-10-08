"""
france_travail/parametres_lba.py
================================
Seul endroit qui dépend des points de l'API de La Bonne Alternance encore
à vérifier sur la vraie API (SPEC_SOURCES.md, section 7). Le reste du code
lit ces valeurs, sans rien supposer d'autre.

Pour les trancher, lancer (clé LBA_API_KEY dans le .env) :

    venv/bin/python scripts/verifier_lba.py

puis reporter ici les valeurs que le script affiche à la fin.

Valeurs prudentes, NON VÉRIFIÉES (phase 5c, 8 octobre 2026) : celles que
le code utilisait avant la phase (romes par 20, rayon de 60 km, exclusion
de France Travail par partners_to_exclude), le reste tiré de la
documentation publique et rendu inoffensif s'il est faux (voir chaque
valeur).
"""

URL_RECHERCHE = "https://api.apprentissage.beta.gouv.fr/api/job/v1/search"

# ─── Paramètres de la recherche ───────────────────────────────────────────────
PARAM_CODES = "romes"          # codes métiers (ROME, 5 caractères), séparés par des virgules
PARAM_LATITUDE = "latitude"
PARAM_LONGITUDE = "longitude"
PARAM_RAYON = "radius"         # en kilomètres

# Codes métiers acceptés dans une requête (au-delà : plusieurs requêtes,
# résultats réunis et dédoublonnés). 20 : valeur utilisée avant la phase.
CODES_PAR_REQUETE = 20

# L'API accepte-t-elle une recherche sans code métier (profil « indifférent ») ?
# False : LBA est ignorée pour un profil sans domaine, avec un message.
ACCEPTE_SANS_CODES = False

# Rayon maximal accepté (km). Les rayons de shared.config.LBA_CENTRES y sont
# ramenés. 60 : valeur utilisée avant la phase.
RAYON_MAX_KM = 60

# Niveau de diplôme visé : paramètre et valeur envoyée pour chaque niveau
# européen (3 CAP, 4 bac, 5 bac+2, 6 bac+3 et bac+4, 7 bac+5). None : le
# niveau n'est jamais envoyé. Si l'API refuse la requête (400) avec ce
# paramètre, la recherche est refaite sans lui et le refus est écrit dans
# les logs : une valeur fausse ne coûte qu'une requête par lancement.
PARAM_NIVEAU = "target_diploma_level"
VALEURS_NIVEAU = {3: "3", 4: "4", 5: "5", 6: "6", 7: "7"}

# Offres déjà relayées depuis France Travail : exclues à la source par ces
# paramètres, puis par le libellé du partenaire (toute offre dont le
# partenaire contient l'un de ces textes, casse et accents ignorés, est
# écartée, même si l'API a ignoré l'exclusion).
PARAMS_EXCLUSION = {"partners_to_exclude": "France Travail"}
PARTENAIRES_FRANCE_TRAVAIL = ("france travail", "pole emploi")

# ─── Plafond ──────────────────────────────────────────────────────────────────
# Résultats au plus par source (partenaire d'offres, ou entreprises à fort
# potentiel) dans une réponse (SPEC_SOURCES section 3 : 150 par source, 450
# au total). Une source qui l'atteint est peut-être tronquée : la recherche
# passe alors aux centres de shared.config.LBA_CENTRES.
PLAFOND_PAR_SOURCE = 150

# ─── Structure des réponses ───────────────────────────────────────────────────
CLE_OFFRES = "jobs"
CLE_ENTREPRISES = "recruiters"   # entreprises à fort potentiel d'embauche

# Champ du libellé de partenaire d'une offre (chemin pointé)
CHAMP_PARTENAIRE = "identifier.partner_label"

# Champs d'une entreprise à fort potentiel : premier chemin pointé non vide.
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
