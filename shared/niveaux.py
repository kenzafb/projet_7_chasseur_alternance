"""
shared/niveaux.py
=================
Niveau de diplôme visé du profil (champ libre « niveau_vise » : « Bac+2 »,
« BTS SIO », « Master 2 »...) converti en niveau du cadre national des
certifications, celui qu'utilise La Bonne Alternance :
  3 CAP, BEP ; 4 bac ; 5 bac+2 (BTS, DUT) ; 6 bac+3 et bac+4 (licence,
  BUT, bachelor) ; 7 bac+5 (master, ingénieur).

Texte vide ou non reconnu : None (aucun filtre de niveau). Si plusieurs
niveaux sont écrits (« Bac+2 à Bac+3 »), le premier compte.
"""

import re
import unicodedata

NIVEAUX = {3: "CAP, BEP", 4: "Bac", 5: "Bac+2", 6: "Bac+3 ou Bac+4", 7: "Bac+5"}

_BAC_PLUS = {0: 4, 1: 5, 2: 5, 3: 6, 4: 6}   # bac+N ; 5 et plus : 7

# (motif, niveau) ; le motif le plus tôt dans le texte l'emporte, à
# position égale le premier de la liste (« bac+2 » avant « bac »)
_MOTIFS = [
    (r"\bbac\s*\+\s*(\d)", None),                    # bac+N, niveau calculé
    (r"\bniveau\s*([3-8])\b", None),                  # « niveau 6 », niveau direct
    (r"\b(master|mastere|msc|mba|ingenieur|doctorat|phd)\b", 7),
    (r"\b(licence|bachelor|but)\b", 6),
    (r"\b(bts|dut|bac\s*\+\s*deux)\b", 5),
    (r"\b(bac\s*pro|baccalaureat|bac|brevet professionnel)\b", 4),
    (r"\b(cap|bep)\b", 3),
]


def _sans_accents(texte: str) -> str:
    texte = unicodedata.normalize("NFD", texte)
    return "".join(c for c in texte if unicodedata.category(c) != "Mn").lower()


def niveau_europeen(texte) -> int | None:
    """Niveau 3 à 7 d'un niveau visé écrit librement, None si non reconnu."""
    texte = _sans_accents(str(texte or ""))
    trouves = []
    for rang, (motif, niveau) in enumerate(_MOTIFS):
        m = re.search(motif, texte)
        if not m:
            continue
        if niveau is None:
            n = int(m.group(1))
            niveau = (_BAC_PLUS.get(n, 7) if "bac" in m.group(0) else min(max(n, 3), 7))
        trouves.append((m.start(), rang, niveau))
    return min(trouves)[2] if trouves else None
