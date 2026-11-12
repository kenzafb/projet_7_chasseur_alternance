"""
shared/completude_profil.py
===========================
Complétude du profil d'un mode, en cinq parties (D144) : Toi, la partie
propre au mode, Ton parcours, Ce que tu cherches, Tes documents. Une partie
est complète quand ses champs obligatoires sont remplis ; sinon elle dit
en une ligne ce qui manque. Une suggestion (taille des entreprises) ne la
rend jamais incomplète.

Sert à l'Accueil (avancement du profil) et à la page Mon profil (état de
chaque partie).
"""

PARTIE_DU_MODE = {"stage": "Ton stage", "alternance": "Ton alternance", "job": "Ton job"}


def _rempli(valeur) -> bool:
    if isinstance(valeur, str):
        return bool(valeur.strip())
    return valeur not in (None, [], {}, "")


def _liste_naturelle(mots: list[str]) -> str:
    """« a », « a et b », « a, b et c »."""
    return mots[0] if len(mots) == 1 else ", ".join(mots[:-1]) + " et " + mots[-1]


def _manque(profil: dict, champs: list[tuple[str, str]]) -> list[str]:
    return [libelle for cle, libelle in champs if not _rempli(profil.get(cle))]


def _phrase(manquants: list[str]) -> str:
    return f"Il manque {_liste_naturelle(manquants)}." if manquants else ""


def _toi(profil: dict) -> list[str]:
    return _manque(profil, [("prenom", "ton prénom"), ("nom", "ton nom"), ("email", "ton email"),
                            ("telephone", "ton téléphone"), ("ville", "ta ville")])


def _partie_du_mode(profil: dict, mode: str) -> list[str]:
    recherche = profil.get("recherche") or {}
    if mode == "stage":
        return _manque(profil, [("date_debut", "la date de début"), ("date_fin", "la date de fin"),
                                ("etablissement", "ton école"), ("formation", "ta formation"),
                                ("missions", "les missions visées")])
    if mode == "alternance":
        manquants = _manque(profil, [("niveau_vise", "la formation visée")])
        manquants += _manque(recherche, [("rythme", "le rythme"), ("disponibilite", "la date de début")])
        return manquants
    return _manque(profil, [("dispo_horaires", "tes disponibilités"), ("duree_souhaitee", "la durée")])


def _parcours(profil: dict) -> list[str]:
    manquants = []
    competences = [c for c in (profil.get("competences") or []) if _rempli(c)]
    if len(competences) < 3:
        reste = 3 - len(competences)
        manquants.append(f"{reste} compétence{'s' if reste > 1 else ''} (3 au moins)")
    projets = [p for p in (profil.get("projets") or []) if isinstance(p, dict) and any(map(_rempli, p.values()))]
    if not projets and not _rempli(profil.get("experience")):
        manquants.append("un projet ou une expérience")
    return manquants


def _recherche(profil: dict) -> tuple[list[str], str]:
    recherche = profil.get("recherche") or {}
    manquants = []
    if not recherche.get("domaines") and recherche.get("domaines_indifferent") is not True:
        manquants.append("un domaine (ou « indifférent »)")
    if not recherche.get("departements"):
        manquants.append("un département")
    conseil = "" if recherche.get("tailles_spontanees") else \
        "Conseil : choisis la taille des entreprises à contacter (toutes sont gardées sinon)."
    return manquants, conseil


def _documents(profil: dict) -> list[str]:
    manquants = []
    if not profil.get("pieces_jointes"):
        manquants.append("ton CV")
    if "{paragraphe}" not in (profil.get("lettre_type") or ""):
        manquants.append("une lettre type avec {paragraphe}")
    return manquants


def completude(profil: dict, mode: str) -> dict:
    """{parties: [{id, titre, complet, manque, conseil}], completes, total}.
    manque : une ligne, vide si la partie est complète."""
    profil = profil or {}
    manquants_recherche, conseil = _recherche(profil)
    parties = [
        ("toi", "Toi", _toi(profil), ""),
        ("mode", PARTIE_DU_MODE.get(mode, "Ta recherche"), _partie_du_mode(profil, mode), ""),
        ("parcours", "Ton parcours", _parcours(profil), ""),
        ("recherche", "Ce que tu cherches", manquants_recherche, conseil),
        ("documents", "Tes documents", _documents(profil), ""),
    ]
    sortie = [{"id": ident, "titre": titre, "complet": not manquants, "manque": _phrase(manquants),
               "conseil": conseil_partie}
              for ident, titre, manquants, conseil_partie in parties]
    return {"parties": sortie, "completes": sum(p["complet"] for p in sortie), "total": len(sortie)}
