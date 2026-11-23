"""
shared/exigences.py
===================
Exigences d'une offre lues dans ses champs structurés (phase 15, D169), sans
IA : permis, formation, expérience et certifications exigés. Les offres
France Travail les portent dans des lignes ajoutées à la description
(offres/france_travail._normaliser_une) :

    Permis : B - Véhicule léger (exigé)
    Expérience : 2 An(s) (exigée)
    Formation : Cuisine - CAP, BEP et équivalents (indispensable)
    Compétence : CACES R489 cat 1 3 5 (indispensable)

Les offres La Bonne Alternance, dans offer.access_conditions (lignes
« Conditions d'accès : ... », exigées par nature).

Profil (profils.recherche, communs aux trois modes, D169) : permis (codes,
ou « aucun »), experience_mois (total), certifications (libellés). Une
information absente de l'offre ne bloque jamais ; un permis ou une
expérience non renseignés dans le profil non plus. Les certifications
exigées absentes du profil bloquent : le profil les liste toutes.
"""

import re
import unicodedata

# Niveaux des formations France Travail (référentiel niveauxFormations) -> crans (bac = 0)
NIVEAUX_FORMATION = {
    "aucune formation scolaire": -3, "primaire a 4eme": -3, "4eme achevee": -3, "3eme achevee ou brevet": -2,
    "2nd ou 1ere achevee": -1, "cap, bep et equivalents": -1, "niveau bac": 0, "bac ou equivalent": 0,
    "bac+2 ou equivalents": 2, "bac+3, bac+4 ou equivalents": 3, "bac+5 et plus ou equivalents": 5,
}
LIBELLES_CRANS = {-3: "sans diplôme", -2: "Brevet", -1: "CAP ou BEP", 0: "Bac", 2: "Bac+2", 3: "Bac+3", 4: "Bac+4",
                  5: "Bac+5"}

# Certifications reconnues (famille -> motif) : une exigée n'est satisfaite
# que par une certification de la même famille dans le profil
CERTIFICATIONS = {
    "CACES": r"\bca[cs]es\b|\bcariste\b.*\bcertifi",
    "SSIAP": r"\bssiap\b",
    "Carte professionnelle de sécurité": r"carte pro(?:fessionnelle)?\b.*s[ée]curit[ée]|\bcqp aps\b|\btfp aps\b",
    "BAFA": r"\bbafa\b",
    "PSC1": r"\bpsc ?1\b|premiers secours",
    "SST": r"\bsst\b|sauveteur secouriste",
    "Habilitation électrique": r"habilitation[s]? [ée]lectrique|\bb0\b|\bh0v?\b|\bbr\b(?=.*habilit)",
    "HACCP": r"\bhaccp\b",
    "FIMO / FCO": r"\bfimo\b|\bfco\b",
}
# Diplôme d'État : en toutes lettres, ou par son sigle (en majuscules)
_DE_TEXTE = re.compile(r"dipl[oô]mes? d.[ée]tat", re.I)
_DE_SIGLES = re.compile(r"\b(?:DEAES|DEES|DEEJE|DEASS|DEAS|DEAP|DEI|DEME|DEJEPS|DESJEPS|DETISF|DECESF)\b")


class _DiplomeEtat:
    @staticmethod
    def search(texte):
        return _DE_TEXTE.search(texte or "") or _DE_SIGLES.search(texte or "")

    @staticmethod
    def finditer(texte):
        yield from _DE_TEXTE.finditer(texte or "")
        yield from _DE_SIGLES.finditer(texte or "")


DIPLOME_ETAT = _DiplomeEtat()
MARQUEURS_EXIGENCE = re.compile(r"exig[ée]e?s?|obligatoires?|imp[ée]rati(?:f|ve)s?|indispensables?|requise?s?")

SUGGESTIONS_CERTIFICATIONS = ["CACES R489", "SSIAP 1", "Carte professionnelle de sécurité", "BAFA", "PSC1"]


