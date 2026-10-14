"""
shared/eligibilite.py
=====================
Éligibilité d'une offre décidée en Python (phase 7, D94), à partir des
champs que le modèle extrait de l'offre sans les juger (niveau_requis,
duree_mois, date_debut_offre, alternance_seulement) et du profil.

Constat : sur trois offres de stage jugées par l'humain, les quatre modèles
essayés ont noté 5 à 9 des offres exigeant un Bac+5, pour un profil de BUT2,
ou un stage de 6 mois pour 10 semaines disponibles. Les critères bloquants
ne sont donc plus confiés au modèle.

Chaque valeur extraite est d'abord contrôlée contre le texte de l'offre
(controler_extraits, D98) : une durée, un niveau ou une date de début que
la description ne contient pas devient non précisé (constat : la durée du
profil, 10 semaines, recopiée en duree_mois pour presque toutes les offres ;
« Bac+5 exigé » lu dans un intitulé « Ingénieur/e Système »).

Règles (une information non précisée ne rend jamais inéligible) :
  - niveau requis supérieur au niveau du profil d'au moins deux crans, si
    l'offre l'exige ; seulement souhaité (« ou équivalent », « idéalement »,
    « de préférence », « souhaité »...) : score baissé de 1 à 2 points et
    raison ajoutée aux points faibles, jamais inéligible ;
  - mode stage : durée de l'offre supérieure à celle du profil de plus de
    4 semaines, ou début de l'offre incompatible avec les dates du profil ;
  - modes stage et job : offre en alternance seulement.

Niveau du profil : champ niveau_etudes ; vide, niveau visé (alternance) ;
vide, déduit de la formation quand c'est sans ambiguïté (BUT1 = bac,
BUT2 = bac+2 en cours, BUT3 = bac+3...) ; sinon inconnu, et le profil
affiche un avertissement qui demande de le remplir.
"""

import re
from datetime import date, timedelta

from shared.stage import MOIS, date_en_lettres, lire_date

# Niveaux de l'énumération du schéma, en crans (bac = 0, bac+5 = 5)
NIVEAUX_REQUIS = ("bac", "bac+2", "bac+3", "bac+4", "bac+5", "non_precise")
CRANS = {"bac": 0, "bac+2": 2, "bac+3": 3, "bac+4": 4, "bac+5": 5}
LIBELLES = {0: "Bac", 1: "Bac+1", 2: "Bac+2", 3: "Bac+3", 4: "Bac+4", 5: "Bac+5"}

ECART_NIVEAU_BLOQUANT = 2          # crans
MARGE_DUREE_SEMAINES = 4
SEMAINES_PAR_MOIS = 52 / 12
TOLERANCE_DEBUT_JOURS = 7          # début précis un peu avant celui du profil : accepté
PLAFOND_SCORE_INELIGIBLE = 3

# ─── Contrôle des valeurs extraites contre le texte de l'offre (D98) ─────────
# Indices de niveau dans la description (jamais l'intitulé du poste : « Stage
# Ingénieur/e Système » ne dit rien du niveau ; le mot « ingénieur » seul non
# plus). Chaque indice autorise un ou plusieurs niveaux de l'énumération.
INDICES_NIVEAU = [
    (r"bac\s*\+\s*5|\bm\s?2\b|master\s*2|[ée]coles? d.ing[ée]nieurs?|dipl[ôo]me d.ing[ée]nieurs?"
     r"|[ée]l[èe]ves?[- ]ing[ée]nieurs?|cycle (?:d.)?ing[ée]nieurs?|formation d.ing[ée]nieurs?", {"bac+5"}),
    (r"\bmasters?\b|\bmsc\b", {"bac+4", "bac+5"}),
    (r"bac\s*\+\s*4|\bm\s?1\b|master\s*1", {"bac+4"}),
    (r"bac\s*\+\s*3|\blicences?\b|\bbachelors?\b", {"bac+3"}),
    (r"bac\s*\+\s*2|\bbts\b|\bdut\b|\bdeug\b", {"bac+2"}),
    (r"\bbac\b(?!\s*\+)|baccalaur[ée]at", {"bac"}),
]
INDICE_BUT = re.compile(r"\bBUT\b")          # en majuscules : pas l'anglais « but »
MARQUEURS_SOUHAIT = re.compile(r"ou [ée]quivalent|id[ée]alement|de pr[ée]f[ée]rence|souhait[ée]e?s?|appr[ée]ci[ée]e?s?"
                               r"|serait un plus|est un plus|un plus\b")
FENETRE_SOUHAIT = (60, 120)                   # caractères avant et après l'indice de niveau
TOLERANCE_DUREE_MOIS = 0.5


def _texte(offre: dict) -> str:
    return (offre.get("description") or "").replace("’", "'")


