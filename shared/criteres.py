"""
shared/criteres.py
==================
Critères de recherche du profil (profils.recherche, colonne JSON) :
  - domaines : codes France Travail, [] pour indifférent (shared.domaines) ;
  - secteurs : divisions NAF de l'employeur (2 chiffres, référentiel
    secteurs_activites), [] pour tous ;
  - tailles : tailles d'entreprise (shared.tailles), [] pour toutes ;
    taille_inconnue : garder les offres sans information (vrai par défaut) ;
  - themes : thèmes France Travail du mode job (13 saisonniers, 17 sans
    diplôme ni expérience), décochés par défaut.

normaliser_recherche les remet en forme à l'enregistrement (valeurs
inconnues retirées, types fixés) ; les autres clés (disponibilité, champs
en lecture seule) passent telles quelles. criteres_france_travail en tire
la recherche d'un mode.
"""

from shared import referentiels
from shared.domaines import normaliser_domaines
from shared.modes import get_mode
from shared.tailles import CLES_TAILLES, TAILLES

# Thèmes proposés en option du mode job (SPEC_SOURCES 2.1)
THEMES_PROPOSES = ["13", "17"]


def _codes_connus(nom: str) -> set[str]:
    return {e["code"] for e in referentiels.france_travail(nom)}


def _liste(valeurs, permises) -> list[str]:
    if not isinstance(valeurs, (list, tuple)):
        return []
    out = []
    for v in valeurs:
        v = str(v).strip()
        if v in permises and v not in out:
            out.append(v)
    return out


def normaliser_recherche(recherche) -> dict:
    """Copie propre de recherche (dict vide si ce n'en est pas un)."""
    if not isinstance(recherche, dict):
        return {}
    out = dict(recherche)
    if "domaines" in out:
        out["domaines"] = normaliser_domaines(out["domaines"])
    if "secteurs" in out:
        out["secteurs"] = _liste(out["secteurs"], _codes_connus("secteurs_activites"))
    if "tailles" in out:
        out["tailles"] = _liste(out["tailles"], set(CLES_TAILLES))
    if "taille_inconnue" in out:
        out["taille_inconnue"] = out["taille_inconnue"] is not False
    if "themes" in out:
        out["themes"] = _liste(out["themes"], set(THEMES_PROPOSES))
    return out


def criteres_france_travail(profil: dict, mode: str) -> dict:
    """Recherche France Travail d'un profil dans un mode :
    {filtres: {paramètre: [valeurs]}, domaines, tailles, taille_inconnue,
    exclure_alternance}. Les valeurs d'un même paramètre sont réunies (OU)."""
    cfg = get_mode(mode)
    rech = normaliser_recherche((profil or {}).get("recherche") or {})
    filtres = {p: list(v) for p, v in cfg.get("ft_filtres", {}).items()}
    options = cfg.get("ft_options", [])
    if "secteurs" in options and rech.get("secteurs"):
        filtres["secteurActivite"] = rech["secteurs"]
    if "themes" in options and rech.get("themes"):
        filtres["theme"] = rech["themes"]
    return {
        "filtres": filtres,
        "domaines": rech.get("domaines", []),
        "tailles": rech.get("tailles", []),
        "taille_inconnue": rech.get("taille_inconnue", True),
        "exclure_alternance": bool(cfg.get("ft_exclure_alternance")),
    }


def options_du_profil() -> dict:
    """Listes proposées dans le profil : secteurs, tailles, thèmes."""
    themes = referentiels.libelles(referentiels.france_travail("themes"))
    return {
        "secteurs": [dict(e) for e in referentiels.france_travail("secteurs_activites")],
        "tailles": [{k: t[k] for k in ("cle", "libelle")} | ({"avertissement": t["avertissement"]}
                                                            if "avertissement" in t else {})
                    for t in TAILLES],
        "themes": [{"code": c, "libelle": themes.get(c, c)} for c in THEMES_PROPOSES],
    }
