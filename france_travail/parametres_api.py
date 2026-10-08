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

Valeurs vérifiées sur la vraie API le 8 octobre 2026 (détail dans
docs/referentiels/france_travail/verification_api.json).
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
    "natureContrat":   2,   # E2,FS : OU des deux (3313)
    "typeContrat":     3,   # CDD,MIS,SAI : OU des trois (21642)
    "grandDomaine":    5,   # cinq lettres : OU (25474)
    "domaine":         1,   # liste refusée (400)
    "secteurActivite": 1,   # liste de cinq refusée : « 2 chaînes séparées par des virgules » (à revérifier)
    "theme":           1,   # liste refusée (400)
}

# Champ d'une offre qui porte la tranche d'effectif de l'établissement,
# en chemin pointé (« entreprise.trancheEffectif » pour un champ imbriqué).
# Valeur lue par shared.tailles.taille_depuis_tranche (code INSEE ou
# libellé). None : aucune offre n'a l'information, toutes sont « taille
# inconnue ».
CHAMP_TRANCHE_EFFECTIF = "trancheEffectifEtab"

# Fenêtre de publication du découpage (minCreationDate, maxCreationDate).
# Début : avant toute offre encore en ligne.
DATE_PLUS_ANCIENNE = "2000-01-01T00:00:00Z"
# Fin : maintenant plus cette marge. Le 8 octobre 2026, la fenêtre
# [2000, maintenant en UTC] ramenait 66709 offres sur 66929 : il manquait
# environ deux heures d'offres (17458 en 7 jours, soit une centaine par
# heure), l'écart de l'heure de Paris en été. L'API lit sans doute les
# dates en heure de Paris malgré le « Z ». Une marge d'un jour couvre tout
# décalage de fuseau ; scripts/verifier_france_travail.py le contrôle.
MARGE_FIN_FENETRE_HEURES = 24
# Plus petite fenêtre découpée : au-delà, la tranche est récupérée jusqu'au
# plafond et le reste signalé (une heure compte une centaine d'offres en IDF)
FENETRE_MIN_HEURES = 1


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
