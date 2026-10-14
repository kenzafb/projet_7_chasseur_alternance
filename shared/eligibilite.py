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

Règles (une information non précisée ne rend jamais inéligible) :
  - niveau requis supérieur au niveau du profil d'au moins deux crans ;
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
    requis = CRANS.get(extraits.get("niveau_requis") or "non_precise")
    profil_crans = niveau_du_profil(profil)["crans"]
    if requis is not None and profil_crans is not None and requis - profil_crans >= ECART_NIVEAU_BLOQUANT:
        raisons.append(f"{LIBELLES[requis]} exigé, profil {LIBELLES[profil_crans]}")
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
