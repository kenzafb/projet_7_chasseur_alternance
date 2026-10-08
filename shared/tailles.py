"""
shared/tailles.py
=================
Tailles d'entreprise proposées dans le profil (choix multiple), communes
aux offres France Travail (filtre après récupération, SPEC_SOURCES 2.3) et
aux candidatures spontanées (Sirene, SPEC_SOURCES 4.2).

Une tranche d'effectif (code INSEE « 12 » ou libellé « 20 à 49 salariés »)
est rangée dans la taille qui contient sa borne basse : les tranches INSEE
ne chevauchent jamais deux tailles.
"""

import re

TAILLES = [
    {"cle": "moins_10",  "libelle": "Moins de 10 salariés", "min": 0,    "max": 9,
     "avertissement": "moins de chances d'accueillir un alternant"},
    {"cle": "10_49",     "libelle": "10 à 49 salariés",     "min": 10,   "max": 49},
    {"cle": "50_249",    "libelle": "50 à 249 salariés",    "min": 50,   "max": 249},
    {"cle": "250_4999",  "libelle": "250 à 4999 salariés",  "min": 250,  "max": 4999},
    {"cle": "5000_plus", "libelle": "5000 salariés et plus", "min": 5000, "max": None},
]
CLES_TAILLES = [t["cle"] for t in TAILLES]

# Tranches d'effectif INSEE : code -> borne basse (NN : non renseigné)
TRANCHES_INSEE = {
    "00": 0, "01": 1, "02": 3, "03": 6, "11": 10, "12": 20, "21": 50, "22": 100,
    "31": 200, "32": 250, "41": 500, "42": 1000, "51": 2000, "52": 5000, "53": 10000,
}


def taille_depuis_effectif(effectif: int | None) -> str | None:
    if effectif is None or effectif < 0:
        return None
    for t in TAILLES:
        if t["max"] is None or effectif <= t["max"]:
            return t["cle"]
    return None


def taille_depuis_tranche(valeur) -> str | None:
    """Taille d'une tranche d'effectif, None si inconnue ou non renseignée.

    Accepte un code INSEE (« 12 »), un libellé (« 20 à 49 salariés »,
    « 1 ou 2 salariés », « 10 000 salariés et plus », « Moins de 10 »)
    ou un dict portant l'un des deux (clés code, libelle).
    """
    if isinstance(valeur, dict):
        return taille_depuis_tranche(valeur.get("code")) or taille_depuis_tranche(valeur.get("libelle"))
    if valeur is None or isinstance(valeur, bool):
        return None
    if isinstance(valeur, int):
        return taille_depuis_effectif(valeur)
    texte = str(valeur).strip()
    if texte in TRANCHES_INSEE:
        return taille_depuis_effectif(TRANCHES_INSEE[texte])
    # « 10 000 » ou « 10 000 » (espaces insécables) -> 10000
    texte = re.sub(r"(?<=\d)[\s  ](?=\d{3}\b)", "", texte)
    nombres = re.findall(r"\d+", texte)
    if not nombres:
        return None
    borne = int(nombres[0])
    if re.search(r"\bmoins\s+de\b", texte, re.I):
        borne = max(borne - 1, 0)
    return taille_depuis_effectif(borne)


def garder_selon_taille(taille: str | None, tailles: list[str], inconnue_ok: bool) -> bool:
    """tailles vide : toutes acceptées. Taille inconnue : selon inconnue_ok."""
    if not tailles:
        return True
    if taille is None:
        return inconnue_ok
    return taille in tailles