def _simple(texte) -> str:
    texte = unicodedata.normalize("NFKD", str(texte or "")).replace("’", "'")
    return "".join(c for c in texte if not unicodedata.combining(c)).lower()


def _lignes(description: str, prefixe: str):
    for ligne in (description or "").splitlines():
        if ligne.startswith(prefixe):
            yield ligne[len(prefixe):].strip()


def _exigee(ligne: str) -> bool:
    return bool(re.search(r"\((?:exig[ée]e?|indispensable)\)\s*$", ligne))


def familles(texte: str) -> set[str]:
    t = _simple(texte)
    return {f for f, motif in CERTIFICATIONS.items() if re.search(motif, t)}


# ─── Lecture de l'offre ───────────────────────────────────────────────────────
PERMIS_SANS_CATEGORIE = "*"      # permis exigé, catégorie non lue dans le texte (D175)


def permis_exiges(description: str) -> list[str]:
    """Codes des permis exigés (« B - Véhicule léger (exigé) » -> « B » ;
    « * » : un permis exigé dont la catégorie n'a pas été lue)."""
    out = []
    for ligne in _lignes(description, "Permis : "):
        if not _exigee(ligne):
            continue
        if ligne.startswith(PERMIS_SANS_CATEGORIE):
            out.append(PERMIS_SANS_CATEGORIE)
        elif m := re.match(r"([A-Z][A-Z0-9]*)\b", ligne):
            out.append(m.group(1))
    return out


def experience_exigee(description: str) -> int | None:
    """Mois d'expérience exigés (ligne « Expérience : 2 An(s) (exigée) »),
    0 pour « Expérience exigée » sans durée, None si rien n'est exigé."""
    for ligne in _lignes(description, "Expérience : "):
        exigee = _exigee(ligne) or ligne.lower().startswith("expérience exigée")
        if not exigee:
            continue
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(an|mois)", ligne, re.I)
        if not m:
            return 0
        n = float(m.group(1).replace(",", "."))
        return round(n * 12 if m.group(2).lower() == "an" else n)
    return None


def formations_exigees(description: str) -> list[tuple[int, str]]:
    """(crans, libellé) des formations exigées (« (indispensable) »)."""
    out = []
    for ligne in _lignes(description, "Formation : "):
        if not _exigee(ligne):
            continue
        niveau = _simple(ligne.rsplit(" - ", 1)[-1].rsplit("(", 1)[0].strip())
        if niveau in NIVEAUX_FORMATION:
            out.append((NIVEAUX_FORMATION[niveau], ligne.rsplit("(", 1)[0].strip()))
    return out


def diplome_etat_exige(description: str) -> bool:
    """Diplôme d'État demandé avec un mot d'exigence près de lui, ou dans une formation exigée."""
    if any(DIPLOME_ETAT.search(f) for _, f in formations_exigees(description)):
        return True
    texte = description or ""
    return any(MARQUEURS_EXIGENCE.search(texte[max(0, m.start() - 80):m.end() + 80])
               for m in DIPLOME_ETAT.finditer(texte))


def certifications_exigees(description: str, conditions=()) -> list[str]:
    """Familles de certification exigées : compétences « (indispensable) »
    France Travail, conditions d'accès LBA."""
    out = set()
    for ligne in _lignes(description, "Compétence : "):
        if _exigee(ligne):
            out |= familles(ligne)
    for c in conditions or ():
        out |= familles(c)
    return sorted(out)


