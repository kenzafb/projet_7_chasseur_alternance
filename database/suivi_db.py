"""
database/suivi_db.py
====================
Tableau de suivi unique des candidatures d'un utilisateur dans un mode
(D107) : les offres où la personne a postulé (candidatures, statut de
suivi) et les candidatures spontanées envoyées (entreprises_modes,
statut_suivi). Une seule notion de candidature : chaque ligne est lue dans
sa table d'origine, rien n'est recopié ; un changement de statut est écrit
là où la candidature vit.

Statuts de suivi communs (ceux qui existaient déjà) : envoye (offre
postulée ou mail envoyé), a_relancer, reponse, entretien, refus, et bounce
(mail revenu, spontanées seulement). « À relancer » est aussi calculé : une
candidature encore « envoye » depuis au moins 7 jours s'affiche à relancer.
"""

from datetime import date as Date, datetime, time, timedelta

from database.candidatures_db import lire_candidature, lire_candidatures, modifier_candidature
from database.dates import fuseau_affichage, maintenant_utc
from database.entreprises_db import lire_entreprises_envoyees, modifier_statut_suivi

STATUTS_SUIVI = ("envoye", "a_relancer", "reponse", "entretien", "refus", "bounce")
STATUTS_OFFRE = ("envoye", "a_relancer", "reponse", "entretien", "refus")   # pas de bounce sans mail
DELAI_RELANCE = timedelta(days=7)
OFFRE, SPONTANEE = "offre", "spontanee"


def _offres(user_id: int, mode: str) -> list[dict]:
    maintenant = maintenant_utc()
    lignes = []
    for o in lire_candidatures(user_id, mode=mode):
        if o.get("statut") not in STATUTS_OFFRE:
            continue
        statut = o["statut"]
        date = o.get("date_candidature") or ""
        if statut == "envoye" and date:
            instant = datetime.combine(Date.fromisoformat(date), time(12), tzinfo=fuseau_affichage())
            if maintenant - instant >= DELAI_RELANCE:
                statut = "a_relancer"
        lignes.append({"type": OFFRE, "id": o["id"], "entreprise": o.get("entreprise") or "",
                       "poste": o.get("titre") or "", "date": date, "statut": statut,
                       "lien": o.get("lien") or "", "contact": o.get("email_candidature") or "",
                       "lettre": bool(o.get("lettre"))})
    return lignes


def _spontanees(user_id: int, mode: str) -> list[dict]:
    lignes = []
    for e in lire_entreprises_envoyees(user_id, mode):   # « à relancer » déjà calculé
        site = e.get("site_web") or e.get("url_scrapee") or ""
        lignes.append({"type": SPONTANEE, "id": str(e["_id"]),
                       "entreprise": e.get("nom_commercial") or e.get("nom") or "",
                       "poste": "Candidature spontanée", "date": (e.get("mail_envoye_le") or "").split(" ")[0],
                       "statut": e.get("statut_suivi") or "envoye",
                       "lien": site if not site or "://" in site else "https://" + site,
                       "contact": ", ".join(e.get("mail_destinataires") or e.get("emails_trouves") or []),
                       "historique": bool(e.get("historique")),
                       "contacts_autres_modes": e.get("contacts_autres_modes") or []})
    return lignes


def lire_suivi(user_id: int, mode: str) -> list[dict]:
    """Toutes les candidatures du mode, les plus récentes d'abord (sans date à la fin)."""
    lignes = _offres(user_id, mode) + _spontanees(user_id, mode)
    lignes.sort(key=lambda l: (bool(l["date"]), l["date"]), reverse=True)
    return lignes


def modifier_statut(user_id: int, mode: str, type_: str, ident: str, statut: str) -> bool:
    """Change le statut de suivi d'une candidature dans sa table d'origine.
    False si la candidature n'est pas à l'utilisateur dans ce mode, ou si le
    statut ne vaut pas pour ce type."""
    if type_ == OFFRE:
        offre = lire_candidature(user_id, ident, mode=mode)
        if statut not in STATUTS_OFFRE or not offre or offre.get("statut") not in STATUTS_OFFRE:
            return False
        return modifier_candidature(user_id, ident, {"statut": statut}, mode=mode)
    if type_ == SPONTANEE and statut in STATUTS_SUIVI and str(ident).isdigit():
        return modifier_statut_suivi(user_id, int(ident), statut, mode)
    return False

