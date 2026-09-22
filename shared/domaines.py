"""
shared/domaines.py
==================
Mapping des "grands domaines maison" vers les codes des deux APIs :
  - France Travail : un grand domaine (ex. "M18" = informatique)
  - La Bonne Alternance : une liste de codes ROME (ex. M1801..M1810)

Pour ajouter un domaine quand un nouvel utilisateur arrive :
  1. Trouver le grand domaine FT (lettre+chiffres, ex. "C15")
  2. Trouver les codes ROME associés (ex. C1501, C1502...)
  3. Ajouter une entrée ci-dessous.
"""

DOMAINES = {
    "informatique": {
        "label": "Informatique & Télécoms",
        "ft_grand_domaine": "M18",
        "lba_romes": [
            "M1801", "M1802", "M1803", "M1804", "M1805",
            "M1806", "M1807", "M1808", "M1809", "M1810",
        ],
        "naf": [
            "62.01Z", "62.02A", "62.02B", "62.03Z", "62.09Z", "63.11Z",
            "58.21Z", "58.29A", "58.29B", "58.29C",
            "61.10Z", "61.20Z", "61.90Z",
            "70.22Z", "71.12B", "74.90B",
        ],
    },
    "immobilier": {
        "label": "Immobilier",
        "ft_grand_domaine": "C15",
        "lba_romes": ["C1501", "C1502", "C1503", "C1504"],
        "naf": [
            "68.31Z",   # Agences immobilières
            "68.32A",   # Administration d'immeubles et autres biens immobiliers (syndic, gestion copro)
            "68.32B",   # Supports juridiques de gestion de patrimoine immobilier
            "68.20A",   # Location de logements
            "68.20B",   # Location de terrains et autres biens immobiliers
            "68.10Z",   # Marchands de biens immobiliers
            "41.10A",   # Promotion immobilière de logements (promoteurs)
        ],
    },
}

# Domaine par défaut si l'utilisateur n'a rien choisi (rétrocompat Kenza)
DOMAINE_DEFAUT = "informatique"


def labels_domaines() -> list[dict]:
    """Liste {cle, label} pour afficher les cases à cocher dans le profil."""
    return [{"cle": k, "label": v["label"]} for k, v in DOMAINES.items()]


def ft_grands_domaines(cles: list[str]) -> list[str]:
    """Grands domaines FT correspondant aux domaines choisis."""
    out = []
    for c in cles:
        d = DOMAINES.get(c)
        if d and d["ft_grand_domaine"] not in out:
            out.append(d["ft_grand_domaine"])
    return out or [DOMAINES[DOMAINE_DEFAUT]["ft_grand_domaine"]]


def lba_romes(cles: list[str]) -> list[str]:
    """Codes ROME LBA correspondant aux domaines choisis (dédupliqués)."""
    out = []
    for c in cles:
        d = DOMAINES.get(c)
        if d:
            for r in d["lba_romes"]:
                if r not in out:
                    out.append(r)
    return out or list(DOMAINES[DOMAINE_DEFAUT]["lba_romes"])


def naf_codes(cles: list[str]) -> list[str]:
    """Codes NAF correspondant aux domaines choisis (pour le fetch d'entreprises)."""
    out = []
    for c in cles:
        d = DOMAINES.get(c)
        if d:
            for n in d.get("naf", []):
                if n not in out:
                    out.append(n)
    return out or list(DOMAINES[DOMAINE_DEFAUT].get("naf", []))
