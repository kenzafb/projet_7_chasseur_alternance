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
    l'offre l'exige explicitement (exigé, obligatoire, impératif, requis,
    indispensable, près du niveau, D103) ; sinon il n'est que souhaité :
    score baissé de 1 à 2 points et raison ajoutée aux points faibles,
    jamais inéligible ;
  - mode stage : durée de l'offre supérieure à celle du profil de plus de
    4 semaines, ou début de l'offre incompatible avec les dates du profil ;
  - mode stage : niveau minimal lu par Python au-dessus de Bac+3, exigé ou
    souhaité (D202) ;
  - mode job : niveau minimal demandé au-dessus du maximum choisi dans le
    profil, exigé ou souhaité (D211) ;
  - modes stage et job : offre en alternance seulement.

raisons_sans_ia applique les mêmes règles à ce que Python lit seul, avant
tout appel à l'IA (D204).

Niveau du profil : champ niveau_etudes ; vide, niveau visé (alternance) ;
vide, déduit de la formation quand c'est sans ambiguïté (BUT1 = bac,
BUT2 = bac+2 en cours, BUT3 = bac+3...) ; sinon inconnu, et le profil
affiche un avertissement qui demande de le remplir.
"""

import re
from datetime import date, timedelta

from shared.stage import MOIS, date_en_lettres, lire_date

# Niveaux de l'énumération du schéma (shared/schemas_ia.py), en crans (bac = 0, bac+5 = 5)
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
# Bac+5 exigé sans mot d'exigence (D177) : stage de fin d'études, dernière année
# d'école d'ingénieurs ou de master, M2
BAC5_EXIGE = (r"stages? de fin d.[ée]tudes|derni[èe]re ann[ée]e (?:d.|de |du )(?:[ée]coles? d.ing[ée]nieurs?"
              r"|cycle d.ing[ée]nieurs?|ing[ée]nieurs?|master)")
M2 = r"\bm\s?2\b|master\s*2"
# M2 ou Master 2 n'est exigé que précédé de « en », « de », « niveau »,
# « étudiant(e) », « préparez », « préparant » (D180) : « dossiers d'entrée en
# Master 1 et Master 2 » d'un poste de scolarité n'exige rien
M2_EXIGE = re.compile(r"(?:\ben|\bde|\bniveau|[ée]tudiante?s?|pr[ée]parez|pr[ée]parant)\s+(?:(?:un|une|le|la|votre|son)\s+)?$")
INDICES_NIVEAU = [
    (BAC5_EXIGE + "|" + M2 + r"|bac\s*\+\s*5|[ée]coles? d.ing[ée]nieurs?|dipl[ôo]me d.ing[ée]nieurs?"
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
# Exigence explicite (D103) : sans l'un de ces mots près de l'indice, le niveau n'est que souhaité
MARQUEURS_EXIGENCE = re.compile(r"exig[ée]e?s?|obligatoires?|imp[ée]rati(?:f|fs|ve|ves|vement)|requise?s?"
                                r"|indispensables?")
FENETRE_SOUHAIT = (60, 120)                   # caractères avant et après l'indice de niveau
TOLERANCE_DUREE_MOIS = 0.5


def _texte(offre: dict) -> str:
    return (offre.get("description") or "").replace("’", "'")


def _indices(texte: str) -> list[tuple[tuple[int, int], set[str]]]:
    """Indices de niveau de la description : [(position, niveaux permis)]."""
    bas = texte.lower()
    trouves = [(m.span(), permis) for motif, permis in INDICES_NIVEAU for m in re.finditer(motif, bas)]
    trouves += [(m.span(), {"bac+2", "bac+3"}) for m in INDICE_BUT.finditer(texte)]
    return trouves


# ─── Diplôme demandé au candidat, ou objet d'une mission (D211) ───────────────
# Un indice de niveau ne compte que dans une phrase de recrutement ; « examens
# d'entrée en Master 1 », « scolarité de 4 masters » disent le travail, pas le niveau.
_FIN_PHRASE = re.compile(r"\n|[.!?;](?=\s|$)")
_RECRUTEMENT = re.compile(
    r"\bniveaux?\b|titulaire|dipl[ôo]m|formation|profil|\bvous\b|[ée]tudiant|requi[st]|souhait|exig|obligatoire"
    r"|indispensable|imp[ée]rati|minimum|id[ée]alement|appr[ée]ci|[ée]quivalent|pr[ée]par(?:ez|ant)|cursus|[ée]tudes"
    r"|[ée]l[èe]ves?\b|\bissue?s?\b|\b[ée]coles?\b|universit|dipl[ôo]mant|derni[èe]re ann[ée]e|fin d.[ée]tude|c[ée]sure")
# Objet d'une mission avant le diplôme, sans rien qui s'adresse au candidat
_OBJET_MISSION = re.compile(r"examens?|auditions?|concours|jurys?|scolarit[ée]|brochures?|dossiers?|inscriptions?"
                            r"|emplois? du temps|soutenances?|plaquettes?")
_CANDIDAT = re.compile(r"\bniveaux?\b|titulaire|dipl[ôo]m[é]e?s?\b|\bprofil|\bvous\b|[ée]tudiante?\b|requi[st]"
                       r"|souhait|exig|obligatoire|indispensable|imp[ée]rati|minimum|id[ée]alement|appr[ée]ci"
                       r"|pr[ée]par(?:ez|ant)")
# Ligne qui commence par le diplôme (« - BTS SIO », « CAP ou BTS ») : une exigence en liste
_DEBUT_LISTE = re.compile(r"(?:[^a-zà-ÿ]|\b(?:de|du|un|une|le|la|ou|et|à|en|cap|bep|bac|bts|dut|but|deug|licences?"
                          r"|bachelors?|masters?|m1|m2|msc)\b)*")


def _de_recrutement(texte: str, a: int, b: int) -> bool:
    """Le diplôme écrit en texte[a:b] est demandé au candidat : sa phrase est
    de recrutement, ou commence par lui ; pas l'objet d'une mission."""
    debut = max((m.end() for m in _FIN_PHRASE.finditer(texte, 0, a)), default=0)
    fin = _FIN_PHRASE.search(texte, b)
    phrase = texte[debut:fin.start() if fin else len(texte)].lower()
    avant = texte[debut:a].lower()
    if _DEBUT_LISTE.fullmatch(avant):
        return True
    if _OBJET_MISSION.search(avant) and not _CANDIDAT.search(phrase):
        return False
    return bool(_RECRUTEMENT.search(phrase))


def _indices_demandes(texte: str) -> list[tuple[tuple[int, int], set[str]]]:
    """Indices de niveau demandés au candidat."""
    return [(pos, permis) for pos, permis in _indices(texte) if _de_recrutement(texte, *pos)]


def niveaux_dans_texte(texte: str) -> tuple[set[str], list[tuple[int, int]]]:
    """(niveaux que la description permet, positions des indices)."""
    trouves = _indices_demandes(texte)
    return set().union(*(p for _, p in trouves)) if trouves else set(), [pos for pos, _ in trouves]


def _pres(motif, texte: str, positions) -> bool:
    avant, apres = FENETRE_SOUHAIT
    return any(motif.search(texte[max(0, a - avant):b + apres].lower()) for a, b in positions)


def exigence_detectee(texte: str, positions) -> str:
    """D103 : « exige » seulement si un marqueur clair (exigé, obligatoire,
    impératif, requis, indispensable) est proche d'un indice de niveau et
    qu'aucun marqueur de souhait (« ou équivalent »...) ne l'adoucit ;
    « souhaite » dans tous les autres cas."""
    if _pres(MARQUEURS_EXIGENCE, texte, positions) and not _pres(MARQUEURS_SOUHAIT, texte, positions):
        return "exige"
    # Stage de fin d'études, dernière année d'école d'ingénieurs ou de master : exigé (D177) ;
    # M2 seulement après « en », « de », « niveau », « étudiant », « préparez » (D180)
    bas = texte.lower()
    for a, b in positions:
        if re.fullmatch(BAC5_EXIGE, bas[a:b]):
            return "exige"
        if re.fullmatch(M2, bas[a:b]) and M2_EXIGE.search(bas[max(0, a - 40):a]):
            return "exige"
    return "souhaite"


def niveau_detecte(texte: str) -> tuple[str, str] | None:
    """(niveau, exigence) lus par Python dans la description, ou None sans
    indice. Chaque indice vaut son niveau le plus haut (« Master » = bac+5) ;
    plusieurs indices (« BTS ou licence ») : le plus bas, celui qui suffit.
    Exigence : exigence_detectee (exige seulement avec un marqueur clair)."""
    trouves = _indices_demandes(texte)
    if not trouves:
        return None
    niveau = min((max(permis, key=CRANS.get) for _, permis in trouves), key=CRANS.get)
    return niveau, exigence_detectee(texte, [pos for pos, _ in trouves])


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
    elif niveau == "non_precise" and (detecte := niveau_detecte(texte)):
        # Secours (D100) : le modèle n'a rien lu, mais la description contient un indice reconnu
        extraits["niveau_requis"], extraits["niveau_exigence"] = detecte
        ecartes.append(f"niveau_requis non_precise remplacé par {detecte[0]} ({detecte[1]}), lu dans l'offre")
        niveau = detecte[0]
    # L'exigence vient du texte, jamais du modèle seul (D103)
    extraits["niveau_exigence"] = "non_precise" if niveau == "non_precise" else exigence_detectee(texte, positions)
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


ECART_ALTERNANCE_PREPARE = 1      # crans au-dessus du niveau visé tolérés en alternance (D178)
# Diplôme préparé lu par Python (D195) : un indice de niveau dans la même phrase,
# peu après « préparation (du titre, du diplôme...) », « préparer »,
# « préparez », « préparant » ou « poursuivre vos études en »
DECLENCHEUR_PREPARE = re.compile(r"\bpr[ée]par(?:ation|er|ez|ant|e)\b|\bpoursuivre (?:vos|ses|tes|leurs|son|votre) [ée]tudes en\b")
FENETRE_PREPARE = 100


def niveau_prepare(texte: str) -> str | None:
    """Plus haut niveau du diplôme préparé que nomme la description
    (« préparation du titre Architecte des SI - Bac+5 », « poursuivre vos
    études en Bac+5 ») ; None sans mention. Fenêtre coupée à la fin de la
    phrase : « titulaire d'un Bac+3 » plus loin ne compte pas."""
    texte = texte.replace("’", "'")
    niveaux = []
    for m in DECLENCHEUR_PREPARE.finditer(texte.lower()):
        fenetre = texte[m.end():m.end() + FENETRE_PREPARE]
        fenetre = re.split(r"[.!?;]\s|\n|\*\*\*", fenetre)[0]
        niveaux += [max(permis, key=CRANS.get) for _, permis in _indices(fenetre)]
    return max(niveaux, key=CRANS.get) if niveaux else None


