"""
database/entreprises_db.py
==========================
Couche d'accès aux entreprises EN BASE, par utilisateur : stats, listing,
et écritures des pipelines spontanées (fetch, scraper, envoyeur, suivi).
"""

import json
from datetime import datetime, timedelta, timezone

from database.connexion import SessionLocal
from database.dates import JOUR_HEURE, depuis_base, en_texte, maintenant_utc, vers_utc

_TRES_ANCIEN = datetime.min.replace(tzinfo=timezone.utc)
from database.models import Entreprise


LONGUEUR_CONTACT_RH = 200   # taille de la colonne entreprises.contact_rh


def normaliser_contact_rh(valeur) -> str:
    """contact_rh sous une seule forme partout : un texte lisible.
    Mistral peut renvoyer une chaîne, une liste de noms ou de dicts, ou un
    dict {prenom, nom, poste} ; d'anciennes lignes contiennent ces structures
    en JSON brut. Tout devient « Prénom Nom (poste), Autre Nom », borné à la
    taille de la colonne."""
    if isinstance(valeur, str):
        texte = valeur.strip()
        if texte[:1] in "[{":
            try:
                valeur = json.loads(texte)   # ancienne écriture en json.dumps
            except ValueError:
                valeur = texte
        else:
            valeur = texte
    if not valeur:
        return ""
    if isinstance(valeur, str):
        resultat = valeur
    elif isinstance(valeur, dict):
        nom = " ".join(str(valeur[k]).strip() for k in ("prenom", "nom") if valeur.get(k)).strip()
        poste = str(valeur.get("poste") or "").strip()
        resultat = f"{nom} ({poste})" if nom and poste else (nom or poste)
    elif isinstance(valeur, (list, tuple)):
        resultat = ", ".join(m for m in (normaliser_contact_rh(v) for v in valeur) if m)
    else:
        resultat = str(valeur)
    return " ".join(resultat.split())[:LONGUEUR_CONTACT_RH]


def _date_envoi(e):
    """Instant d'envoi pour trier, les entreprises sans date en dernier."""
    return depuis_base(e.mail_envoye_le) or _TRES_ANCIEN


def calculer_stats(user_id: int) -> dict:
    """Statistiques globales des entreprises d'un utilisateur."""
    db = SessionLocal()
    try:
        q = db.query(Entreprise).filter_by(user_id=user_id)
        toutes = q.all()
        raw         = len(toutes)
        avec_email  = sum(1 for e in toutes if e.emails_trouves)
        mail_envoye = sum(1 for e in toutes if e.mail_envoye)

        # 5 dernières entreprises contactées : les plus récentes par date d'envoi
        # (à date égale, la dernière insérée d'abord)
        recentes = sorted((e for e in toutes if e.mail_envoye),
                          key=lambda e: (_date_envoi(e), e.id), reverse=True)[:5]
        dernieres = [
            {
                "nom":    (e.nom_commercial or "?")[:40],
                "ville":  e.ville or "",
                "email":  (e.emails_trouves or [""])[0] if e.emails_trouves else "",
                "envoye": bool(e.mail_envoye),
                "date":   en_texte(e.mail_envoye_le, JOUR_HEURE),
            }
            for e in recentes
        ]
        return {
            "raw": raw,
            "avec_email": avec_email,
            "mail_envoye": mail_envoye,
            "dernieres": dernieres,
        }
    finally:
        db.close()

# ─── Lecture/écriture complète pour l'envoyeur (CLI + crontab) ────────────────

# Champs rangés dans la colonne "extra", que l'envoyeur et le scraper
# attendent au niveau racine du dict.
_CHAMPS_EXTRA_REMONTES = ["nom", "mail_destinataires", "mail_note", "url_scrapee", "source_recherche"]
# Champs du scraper gardés dans extra (bug 5 : ils étaient perdus)
# emails_non_valides : emails lus dans la page sans validation par Mistral
_CHAMPS_EXTRA_SCRAPER = ("telephone", "url_scrapee", "source_recherche", "tentatives_site",
                         "emails_non_valides")


