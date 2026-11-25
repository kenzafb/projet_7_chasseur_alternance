"""
shared/domaines_experience.py
=============================
Domaine d'expérience qu'une offre exige, rapproché des domaines du profil job
(« Mon expérience par domaine », D211). Correspondance faite en Python avec
les synonymes de shared/referentiels/domaines_experience.txt, jamais par l'IA.
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

FICHIER = Path(__file__).resolve().parent / "referentiels" / "domaines_experience.txt"


def simplifier(texte) -> str:
    texte = unicodedata.normalize("NFKD", str(texte or "")).replace("’", "'")
    return "".join(c for c in texte if not unicodedata.combining(c)).lower()


def _motif(synonymes: list[str]) -> re.Pattern:
    """Synonymes en mots entiers, chaque mot au singulier ou au pluriel."""
    noms = sorted(synonymes, key=len, reverse=True)
    motifs = [r"[\s-]+".join(re.escape(mot) + ("" if mot.endswith(("s", "x")) else "s?")
                             for mot in re.split(r"[\s-]+", nom)) for nom in noms]
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(motifs) + r")(?![a-z0-9])")


@lru_cache(maxsize=1)
def referentiel() -> dict[str, tuple[str, re.Pattern]]:
    """{clé: (libellé, motif des synonymes)}, dans l'ordre du fichier."""
    out = {}
    for ligne in FICHIER.read_text(encoding="utf-8").splitlines():
        if not ligne.strip() or ligne.startswith("#"):
            continue
        cle, libelle, synonymes = (x.strip() for x in ligne.split("|"))
        out[cle] = (libelle, _motif([simplifier(s).strip() for s in synonymes.split(",") if s.strip()]))
    return out


def options() -> list[dict]:
    """Domaines proposés dans le profil."""
    return [{"cle": c, "libelle": libelle} for c, (libelle, _) in referentiel().items()]


def normaliser(valeurs) -> list[dict]:
    """[{domaine, mois}] propre : domaines connus, 1 à 600 mois ; un domaine
    en double garde la durée la plus longue."""
    mois_par_domaine = {}
    for v in valeurs if isinstance(valeurs, (list, tuple)) else []:
        if not isinstance(v, dict) or v.get("domaine") not in referentiel():
            continue
        try:
            mois = int(str(v.get("mois")).strip())
        except ValueError:
            continue
        if 1 <= mois <= 600:
            mois_par_domaine[v["domaine"]] = max(mois, mois_par_domaine.get(v["domaine"], 0))
    return [{"domaine": d, "mois": m} for d, m in mois_par_domaine.items()]


# Mots qui ne nomment pas un domaine (« expérience exigée sur un poste similaire »)
_GENERIQUES = set("""
a an ans annee annees au aux avec ce cet cette comme d dans de des domaine domaines du emploi en et etre exige exigee
experience experiences fonction fonctions identique identiques indispensable l la le les meme memes metier metiers
minimum mini mois moins notre ou plus poste postes premier premiere professionnel professionnelle que requis requise
reussie s secteur secteurs significative similaire similaires equivalent equivalente equivalents sur tant type types
un une activite activites confirmee demandee obligatoire acquise
""".split())


def classer(texte: str, titre: str = "") -> tuple[set[str], bool]:
    """(domaines reconnus, domaine précisé ?) du domaine exigé écrit dans
    l'offre. Rien d'écrit, ou que des mots généraux (« poste similaire ») : le
    domaine est celui de l'intitulé, s'il est reconnu, sinon non précisé. Un
    domaine écrit mais inconnu du référentiel est précisé, sans domaine reconnu."""
    t = simplifier(texte)
    reconnus = {c for c, (_, motif) in referentiel().items() if motif.search(t)}
    if reconnus:
        return reconnus, True
    if [m for m in re.findall(r"[a-z]+", t) if m not in _GENERIQUES]:
        return set(), True
    du_titre = {c for c, (_, motif) in referentiel().items() if motif.search(simplifier(titre))}
    return du_titre, bool(du_titre)
