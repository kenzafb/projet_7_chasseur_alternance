"""
routes/offres.py
================
Offres : liste, recherche France Travail et La Bonne Alternance (thread),
état des pipelines et journal, analyse d'une offre, statuts, « J'ai
postulé », archivage, lettre enregistrée.
"""

import threading
from typing import Literal

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from auth.securite import utilisateur_requis
from database.candidatures_db import (ajouter_candidature, lire_candidature, lire_candidatures, modifier_candidature)
from database.dates import maintenant_utc
from database.models import User
from database.profil_db import (lire_profil)
from offres.analyse_differee import enregistrer_analyse
from offres.analyse import analyser_offre, marquer_non_analysee
from offres.recherche import lancer_recherche
from offres.la_bonne_alternance import ignoree_pour_profil as lba_ignoree_pour_profil
from offres.la_bonne_alternance import rechercher_offres_pour_profil as rechercher_lba
from routes import commun
from routes.analyse import analyse_automatique
from routes.commun import OffreId, limite_appliquee, mode_requis, routeur_prive
from shared import config
from shared.erreurs import ErreurUtilisateur, exiger_profil
from shared.modes import get_mode
from shared.pipelines import ANALYSE, RECHERCHE, SPONTANEES

router = routeur_prive()


# Valeurs autorisées (cf. database/models.py)
StatutCandidature = Literal["nouveau", "en_cours", "envoye", "a_relancer", "reponse", "entretien", "refus", "archive"]
# « a_relancer » : statut de suivi commun aux offres et aux spontanées (D107)
RaisonArchivage = Literal["manuel", "note_basse", "ineligible", "ecole_cfa", "hors_domaine", "public_specifique",
                          "stage"]

class MajStatut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    statut: StatutCandidature

class Archivage(BaseModel):
    """Soit {id, desarchiver: true}, soit {id, raison}."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    desarchiver: bool = False
    raison: RaisonArchivage | None = None

    @model_validator(mode="after")
    def une_seule_action(self):
        if self.desarchiver == (self.raison is not None):
            raise ValueError("indiquer soit desarchiver: true, soit une raison d'archivage")
        return self

class Postuler(BaseModel):
    """J'ai postulé (date du jour par défaut, modifiable), ou retour en arrière."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    date: str | None = Field(None, max_length=10)   # AAAA-MM-JJ
    annuler: bool = False

class Sauvegarde(BaseModel):
    id: str
    lettre: str | None = None
    email_candidature: str | None = None
    objet_email: str | None = None

