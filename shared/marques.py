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
d'alternance (est_organisme_verifie).
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

FICHIER = Path(__file__).resolve().parent / "referentiels" / "organismes_formation.txt"

NIVEAU_DIFFERENT = "niveau_different"
ORGANISME_FORMATION = "organisme_formation"
MARQUES = {
    NIVEAU_DIFFERENT: "Niveau différent du tien",
    ORGANISME_FORMATION: "Offre déposée par un organisme de formation",
}
CHAMPS = ("titre", "entreprise", "description")


def simplifier(texte) -> str:
    """Minuscules, sans accents, apostrophes droites."""
    texte = unicodedata.normalize("NFKD", str(texte or "")).replace("’", "'")
    return "".join(c for c in texte if not unicodedata.combining(c)).lower()


@lru_cache(maxsize=1)
def liste() -> tuple[tuple[tuple[str, re.Pattern], ...], tuple[tuple[str, re.Pattern], ...]]:
    """((nom, motif) des organismes vérifiés, (mot, motif) des indices)."""
    verifies, indices = [], []
    for ligne in FICHIER.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        signe, _, nom = ligne.partition(" ")
        nom = simplifier(nom.strip())
        if signe not in ("+", "?") or not nom:
            raise ValueError(f"{FICHIER.name} : ligne illisible « {ligne} »")
        motif = re.compile(r"(?<![\w])" + re.escape(nom).replace(r"\ ", r"[\s-]+") + r"(?![\w])")
        (verifies if signe == "+" else indices).append((nom, motif))
    return tuple(verifies), tuple(indices)


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


def ajouter_marque(offre: dict, cle: str) -> dict:
    marques = list(offre.get("marques") or [])
    if cle not in marques:
        marques.append(cle)
    offre["marques"] = marques
    return offre


def etiquettes(offre: dict) -> list[str]:
    """Textes affichés sur l'offre : ses marques, puis les indices d'école."""
    out = [MARQUES[m] for m in offre.get("marques") or [] if m in MARQUES]
    if ORGANISME_FORMATION not in (offre.get("marques") or []) and (mots := indices_ecole(offre)):
        out.append("Indice d'école ou de CFA : « " + " », « ".join(mots) + " »")
    return out
