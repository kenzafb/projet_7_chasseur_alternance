"""
routes/spontanees.py
====================
Candidatures spontanées : statistiques, étapes du pipeline (récupérer,
scraper, valider, envoyer) dans des threads, arrêt, validation manuelle des
emails, « J'ai postulé » sur La Bonne Alternance (D130).
"""

import threading

from fastapi import Body, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from auth.securite import utilisateur_requis
from database import compte_envoi_db
from database.entreprises_db import calculer_stats
from database.models import User
from database.profil_db import (lire_profil)
from offres.la_bonne_alternance import ignoree_pour_profil as lba_ignoree_pour_profil
from routes import commun
from routes.commun import limite_appliquee, mode_requis, routeur_prive
from shared import compte_envoi, config
from shared.erreurs import ErreurUtilisateur
from shared.modes import get_mode
from shared.pipelines import SPONTANEES

router = routeur_prive()


class Fetch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_entreprises: int | None = None

class Scraper(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_scrapees: int | None = None

class Revalider(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_revalidations: int | None = None

class ValiderEmails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int

class ValiderAdresse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    adresse: str = Field(min_length=3, max_length=255)

class Envoyer(BaseModel):
    limite: int | None = None
    test: bool = False


# ─── Spontanées — Stats ───────────────────────────────────────────────────────

@router.post("/api/spontanees/postule_lba")
def api_spontanees_postule_lba(body: dict = Body(...), user: User = Depends(utilisateur_requis),
                               mode: str = Depends(mode_requis)):
    """« J'ai postulé » après une candidature sur La Bonne Alternance (D130) :
    l'entreprise passe « Envoyée » à la date donnée (jour de Paris,
    aujourd'hui par défaut, jamais dans le futur) et entre dans le suivi."""
    from datetime import datetime, time
    from database.dates import fuseau_affichage, maintenant_affichage
    from database.entreprises_db import marquer_postule_lba
    from shared.stage import lire_date
    jour = lire_date(str(body.get("date") or ""), "Date de candidature") or maintenant_affichage().date()
    if jour > maintenant_affichage().date():
        raise ErreurUtilisateur("La date de candidature ne peut pas être dans le futur.")
    try:
        ident = int(body.get("id"))
    except (TypeError, ValueError):
        raise ErreurUtilisateur("Entreprise introuvable.")
    instant = datetime.combine(jour, time(12), tzinfo=fuseau_affichage())
    if not marquer_postule_lba(user.id, ident, instant, mode=mode):
        return JSONResponse({"erreur": "Entreprise introuvable, déjà envoyée ou sans candidature La Bonne Alternance."},
                            status_code=404)
    return {"ok": True, "date": jour.isoformat()}


@router.get("/api/spontanees/stats")
def api_spontanees_stats(request: Request, user: User = Depends(utilisateur_requis),
                         mode: str = Depends(mode_requis)):
    # Lecture des stats depuis la base
    stats = calculer_stats(user.id, mode)
    # Maximums utiles des lancements (le serveur les applique aussi)
    from database.entreprises_db import compter_a_scraper
    from spontanees.envoi import compter_a_envoyer
    stats["a_scraper"] = compter_a_scraper(user.id, mode)
    stats["a_envoyer"] = compter_a_envoyer(user.id, mode)
    from database.entreprises_db import compter_a_valider
    stats["a_valider"] = compter_a_valider(user.id, mode)
    # Ce que « Récupérer » ne cherchera pas, dit avant tout lancement
    from shared.naf import sirene_pour_profil
    stats["avertissement_recuperer"] = sirene_pour_profil(lire_profil(user.id, mode=mode))["avertissement"]
    # On ajoute l'état du pipeline de l'utilisateur, géré en mémoire
    etat = commun.pipelines.etat(SPONTANEES, user.id)
    stats.update({cle: etat[cle] for cle in ("en_cours", "etape", "message", "pourcentage", "mode_test", "mode")})
    return stats

@router.post("/api/spontanees/stop")
def api_spontanees_stop(user: User = Depends(utilisateur_requis)):
    """Arrête le pipeline spontané de l'utilisateur connecté, et lui seul."""
    en_cours = commun.pipelines.demander_arret(user.id)
    if en_cours:
        commun.pipelines.log(user.id, "⏹️  Arrêt demandé par l'utilisateur")
    return {"ok": True, "en_cours": en_cours}


def _lancer_spontanees(user_id: int, etape: str, message: str, debut_log: str,
                       travail, fin_message: str, fin_log: str, nom_erreur: str, **etat):
    """Lance une étape du pipeline spontané dans un thread, pour cet utilisateur.
    travail(stop_event, log_fn, on_progress) fait le vrai travail.
    Retourne une réponse 400 si un pipeline spontané de l'utilisateur tourne déjà."""
    if not commun.pipelines.demarrer(SPONTANEES, user_id, etape=etape, message=message, **etat):
        en_cours = commun.pipelines.etat(SPONTANEES, user_id).get("mode")
        return JSONResponse({"erreur": f"Pipeline déjà en cours (mode {en_cours})"}, status_code=400)
    arret = commun.pipelines.evenement_arret(user_id)

    def log(msg):
        commun.pipelines.log(user_id, msg)

    def on_progress(pct, message=None):
        champs = {"pourcentage": pct}
        if message:
            champs["message"] = message
        commun.pipelines.maj(SPONTANEES, user_id, **champs)

    def lancer():
        log(debut_log)
        try:
            travail(arret, log, on_progress)
            if arret.is_set():
                commun.pipelines.maj(SPONTANEES, user_id, message="Arrêté — données sauvegardées")
            else:
                commun.pipelines.maj(SPONTANEES, user_id, message=fin_message)
                log(fin_log)
        except Exception as e:
            commun.pipelines.maj(SPONTANEES, user_id, message=f"Erreur {nom_erreur} : {e}")
            log(f"❌ Erreur {nom_erreur} : {e}")
        finally:
            commun.pipelines.terminer(SPONTANEES, user_id, etape=None)

    threading.Thread(target=lancer, daemon=True).start()
    return {"status": "démarré"}


def _aveclimite_appliquee(reponse, **limite):
    """Ajoute la limite effective à la réponse d'un lancement réussi."""
    if isinstance(reponse, dict):
        reponse.update(limite)
    return reponse

@router.post("/api/spontanees/fetch")
def api_spontanees_fetch(request: Request, body: Fetch | None = None,
                         user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    user_id = user.id
    maximum, note = limite_appliquee("entreprises", body.max_entreprises if body else None)
    # Même profil que fetch_entreprises (celui du mode) : LBA si le mode l'utilise, et Sirene
    from shared.naf import sirene_pour_profil
    profil = lire_profil(user_id, mode=mode)
    sirene = sirene_pour_profil(profil)
    avec_lba = "lba" in get_mode(mode)["sources"]
    if sirene["rien_a_chercher"] and not avec_lba:
        # Sirene seule source du mode (job, stage) : rien ne serait cherché
        raise ErreurUtilisateur(sirene["avertissement"])
    avertissement = " ".join(filter(None, [lba_ignoree_pour_profil(profil) if avec_lba else "",
                                           sirene["avertissement"]]))

    def travail(arret, log, on_progress):
        from spontanees.recuperation import main as fetch_main
        fetch_main(stop_event=arret, on_progress=on_progress, user_id=user_id,
                   max_entreprises=maximum, log_fn=log, mode=mode)

    return _aveclimite_appliquee(_lancer_spontanees(
        user_id, "fetch", "Récupération des entreprises en Île-de-France...",
        f"▶ Fetch entreprises démarré (au plus {maximum} nouvelles entreprises){note}", travail,
        "Fetch terminé !", "✅ Fetch terminé", "fetch", mode=mode), max_entreprises=maximum,
        **({"avertissement": avertissement} if avertissement else {}))

@router.post("/api/spontanees/scraper")
def api_spontanees_scraper(request: Request, body: Scraper | None = None,
                           user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    user_id = user.id
    from database.entreprises_db import compter_a_scraper
    disponibles = compter_a_scraper(user_id, mode)
    if not disponibles:
        raise ErreurUtilisateur("Aucune entreprise à scraper : lance d'abord « Récupérer ».")
    maximum, note = limite_appliquee("scrapees", body.max_scrapees if body else None, disponibles)

    def travail(arret, log, on_progress):
        from spontanees.recherche_emails import main as scraper_main
        scraper_main(stop_event=arret, log_fn=log, user_id=user_id, on_progress=on_progress,
                     max_scrapees=maximum, mode=mode)

    return _aveclimite_appliquee(_lancer_spontanees(
        user_id, "scraper", "Scraping des emails...",
        f"▶ Scraper emails démarré (au plus {maximum} entreprises){note}", travail,
        "Scraping terminé !", "✅ Scraping terminé", "scraper", mode=mode), max_scrapees=maximum)

# ─── Emails non validés par l'IA : jamais envoyés tels quels (D15) ────────────
@router.get("/api/spontanees/a_valider")
def api_spontanees_a_valider(request: Request, user: User = Depends(utilisateur_requis),
                             mode: str = Depends(mode_requis)):
    from database.entreprises_db import lire_a_valider
    return lire_a_valider(user.id, mode)

@router.post("/api/spontanees/valider")
def api_spontanees_valider(body: ValiderEmails, user: User = Depends(utilisateur_requis)):
    """Validation manuelle des emails d'une entreprise, une à la fois."""
    from database.entreprises_db import valider_emails
    if not valider_emails(user.id, body.id):
        return JSONResponse({"erreur": "Entreprise introuvable ou sans email à valider"}, status_code=404)
    return {"ok": True}

@router.post("/api/spontanees/valider_adresse")
def api_spontanees_valider_adresse(body: ValiderAdresse, user: User = Depends(utilisateur_requis)):
    """Validation manuelle d'une adresse, douteuse ou écartée par l'IA."""
    from database.entreprises_db import valider_adresse
    if not valider_adresse(user.id, body.id, body.adresse):
        return JSONResponse({"erreur": "Adresse introuvable ou déjà validée"}, status_code=404)
    return {"ok": True}

@router.post("/api/spontanees/revalider")
def api_spontanees_revalider(request: Request, body: Revalider | None = None,
                             user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    """Relance la validation par l'IA des entreprises du mode aux emails non validés."""
    user_id = user.id
    if not config.analyse_ia_active():
        raise ErreurUtilisateur("Validation par l'IA indisponible : l'IA est désactivée (ANALYSE_IA=false). "
                                "Valide les emails à la main.")
    from database.entreprises_db import compter_a_valider
    disponibles = compter_a_valider(user_id, mode)
    if not disponibles:
        raise ErreurUtilisateur("Aucun email en attente de validation.")
    maximum, note = limite_appliquee("revalidations", body.max_revalidations if body else None, disponibles)

    def travail(arret, log, on_progress):
        from spontanees.recherche_emails import revalider
        revalider(user_id, stop_event=arret, log_fn=log, on_progress=on_progress, max_n=maximum, mode=mode)

    return _aveclimite_appliquee(_lancer_spontanees(
        user_id, "revalider", "Validation IA des emails...",
        f"▶ Validation IA démarrée (au plus {maximum} entreprises){note}", travail,
        "Validation terminée !", "✅ Validation terminée", "validation", mode=mode),
        max_revalidations=maximum)

@router.post("/api/spontanees/envoyer")
def api_spontanees_envoyer(body: Envoyer, request: Request, user: User = Depends(utilisateur_requis),
                           mode: str = Depends(mode_requis)):
    user_id = user.id
    # Plafond de sécurité par lancement (réputation du compte d'envoi)
    # Refus clair AVANT tout lancement : pas de clé (503), pas de compte ou
    # compte jamais vérifié (400), plafond du jour déjà atteint (400), rien à envoyer (400)
    compte = compte_envoi.exiger_compte_verifie(user_id)
    if compte_envoi_db.envois_du_jour(user_id) >= config.PLAFOND_ENVOIS_JOUR:
        raise ErreurUtilisateur(f"Plafond de {config.PLAFOND_ENVOIS_JOUR} mails par jour atteint : "
                                "les envois reprendront demain.")
    from spontanees.envoi import compter_a_envoyer, objet_et_corps
    # Balise inconnue, ou vide dans le profil (dates du stage...) : 400 avant tout lancement
    objet_et_corps(lire_profil(user_id, mode=mode), mode)
    disponibles = compter_a_envoyer(user_id, mode)
    if not disponibles:
        raise ErreurUtilisateur("Rien à envoyer : aucune entreprise avec un email non contacté dans ce mode.")
    limite, note = limite_appliquee("mails", body.limite, disponibles)
    # Mode test : option du compte d'envoi, ou demandé pour ce lancement
    test = bool(body.test or compte["mode_test"])
    if test:
        message = f"🧪 MODE TEST : envoi vers {compte['adresse']} (limite : {limite})..."
        debut = f"▶ Envoi démarré, limite {limite}{note}. 🧪 MODE TEST : tout part vers {compte['adresse']}"
    else:
        message = f"Envoi en cours (limite : {limite})..."
        debut = f"▶ Envoi démarré, limite {limite}{note}"

    def travail(arret, log, on_progress):
        from spontanees.envoi import main as env_main
        env_main(limite=limite, test=test, stop_event=arret, log_fn=log,
                 user_id=user_id, on_progress=on_progress, mode=mode)

    reponse = _lancer_spontanees(user_id, "envoyer", message, debut, travail,
                                 "Envoi de test terminé !" if test else "Envoi terminé !",
                                 "✅ Envoi terminé", "envoi", mode_test=test, mode=mode)
    return _aveclimite_appliquee(reponse, limite=limite, mode_test=test)
