"""
shared/balises_mail.py
======================
Balises de l'objet et de la trame du mail de candidature spontanée
(phase 6b), remplacées à l'envoi par les valeurs du profil du mode :

  tous les modes : {prenom} {nom} {telephone} {email} {date} (date du jour)
  mode stage     : {date_debut} {date_fin} {duree_semaines} {etablissement}
                   {formation} {missions} {portfolio}

Comme pour la lettre type, les espaces dans une balise sont tolérés
(« { date } ») et toute autre accolade est refusée avec un message lisible :
à l'enregistrement du profil, et avant le premier envoi. Une balise
employée dont la valeur est vide dans le profil (dates du stage non
remplies, par exemple) bloque l'envoi avant le premier mail, plutôt que
de partir avec un trou dans le texte.
"""

import re

from database.dates import maintenant_affichage
from shared.erreurs import ErreurUtilisateur
from shared.stage import date_en_lettres, duree_semaines, lire_date

BALISES_COMMUNES = ("prenom", "nom", "telephone", "email", "date")
BALISES_STAGE = ("date_debut", "date_fin", "duree_semaines", "etablissement", "formation", "missions",
                 "portfolio")
BALISES_PAR_MODE = {"stage": BALISES_COMMUNES + BALISES_STAGE}

_BALISE = re.compile(r"\{\s*([A-Za-z_]*)\s*\}")


def balises_du_mode(mode: str) -> tuple[str, ...]:
    return BALISES_PAR_MODE.get(mode, BALISES_COMMUNES)


def _liste(mode: str) -> str:
    return ", ".join("{" + b + "}" for b in balises_du_mode(mode))


def verifier_balises(texte: str, mode: str) -> list[str]:
    """Balises employées dans texte, dans l'ordre ; ErreurUtilisateur (400)
    pour une balise inconnue du mode ou une accolade isolée."""
    permises = balises_du_mode(mode)
    employees = []
    for m in _BALISE.finditer(texte or ""):
        if m.group(1) not in permises:
            raise ErreurUtilisateur(
                f"Balise inconnue dans l'objet ou le message du mail : {m.group(0)}. "
                f"Balises possibles dans ce mode : {_liste(mode)}.")
        if m.group(1) not in employees:
            employees.append(m.group(1))
    if re.search(r"[{}]", _BALISE.sub("", texte or "")):
        raise ErreurUtilisateur(
            "L'objet ou le message du mail contient une accolade { ou } isolée. "
            f"Seules les balises {_liste(mode)} sont permises.")
    return employees


def _date_du_jour() -> str:
    return date_en_lettres(maintenant_affichage().date())


def valeurs(profil: dict, mode: str) -> dict[str, str]:
    """Valeur de chaque balise du mode, d'après le profil (lire_profil)."""
    out = {
        "prenom": profil.get("prenom") or "",
        "nom": profil.get("nom") or "",
        "telephone": profil.get("telephone") or "",
        "email": profil.get("email") or "",
        "date": _date_du_jour(),
    }
    if "date_debut" in balises_du_mode(mode):
        debut, fin = lire_date(profil.get("date_debut")), lire_date(profil.get("date_fin"))
        duree = duree_semaines(debut, fin)
        out.update({
            "date_debut": date_en_lettres(debut),
            "date_fin": date_en_lettres(fin),
            "duree_semaines": str(duree) if duree else "",
            "etablissement": profil.get("etablissement") or "",
            "formation": profil.get("formation") or "",
            "missions": profil.get("missions") or "",
            "portfolio": profil.get("portfolio") or "",
        })
    return {k: str(v).strip() for k, v in out.items()}


LIBELLES = {
    "prenom": "ton prénom", "nom": "ton nom", "telephone": "ton téléphone", "email": "ton email de contact",
    "date_debut": "la date de début du stage", "date_fin": "la date de fin du stage",
    "duree_semaines": "les dates du stage (la durée en découle)", "etablissement": "ton établissement",
    "formation": "ta formation", "missions": "les missions visées", "portfolio": "le lien de ton portfolio",
}


def remplir(texte: str, profil: dict, mode: str) -> str:
    """texte avec ses balises remplacées. ErreurUtilisateur si une balise est
    inconnue ou si sa valeur est vide dans le profil."""
    employees = verifier_balises(texte, mode)
    vals = valeurs(profil, mode)
    vides = [b for b in employees if not vals.get(b)]
    if vides:
        raise ErreurUtilisateur(
            "Le mail de candidature emploie " + ", ".join("{" + b + "}" for b in vides)
            + " mais le profil ne le renseigne pas : complète "
            + ", ".join(dict.fromkeys(LIBELLES.get(b, b) for b in vides)) + " dans l'onglet Profil.")
    return _BALISE.sub(lambda m: vals[m.group(1)], texte or "")