class Recherche(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_offres: int | None = None


@router.get("/api/logs")
def api_logs(user: User = Depends(utilisateur_requis)):
    return commun.pipelines.logs(user.id)

@router.get("/api/candidatures")
def api_candidatures(user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    return lire_candidatures(user.id, mode=mode)


# ─── France Travail + La Bonne Alternance ────────────────────────────────────

@router.post("/api/recherche")
def api_recherche(request: Request, body: Recherche | None = None, user: User = Depends(utilisateur_requis),
                  mode: str = Depends(mode_requis)):
    """Recherche France Travail et LBA. Les offres sont toujours ajoutées
    « non analysées », sans attendre l'IA (D21) ; l'analyse vient après,
    lancée à la main ou d'elle-même si l'option du profil est cochée."""
    user_id = user.id   # capturé AVANT le thread (le thread n'a pas accès à request)
    # Offres ajoutées au plus, France Travail et LBA confondues : 30 par défaut
    # avec l'IA (à analyser ensuite), 100 sans elle (D20)
    max_offres, note = limite_appliquee("offres" if config.analyse_ia_active() else "offres_sans_ia",
                               body.max_offres if body else None)
    cfg_mode = get_mode(mode)
    profil = lire_profil(user_id, mode=mode)
    exiger_profil(profil)   # 400 tout de suite plutôt qu'une erreur dans le thread

    if not commun.pipelines.demarrer(RECHERCHE, user_id, message="Démarrage...", mode=mode):
        en_cours = commun.pipelines.etat(RECHERCHE, user_id).get("mode")
        return JSONResponse({"erreur": f"Recherche déjà en cours (mode {en_cours})"}, status_code=400)

    def etat(**champs):
        commun.pipelines.maj(RECHERCHE, user_id, **champs)

    def log(msg):
        commun.pipelines.log(user_id, msg)

    def lancer():
        termine = False
        try:
            # Chaque offre est écrite en base au fur et à mesure
            def ecrire_en_base(offre):
                ajouter_candidature(user_id, offre, mode=mode)

            etat(message="Recherche France Travail...")
            log(f"🔍 Recherche France Travail démarrée (au plus {max_offres} offres){note}")
            ajoutees = lancer_recherche(user_id, profil, max_offres=max_offres,
                                        on_offre=ecrire_en_base, mode=mode, log_fn=log) or []
            reste = max_offres - len(ajoutees)
            log(f"✅ France Travail terminé : {len(ajoutees)} offres ajoutées")

            # LBA (mode alternance) : offres seulement, les entreprises à fort
            # potentiel n'entrent que par l'étape « Récupérer » (D46). None :
            # LBA ignorée, raison déjà écrite (pas de « Aucune offre LBA » en plus).
            lba = None
            if "lba" not in cfg_mode["sources"]:
                log("ℹ️  LBA ignorée (mode sans alternance)")
            elif reste <= 0:
                log(f"ℹ️  LBA ignorée : limite de {max_offres} offres atteinte")
            else:
                etat(message="Recherche La Bonne Alternance...", pourcentage=50)
                log("🔍 Recherche La Bonne Alternance démarrée")
                lba = rechercher_lba(profil, log=log)
            offres_lba = lba["offres"] if lba else []

            if offres_lba:
                # Déduplication : refs déjà présentes en base pour cet utilisateur
                ids_existants = {c["id"] for c in lire_candidatures(user_id, mode=mode)}
                nouvelles_lba = [o for o in offres_lba if o["id"] not in ids_existants]
                log(f"  {len(nouvelles_lba)} nouvelles offres LBA (hors doublons FT)")
                if len(nouvelles_lba) > reste:
                    # Les suivantes ne sont pas en base : proposées au prochain lancement
                    log(f"  Limite : {reste} offres LBA sur {len(nouvelles_lba)}")
                    nouvelles_lba = nouvelles_lba[:reste]
                # Écrites « non analysées », archivage par mots-clés seulement
                for offre in nouvelles_lba:
                    marquer_non_analysee(offre, verbeux=False)
                    ajouter_candidature(user_id, offre, mode=mode)
                if nouvelles_lba:
                    log(f"✅ {len(nouvelles_lba)} offres LBA ajoutées")
            elif lba is not None:
                log("ℹ️  Aucune offre LBA récupérée")

            etat(pourcentage=100, message="Terminé !")
            log("✅ Recherche complète terminée")
            termine = True
        except Exception as e:
            etat(message=f"Erreur : {e}")
            log(f"❌ Erreur recherche : {e}")
        finally:
            commun.pipelines.terminer(RECHERCHE, user_id)
        if termine and profil.get("analyse_auto"):
            analyse_automatique(user_id, mode)

    threading.Thread(target=lancer, daemon=True).start()
    reponse = {"status": "démarré", "max_offres": max_offres}
    if "lba" in cfg_mode["sources"]:
        if avertissement := lba_ignoree_pour_profil(profil):
            reponse["avertissement"] = avertissement
    return reponse

@router.get("/api/statut_pipelines")
def api_statut_pipelines(user: User = Depends(utilisateur_requis)):
    """État des pipelines de l'utilisateur en une requête (polling du front)."""
    return {"recherche": commun.pipelines.etat(RECHERCHE, user.id),
            "analyse": commun.pipelines.etat(ANALYSE, user.id),
            "spontanees": commun.pipelines.etat(SPONTANEES, user.id)}


@router.post("/api/analyser")
def api_analyser(body: OffreId, request: Request, user: User = Depends(utilisateur_requis),
                 mode: str = Depends(mode_requis)):
    """Analyse (ou réanalyse) une offre tout de suite, archivage compris."""
    offre = lire_candidature(user.id, body.id, mode=mode)
    if not offre:
        return JSONResponse({"erreur": "Offre introuvable"}, status_code=404)
    if not config.analyse_ia_active():
        return JSONResponse({"erreur": "Analyse indisponible : l'IA est désactivée (ANALYSE_IA=false)."},
                            status_code=503)
    profil = lire_profil(user.id, mode=mode)
    # ErreurIA : réponse 502/503 (gestionnaire plus haut), l'offre n'est pas touchée
    analyse = analyser_offre(offre, profil, mode=mode)
    modifs = enregistrer_analyse(user.id, mode, offre, analyse)
    return {**analyse, "statut": modifs.get("statut", offre.get("statut")),
            "raison_archivage": modifs.get("raison_archivage", offre.get("raison_archivage"))}

@router.post("/api/maj_statut")
def api_maj_statut(body: MajStatut, request: Request, user: User = Depends(utilisateur_requis),
                   mode: str = Depends(mode_requis)):
    modifs = {"statut": body.statut}
    if body.statut in STATUTS_POSTULEE:
        offre = lire_candidature(user.id, body.id, mode=mode)
        if offre and not offre.get("date_candidature"):
            modifs["date_candidature"] = maintenant_utc()
    modifier_candidature(user.id, body.id, modifs, mode=mode)
    return {"ok": True}

# Statuts d'une offre où la personne a postulé (D105) : « envoye » (affiché
# « Postulée »), puis le suivi de la page Mes candidatures
STATUTS_POSTULEE = ("envoye", "a_relancer", "reponse", "entretien", "refus")


@router.post("/api/offre/postuler")
def api_offre_postuler(body: Postuler, user: User = Depends(utilisateur_requis), mode: str = Depends(mode_requis)):
    """Marque l'offre « postulée » à la date donnée (jour de Paris, aujourd'hui
    par défaut ; date future refusée), change la date d'une offre déjà
    postulée, ou annule (retour aux offres à traiter, date effacée)."""
    from datetime import datetime, time
    from database.dates import fuseau_affichage, maintenant_affichage
    from shared.stage import lire_date
    offre = lire_candidature(user.id, body.id, mode=mode)
    if not offre:
        return JSONResponse({"erreur": "Offre introuvable"}, status_code=404)
    if body.annuler:
        modifier_candidature(user.id, body.id, {"statut": "nouveau", "date_candidature": None}, mode=mode)
        return {"ok": True, "statut": "nouveau", "date_candidature": ""}
    jour = lire_date(body.date, "Date de candidature") or maintenant_affichage().date()
    if jour > maintenant_affichage().date():
        raise ErreurUtilisateur("La date de candidature ne peut pas être dans le futur.")
    # Midi, heure de Paris : le jour reste le même une fois converti en UTC
    instant = datetime.combine(jour, time(12), tzinfo=fuseau_affichage())
    statut = offre.get("statut") if offre.get("statut") in STATUTS_POSTULEE else "envoye"
    modifier_candidature(user.id, body.id, {"statut": statut, "date_candidature": instant,
                                            "raison_archivage": ""}, mode=mode)
    return {"ok": True, "statut": statut, "date_candidature": jour.isoformat()}

@router.post("/api/archiver")
def api_archiver(body: OffreId, request: Request, user: User = Depends(utilisateur_requis),
                 mode: str = Depends(mode_requis)):
    modifier_candidature(user.id, body.id, {"statut": "archive"}, mode=mode)
    return {"ok": True}

@router.post("/api/offre/archivage")
def api_offre_archivage(body: Archivage, request: Request, user: User = Depends(utilisateur_requis),
                        mode: str = Depends(mode_requis)):
    """Gère la raison d'archivage et le désarchivage d'une offre."""
    if body.desarchiver:
        modifs = {"statut": "nouveau", "raison_archivage": ""}
    else:
        # Archive avec la raison choisie (et s'assure qu'elle reste archivée)
        modifs = {"statut": "archive", "raison_archivage": body.raison}
    modifier_candidature(user.id, body.id, modifs, mode=mode)
    return {"ok": True}

@router.post("/api/sauvegarder")
def api_sauvegarder(body: Sauvegarde, request: Request, user: User = Depends(utilisateur_requis),
                    mode: str = Depends(mode_requis)):
    modifs = {}
    if body.lettre is not None:            modifs["lettre"] = body.lettre
    if body.email_candidature is not None: modifs["email_candidature"] = body.email_candidature
    if body.objet_email is not None:       modifs["objet_email"] = body.objet_email
    modifier_candidature(user.id, body.id, modifs, mode=mode)
    return {"ok": True}
