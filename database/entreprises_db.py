"""
database/entreprises_db.py
==========================
Couche d'accès aux entreprises EN BASE, par utilisateur : stats, listing,
et écritures des pipelines spontanées (fetch, scraper, envoyeur, suivi).

Une entreprise est unique par utilisateur (SIRET, puis SIREN, D59) ; ses
données publiques (site, emails, téléphones, contact) sont communes à tous
les modes et ne sont scrapées qu'une fois. La sélection pour un mode,
l'envoi, sa date, les destinataires et le statut de suivi sont propres à
chaque mode (table entreprises_modes, phase 6a). Les fonctions de lecture
et d'envoi ne voient que les entreprises sélectionnées dans le mode
demandé ; un contact dans un autre mode est signalé, jamais bloquant.
"""

import json
from datetime import datetime, timedelta, timezone

from database.connexion import SessionLocal
from database.dates import JOUR, JOUR_HEURE, depuis_base, en_texte, maintenant_utc, vers_utc

_TRES_ANCIEN = datetime.min.replace(tzinfo=timezone.utc)
from sqlalchemy.orm import selectinload

from database.models import EmailContacte, Entreprise, EntrepriseMode
from shared.modes import MODE_DEFAUT
from shared.emails_exclus import email_exclu, filtrer as filtrer_emails_exclus


LONGUEUR_CONTACT_RH = 200   # taille de la colonne entreprises.contact_rh

# Sources des entreprises (colonne sources, liste) : Sirene et les
# entreprises à fort potentiel de La Bonne Alternance, traitées et
# affichées ensemble, sans priorité de l'une sur l'autre (décision D44)
SOURCE_LBA = "lba"
SOURCE_SIRENE = "sirene"
SOURCES = (SOURCE_SIRENE, SOURCE_LBA)
PROCHAINES_AFFICHEES = 30
# Statuts de suivi comptés comme une réponse de l'entreprise
STATUTS_REPONSE = {"reponse", "entretien", "refus"}


def _siren(e) -> str:
    """SIREN d'une entreprise en base : colonne, à défaut début du SIRET."""
    return e.siren or ((e.extra or {}).get("siret") or "")[:9]


def _avec_source(e, source: str) -> bool:
    """Ajoute source à la liste de l'entreprise ; vrai si elle n'y était pas."""
    sources = list(e.sources or [])
    if source in sources:
        return False
    e.sources = sources + [source]
    return True


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


def _date_envoi(m):
    """Instant d'envoi pour trier, les entreprises sans date en dernier."""
    return depuis_base(m.mail_envoye_le) or _TRES_ANCIEN


def _du_mode(db, user_id: int, mode: str):
    """[(Entreprise, EntrepriseMode)] des entreprises sélectionnées dans ce
    mode, dans l'ordre de sélection."""
    return (db.query(Entreprise, EntrepriseMode)
              .join(EntrepriseMode, EntrepriseMode.entreprise_id == Entreprise.id)
              .filter(Entreprise.user_id == user_id, EntrepriseMode.user_id == user_id,
                      EntrepriseMode.mode == mode)
              .order_by(EntrepriseMode.id).all())


def _selectionner(db, e: Entreprise, mode: str) -> EntrepriseMode:
    """Ligne de l'entreprise dans ce mode, créée si elle n'existe pas."""
    m = next((x for x in e.modes if x.mode == mode), None)
    if m is None:
        m = EntrepriseMode(user_id=e.user_id, mode=mode, mail_envoye=False, statut_suivi="envoye",
                           mail_destinataires=[], mail_note="", historique=False)
        e.modes.append(m)
    return m


