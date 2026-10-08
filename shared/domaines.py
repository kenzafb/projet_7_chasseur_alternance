"""
shared/domaines.py
==================
Domaines recherchés d'un profil, dans la nomenclature de France Travail
(SPEC_SOURCES.md, section 1) :
  - 14 grands domaines, une lettre (« M » Support à l'entreprise) ;
  - 110 domaines, 3 caractères (« M18 » Systèmes d'information et de
    télécommunication), dont la lettre est celle du grand domaine.

Stockage dans le profil : liste de codes, recherche.domaines = ["M18"],
["C"], ou [] pour « indifférent ». Les listes viennent des référentiels
versionnés (shared.referentiels), jamais du code.

LBA et Sirene ne sont pas encore passés à ce modèle (phases 5c et 5d) :
leurs correspondances d'avant la phase 5b sont gardées telles quelles,
rangées sous les nouveaux codes (lba_romes, naf_codes).
"""

from functools import lru_cache

from shared import referentiels

# Clés des domaines écrits à la main avant la phase 5b (migration 0007)
ANCIENNES_CLES = {"informatique": "M18", "immobilier": "C15"}


@lru_cache(maxsize=1)
def _arbre() -> tuple:
    domaines = referentiels.france_travail("domaines")
    return tuple(
        {"code": g["code"], "libelle": g["libelle"],
         "domaines": [dict(d) for d in domaines if d["code"].startswith(g["code"])]}
        for g in referentiels.local("grands_domaines"))


def grands_domaines() -> list[dict]:
    """[{code, libelle, domaines: [{code, libelle}]}] pour le choix dans le profil."""
    return [{**g, "domaines": [dict(d) for d in g["domaines"]]} for g in _arbre()]


@lru_cache(maxsize=1)
def _libelles() -> dict[str, str]:
    out = {}
    for g in _arbre():
        out[g["code"]] = g["libelle"]
        out.update({d["code"]: d["libelle"] for d in g["domaines"]})
    return out


def est_grand_domaine(code: str) -> bool:
    return len(code) == 1


def domaines_du_grand_domaine(lettre: str) -> list[str]:
    return [d["code"] for g in _arbre() if g["code"] == lettre for d in g["domaines"]]


def normaliser_domaines(codes) -> list[str]:
    """Liste propre : anciennes clés converties, codes inconnus et doublons
    retirés, domaines déjà couverts par leur grand domaine retirés.
    [] : indifférent."""
    if not isinstance(codes, (list, tuple)):
        return []
    connus = _libelles()
    out = []
    for c in codes:
        c = ANCIENNES_CLES.get(str(c).strip(), str(c).strip().upper())
        if c in connus and c not in out:
            out.append(c)
    lettres = {c for c in out if est_grand_domaine(c)}
    return [c for c in out if est_grand_domaine(c) or c[0] not in lettres]


def domaines_du_profil(profil: dict) -> list[str]:
    return normaliser_domaines((profil.get("recherche") or {}).get("domaines"))


def libelles_domaines(codes) -> list[str]:
    """Libellés lisibles, dans l'ordre des codes."""
    libelles = _libelles()
    return [libelles[c] for c in normaliser_domaines(codes)]


# ─── Sources pas encore refondues : correspondances d'avant la phase 5b ───────
# LBA (phase 5c) : codes ROME ; Sirene (phase 5d) : codes NAF. Un profil
# « indifférent » garde l'ancien défaut (informatique) ; un domaine sans
# correspondance n'est pas cherché sur ces sources.
DOMAINE_DEFAUT_SOURCES = "M18"

_LBA_ROMES = {
    "M18": ["M1801", "M1802", "M1803", "M1804", "M1805",
            "M1806", "M1807", "M1808", "M1809", "M1810"],
    "C15": ["C1501", "C1502", "C1503", "C1504"],
}

_SIRENE_NAF = {
    "M18": [
        "62.01Z", "62.02A", "62.02B", "62.03Z", "62.09Z", "63.11Z",
        "58.21Z", "58.29A", "58.29B", "58.29C",
        "61.10Z", "61.20Z", "61.90Z",
        "70.22Z", "71.12B", "74.90B",
    ],
    "C15": [
        "68.31Z",   # Agences immobilières
        "68.32A",   # Administration d'immeubles et autres biens immobiliers (syndic, gestion copro)
        "68.32B",   # Supports juridiques de gestion de patrimoine immobilier
        "68.20A",   # Location de logements
        "68.20B",   # Location de terrains et autres biens immobiliers
        "68.10Z",   # Marchands de biens immobiliers
        "41.10A",   # Promotion immobilière de logements (promoteurs)
    ],
}


def _correspondance(table: dict, codes) -> list[str]:
    codes = normaliser_domaines(codes) or [DOMAINE_DEFAUT_SOURCES]
    out = []
    for c in codes:
        for valeur in table.get(c, []):
            if valeur not in out:
                out.append(valeur)
    return out


def lba_romes(codes) -> list[str]:
    """Codes ROME cherchés sur LBA ; vide si aucun domaine choisi n'a de correspondance."""
    return _correspondance(_LBA_ROMES, codes)


def naf_codes(codes) -> list[str]:
    """Codes NAF cherchés sur Sirene ; vide si aucun domaine choisi n'a de correspondance."""
    return _correspondance(_SIRENE_NAF, codes)


NOMS_SOURCES = {"lba": "La Bonne Alternance", "sirene": "Sirene (candidatures spontanées)"}


def avertissement_non_couverts(codes, source: str) -> str:
    """Message pour l'interface au lancement (décision D27), vide si tout est couvert."""
    manquants = domaines_sans_correspondance(codes, source)
    if not manquants:
        return ""
    libelles = _libelles()
    noms = ", ".join(f"{libelles[c]} ({c})" for c in manquants)
    suite = ("aucun domaine du profil n'y est encore couvert, cette source est ignorée"
             if not _correspondance({"lba": _LBA_ROMES, "sirene": _SIRENE_NAF}[source], codes)
             else "ils n'y sont pas cherchés pour l'instant")
    return f"Domaines pas encore couverts par {NOMS_SOURCES[source]} : {noms} ; {suite}."


def domaines_sans_correspondance(codes, source: str) -> list[str]:
    """Domaines choisis qu'une source pas encore refondue ne sait pas chercher."""
    table = {"lba": _LBA_ROMES, "sirene": _SIRENE_NAF}[source]
    return [c for c in normaliser_domaines(codes) if c not in table]
