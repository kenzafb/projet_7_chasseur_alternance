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

LBA cherche par codes métiers (5 caractères, référentiel metiers), qui
commencent par le code de leur domaine : codes_metiers les en déduit.
Sirene cherche par codes NAF : correspondance dans shared.naf.
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


# ─── Codes métiers (La Bonne Alternance, phase 5c) ────────────────────────────
@lru_cache(maxsize=1)
def _metiers() -> tuple[str, ...]:
    return tuple(sorted(m["code"] for m in referentiels.france_travail("metiers")))


def codes_metiers(codes) -> list[str]:
    """Codes métiers des domaines et grands domaines choisis (« M18 » :
    M1801 à M1896...), triés. Vide pour un profil indifférent."""
    prefixes = tuple(normaliser_domaines(codes))
    if not prefixes:
        return []
    return [m for m in _metiers() if m.startswith(prefixes)]