# Stage (D202) : 1re ou 2e année visée, 3e au plus. Un profil déjà au-dessus garde son niveau
NIVEAU_MAX_STAGE = 3


def niveau_trop_haut_stage(offre: dict, profil: dict) -> str:
    """Raison d'inéligibilité d'un stage dont le niveau minimal demandé
    (niveau_detecte : lu par Python, borne basse d'une fourchette, exigé ou
    souhaité) dépasse Bac+3 ; "" sinon, ou sans niveau écrit."""
    detecte = niveau_detecte(_texte(offre))
    if not detecte:
        return ""
    maximum = max(NIVEAU_MAX_STAGE, niveau_du_profil(profil)["crans"] or 0)
    crans = CRANS[detecte[0]]
    if crans <= maximum:
        return ""
    return f"{LIBELLES[crans]} {'exigé' if detecte[1] == 'exige' else 'souhaité'}, {LIBELLES[maximum]} au plus en stage"


# Job (D211) : « Niveau maximal demandé par l'offre » du profil, en crans ; vide : sans limite
NIVEAUX_MAX_OFFRE = {"aucun": (-3, "aucun diplôme"), "cap": (-1, "CAP/BEP"), "bac": (0, "Bac"), "bac+2": (2, "Bac+2"),
                     "bac+3": (3, "Bac+3"), "bac+5": (5, "Bac+5")}
