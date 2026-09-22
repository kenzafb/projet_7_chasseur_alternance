"""
database/entreprises_db.py
==========================
Couche d'accès aux entreprises EN BASE, par utilisateur.
Pour l'instant : LECTURE SEULE (stats + listing).
Le JSON entreprises reste la source d'écriture (scraper/envoyeur/crontab)
jusqu'à ce qu'on raccorde ces pipelines plus tard, en sécurité.
"""

from database.connexion import SessionLocal
from database.models import Entreprise


def calculer_stats(user_id: int) -> dict:
    """Statistiques globales des entreprises d'un utilisateur (lecture seule)."""
    db = SessionLocal()
    try:
        q = db.query(Entreprise).filter_by(user_id=user_id)
        toutes = q.all()
        raw         = len(toutes)
        avec_email  = sum(1 for e in toutes if e.emails_trouves)
        mail_envoye = sum(1 for e in toutes if e.mail_envoye)

        # 5 dernières entreprises contactées
        recentes = [e for e in toutes if e.mail_envoye][-5:]
        dernieres = [
            {
                "nom":    (e.nom_commercial or "?")[:40],
                "ville":  e.ville or "",
                "email":  (e.emails_trouves or [""])[0] if e.emails_trouves else "",
                "envoye": bool(e.mail_envoye),
                "date":   e.mail_envoye_le or "",
            }
            for e in recentes
        ]
        return {
            "raw": raw,
            "avec_email": avec_email,
            "mail_generee": 0,   # champ historique, plus suivi en base
            "mail_envoye": mail_envoye,
            "dernieres": dernieres,
        }
    finally:
        db.close()

# ─── Lecture/écriture complète pour l'envoyeur (CLI + crontab) ────────────────

# Champs rangés dans la colonne "extra" à la migration, que l'envoyeur attend
# au niveau racine du dict.
_CHAMPS_EXTRA_REMONTES = ["nom", "mail_destinataires", "mail_note"]


def _entreprise_vers_dict(e) -> dict:
    """Une ligne Entreprise → dict au format attendu par l'envoyeur (comme l'ancien JSON)."""
    extra = e.extra or {}
    d = {
        "nom_commercial": e.nom_commercial,
        "ville":          e.ville,
        "code_postal":    e.code_postal,
        "siren":          e.siren,
        "site_web":       e.site_web,
        "secteur":        e.secteur,
        "emails_trouves": e.emails_trouves or [],
        "telephones":     e.telephones or [],
        "contact_rh":     e.contact_rh,
        "traite":         bool(e.traite),
        "mail_envoye":    bool(e.mail_envoye),
        "mail_envoye_le": e.mail_envoye_le or "",
    }
    # On remonte les champs utiles depuis extra
    for champ in _CHAMPS_EXTRA_REMONTES:
        d[champ] = extra.get(champ, "")
    # On garde extra complet aussi, au cas où
    d["_extra"] = extra
    d["_id"] = e.id   # id technique en base, pour réécrire précisément
    return d


def lire_entreprises(user_id: int) -> list[dict]:
    """Toutes les entreprises d'un utilisateur, format dict (comme l'ancien JSON)."""
    db = SessionLocal()
    try:
        lignes = db.query(Entreprise).filter_by(user_id=user_id).all()
        return [_entreprise_vers_dict(e) for e in lignes]
    finally:
        db.close()


def sauvegarder_entreprises(user_id: int, liste: list[dict]):
    """
    Réécrit en base les modifications faites par l'envoyeur.
    On met à jour les champs que l'envoyeur touche : mail_envoye,
    mail_envoye_le, et mail_destinataires/mail_note (dans extra).
    On retrouve chaque ligne par son _id technique.
    """
    db = SessionLocal()
    try:
        for d in liste:
            e = db.query(Entreprise).filter_by(id=d.get("_id"), user_id=user_id).first()
            if not e:
                continue
            e.mail_envoye    = bool(d.get("mail_envoye", False))
            e.mail_envoye_le = d.get("mail_envoye_le", "") or ""
            # Champs qui vivent dans extra
            extra = dict(e.extra or {})
            if "mail_destinataires" in d:
                extra["mail_destinataires"] = d["mail_destinataires"]
            if "mail_note" in d:
                extra["mail_note"] = d["mail_note"]
            e.extra = extra
        db.commit()
    finally:
        db.close()