def contacts_autres_modes(db, user_id: int, mode: str, entreprises) -> dict[int, list[dict]]:
    """Pour chaque entreprise (id), ses contacts dans les AUTRES modes :
    [{"mode", "date" (AAAA-MM-JJ, vide si inconnue), "historique"}], un par
    mode, triés par mode. Un contact, c'est un envoi enregistré pour
    l'entreprise dans ce mode, ou l'une de ses adresses déjà contactée
    dans ce mode (emails_contactes, import historique compris). Sert
    d'étiquette dans la page Spontanées ; ne bloque jamais l'envoi."""
    entreprises = list(entreprises)
    ids = [e.id for e in entreprises]
    if not ids:
        return {}
    trouves: dict[int, dict[str, dict]] = {}

    def noter(eid, autre, date, historique=False):
        actuel = trouves.setdefault(eid, {}).get(autre)
        date = depuis_base(date)
        if actuel is None:
            trouves[eid][autre] = {"date": date, "historique": historique}
        else:
            if date and (actuel["date"] is None or date < actuel["date"]):
                actuel["date"] = date
            actuel["historique"] = actuel["historique"] or historique

    for m in (db.query(EntrepriseMode)
                .filter(EntrepriseMode.user_id == user_id, EntrepriseMode.mode != mode,
                        EntrepriseMode.mail_envoye.is_(True), EntrepriseMode.entreprise_id.in_(ids))):
        noter(m.entreprise_id, m.mode, m.mail_envoye_le, bool(m.historique))
    par_email = {}
    for c in (db.query(EmailContacte)
                .filter(EmailContacte.user_id == user_id, EmailContacte.mode != mode)):
        par_email.setdefault(c.email, []).append(c)
    if par_email:
        for e in entreprises:
            for adresse in {(a or "").strip().lower() for a in (e.emails_trouves or [])}:
                for c in par_email.get(adresse, []):
                    noter(e.id, c.mode, c.contacte_le)
    return {eid: [{"mode": autre, "date": en_texte(v["date"], JOUR) if v["date"] else "",
                   "historique": v["historique"]} for autre, v in sorted(modes.items())]
            for eid, modes in trouves.items()}


def repartition_par_source(paires) -> dict:
    """Pour chaque source : entreprises, emails trouvés, mails envoyés,
    réponses (réponse, entretien, refus) et entretiens, dans un mode
    (paires (Entreprise, EntrepriseMode)). Une entreprise trouvée par les
    deux sources compte dans chacune ; « les_deux » les compte à part."""
    def compter(liste):
        return {
            "entreprises": len(liste),
            "avec_email":  sum(1 for e, _ in liste if e.emails_trouves),
            "envoyes":     sum(1 for _, m in liste if m.mail_envoye and not m.historique),
            "reponses":    sum(1 for _, m in liste if m.mail_envoye and m.statut_suivi in STATUTS_REPONSE),
            "entretiens":  sum(1 for _, m in liste if m.mail_envoye and m.statut_suivi == "entretien"),
        }
    out = {src: compter([(e, m) for e, m in paires if src in (e.sources or [])]) for src in SOURCES}
    out["les_deux"] = compter([(e, m) for e, m in paires if set(SOURCES) <= set(e.sources or [])])
    return out


def calculer_stats(user_id: int, mode: str = MODE_DEFAUT) -> dict:
    """Statistiques des entreprises sélectionnées dans un mode."""
    db = SessionLocal()
    try:
        paires = _du_mode(db, user_id, mode)
        raw         = len(paires)
        avec_email  = sum(1 for e, _ in paires if e.emails_trouves)
        mail_envoye = sum(1 for _, m in paires if m.mail_envoye and not m.historique)
        historiques = sum(1 for _, m in paires if m.historique)
        prochaines_paires = [(e, m) for e, m in paires if not m.mail_envoye][:PROCHAINES_AFFICHEES]
        recentes = sorted(((e, m) for e, m in paires if m.mail_envoye),
                          key=lambda p: (_date_envoi(p[1]), p[1].id), reverse=True)[:5]
        ailleurs = contacts_autres_modes(db, user_id, mode, [e for e, _ in prochaines_paires + recentes])

        # 5 dernières entreprises contactées : les plus récentes par date d'envoi
        # (à date égale, la dernière sélectionnée d'abord)
        dernieres = [
            {
                "id":     e.id,
                "nom":    (e.nom_commercial or "?")[:40],
                "ville":  e.ville or "",
                "email":  (e.emails_trouves or [""])[0] if e.emails_trouves else "",
                "envoye": True,
                "historique": bool(m.historique),
                "date":   en_texte(m.mail_envoye_le, JOUR_HEURE),
                "sources": list(e.sources or []),
                "contacts_autres_modes": ailleurs.get(e.id, []),
            }
            for e, m in recentes
        ]
        # Prochaines entreprises traitées, dans l'ordre du scraper et de l'envoyeur
        prochaines = [
            {
                "id":        e.id,
                "nom":       (e.nom_commercial or (e.extra or {}).get("nom", "") or "?")[:40],
                "ville":     e.ville or "",
                "email":     (e.emails_trouves or [""])[0] if e.emails_trouves else "",
                "envoye":    False,
                "sources":   list(e.sources or []),
                "email_lba": bool(set(e.emails_trouves or []) & set((e.extra or {}).get("emails_lba") or [])),
                "contacts_autres_modes": ailleurs.get(e.id, []),
            }
            for e, m in prochaines_paires
        ]
        return {
            "mode": mode,
            "raw": raw,
            "avec_email": avec_email,
            "mail_envoye": mail_envoye,
            "historiques": historiques,
            "par_source": repartition_par_source(paires),
            "dernieres": dernieres,
            "prochaines": prochaines,
        }
    finally:
        db.close()

