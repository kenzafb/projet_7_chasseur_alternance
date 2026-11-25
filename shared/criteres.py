"""
shared/criteres.py
==================
Critères de recherche du profil (profils.recherche, colonne JSON) :
  - domaines : codes France Travail, [] pour indifférent (shared.domaines) ;
  - secteurs : divisions NAF de l'employeur (2 chiffres, référentiel
    secteurs_activites), [] pour tous ;
  - tailles : tailles d'entreprise (shared.tailles), [] pour toutes ;
    taille_inconnue : garder les offres sans information (vrai par défaut) ;
  - tailles_spontanees, taille_inconnue_spontanees : les mêmes pour les
    entreprises des candidatures spontanées (Sirene, LBA), réglage distinct
    des offres (décision D63) ;
  - themes : thèmes France Travail du mode job (13 saisonniers, 17 sans
    diplôme ni expérience), décochés par défaut ;
  - departements : départements d'Île-de-France des candidatures
    spontanées (Sirene), [] pour tous ;
  - tous_secteurs : candidatures spontanées sans filtre de secteur (Sirene,
    toutes activités), faux par défaut : choix explicite (phase 6b) ;
  - domaines_indifferent : « indifférent » coché par la personne elle-même
    (domaines vides par choix, pas par oubli), pour la complétude du
    profil (D144) ; sans effet sur la recherche ;
  - rythme : rythme de l'alternance (texte libre), pour la complétude ;
  - permis (codes du référentiel France Travail, ou « aucun »),
    experience_mois (expérience professionnelle totale, en mois) et
    certifications (CACES R489, SSIAP 1...) : ce que la personne a, pour les
    exigences des offres (shared/exigences.py, D169) ; copiables ;
  - job (D211) : niveau_max_offre, niveau maximal demandé par l'offre (clé
    de shared.eligibilite.NIVEAUX_MAX_OFFRE, absent : sans limite), et
    experience_domaines, [{domaine, mois}] (shared.domaines_experience) ;
    vide : règle D174 sur experience_mois.

normaliser_recherche les remet en forme à l'enregistrement (valeurs
inconnues retirées, types fixés) ; les autres clés (disponibilité, champs
en lecture seule) passent telles quelles. criteres_france_travail en tire
la recherche d'un mode.
"""

from shared import domaines_experience, referentiels
from shared.config import DEPTS_IDF
from shared.domaines import normaliser_domaines
from shared.eligibilite import NIVEAUX_MAX_OFFRE
from shared.exigences import SUGGESTIONS_CERTIFICATIONS
from shared.modes import get_mode
from shared.tailles import CLES_TAILLES, TAILLES

# Permis : codes du référentiel France Travail, ou « aucun » (D169)
AUCUN_PERMIS = "aucun"

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
    if "tailles_spontanees" in out:
        out["tailles_spontanees"] = _liste(out["tailles_spontanees"], set(CLES_TAILLES))
    if "taille_inconnue_spontanees" in out:
        out["taille_inconnue_spontanees"] = out["taille_inconnue_spontanees"] is not False
    if "themes" in out:
        out["themes"] = _liste(out["themes"], set(THEMES_PROPOSES))
    if "departements" in out:
        out["departements"] = sorted(_liste(out["departements"], DEPTS_IDF))
    if "tous_secteurs" in out:
        out["tous_secteurs"] = out["tous_secteurs"] is True
    if "inclure_transverses" in out:
        # Grandes entreprises hors des secteurs du domaine (D190) : oui par défaut
        out["inclure_transverses"] = out["inclure_transverses"] is not False
    if "domaines_indifferent" in out:
        # Indifférent et des domaines cochés ne vont pas ensemble
        out["domaines_indifferent"] = out["domaines_indifferent"] is True and not out.get("domaines")
    if "rythme" in out:
        out["rythme"] = str(out["rythme"] or "").strip()[:200]
    # Permis, expérience et certifications (D169), communs aux trois modes
    if "permis" in out:
        permis = _liste(out["permis"], _codes_connus("permis") | {AUCUN_PERMIS})
        out["permis"] = [AUCUN_PERMIS] if AUCUN_PERMIS in permis else permis
    if "experience_mois" in out:
        try:
            mois = int(str(out["experience_mois"]).strip())
            out["experience_mois"] = mois if 0 <= mois <= 600 else None
        except (TypeError, ValueError):
            out["experience_mois"] = None
        if out["experience_mois"] is None:
            del out["experience_mois"]
    if "niveau_max_offre" in out and out["niveau_max_offre"] not in NIVEAUX_MAX_OFFRE:
        del out["niveau_max_offre"]
    if "experience_domaines" in out:
        out["experience_domaines"] = domaines_experience.normaliser(out["experience_domaines"])
    if "certifications" in out:
        vues, certifs = set(), []
        for c in out["certifications"] if isinstance(out["certifications"], (list, tuple)) else []:
            c = " ".join(str(c).split())[:60]
            if c and c.lower() not in vues:
                vues.add(c.lower())
                certifs.append(c)
        out["certifications"] = certifs[:20]
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
        # Mode stage : domaines jugés par l'IA, pas filtrés à la source (D152)
        "domaines": [] if cfg.get("ft_sans_domaine") else rech.get("domaines", []),
        "tailles": rech.get("tailles", []),
        "taille_inconnue": rech.get("taille_inconnue", True),
        "exclure_alternance": bool(cfg.get("ft_exclure_alternance")),
        "intitules_stage": bool(cfg.get("ft_intitules_stage")),
    }


def options_du_profil() -> dict:
    """Listes proposées dans le profil : secteurs, tailles, thèmes,
    départements ; domaines qui ont une correspondance NAF pour Sirene et
    volume de « tous les secteurs » (message des candidatures spontanées)."""
    from shared.naf import MESSAGE_RIEN_A_CHERCHER, VOLUME_TOUS_SECTEURS, domaines_couverts
    themes = referentiels.libelles(referentiels.france_travail("themes"))
    return {
        "domaines_naf": sorted(domaines_couverts()),
        "volume_tous_secteurs": VOLUME_TOUS_SECTEURS,
        "message_rien_a_chercher": MESSAGE_RIEN_A_CHERCHER,
        "departements": [dict(e) for e in referentiels.france_travail("departements") if e["code"] in DEPTS_IDF],
        "secteurs": [dict(e) for e in referentiels.france_travail("secteurs_activites")],
        "tailles": [{k: t[k] for k in ("cle", "libelle")} | ({"avertissement": t["avertissement"]}
                                                            if "avertissement" in t else {})
                    for t in TAILLES],
        "themes": [{"code": c, "libelle": themes.get(c, c)} for c in THEMES_PROPOSES],
        # Permis et certifications du profil (D169)
        "permis": [dict(e) for e in referentiels.france_travail("permis")],
        "certifications": SUGGESTIONS_CERTIFICATIONS,
        "experience_domaines": domaines_experience.options(),      # profil job (D211)
    }