# Sous le bac, que l'énumération de l'IA ne connaît pas : le bas d'une fourchette (« CAP à Bac+2 »)
_CAP_BEP = re.compile(r"\b(?:CAP|BEP)\b(?!\s+(?i:emploi))")       # en majuscules : pas « garder le cap »
_SANS_DIPLOME = re.compile(r"(?:sans|aucun) dipl[ôo]me|aucune formation scolaire"
                           r"|dipl[ôo]me (?:non|pas) (?:exig[ée]|requis|obligatoire|n[ée]cessaire)")
# Faux indices des offres de job : surface (« 500 m2 ») et licence d'un débit de boissons
_SURFACE = re.compile(r"\d\s*$")
_LICENCE_EXPLOITATION = re.compile(r"\s+(?:iv|4|de d[ée]bit|d.exploitation|de taxi)\b")


def niveau_minimal_job(texte: str) -> int | None:
    """Niveau minimal demandé par une offre de job, en crans : la lecture de
    niveau_detecte (borne basse, exigé ou souhaité), plus CAP/BEP et « sans
    diplôme », moins les faux indices du mode job. None sans niveau écrit."""
    bas = texte.lower()
    crans = []
    for (a, b), permis in _indices_demandes(texte):
        mot = bas[a:b]
        if re.fullmatch(r"m\s?2", mot) and _SURFACE.search(bas[:a]):
            continue
        if mot.startswith("licence") and _LICENCE_EXPLOITATION.match(bas[b:]):
            continue
        crans.append(max(CRANS[n] for n in permis))
    if any(_de_recrutement(texte, *m.span()) for m in _CAP_BEP.finditer(texte)):
        crans.append(-1)
    if _SANS_DIPLOME.search(bas):
        crans.append(-3)
    return min(crans) if crans else None