# ─── Lecture/écriture complète pour l'envoyeur (CLI + crontab) ────────────────

# Champs rangés dans la colonne "extra", que l'envoyeur et le scraper
# attendent au niveau racine du dict.
_CHAMPS_EXTRA_REMONTES = ["nom", "url_scrapee", "source_recherche"]
# Champs du scraper gardés dans extra (bug 5 : ils étaient perdus)
# emails_non_valides : emails lus dans la page sans validation par Mistral
_CHAMPS_EXTRA_SCRAPER = ("telephone", "url_scrapee", "source_recherche", "tentatives_site",
                         "emails_non_valides")


def _entreprise_vers_dict(e, m, ailleurs=()) -> dict:
    """Une entreprise et son état dans un mode → dict au format attendu par
    l'envoyeur et le scraper (comme l'ancien JSON)."""
    extra = e.extra or {}
    d = {
        "mode":           m.mode,
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
        "mail_envoye":    bool(m.mail_envoye),
        "mail_envoye_le": en_texte(m.mail_envoye_le, JOUR_HEURE),
        "mail_destinataires": list(m.mail_destinataires or []),
        "mail_note":      m.mail_note or "",
        "historique":     bool(m.historique),
        "statut_suivi":   m.statut_suivi or "envoye",
        "sources":        list(e.sources or []),
        "emails_lba":     list(extra.get("emails_lba") or []),
        "contacts_autres_modes": list(ailleurs),
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
    """Entreprise que le scraper doit encore traiter (données communes à
    tous les modes : une entreprise déjà scrapée ne l'est plus)."""
    return not (e.get("traite") or e.get("emails_trouves") or e.get("mail_envoye"))


def compter_a_scraper(user_id: int, mode: str = MODE_DEFAUT) -> int:
    """Nombre d'entreprises du mode à scraper : le maximum utile d'un lancement."""
    db = SessionLocal()
    try:
        return sum(1 for e, m in _du_mode(db, user_id, mode)
                   if not (e.traite or e.emails_trouves or m.mail_envoye))
    finally:
        db.close()


def _en_attente_de_validation(e: Entreprise, m: EntrepriseMode) -> bool:
    """Emails lus dans la page sans validation par l'IA, pas encore envoyés
    dans ce mode (D15)."""
    return bool((e.extra or {}).get("emails_non_valides")) and bool(e.emails_trouves) and not m.mail_envoye


def lire_a_valider(user_id: int, mode: str = MODE_DEFAUT) -> list[dict]:
    """Entreprises du mode dont les emails attendent une validation
    (manuelle ou par l'IA ; la validation vaut pour tous les modes)."""
    db = SessionLocal()
    try:
        return [{"id": e.id, "nom": e.nom_commercial or (e.extra or {}).get("nom", "") or "?",
                 "ville": e.ville or "", "site": e.site_web or "", "emails": list(e.emails_trouves or [])}
                for e, m in _du_mode(db, user_id, mode)
                if _en_attente_de_validation(e, m)]
    finally:
        db.close()


def compter_a_valider(user_id: int, mode: str = MODE_DEFAUT) -> int:
    return len(lire_a_valider(user_id, mode))


def valider_emails(user_id: int, entreprise_id: int) -> bool:
    """Validation manuelle des emails d'une entreprise de l'utilisateur
    (donnée commune à tous les modes). False si l'entreprise n'existe pas
    (ou n'est pas à lui) ou n'attend rien."""
    db = SessionLocal()
    try:
        e = db.query(Entreprise).filter_by(user_id=user_id, id=entreprise_id).first()
        if not e or not ((e.extra or {}).get("emails_non_valides") and e.emails_trouves):
            return False
        e.extra = {**(e.extra or {}), "emails_non_valides": False}
        db.commit()
        return True
    finally:
        db.close()


def lire_entreprises(user_id: int, mode: str = MODE_DEFAUT) -> list[dict]:
    """Entreprises sélectionnées dans un mode, format dict (comme l'ancien
    JSON), dans l'ordre de sélection, toutes sources confondues (D44), avec
    leurs contacts dans les autres modes."""
    db = SessionLocal()
    try:
        paires = _du_mode(db, user_id, mode)
        ailleurs = contacts_autres_modes(db, user_id, mode, [e for e, _ in paires])
        return [_entreprise_vers_dict(e, m, ailleurs.get(e.id, [])) for e, m in paires]
    finally:
        db.close()


def sauvegarder_entreprises(user_id: int, liste: list[dict], mode: str = MODE_DEFAUT):
    """
    Réécrit en base les modifications faites par l'envoyeur, dans ce mode :
    mail_envoye, mail_envoye_le, mail_destinataires et mail_note. On
    retrouve chaque ligne par l'id technique de l'entreprise (_id).
    """
    db = SessionLocal()
    try:
        for d in liste:
            m = (db.query(EntrepriseMode)
                   .filter_by(entreprise_id=d.get("_id"), user_id=user_id, mode=mode).first())
            if not m:
                continue
            m.mail_envoye    = bool(d.get("mail_envoye", False))
            # Une date relue (texte en heure d'affichage) et non modifiée n'est
            # pas réécrite : seule une nouvelle valeur (datetime) l'est.
            date = d.get("mail_envoye_le")
            if not (isinstance(date, str) and date and date == en_texte(m.mail_envoye_le, JOUR_HEURE)):
                m.mail_envoye_le = vers_utc(date)
            if "mail_destinataires" in d:
                m.mail_destinataires = list(d["mail_destinataires"] or [])
            if "mail_note" in d:
                m.mail_note = str(d["mail_note"] or "")[:200]
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
                # Dernier rempart : aucune adresse technique ou factice enregistrée (D47)
                e.emails_trouves = filtrer_emails_exclus(d["emails_trouves"])
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


def _index_entreprises(db, user_id: int):
    """Entreprises de l'utilisateur par SIRET, par SIREN et par identifiant LBA."""
    par_siret, par_siren, par_identifiant = {}, {}, {}
    for e in (db.query(Entreprise).filter_by(user_id=user_id)
                .options(selectinload(Entreprise.modes)).order_by(Entreprise.id)):
        extra = e.extra or {}
        if extra.get("siret"):
            par_siret[extra["siret"]] = e
        if _siren(e):
            par_siren.setdefault(_siren(e), e)
        if (extra.get("lba") or {}).get("identifiant"):
            par_identifiant[extra["lba"]["identifiant"]] = e
    return par_siret, par_siren, par_identifiant


def _dans_le_mode(e: Entreprise, mode: str) -> bool:
    return any(m.mode == mode for m in e.modes)


def ajouter_entreprises(user_id: int, liste: list[dict], mode: str = MODE_DEFAUT) -> int:
    """
    Sélectionne dans le mode les NOUVELLES entreprises trouvées par Sirene.
    Une entreprise déjà en base dans un autre mode (même SIRET, puis même
    SIREN, D59) n'est pas dupliquée : elle est sélectionnée dans ce mode,
    avec ses données déjà scrapées, et la source « sirene » y est notée.
    Celles déjà dans le mode ne sont pas touchées.
    Retourne le nombre d'entreprises ajoutées au mode.
    """
    db = SessionLocal()
    ajoutees = 0
    try:
        par_siret, par_siren, _ = _index_entreprises(db, user_id)
        for d in liste:
            siret = d.get("siret", "")
            siren = d.get("siren") or siret[:9]
            e = (par_siret.get(siret) if siret else None) or (par_siren.get(siren) if siren else None)
            if e is not None:
                if _dans_le_mode(e, mode):
                    continue  # déjà dans le mode (la source est notée par noter_source)
                _avec_source(e, SOURCE_SIRENE)
                _selectionner(db, e, mode)
                ajoutees += 1
                continue
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
                sources        = [SOURCE_SIRENE],
                extra          = extra,
            )
            db.add(e)
            _selectionner(db, e, mode)
            if siret:
                par_siret[siret] = e
            if siren:
                par_siren.setdefault(siren, e)
            ajoutees += 1
        db.commit()
    finally:
        db.close()
    return ajoutees


