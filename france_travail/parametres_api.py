"""
france_travail/parametres_api.py
================================
Seul endroit qui dépend des points de l'API France Travail encore à
vérifier sur la vraie API (SPEC_SOURCES.md, section 7). Le reste du code
lit ces valeurs, sans rien supposer d'autre.

Pour les trancher, lancer (identifiants FT_CLIENT_ID et FT_CLIENT_SECRET
dans le .env) :

    venv/bin/python scripts/verifier_france_travail.py

puis reporter ici les valeurs que le script affiche à la fin.

Valeurs actuelles : choix prudents en attendant la vérification (une
requête par valeur ; c'est toujours juste, au prix de plus de requêtes).
"""

# Paramètre de recherche d'un grand domaine (lettre A à N). None : l'API
# n'en a pas, les lettres sont remplacées par leurs domaines.
PARAM_GRAND_DOMAINE = "grandDomaine"

# Paramètre de recherche d'un domaine (3 caractères : M18, C15).
PARAM_DOMAINE = "domaine"

# Nombre de valeurs acceptées dans une requête, séparées par des virgules,
# pour chaque paramètre à valeurs multiples. 1 : une requête par valeur
# (résultats réunis et dédoublonnés) ; None : sans limite.
VALEURS_PAR_REQUETE = {
    "natureContrat":   1,
    "typeContrat":     1,
    "grandDomaine":    1,
    "domaine":         1,
    "secteurActivite": 1,
    "theme":           1,
}

# Champ d'une offre qui porte la tranche d'effectif de l'établissement,
# en chemin pointé (« entreprise.trancheEffectif » pour un champ imbriqué).
# Valeur lue par shared.tailles.taille_depuis_tranche (code INSEE ou
# libellé). None : aucune offre n'a l'information, toutes sont « taille
# inconnue ».
CHAMP_TRANCHE_EFFECTIF = "trancheEffectifEtab"

# Début de la fenêtre de publication quand le découpage descend jusqu'aux
# dates (minCreationDate, maxCreationDate).
DATE_PLUS_ANCIENNE = "2000-01-01T00:00:00Z"


def valeurs_par_requete(param: str) -> int | None:
    """Valeurs acceptées par requête pour param (1 si le paramètre n'est pas listé)."""
    return VALEURS_PAR_REQUETE.get(param, 1)


def tranche_effectif(offre: dict):
    """Valeur brute de la tranche d'effectif d'une offre, None si absente."""
    if not CHAMP_TRANCHE_EFFECTIF:
        return None
    valeur = offre
    for cle in CHAMP_TRANCHE_EFFECTIF.split("."):
        if not isinstance(valeur, dict):
            return None
        valeur = valeur.get(cle)
    return valeur