def sauvegarder_enrichissement(user_id: int, liste: list[dict]):
    """
    Réécrit en base les enrichissements faits par le scraper d'emails :
    emails_trouves, telephones, contact_rh, traite, et telephone (dans extra).
    On retrouve chaque ligne par son _id technique.
    """
    db = SessionLocal()
    try:
        for d in liste:
            e = db.query(Entreprise).filter_by(id=d.get("_id"), user_id=user_id).first()
            if not e:
                continue
            if "emails_trouves" in d:
                e.emails_trouves = d["emails_trouves"] or []
            if "telephones" in d:
                e.telephones = d["telephones"] or []
            if "contact_rh" in d:
                # contact_rh peut être None/str/list/dict → on normalise en str
                v = d["contact_rh"]
                if isinstance(v, (list, dict)):
                    import json as _json
                    e.contact_rh = _json.dumps(v, ensure_ascii=False) if v else ""
                else:
                    e.contact_rh = v or ""
            if "traite" in d:
                e.traite = bool(d["traite"])
            # telephone (singulier) vit dans extra
            if "telephone" in d:
                extra = dict(e.extra or {})
                extra["telephone"] = d["telephone"]
                e.extra = extra
        db.commit()
    finally:
        db.close()


def ajouter_entreprises(user_id: int, liste: list[dict]) -> int:
    """
    Insère en base les NOUVELLES entreprises trouvées par le fetch.
    Dédup par siret (stocké dans extra). Ne touche pas aux existantes.
    Retourne le nombre de nouvelles entreprises ajoutées.
    """
    db = SessionLocal()
    ajoutees = 0
    try:
        # Sirets déjà présents pour cet utilisateur (dédup)
        existantes = db.query(Entreprise).filter_by(user_id=user_id).all()
        sirets_connus = set()
        for e in existantes:
            s = (e.extra or {}).get("siret")
            if s:
                sirets_connus.add(s)

        for d in liste:
            siret = d.get("siret", "")
            if siret and siret in sirets_connus:
                continue  # déjà en base
            # Champs connus → colonnes ; le reste → extra
            extra = {
                "siret":       siret,
                "nom":         d.get("nom", ""),
                "code_naf":    d.get("code_naf", ""),
                "adresse":     d.get("adresse", ""),
                "departement": d.get("departement", ""),
                "taille":      d.get("taille", ""),
                "categorie":   d.get("categorie", ""),
                "dirigeant":   d.get("dirigeant", ""),
            }
            e = Entreprise(
                user_id        = user_id,
                nom_commercial = d.get("nom_commercial") or d.get("nom", ""),
                ville          = d.get("ville", ""),
                code_postal    = d.get("code_postal", ""),
                siren          = d.get("siren", ""),
                site_web       = d.get("site_web") or "",
                secteur        = d.get("code_naf", ""),
                extra          = extra,
            )
            db.add(e)
            if siret:
                sirets_connus.add(siret)
            ajoutees += 1
        db.commit()
    finally:
        db.close()
    return ajoutees


def lire_entreprises_envoyees(user_id: int) -> list[dict]:
    """
    Entreprises où un mail a été envoyé, pour le tableau de suivi.
    Calcule automatiquement le statut 'a_relancer' si envoyé depuis +7 jours
    et toujours au statut 'envoye'.
    """
    from datetime import datetime, timedelta
    db = SessionLocal()
    try:
        envoyees = (db.query(Entreprise)
                      .filter_by(user_id=user_id, mail_envoye=True)
                      .all())
        maintenant = datetime.now()
        resultat = []
        for e in envoyees:
            statut = e.statut_suivi or "envoye"
            # Calcul auto "à relancer" : seulement si encore au statut brut "envoye"
            if statut == "envoye" and e.mail_envoye_le:
                try:
                    envoye_le = datetime.strptime(e.mail_envoye_le, "%Y-%m-%d %H:%M")
                    if maintenant - envoye_le >= timedelta(days=7):
                        statut = "a_relancer"
                except ValueError:
                    pass
            d = _entreprise_vers_dict(e)
            d["statut_suivi"] = statut
            resultat.append(d)
        # Tri : les plus récemment envoyées en premier
        resultat.sort(key=lambda x: x.get("mail_envoye_le", ""), reverse=True)
        return resultat
    finally:
        db.close()


def modifier_statut_suivi(user_id: int, entreprise_id: int, statut: str) -> bool:
    """Change le statut de suivi d'une entreprise (envoye/reponse/entretien/refus/bounce)."""
    valides = {"envoye", "a_relancer", "reponse", "entretien", "refus", "bounce"}
    if statut not in valides:
        return False
    db = SessionLocal()
    try:
        e = db.query(Entreprise).filter_by(user_id=user_id, id=entreprise_id).first()
        if not e:
            return False
        e.statut_suivi = statut
        db.commit()
        return True
    finally:
        db.close()