def cles_connues(user_id: int, mode: str = MODE_DEFAUT) -> frozenset:
    """SIRET, SIREN et identifiants LBA des entreprises déjà sélectionnées
    dans le mode (une entreprise d'un autre mode reste à sélectionner)."""
    db = SessionLocal()
    try:
        cles = set()
        for e, _ in _du_mode(db, user_id, mode):
            extra = e.extra or {}
            cles.update(c for c in (extra.get("siret"), _siren(e), (extra.get("lba") or {}).get("identifiant")) if c)
        return frozenset(cles)
    finally:
        db.close()


def noter_source(user_id: int, sirets, source: str, sirens=()) -> int:
    """Ajoute source aux entreprises déjà en base retrouvées par une autre
    source : même SIRET, ou même SIREN (D59). Retourne le nombre
    d'entreprises complétées."""
    sirets, sirens = set(s for s in sirets if s), set(s for s in sirens if s)
    if not (sirets or sirens):
        return 0
    db = SessionLocal()
    try:
        n = sum(1 for e in db.query(Entreprise).filter_by(user_id=user_id)
                if ((e.extra or {}).get("siret") in sirets or _siren(e) in sirens) and _avec_source(e, source))
        db.commit()
        return n
    finally:
        db.close()


def ajouter_entreprises_lba(user_id: int, liste: list[dict], maximum: int | None = None,
                            mode: str = MODE_DEFAUT) -> dict:
    """Entreprises à fort potentiel de La Bonne Alternance (normalisées par
    france_travail.scraper_lba) dans les candidatures spontanées du mode
    (alternance), source « lba ». Dédoublonnage par SIRET avec toutes les
    entreprises de l'utilisateur (Sirene comprises, tous modes), puis par
    SIREN (un autre établissement de la même entreprise, D59), à défaut par
    identifiant LBA. Une entreprise déjà connue garde ses données et ajoute
    « lba » à ses sources (D44) ; connue seulement dans un autre mode, elle
    est sélectionnée dans celui-ci (comptée parmi les ajoutées, dans la
    limite). Un email fourni par LBA est ajouté à ses emails s'il n'y est
    pas et qu'elle n'a encore été contactée dans aucun mode. Les emails
    fournis par LBA sont notés dans extra["emails_lba"]. maximum :
    nouvelles entreprises du mode au plus (None : toutes). Retourne
    {"ajoutees", "deja_connues", "deux_sources" (déjà connues d'une autre
    source), "avec_email", "non_ajoutees"}."""
    bilan = {"ajoutees": 0, "deja_connues": 0, "deux_sources": 0, "avec_email": 0, "non_ajoutees": 0}
    db = SessionLocal()
    try:
        par_siret, par_siren, par_identifiant = _index_entreprises(db, user_id)
        for d in liste:
            infos_lba = {k: d.get(k, "") for k in ("identifiant", "candidature_id", "candidature_url", "libelle_naf")}
            email = d.get("email") or ""
            email = "" if email_exclu(email) else email
            e = ((par_siret.get(d["siret"]) if d.get("siret") else None)
                 or (par_siren.get(d["siren"]) if d.get("siren") else None)
                 or (par_identifiant.get(infos_lba["identifiant"]) if infos_lba["identifiant"] else None))
            if e is not None:
                if not _dans_le_mode(e, mode):
                    if maximum is not None and bilan["ajoutees"] >= maximum:
                        bilan["non_ajoutees"] += 1
                        continue
                    _selectionner(db, e, mode)
                    bilan["ajoutees"] += 1
                else:
                    bilan["deja_connues"] += 1
                extra = dict(e.extra or {})
                extra["lba"] = infos_lba
                if _avec_source(e, SOURCE_LBA):
                    bilan["deux_sources"] += 1
                envoyee = any(m.mail_envoye for m in e.modes)
                if email and not envoyee and email not in (e.emails_trouves or []):
                    e.emails_trouves = list(e.emails_trouves or []) + [email]
                if email:
                    extra["emails_lba"] = sorted(set(extra.get("emails_lba") or []) | {email})
                e.extra = extra
                continue
            if maximum is not None and bilan["ajoutees"] >= maximum:
                bilan["non_ajoutees"] += 1
                continue
            extra = {
                "siret":       d.get("siret", ""),
                "nom":         d.get("nom", ""),
                "code_naf":    d.get("code_naf", ""),
                "adresse":     d.get("adresse", ""),
                "departement": d.get("departement", ""),
                "taille":      d.get("taille", ""),
                "lba":         infos_lba,
            }
            if email:
                extra["emails_lba"] = [email]
                bilan["avec_email"] += 1
            e = Entreprise(
                user_id        = user_id,
                sources        = [SOURCE_LBA],
                nom_commercial = d.get("nom_commercial") or d.get("nom", ""),
                ville          = d.get("ville", ""),
                code_postal    = d.get("code_postal", ""),
                siren          = d.get("siren", ""),
                site_web       = d.get("site_web") or "",
                secteur        = d.get("code_naf", ""),
                emails_trouves = [email] if email else [],
                telephones     = [d["telephone"]] if d.get("telephone") else [],
                extra          = extra,
            )
            db.add(e)
            _selectionner(db, e, mode)
            if d.get("siret"):
                par_siret[d["siret"]] = e
            if d.get("siren"):
                par_siren.setdefault(d["siren"], e)
            if infos_lba["identifiant"]:
                par_identifiant[infos_lba["identifiant"]] = e
            bilan["ajoutees"] += 1
        db.commit()
    finally:
        db.close()
    return bilan