def _entreprise_vers_dict(e) -> dict:
    """Une ligne Entreprise → dict au format attendu par l'envoyeur (comme l'ancien JSON)."""
    extra = e.extra or {}
    d = {
        "mode":           e.mode,
        "nom_commercial": e.nom_commercial,
        "ville":          e.ville,
        "code_postal":    e.code_postal,
        "siren":          e.siren,
        "site_web":       e.site_web,
        "secteur":        e.secteur,
        "emails_trouves": e.emails_trouves or [],
        "telephones":     e.telephones or [],
        "contact_rh":     normaliser_contact_rh(e.contact_rh),
        "traite":         bool(e.traite),
        "mail_envoye":    bool(e.mail_envoye),
        "mail_envoye_le": en_texte(e.mail_envoye_le, JOUR_HEURE),
    }
    # On remonte les champs utiles depuis extra
    for champ in _CHAMPS_EXTRA_REMONTES:
        d[champ] = extra.get(champ, "")
    d["tentatives_site"] = int(extra.get("tentatives_site") or 0)
    d["emails_non_valides"] = bool(extra.get("emails_non_valides"))
    # On garde extra complet aussi, au cas où
    d["_extra"] = extra
    d["_id"] = e.id   # id technique en base, pour réécrire précisément
    return d


def a_scraper(e: dict) -> bool:
    """Entreprise que le scraper doit encore traiter."""
    return not (e.get("traite") or e.get("emails_trouves") or e.get("mail_envoye"))


def compter_a_scraper(user_id: int) -> int:
    """Nombre d'entreprises à scraper : le maximum utile d'un lancement."""
    db = SessionLocal()
    try:
        return sum(1 for e in db.query(Entreprise).filter_by(user_id=user_id)
                   if not (e.traite or e.emails_trouves or e.mail_envoye))
    finally:
        db.close()


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
            # Une date relue (texte en heure d'affichage) et non modifiée n'est
            # pas réécrite : seule une nouvelle valeur (datetime) l'est.
            date = d.get("mail_envoye_le")
            if not (isinstance(date, str) and date and date == en_texte(e.mail_envoye_le, JOUR_HEURE)):
                e.mail_envoye_le = vers_utc(date)
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
    site_web, emails_trouves, telephones, contact_rh (texte normalisé),
    traite, et dans extra telephone, url_scrapee, source_recherche et
    tentatives_site. On retrouve chaque ligne par son _id technique.
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
            if "site_web" in d:
                e.site_web = d["site_web"] or ""
            if "contact_rh" in d:
                e.contact_rh = normaliser_contact_rh(d["contact_rh"])
            if "traite" in d:
                e.traite = bool(d["traite"])
            # Champs sans colonne : dans extra (une valeur vide n'est écrite
            # que pour remplacer une valeur existante)
            extra = dict(e.extra or {})
            for champ in _CHAMPS_EXTRA_SCRAPER:
                if champ in d and (d[champ] or champ in extra):
                    extra[champ] = d[champ]
            if extra != (e.extra or {}):
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
    db = SessionLocal()
    try:
        envoyees = (db.query(Entreprise)
                      .filter_by(user_id=user_id, mail_envoye=True)
                      .all())
        maintenant = maintenant_utc()
        resultat = []
        for e in envoyees:
            statut = e.statut_suivi or "envoye"
            # Calcul auto "à relancer" : seulement si encore au statut brut "envoye"
            if statut == "envoye" and e.mail_envoye_le:
                if maintenant - depuis_base(e.mail_envoye_le) >= timedelta(days=7):
                    statut = "a_relancer"
            d = _entreprise_vers_dict(e)
            d["statut_suivi"] = statut
            resultat.append((depuis_base(e.mail_envoye_le) or _TRES_ANCIEN, d))
        # Tri sur l'instant UTC (pas sur le texte affiché) : les plus récentes en premier
        resultat.sort(key=lambda paire: paire[0], reverse=True)
        return [d for _, d in resultat]
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