def niveaux_dans_texte(texte: str) -> tuple[set[str], list[tuple[int, int]]]:
    """(niveaux que la description permet, positions des indices)."""
    niveaux, positions = set(), []
    bas = texte.lower()
    for motif, permis in INDICES_NIVEAU:
        for m in re.finditer(motif, bas):
            niveaux |= permis
            positions.append(m.span())
    for m in INDICE_BUT.finditer(texte):
        niveaux |= {"bac+2", "bac+3"}
        positions.append(m.span())
    return niveaux, positions


def durees_dans_texte(texte: str) -> list[float]:
    """Durées écrites dans la description, en mois (« 6 mois », « 10 semaines »).
    Les lignes « Expérience : ... » ajoutées par France Travail ne comptent pas."""
    lignes = [l for l in texte.lower().splitlines() if not l.strip().startswith("expérience")]
    durees = []
    for nombre, unite in re.findall(r"(\d+(?:[.,]\d+)?)\s*(mois|semaines?)\b", "\n".join(lignes)):
        n = float(nombre.replace(",", "."))
        durees.append(n if unite == "mois" else n / SEMAINES_PAR_MOIS)
    return durees


def _date_dans_texte(jour: date, texte: str) -> bool:
    """Le mois (en lettres ou en chiffres) et l'année du début figurent-ils dans la description ?"""
    bas = texte.lower()
    mois = MOIS[jour.month - 1]
    sans_accent = mois.replace("é", "e").replace("û", "u")
    mois_ecrit = (mois in bas or sans_accent in bas
                  or re.search(rf"\b0?{jour.month}[/.-](?:\d\d[/.-])?{jour.year}\b", bas)
                  or re.search(rf"\b{jour.year}-0?{jour.month}\b", bas))
    return bool(mois_ecrit) and str(jour.year) in bas


def controler_extraits(extraits: dict, offre: dict) -> list[str]:
    """Contrôle les valeurs extraites contre la description de l'offre et
    remet à « non précisé » celles qu'elle ne contient pas. Modifie extraits
    en place ; retourne ce qui a été écarté (journal, script)."""
    texte = _texte(offre)
    ecartes = []
    duree = extraits.get("duree_mois")
    if duree and not any(abs(duree - d) <= TOLERANCE_DUREE_MOIS for d in durees_dans_texte(texte)):
        ecartes.append(f"duree_mois {duree:g} absente de l'offre")
        extraits["duree_mois"] = None
    niveau = extraits.get("niveau_requis") or "non_precise"
    niveaux, positions = niveaux_dans_texte(texte)
    if niveau != "non_precise" and niveau not in niveaux:
        ecartes.append(f"niveau_requis {niveau} absent de l'offre")
        niveau = extraits["niveau_requis"] = "non_precise"
    if niveau == "non_precise":
        extraits["niveau_exigence"] = "non_precise"
    elif extraits.get("niveau_exigence") == "exige":
        avant, apres = FENETRE_SOUHAIT
        if any(MARQUEURS_SOUHAIT.search(texte[max(0, a - avant):b + apres].lower()) for a, b in positions):
            extraits["niveau_exigence"] = "souhaite"
    debut = extraits.get("date_debut_offre")
    lu = lire_debut_offre(debut)
    if lu and not _date_dans_texte(lu[0], texte):
        ecartes.append(f"date_debut_offre « {debut} » absente de l'offre")
        extraits["date_debut_offre"] = None
    return ecartes


def ecart_niveau(extraits: dict, profil: dict) -> tuple[int, int, int] | None:
    """(écart en crans, crans requis, crans du profil), ou None si l'un manque."""
    requis = CRANS.get(extraits.get("niveau_requis") or "non_precise")
    profil_crans = niveau_du_profil(profil)["crans"]
    if requis is None or profil_crans is None:
        return None
    return requis - profil_crans, requis, profil_crans


def penalite_souhait(extraits: dict, profil: dict) -> tuple[int, str]:
    """Niveau seulement souhaité, d'au moins deux crans au-dessus du profil :
    (points retirés au score, 1 pour deux crans et 2 au-delà ; raison)."""
    ecart = ecart_niveau(extraits, profil)
    if extraits.get("niveau_exigence") != "souhaite" or not ecart or ecart[0] < ECART_NIVEAU_BLOQUANT:
        return 0, ""
    points = 1 if ecart[0] == ECART_NIVEAU_BLOQUANT else 2
    return points, f"{LIBELLES[ecart[1]]} souhaité, profil {LIBELLES[ecart[2]]}"

MESSAGE_NIVEAU_INCONNU = ("Indique ton niveau d'études actuel (par exemple « Bac+2 en cours ») : sans lui, "
                          "les offres qui exigent un niveau bien supérieur ne peuvent pas être écartées.")

