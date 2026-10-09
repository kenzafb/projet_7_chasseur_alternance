"""
shared/stage.py
===============
Dates du profil de stage (phase 6b) : lecture, durée en semaines, écriture
en toutes lettres pour le mail de candidature spontanée.

Les dates du stage sont des jours du calendrier (« 2027-01-04 »), pas des
instants : aucun fuseau n'intervient.

Durée : jours du premier au dernier jour compris, divisés par 7, arrondis
à la semaine la plus proche (une demi-semaine compte pour une semaine),
au moins 1. Du lundi 4 janvier au vendredi 25 juin 2027 : 173 jours,
25 semaines.
"""

from datetime import date

from shared.erreurs import ErreurUtilisateur

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def lire_date(valeur, champ: str = "date") -> date | None:
    """« AAAA-MM-JJ » (champ date du formulaire) ou date -> date ; vide -> None.
    Autre chose : ErreurUtilisateur (400) avec un message lisible."""
    if valeur is None or isinstance(valeur, date):
        return valeur
    texte = str(valeur).strip()
    if not texte:
        return None
    try:
        return date.fromisoformat(texte)
    except ValueError:
        raise ErreurUtilisateur(f"{champ} invalide : « {texte[:20]} » (format attendu AAAA-MM-JJ).") from None


def verifier_periode(debut: date | None, fin: date | None):
    """Refuse une fin antérieure au début (400)."""
    if debut and fin and fin < debut:
        raise ErreurUtilisateur("La date de fin du stage est antérieure à sa date de début.")


def duree_semaines(debut: date | None, fin: date | None) -> int | None:
    """Durée du stage en semaines (règle en tête du module), None sans les deux dates."""
    if not (debut and fin) or fin < debut:
        return None
    jours = (fin - debut).days + 1
    return max(1, (jours + 3) // 7)


def date_en_lettres(jour: date | None) -> str:
    """« 4 janvier 2027 », « 1er février 2027 » ; vide sans date."""
    if not jour:
        return ""
    return f"{'1er' if jour.day == 1 else jour.day} {MOIS[jour.month - 1]} {jour.year}"
