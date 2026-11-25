"""
shared/marques.py
=================
Marques posées sur une offre par la recherche (colonne candidatures.marques,
D154) et indices affichés, sans effet sur l'archivage :

  - niveau_different : offre La Bonne Alternance d'un niveau adjacent au
    niveau visé du profil (visé ± 1, D154) ;
  - organisme_formation : offre La Bonne Alternance déposée par un organisme
    de formation pour une entreprise (is_delegated, D155) ;
  - indices école ou CFA : mots génériques du fichier
    shared/referentiels/organismes_formation.txt (« ? »), cherchés à la
    lecture dans le titre et le nom de l'entreprise (D156).

Les organismes vérifiés du même fichier (« + ») archivent une offre
d'alternance ; les intermédiaires (« = », CAPIVISION) la marquent
organisme_formation sans l'archiver (D156).
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

FICHIER = Path(__file__).resolve().parent / "referentiels" / "organismes_formation.txt"

NIVEAU_DIFFERENT = "niveau_different"
ORGANISME_FORMATION = "organisme_formation"
# Posée par l'analyse (D189) : « description_coupee:<caractères lus> »
DESCRIPTION_COUPEE = "description_coupee"
# Stage hors informatique d'après son code métier ROME (D203)
HORS_INFORMATIQUE = "hors_informatique"
MARQUES = {
    HORS_INFORMATIQUE: "Hors informatique (code métier)",
    NIVEAU_DIFFERENT: "Niveau différent du tien",
    ORGANISME_FORMATION: "Offre déposée par un organisme de formation",
}
CHAMPS = ("titre", "entreprise", "description")


def simplifier(texte) -> str:
    """Minuscules, sans accents, apostrophes droites."""
    texte = unicodedata.normalize("NFKD", str(texte or "")).replace("’", "'")
    return "".join(c for c in texte if not unicodedata.combining(c)).lower()


@lru_cache(maxsize=1)
def liste() -> tuple:
    """((nom, motif) des organismes vérifiés, (mot, motif) des indices,
    (nom, motif) des intermédiaires à marquer)."""
    verifies, indices, a_marquer = [], [], []
    for ligne in FICHIER.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        signe, _, nom = ligne.partition(" ")
        nom = simplifier(nom.strip())
        if signe not in ("+", "?", "=") or not nom:
            raise ValueError(f"{FICHIER.name} : ligne illisible « {ligne} »")
        motif = re.compile(r"(?<![\w])" + re.escape(nom).replace(r"\ ", r"[\s-]+") + r"(?![\w])")
        {"+": verifies, "?": indices, "=": a_marquer}[signe].append((nom, motif))
    return tuple(verifies), tuple(indices), tuple(a_marquer)


def _trouves(offre: dict, motifs, champs=CHAMPS) -> list[str]:
    textes = [simplifier(offre.get(c)) for c in champs]
    return [nom for nom, motif in motifs if any(motif.search(t) for t in textes)]


def organismes_verifies(offre: dict) -> list[str]:
    """Organismes vérifiés nommés par l'offre (titre, entreprise, description)."""
    return _trouves(offre, liste()[0])


def indices_ecole(offre: dict) -> list[str]:
    """Mots génériques d'école ou de CFA trouvés dans le titre ou le nom de
    l'entreprise (indices affichés ; dans la description, « école » et « CFA »
    sont dans presque toutes les offres d'alternance)."""
    return _trouves(offre, liste()[1], ("titre", "entreprise"))


def intermediaires(offre: dict) -> list[str]:
    """Intermédiaires d'écoles (« = » du fichier) nommés par l'offre."""
    return _trouves(offre, liste()[2])


def marquer_intermediaire(offre: dict) -> dict:
    """Offre d'un intermédiaire d'école (CAPIVISION...) : marquée
    organisme_formation, donc jamais écartée « École ou CFA » (D156)."""
    if intermediaires(offre):
        ajouter_marque(offre, ORGANISME_FORMATION)
    return offre


def ajouter_marque(offre: dict, cle: str) -> dict:
    marques = list(offre.get("marques") or [])
    if cle not in marques:
        marques.append(cle)
    offre["marques"] = marques
    return offre


def marquer_description_coupee(offre: dict, lus: int | None) -> dict:
    """Pose (lus : caractères lus par l'IA pour la note) ou retire la marque
    de description coupée : une nouvelle analyse la remet à jour."""
    marques = [m for m in offre.get("marques") or [] if not str(m).startswith(DESCRIPTION_COUPEE)]
    offre["marques"] = marques + ([f"{DESCRIPTION_COUPEE}:{lus}"] if lus else [])
    return offre


def _milliers(n: int) -> str:
    return f"{n:,}".replace(",", "\u202f")


def etiquettes(offre: dict) -> list[str]:
    """Textes affichés sur l'offre : ses marques, puis les indices d'école."""
    out = [MARQUES[m] for m in offre.get("marques") or [] if m in MARQUES]
    for m in offre.get("marques") or []:
        if str(m).startswith(DESCRIPTION_COUPEE + ":") and str(m).split(":", 1)[1].isdigit():
            total = len(" ".join(str(offre.get("description") or "").split()))
            out.append(f"Description longue : l'IA en a lu les {_milliers(int(m.split(':', 1)[1]))} premiers "
                       f"caractères sur {_milliers(total)} pour la note")
    if ORGANISME_FORMATION not in (offre.get("marques") or []) and (mots := indices_ecole(offre)):
        out.append("Indice d'école ou de CFA : « " + " », « ".join(mots) + " »")
    return out