# Formation -> crans, seulement les cas sans ambiguïté (BUT1 = bac, comme
# convenu ; BUT2 = bac+1 validé, donc bac+2 en cours)
_ANNEE = r"\s*(?:(?:e|è|ème|eme|re|ère|ere)\s*ann[ée]e)?"
_FORMATIONS = [
    (re.compile(rf"\bbut\s*([123]){_ANNEE}\b"), {"1": 0, "2": 2, "3": 3}),
    (re.compile(rf"\b([123]){_ANNEE}\s*(?:de\s+)?but\b"), {"1": 0, "2": 2, "3": 3}),
    (re.compile(r"\b(?:licence|l)\s*([123])\b"), {"1": 0, "2": 2, "3": 3}),
    (re.compile(r"\b(?:master|m)\s*([12])\b"), {"1": 4, "2": 5}),
]


def crans_texte(texte: str) -> set[int]:
    """Niveaux (crans) lisibles dans un texte : « Bac+3 », « BUT2 », « M1 »..."""
    t = (texte or "").lower()
    crans = {min(5, int(n)) for n in re.findall(r"\bbac\s*\+\s*(\d)", t)}
    if re.search(r"\bbac\b(?!\s*\+)", t) and not crans:
        crans.add(0)
    for motif, table in _FORMATIONS:
        crans.update(table[m] for m in motif.findall(t))
    return crans


def niveau_du_profil(profil: dict) -> dict:
    """{"crans" (int ou None), "libelle", "source", "avertissement"}."""
    for champ, source in (("niveau_etudes", "niveau d'études"), ("niveau_vise", "niveau visé"),
                          ("formation", "formation")):
        crans = crans_texte(profil.get(champ) or "")
        if len(crans) == 1:
            n = crans.pop()
            return {"crans": n, "libelle": LIBELLES[n], "source": source, "avertissement": ""}
        if crans and champ == "niveau_etudes":
            # Plusieurs niveaux écrits (« Bac+2 en cours, Bac obtenu ») : le plus haut
            n = max(crans)
            return {"crans": n, "libelle": LIBELLES[n], "source": source, "avertissement": ""}
    return {"crans": None, "libelle": "", "source": "", "avertissement": MESSAGE_NIVEAU_INCONNU}


def lire_debut_offre(texte) -> tuple[date, bool] | None:
    """(date, précise ?) d'un début écrit dans l'offre : « 2027-01-15 »,
    « 15/01/2027 », « janvier 2027 », « 01/2027 ». Sans année, ou « dès que
    possible » : None (non précisé)."""
    t = (texte or "").strip().lower()
    if not t:
        return None
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3])), True
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b", t)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1])), True
    m = re.search(r"\b(\d{1,2})/(20\d\d)\b", t)
    if m and 1 <= int(m[1]) <= 12:
        return date(int(m[2]), int(m[1]), 1), False
    for i, mois in enumerate(MOIS, 1):
        m = re.search(rf"\b(?:(\d{{1,2}})(?:er)?\s+)?{mois}\s+(20\d\d)\b", t)
        if m:
            return (date(int(m[2]), i, int(m[1])), True) if m[1] else (date(int(m[2]), i, 1), False)
    return None


def raisons_ineligibilite(extraits: dict, profil: dict, mode: str) -> list[str]:
    """Raisons d'inéligibilité établies en Python ; vide si rien ne bloque."""
    raisons = []
    ecart = ecart_niveau(extraits, profil)
    if ecart and ecart[0] >= ECART_NIVEAU_BLOQUANT and extraits.get("niveau_exigence") == "exige":
        raisons.append(f"{LIBELLES[ecart[1]]} exigé, profil {LIBELLES[ecart[2]]}")
    if mode in ("stage", "job") and extraits.get("alternance_seulement"):
        raisons.append("offre en alternance seulement")
    if mode == "stage":
        debut, fin = lire_date(profil.get("date_debut") or None), lire_date(profil.get("date_fin") or None)
        semaines = profil.get("duree_semaines")
        duree = extraits.get("duree_mois")
        if duree and semaines and duree * SEMAINES_PAR_MOIS > semaines + MARGE_DUREE_SEMAINES:
            mois = f"{duree:g} mois"
            raisons.append(f"{mois} demandés, {semaines} semaines disponibles")
        lu = lire_debut_offre(extraits.get("date_debut_offre"))
        if lu and debut and fin:
            jour, precise = lu
            if precise:
                hors = jour < debut - timedelta(days=TOLERANCE_DEBUT_JOURS) or jour > fin
            else:
                hors = (jour.year, jour.month) < (debut.year, debut.month) or (jour.year, jour.month) > (fin.year, fin.month)
            if hors:
                ecrit = date_en_lettres(jour) if precise else f"{MOIS[jour.month - 1]} {jour.year}"
                raisons.append(f"début le {ecrit}" if precise else f"début en {ecrit}")
                raisons[-1] += f", stage possible du {date_en_lettres(debut)} au {date_en_lettres(fin)}"
    return raisons