def lire_entreprises_envoyees(user_id: int, mode: str = MODE_DEFAUT) -> list[dict]:
    """
    Entreprises où un mail a été envoyé dans ce mode, pour le tableau de
    suivi (contactées avant la refonte comprises, notées « historique »).
    Calcule automatiquement le statut 'a_relancer' si envoyé depuis +7 jours
    par l'application et toujours au statut 'envoye'.
    """
    db = SessionLocal()
    try:
        envoyees = [(e, m) for e, m in _du_mode(db, user_id, mode) if m.mail_envoye]
        ailleurs = contacts_autres_modes(db, user_id, mode, [e for e, _ in envoyees])
        maintenant = maintenant_utc()
        resultat = []
        for e, m in envoyees:
            statut = m.statut_suivi or "envoye"
            # Calcul auto "à relancer" : seulement si encore au statut brut "envoye"
            if statut == "envoye" and m.mail_envoye_le and not m.historique:
                if maintenant - depuis_base(m.mail_envoye_le) >= timedelta(days=7):
                    statut = "a_relancer"
            d = _entreprise_vers_dict(e, m, ailleurs.get(e.id, []))
            d["statut_suivi"] = statut
            resultat.append((depuis_base(m.mail_envoye_le) or _TRES_ANCIEN, d))
        # Tri sur l'instant UTC (pas sur le texte affiché) : les plus récentes en premier
        resultat.sort(key=lambda paire: paire[0], reverse=True)
        return [d for _, d in resultat]
    finally:
        db.close()


def modifier_statut_suivi(user_id: int, entreprise_id: int, statut: str, mode: str = MODE_DEFAUT) -> bool:
    """Change le statut de suivi d'une entreprise dans ce mode (envoye/reponse/entretien/refus/bounce)."""
    valides = {"envoye", "a_relancer", "reponse", "entretien", "refus", "bounce"}
    if statut not in valides:
        return False
    db = SessionLocal()
    try:
        m = (db.query(EntrepriseMode)
               .filter_by(user_id=user_id, entreprise_id=entreprise_id, mode=mode).first())
        if not m:
            return False
        m.statut_suivi = statut
        db.commit()
        return True
    finally:
        db.close()