def niveau_trop_haut_job(offre: dict, profil: dict) -> str:
    """Raison d'inéligibilité d'une offre de job dont le niveau minimal demandé
    dépasse le maximum choisi dans le profil ; "" sinon, ou sans niveau écrit."""
    plafond = NIVEAUX_MAX_OFFRE.get(((profil or {}).get("recherche") or {}).get("niveau_max_offre") or "")
    crans = niveau_minimal_job(_texte(offre)) if plafond else None
    if crans is None or crans <= plafond[0]:
        return ""
    libelle = "CAP/BEP" if crans == -1 else LIBELLES[crans]
    return f"Niveau demandé trop élevé ({libelle} demandé, {plafond[1]} au plus)"


# ─── Ce que Python lit seul, sans l'IA (D204) ─────────────────────────────────
# Durée et début ne sont sûrs que dans une tournure qui ne peut désigner que le
# stage, sans mention contraire ailleurs dans le texte ; sinon l'IA les lit.
_DUREE = r"(\d+(?:[.,]\d+)?)\s*(?:(?:à|-|–|/|ou|et)\s*\d+(?:[.,]\d+)?\s*)?(mois|semaines?)\b"
_TOUTE_DUREE = re.compile(_DUREE)
_DUREE_SURE = re.compile(r"(?:\bstage(?: conventionné)?(?: d.une durée)? (?:de|:|-)\s*(?:entre )?"
                         r"|\bdurée(?: du stage| de stage)?\s*(?::|,|de)\s*(?:de |entre )?)" + _DUREE)
_PASSE = re.compile(r"exp[ée]rience|d[ée]j[àa]|effectu|premi[èe]re?|pr[ée]c[ée]dent|ancien|\bcdi\b|\bcdd\b")
_NOMS_MOIS = r"janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|d[ée]cembre"
_DEBUT_SUR = re.compile(r"(?:à partir d[eu']|à compter d[eu']|\bdès|\b(?:date de )?début(?: du stage)?\s*:|\bdémarrage\s*:"
                        r"|à pourvoir (?:en|début))\s*(?:le |en |début |du )?"
                        rf"((?:1er |\d{{1,2}} )?(?:{_NOMS_MOIS}) 20\d\d|\d{{1,2}}/\d{{1,2}}/20\d\d)")
_SOUPLE = re.compile(r"flexible|n[ée]gociable|modulable|adaptable|id[ée]alement|selon (?:vos|tes|les) disponibilit"
                     r"|\bou (?:" + _NOMS_MOIS + r")\b")


def _texte_plat(offre: dict) -> str:
    """Titre et description, sans les lignes « Expérience », en minuscules."""
    lignes = [l for l in _texte(offre).splitlines() if not l.strip().lower().startswith("expérience")]
    return " ".join(" ".join([(offre.get("titre") or "") + " .", *lignes]).lower().replace("’", "'").split())


def _en_mois(nombre: str, unite: str) -> float:
    n = float(nombre.replace(",", "."))
    return n if unite == "mois" else n / SEMAINES_PAR_MOIS


def duree_sure(offre: dict) -> float | None:
    """Durée du stage lue sans l'IA, en mois (borne basse d'une fourchette) :
    la plus courte de toutes les durées écrites, si l'une d'elles est dans
    une tournure sûre (« stage de 6 mois », « durée : 4 à 6 mois »). Une
    durée plus courte ailleurs (délai, expérience) l'emporte : jamais plus
    sévère que le texte."""
    texte = _texte_plat(offre)
    sure = any(not _PASSE.search(texte[max(0, m.start() - 60):m.start()]) for m in _DUREE_SURE.finditer(texte))
    if not sure:
        return None
    return min(_en_mois(*m.groups()) for m in _TOUTE_DUREE.finditer(texte))


