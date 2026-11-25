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
ou « aucun »), experience_mois (total), certifications (libellés) ; en job,
experience_domaines (mois par domaine, D211) remplace experience_mois ; en
stage, experience_mois est le plafond (D212). Une
information absente de l'offre ne bloque jamais ; un permis ou une
expérience non renseignés dans le profil non plus. Les certifications
exigées absentes du profil bloquent : le profil les liste toutes.
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from shared import domaines_experience

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


_DUREE_LIGNE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:(an)(?:\(s\)|n[ée]es?|s)?|mois)(?![a-zé])", re.I)
_SANS_EXIGENCE = re.compile(r"^(?:d[ée]butant accept[ée]|exp[ée]rience souhait[ée]e)|\((?:souhait[ée]e|d[ée]butant accept[ée])\)\s*$",
                            re.I)


def experience_demandee(description: str) -> tuple[int, str] | None:
    """(mois, domaine écrit) de l'expérience exigée (D211) ; 0 mois sans durée,
    "" sans domaine ; None si rien n'est exigé, si un débutant est accepté ou
    si l'expérience est seulement souhaitée. La ligne de France Travail
    (« 2 An(s) - En cuisine collective (exigée) ») passe avant celle de
    l'extraction, qui complète la durée ou le domaine manquant."""
    lignes = list(_lignes(description, "Expérience : "))
    if any(_SANS_EXIGENCE.search(x) for x in lignes):
        return None
    exigees = [x for x in lignes if _exigee(x) or x.lower().startswith("expérience exigée")]
    if not exigees:
        return None
    mois, domaine = 0, ""
    for ligne in exigees:
        texte = re.sub(r"\((?:exig[ée]e?|indispensable)\)\s*$", "", ligne)
        if (m := _DUREE_LIGNE.search(texte)) and not mois:
            n = float(m.group(1).replace(",", "."))
            mois = round(n * 12 if m.group(2) else n)
        texte = re.sub(r"^\s*exp[ée]rience exig[ée]e", "", _DUREE_LIGNE.sub(" ", texte), flags=re.I).strip(" -–:")
        domaine = domaine or texte
    return mois, domaine


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


# ─── Années d'expérience écrites dans le texte libre (D176) ────────────────────
NOMBRES = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
           "neuf": 9, "dix": 10}
_NOMBRE = r"(\d{1,2}|" + "|".join(NOMBRES) + r")"
_ANNEES = re.compile(
    rf"(?:minimum|au moins|plus de)?\s*{_NOMBRE}\s*(?:(?:à|a|-|–|ou)\s*{_NOMBRE}\s*)?(?:ans?|ann[ée]es?)\b(?:\s*minimum)?")


def annees_dans_texte(texte: str) -> set[int]:
    """Années écrites dans le texte : « 2 ans », « trois ans », « 3 à 5 ans »
    et « 3-5 ans » (borne basse), « 2 ans minimum », « au moins deux années »."""
    t = _simple(texte)
    return {int(m.group(1)) if m.group(1).isdigit() else NOMBRES[m.group(1)] for m in _ANNEES.finditer(t)}