# ─── Profil ───────────────────────────────────────────────────────────────────
def du_profil(profil: dict) -> dict:
    """{permis: set | None (non renseigné), experience_mois: int | None,
    certifications: set de familles, diplome_etat: bool}."""
    rech = (profil or {}).get("recherche") or {}
    permis = rech.get("permis")
    texte = " ".join(str(profil.get(c) or "") for c in ("formation", "niveau_etudes"))
    certifs = list(rech.get("certifications") or [])
    return {
        "permis": None if not permis else ({p for p in permis if p != "aucun"}),
        "experience_mois": rech.get("experience_mois") if isinstance(rech.get("experience_mois"), int) else None,
        "certifications": set().union(*(familles(c) for c in certifs)) if certifs else set(),
        "diplome_etat": bool(DIPLOME_ETAT.search(texte) or any(DIPLOME_ETAT.search(c) for c in certifs)),
    }


# ─── Règles ───────────────────────────────────────────────────────────────────
ANNEES_ALTERNANCE = 24     # alternance : « plusieurs années » d'expérience exigées (D169)
# Job : inéligible seulement au-delà de 12 mois de plus que le profil ;
# en deçà, éligible, plafond Moyen et « Expérience demandée » (D174)
ECART_EXPERIENCE_JOB_MOIS = 12
PLAFOND_RESERVE = 5        # note de « Moyen »


def reserves(offre: dict, profil: dict, mode: str) -> list[str]:
    """Exigences qui ne rendent pas inéligible mais plafonnent la note à
    Moyen, avec leur message pour « Ce qui coince » (D174)."""
    if mode != "job":
        return []
    mois = experience_exigee(offre.get("description") or "")
    p = du_profil(profil)
    if mois and p["experience_mois"] is not None and 0 < mois - p["experience_mois"] <= ECART_EXPERIENCE_JOB_MOIS:
        return [f"Expérience demandée : {_duree(mois)}"]
    return []


def raisons(offre: dict, profil: dict, mode: str, crans_profil: int | None) -> list[str]:
    """Raisons d'inéligibilité tirées des exigences structurées de l'offre."""
    description = offre.get("description") or ""
    p = du_profil(profil)
    out = []
    exiges = permis_exiges(description)
    categories = [c for c in exiges if c != PERMIS_SANS_CATEGORIE]
    if p["permis"] is not None and not p["permis"] and exiges:
        # « Aucun permis » : tout permis exigé écarte l'offre, catégorie lue ou non (D175)
        out.append(f"permis {' ou '.join(categories)} exigé, tu n'as pas de permis" if categories
                   else "permis exigé, tu n'as pas de permis")
    elif categories and p["permis"] and not set(categories) & p["permis"]:
        out.append(f"permis {' ou '.join(categories)} exigé, ton permis : {', '.join(sorted(p['permis']))}")
    for crans, libelle in formations_exigees(description):
        if crans_profil is not None and crans > crans_profil:
            out.append(f"formation exigée : {libelle}, profil {LIBELLES_CRANS.get(crans_profil, crans_profil)}")
            break
    # Alternance : le diplôme d'État est souvent celui que le contrat prépare
    if mode != "alternance" and diplome_etat_exige(description) and not p["diplome_etat"]:
        out.append("diplôme d'État exigé")
    mois = experience_exigee(description)
    if mois is not None:
        if mode == "alternance" and mois >= ANNEES_ALTERNANCE:
            out.append(f"{mois // 12} ans d'expérience exigés : ce n'est pas une alternance")
        elif (mode == "job" and p["experience_mois"] is not None
              and mois - p["experience_mois"] > ECART_EXPERIENCE_JOB_MOIS):
            out.append(f"{_duree(mois)} d'expérience exigés, profil {_duree(p['experience_mois'])}")
    manquantes = [c for c in certifications_exigees(description, offre.get("conditions_acces") or ())
                  if c not in p["certifications"]]
    if manquantes:
        out.append(f"{', '.join(manquantes)} exigé{'s' if len(manquantes) > 1 else ''}, absent du profil")
    return out


def _duree(mois: int) -> str:
    if mois == 0:
        return "aucune"
    return f"{mois // 12} an{'s' if mois >= 24 else ''}" if mois % 12 == 0 else f"{mois} mois"
