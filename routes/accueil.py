"""
routes/accueil.py
=================
Accueil d'un mode (D144) : salutation, ce qui attend (offres bien notées,
candidatures à relancer, offres à noter), la recherche en bref et
l'avancement du profil, en une requête.
"""

from datetime import date as Date

from fastapi import Depends

from auth.securite import utilisateur_requis
from database.candidatures_db import compter_en_attente, lire_candidatures
from database.dates import maintenant_affichage
from database.models import User
from database.profil_db import lire_profil
from database.suivi_db import lire_suivi
from offres.analyse import VERDICT_NON_ANALYSEE
from offres.analyse_differee import estimation_file
from routes.commun import mode_requis, routeur_prive
from shared import config
from shared.completude_profil import completude

router = routeur_prive()

# Note à partir de laquelle une offre « correspond bien » (vert, DESIGN.md)
NOTE_BIEN = 6
# Offres encore à regarder : ni gardées, ni écartées, ni postulées
STATUTS_A_VOIR = ("nouveau", "en_cours", "", None)
STATUTS_REPONSE = ("reponse", "entretien", "refus", "acceptee")
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre")


def date_en_lettres(texte: str, annee: bool = True) -> str:
    """« 2027-02-08 » -> « 8 février 2027 » (ou « 8 février ») ; vide si illisible."""
    try:
        jour = Date.fromisoformat(str(texte)[:10])
    except ValueError:
        return ""
    sortie = f"{'1er' if jour.day == 1 else jour.day} {MOIS[jour.month - 1]}"
    return f"{sortie} {jour.year}" if annee else sortie


def salutation(heure: int) -> str:
    return "Bonjour" if 5 <= heure < 18 else "Bonsoir"


def phrase_du_mode(profil: dict, mode: str) -> str:
    """Rappel de ce que la personne cherche, d'après son profil."""
    recherche = profil.get("recherche") or {}
    if mode == "stage" and profil.get("date_debut") and profil.get("date_fin"):
        return f"Ton stage : du {date_en_lettres(profil['date_debut'], annee=False)} " \
               f"au {date_en_lettres(profil['date_fin'])}."
    if mode == "alternance" and (recherche.get("disponibilite") or "").strip():
        return f"Ton alternance : à partir de {recherche['disponibilite'].strip()}."
    if mode == "job" and (profil.get("duree_souhaitee") or "").strip():
        return f"Ton job : {profil['duree_souhaitee'].strip()}."
    return ""


def _offres_bien_notees(offres: list[dict]) -> dict | None:
    bonnes = sorted((o for o in offres if o.get("statut") in STATUTS_A_VOIR
                     and o.get("verdict") != VERDICT_NON_ANALYSEE and (o.get("score") or 0) >= NOTE_BIEN),
                    key=lambda o: -(o.get("score") or 0))
    if not bonnes:
        return None
    meilleure = bonnes[0]
    titre = "Une offre te correspond bien" if len(bonnes) == 1 else f"{len(bonnes)} offres te correspondent bien"
    return {"genre": "offre", "id": meilleure["id"], "titre": titre,
            "texte": f"{meilleure.get('titre') or 'Offre sans titre'}, notée {meilleure.get('score')}/10. "
                     "Prépare ta lettre et postule.",
            "bouton": "Voir l'offre", "page": "offres"}


def _relances(suivi: list[dict]) -> dict | None:
    a_relancer = [c for c in suivi if c.get("statut") == "a_relancer"]
    if not a_relancer:
        return None
    if len(a_relancer) == 1:
        c = a_relancer[0]
        quand = date_en_lettres(c.get("date") or "", annee=False)
        return {"genre": "relance", "id": c["id"], "titre": f"Relance {c.get('entreprise') or 'cette entreprise'}",
                "texte": (f"Tu as postulé le {quand} " if quand else "Tu as postulé ")
                         + "et tu n'as pas eu de réponse. Un petit mail suffit.",
                "bouton": "Voir la candidature", "page": "candidatures"}
    return {"genre": "relance", "id": "", "titre": f"{len(a_relancer)} candidatures à relancer",
            "texte": "Pas de réponse depuis une semaine ou plus. Un petit mail suffit.",
            "bouton": "Voir les candidatures", "page": "candidatures"}


def _a_noter(user_id: int, mode: str) -> dict | None:
    if not config.analyse_ia_active():
        return None
    n = compter_en_attente(user_id, mode)
    if not n:
        return None
    titre = "1 nouvelle offre à noter" if n == 1 else f"{n} nouvelles offres à noter"
    return {"genre": "a_noter", "id": "", "nombre": n, "titre": titre,
            "texte": f"Le Chasseur les lit et te dit si elles te correspondent. {estimation_file(n)['texte'].capitalize()}.",
            "bouton": "Les noter", "page": "offres"}


@router.get("/api/accueil")
def api_accueil(user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    profil = lire_profil(user.id, mode=mode)
    offres = lire_candidatures(user.id, mode=mode)
    suivi = lire_suivi(user.id, mode)
    a_faire = [x for x in (_offres_bien_notees(offres), _relances(suivi), _a_noter(user.id, mode)) if x]
    return {
        "salutation": salutation(maintenant_affichage().hour),
        "prenom": (profil.get("prenom") or "").strip(),
        "phrase": phrase_du_mode(profil, mode),
        "a_faire": a_faire,
        "en_bref": {"offres_a_regarder": sum(o.get("statut") in STATUTS_A_VOIR for o in offres),
                    "candidatures_envoyees": len(suivi),
                    "reponses_recues": sum(c.get("statut") in STATUTS_REPONSE for c in suivi)},
        "profil": completude(profil, mode),
    }