# ─── Profil ───────────────────────────────────────────────────────────────────
def du_profil(profil: dict) -> dict:
    """{permis: set | None (non renseigné), experience_mois: int | None,
    experience_domaines: {domaine: mois} (job, D211), certifications: set de
    familles, diplome_etat: bool}."""
    rech = (profil or {}).get("recherche") or {}
    permis = rech.get("permis")
    texte = " ".join(str(profil.get(c) or "") for c in ("formation", "niveau_etudes"))
    certifs = list(rech.get("certifications") or [])
    return {
        "permis": None if not permis else ({p for p in permis if p != "aucun"}),
        "experience_mois": rech.get("experience_mois") if isinstance(rech.get("experience_mois"), int) else None,
        "experience_domaines": {e["domaine"]: e["mois"] for e in domaines_experience.normaliser(
            rech.get("experience_domaines"))},
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
    p = du_profil(profil)
    if mode != "job" or p["experience_domaines"]:      # par domaine (D211) : exigée et tenue, ou inéligible
        return []
    mois = experience_exigee(offre.get("description") or "")
    if mois and p["experience_mois"] is not None and 0 < mois - p["experience_mois"] <= ECART_EXPERIENCE_JOB_MOIS:
        return [f"Expérience demandée : {_duree(mois)}"]
    return []


# Métiers de conduite : permis exigé d'après l'intitulé (D182)
FICHIER_CONDUITE = Path(__file__).resolve().parent / "referentiels" / "metiers_conduite.txt"


@lru_cache(maxsize=1)
def _metiers_conduite() -> re.Pattern:
    noms = [_simple(x.split("#", 1)[0]).strip() for x in FICHIER_CONDUITE.read_text(encoding="utf-8").splitlines()]
    noms = sorted({n for n in noms if n}, key=len, reverse=True)
    motifs = [re.escape(n).replace(r"\ ", r"[\s-]+").replace(r"\-", r"[\s-]+") + r"s?" for n in noms]
    return re.compile(r"(?<![a-z])(?:" + "|".join(motifs) + r")(?![a-z])")


def metier_de_conduite(titre: str) -> bool:
    """L'intitulé nomme un métier de conduite (conducteur de bus, chauffeur...)."""
    return bool(_metiers_conduite().search(_simple(titre)))


# Poste confirmé, senior ou expérimenté (D179), dans l'intitulé ; pas « responsable » seul
POSTE_SENIOR = re.compile(r"\b(?:confirm[ée]e?s?|senior|seniors|exp[ée]riment[ée]e?s?)\b", re.I)


def poste_senior(offre: dict, mode: str) -> bool:
    """Job et alternance : intitulé « confirmé », « senior » ou « expérimenté »,
    sauf offre déposée par un organisme de formation (D179)."""
    if mode not in ("job", "alternance"):
        return False
    if "organisme_formation" in (offre.get("marques") or []):
        return False
    return bool(POSTE_SENIOR.search(offre.get("titre") or ""))


def raison_experience_domaine(offre: dict, domaines: dict[str, int]) -> str:
    """Job, « Mon expérience par domaine » rempli (D211) : raison
    d'inéligibilité, ou "". Domaine exigé (à défaut celui de l'intitulé) parmi
    les miens et durée tenue dans ce domaine ; domaine inconnu : durée comparée
    à mon maximum. Aucune tolérance."""
    exigee = experience_demandee(offre.get("description") or "")
    if exigee is None:
        return ""
    mois, texte = exigee
    reconnus, precise = domaines_experience.classer(texte, offre.get("titre") or "")
    if precise and not reconnus & set(domaines):
        ecrit = texte if domaines_experience.classer(texte)[1] else f"intitulé {offre.get('titre') or ''}"
        detail = ", ".join(x for x in (_duree(mois) if mois else "", ecrit) if x)
        return f"Expérience exigée dans un autre domaine ({detail})"
    maximum = max(m for d, m in domaines.items() if not precise or d in reconnus)
    if mois > maximum:
        return f"Expérience exigée trop longue ({_duree(mois)}, {_duree(maximum)} au plus)"
    return ""


_ZERO = re.compile(r"(?<!\d)0\s*(?:an|mois)", re.I)


def raison_experience_totale(offre: dict, mois_profil: int | None) -> str:
    """Stage (D212) : raison d'inéligibilité d'une offre qui exige
    plus que « Expérience professionnelle, en mois », ou "". Champ vide, débutant
    accepté, expérience souhaitée, « 0 An(s) » ou sans durée : rien."""
    description = offre.get("description") or ""
    exigee = experience_demandee(description)
    if mois_profil is None or exigee is None or any(
            _exigee(x) and _ZERO.search(x) for x in _lignes(description, "Expérience : ")):
        return ""
    if exigee[0] > mois_profil:
        return f"Expérience exigée trop longue ({_duree(exigee[0])}, {_duree(mois_profil)} au plus)"
    return ""


def raisons(offre: dict, profil: dict, mode: str, crans_profil: int | None) -> list[str]:
    """Raisons d'inéligibilité tirées des exigences structurées de l'offre."""
    description = offre.get("description") or ""
    p = du_profil(profil)
    out = []
    if poste_senior(offre, mode):
        out.append("poste confirmé ou senior")
    exiges = permis_exiges(description)
    if metier_de_conduite(offre.get("titre") or ""):
        exiges.append(PERMIS_SANS_CATEGORIE)          # permis implicite (D182)
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
    if mode == "job" and p["experience_domaines"]:
        if raison := raison_experience_domaine(offre, p["experience_domaines"]):
            out.append(raison)
    elif mode == "stage" and (raison := raison_experience_totale(offre, p["experience_mois"])):
        out.append(raison)
    elif mois is not None:
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