def debut_sur(offre: dict) -> str | None:
    """Début du stage lu sans l'IA (« à partir de janvier 2027 ») : une seule
    date sûre, dans un texte qui n'offre pas de souplesse ; None sinon."""
    texte = _texte_plat(offre)
    if _SOUPLE.search(texte):
        return None
    dates = {m.group(1) for m in _DEBUT_SUR.finditer(texte)
             if not re.search(r"candidature|limite|alternance", texte[max(0, m.start() - 60):m.start()])}
    return dates.pop() if len(dates) == 1 else None


def _mois_du_profil_cites(offre: dict, debut: date, fin: date) -> bool:
    """Le texte nomme un mois de la période du profil (« entre janvier et avril ») : à lire par l'IA."""
    mois, jour = set(), debut
    while (jour.year, jour.month) <= (fin.year, fin.month):
        mois.add(MOIS[jour.month - 1])
        jour = date(jour.year + jour.month // 12, jour.month % 12 + 1, 1)
    texte = _texte_plat(offre)
    return any(re.search(rf"\b{m.replace('é', '[ée]').replace('û', '[ûu]')}\b", texte) for m in mois)


def extraits_python(offre: dict, profil: dict, mode: str) -> dict:
    """Champs que Python lit seul dans l'offre, au format de l'extraction de l'IA."""
    niveau, exigence = niveau_detecte(_texte(offre)) or ("non_precise", "non_precise")
    extraits = {"niveau_requis": niveau, "niveau_exigence": exigence, "duree_mois": None, "date_debut_offre": None,
                "alternance_seulement": False}
    if mode == "stage":
        extraits["duree_mois"] = duree_sure(offre)
        debut, fin = lire_date(profil.get("date_debut") or None), lire_date(profil.get("date_fin") or None)
        if debut and fin and not _mois_du_profil_cites(offre, debut, fin):
            extraits["date_debut_offre"] = debut_sur(offre)
    return extraits


def raisons_sans_ia(offre: dict, profil: dict, mode: str) -> list[str]:
    """Raisons d'inéligibilité que Python établit seul, avant tout appel à l'IA."""
    return raisons_ineligibilite(extraits_python(offre, profil, mode), profil, mode, offre)


def raisons_ineligibilite(extraits: dict, profil: dict, mode: str, offre: dict | None = None) -> list[str]:
    """Raisons d'inéligibilité établies en Python ; vide si rien ne bloque.
    offre : ses exigences structurées (permis, formation, expérience,
    certifications, shared/exigences.py, D169) comptent aussi."""
    raisons = []
    if offre is not None:
        from shared.exigences import raisons as raisons_exigences
        raisons += raisons_exigences(offre, profil, mode, niveau_du_profil(profil)["crans"])
    ecart = ecart_niveau(extraits, profil)
    niveau_bloque = bool(ecart and ecart[0] >= ECART_NIVEAU_BLOQUANT and extraits.get("niveau_exigence") == "exige")
    trop_haut_job = niveau_trop_haut_job(offre, profil) if mode == "job" and offre is not None else ""
    if trop_haut_job:
        raisons.append(trop_haut_job)
    elif niveau_bloque:
        raisons.append(f"{LIBELLES[ecart[1]]} exigé, profil {LIBELLES[ecart[2]]}")
    # Alternance : diplôme préparé à plus d'un niveau au-dessus du niveau visé (D178)
    if mode == "alternance" and not niveau_bloque:
        vise = crans_texte(profil.get("niveau_vise") or "")
        requis = CRANS.get(extraits.get("niveau_requis") or "non_precise")
        # Diplôme préparé lu par Python, sans dépendre de l'IA (D195) : le plus haut des deux
        prepare = CRANS.get(niveau_prepare(_texte(offre)) or "non_precise") if offre is not None else None
        if prepare is not None and (requis is None or prepare > requis):
            requis = prepare
        if requis is not None and vise and requis - max(vise) > ECART_ALTERNANCE_PREPARE:
            raisons.append(f"diplôme préparé {LIBELLES[requis]}, niveau visé {LIBELLES[max(vise)]}")
    if mode in ("stage", "job") and extraits.get("alternance_seulement"):
        raisons.append("offre en alternance seulement")
    if mode == "stage":
        if offre is not None and not niveau_bloque and (trop_haut := niveau_trop_haut_stage(offre, profil)):
            raisons.append(trop_haut)
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
