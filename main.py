"""
main.py — Chasseur d'Alternance (FastAPI)
=========================================
Application web : pages, routes /api, lancement des pipelines.

Lancement :
    uvicorn main:app --reload --port 5002
    → http://localhost:5002
    → doc API auto-générée : http://localhost:5002/docs

Les pipelines longs (recherche, fetch, scraper, envoi) tournent dans des
threads avec stop_event : les fonctions métier sont synchrones.
"""

import logging
import os
import re
import secrets
import threading
import unicodedata

from shared import config
from shared.config import STATIC_DIR, TEMPLATES_DIR, COOKIE_SECURE, chemin_lettre_pdf, chemin_piece_jointe, secret_key
from fastapi import FastAPI, APIRouter, Depends, Request, Body, UploadFile, File, Form
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from auth.routes import router as auth_router
from auth.securite import NonConnecte, utilisateur_requis, mode_courant
from database.models import User
from shared.erreurs import ErreurUtilisateur, exiger_profil
from database.candidatures_db import (lire_candidatures, lire_candidature, modifier_candidature, ajouter_candidature,
                                     lire_lettre_pdf, enregistrer_lettre_pdf)
from database.profil_db import (lire_profil, sauvegarder_profil, ajouter_piece_jointe, supprimer_piece_jointe,
                                fichiers_references)
from database.entreprises_db import calculer_stats, lire_entreprises_envoyees, modifier_statut_suivi
from typing import Literal
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from shared.chiffrement import ChiffrementIndisponible, raison_indisponible
from shared import compte_envoi
from database import compte_envoi_db
from shared.pipelines import Pipelines, RECHERCHE, SPONTANEES
from shared.statique import importmap, url_statique
from database.dates import maintenant_utc

# ─── Modules métier ───────────────────────────────────────────────
from france_travail.main import lancer_recherche
from france_travail.generateur import generer_lettre
from france_travail.analyseur import analyser_offre, appliquer_analyse, marquer_non_analysee
from shared.ia import ErreurIA, ErreurIABloquante, ErreurIAPassagere
from france_travail.pdf_generator import generer_pdf_lettre, nom_telechargement
from france_travail.scraper_lba import ignoree_pour_profil as lba_ignoree_pour_profil
from france_travail.scraper_lba import rechercher_pour_profil as rechercher_lba

# Documentation automatique désactivée ici : elle est servie plus bas par des
# routes privées (/docs, /openapi.json), réservées aux utilisateurs connectés.
app = FastAPI(title="Chasseur d'Alternance", version="15",
              docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
# URL des JS et CSS versionnées par leur contenu (cache navigateur)
templates.env.globals.update(statique=url_statique, importmap=importmap)

# Sessions signées (cookie de connexion). secret_key() lève une erreur si
# SECRET_KEY est absente ou trop courte : l'app ne démarre pas sans elle.
app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key(),
    max_age=60 * 60 * 24 * 14,   # session valable 14 jours
    same_site="lax",
    https_only=COOKIE_SECURE,
)
app.include_router(auth_router)   # /login, /logout, /register : publiques

# Toutes les autres routes passent par ce routeur : utilisateur_requis
# s'applique à chacune, qu'elle se serve de l'utilisateur ou non.
prive = APIRouter(dependencies=[Depends(utilisateur_requis)])


@app.exception_handler(NonConnecte)
def non_connecte(request: Request, exc: NonConnecte):
    """Sans session : 401 JSON pour l'API, redirection vers /login pour les pages."""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(RequestValidationError)
def requete_invalide(request: Request, exc: RequestValidationError):
    """Corps de requête refusé par son modèle Pydantic : 422, avec un message
    lisible dans "erreur" (affiché par le front) et le détail habituel."""
    # Sans "input" : la valeur reçue (un mot de passe, par exemple) n'est
    # jamais renvoyée ; "ctx" peut contenir l'exception d'origine.
    erreurs = jsonable_encoder([{k: v for k, v in e.items() if k not in ("input", "ctx")}
                                for e in exc.errors()])
    premiere = erreurs[0] if erreurs else {}
    champ = ".".join(str(x) for x in premiere.get("loc", []) if x != "body")
    message = f"Requête invalide : {champ + ' : ' if champ else ''}{premiere.get('msg', '')}"
    return JSONResponse({"erreur": message, "detail": erreurs}, status_code=422)


@app.exception_handler(ErreurUtilisateur)
def erreur_utilisateur(request: Request, exc: ErreurUtilisateur):
    """Profil incomplet, lettre type invalide... : 400 avec un message lisible."""
    return JSONResponse({"erreur": str(exc)}, status_code=400)


@app.exception_handler(ChiffrementIndisponible)
def chiffrement_indisponible(request: Request, exc: ChiffrementIndisponible):
    """CLE_CHIFFREMENT absente ou invalide : l'app tourne, mais configuration
    et envoi de mails sont désactivés (503, message lisible)."""
    return JSONResponse({"erreur": str(exc)}, status_code=503)


@app.exception_handler(ErreurIA)
def erreur_ia(request: Request, exc: ErreurIA):
    """Échec Mistral sur une route directe (lettre, réanalyse) : rien n'est
    enregistré. 503 si la configuration est en cause, 502 sinon."""
    statut = 503 if isinstance(exc, ErreurIABloquante) else 502
    return JSONResponse({"erreur": str(exc)}, status_code=statut)


if raison_indisponible():
    print(f"⚠️  {raison_indisponible()}")


# ─── Journal d'accès : sans les requêtes de statut ───────────────────────────
# Le front interroge l'état des pipelines toutes les quelques secondes tant
# qu'ils tournent : ces lignes noieraient le journal d'accès d'uvicorn.
ROUTES_DE_STATUT = frozenset({"/api/statut_pipelines", "/api/statut_recherche", "/api/spontanees/statut"})


class SansRequetesDeStatut(logging.Filter):
    """Écarte du journal « uvicorn.access » les requêtes vers ROUTES_DE_STATUT.
    uvicorn journalise (client, méthode, chemin avec requête, version, code)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            return str(args[2]).split("?", 1)[0] not in ROUTES_DE_STATUT
        return True


FILTRE_STATUT = SansRequetesDeStatut()
# Le filtre est posé sur le logger : la configuration des logs d'uvicorn
# (dictConfig, appelée avant l'import de l'app) ne le retire pas
logging.getLogger("uvicorn.access").addFilter(FILTRE_STATUT)

# ─── États, arrêts et logs des pipelines, par utilisateur ─────────────────────
pipelines = Pipelines()


# ─── Modèles de requête ───────────────────────────────────────────────────────
class OffreId(BaseModel):
    id: str

# Valeurs autorisées (cf. database/models.py)
StatutCandidature = Literal["nouveau", "en_cours", "envoye", "reponse", "entretien", "refus", "archive"]
RaisonArchivage = Literal["manuel", "note_basse", "ecole_cfa", "hors_domaine", "public_specifique", "stage"]

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

class Sauvegarde(BaseModel):
    id: str
    lettre: str | None = None
    email_candidature: str | None = None
    objet_email: str | None = None

class TelechargerPdf(BaseModel):
    id: str
    lettre: str | None = None

# Limites d'un lancement : absentes = défaut, bornées par config.limite_lancement
def _limite(cle: str, demandee, disponibles: int | None = None) -> tuple[int, str]:
    """Limite appliquée à un lancement, bornée par le plafond et, s'il est
    donné, par le nombre d'éléments disponibles ; et la précision à
    journaliser quand la valeur demandée a été ramenée (décision D6)."""
    appliquee = config.limite_lancement(cle, demandee)
    if disponibles is not None:
        appliquee = min(appliquee, disponibles)
    if demandee is None or demandee == appliquee:
        return appliquee, ""
    return appliquee, f" (demandé : {demandee}, ramené à {appliquee})"

class Recherche(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_analyses: int | None = None

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

class Envoyer(BaseModel):
    limite: int | None = None
    test: bool = False

class CompteEnvoiCorps(BaseModel):
    """Configuration du compte d'envoi. mot_de_passe : en écriture seule,
    absent ou vide = garder celui déjà enregistré."""
    model_config = ConfigDict(extra="forbid")
    preset: Literal["gmail", "autre"]
    adresse: str = Field(max_length=255)
    nom_affiche: str = Field("", max_length=150)
    serveur: str = Field("", max_length=255)
    port: int | None = None
    chiffrement: Literal["ssl", "starttls"] | None = None
    identifiant: str = Field("", max_length=255)
    mot_de_passe: SecretStr | None = None

class ModeTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actif: bool

class MailTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destinataire: str | None = Field(None, max_length=255)


# ─── Page + logs ──────────────────────────────────────────────────────────────

@prive.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "base.html", {"mode": mode_courant(request),
                                                             "limites": config.LIMITES_LANCEMENT,
                                                             "analyse_ia": config.analyse_ia_active()})

@prive.get("/api/logs")
def api_logs(user: User = Depends(utilisateur_requis)):
    return pipelines.logs(user.id)

@prive.get("/api/candidatures")
def api_candidatures(request: Request, user: User = Depends(utilisateur_requis)):
    return lire_candidatures(user.id, mode=mode_courant(request))


# ─── Profil utilisateur ───────────────────────────────────────────────────────
@prive.get("/api/mode")
def api_get_mode(request: Request):
    """Mode actuel (alternance/job) + son label et sa couleur."""
    from shared.modes import get_mode
    cle = mode_courant(request)
    m = get_mode(cle)
    return {"mode": cle, "label": m["label"], "couleur": m["couleur"]}


@prive.post("/api/mode")
def api_set_mode(request: Request, body: dict = Body(...)):
    """Bascule le mode de chasse dans la session."""
    from shared.modes import MODES, MODE_DEFAUT
    nouveau = body.get("mode", MODE_DEFAUT)
    if nouveau not in MODES:
        return JSONResponse({"erreur": "Mode inconnu"}, status_code=400)
    request.session["mode"] = nouveau
    return {"ok": True, "mode": nouveau}


@prive.get("/api/domaines")
def api_domaines():
    """Grands domaines et leurs domaines, pour le choix dans le profil."""
    from shared.domaines import grands_domaines
    return grands_domaines()


@prive.get("/api/criteres_options")
def api_criteres_options():
    """Secteurs employeur, tailles d'entreprise et thèmes proposés dans le profil."""
    from shared.criteres import options_du_profil
    return options_du_profil()


@prive.get("/api/profil")
def api_get_profil(request: Request, user: User = Depends(utilisateur_requis)):
    return lire_profil(user.id, mode=mode_courant(request))


@prive.post("/api/profil")
def api_post_profil(request: Request, body: dict = Body(...), user: User = Depends(utilisateur_requis)):
    ok = sauvegarder_profil(user.id, body, mode=mode_courant(request))
    return {"ok": ok}


# ─── Pièces jointes du profil ─────────────────────────────────────────────────
TAILLE_MAX_PJ = 5 * 1024 * 1024  # 5 Mo
LONGUEUR_MAX_NOM_PJ = 60          # caractères, hors suffixe unique et extension


def _base_nom_fichier(nom: str) -> str:
    """Nom d'origine -> base sûre : sans dossier ni extension, ASCII,
    [A-Za-z0-9_-] seulement, raccourcie (anti path-traversal)."""
    nom = nom.replace("\\", "/").split("/")[-1]
    base = re.sub(r"\.[^.]*$", "", nom)   # extension retirée (splitext garde "....pdf")
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_-")
    return base[:LONGUEUR_MAX_NOM_PJ].rstrip("_-") or "document"


def _ecrire_piece_jointe(user_id: int, nom_origine: str, contenu: bytes) -> str:
    """Écrit le fichier sous un nom unique (base_<hex>.pdf) dans le dossier de
    l'utilisateur, sans jamais écraser un fichier existant. Retourne le chemin
    relatif à UPLOADS_DIR stocké en base."""
    base = _base_nom_fichier(nom_origine)
    while True:
        relatif = f"user_{user_id}/{base}_{secrets.token_hex(4)}.pdf"
        chemin = chemin_piece_jointe(relatif)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(chemin, "xb") as out:   # "x" : échoue si le fichier existe
                out.write(contenu)
            return relatif
        except FileExistsError:
            continue


def _supprimer_si_orpheline(user_id: int, fichiers: list[str]):
    """Supprime du disque les fichiers qu'aucun profil de l'utilisateur
    (tous modes confondus) ne référence plus (bug 9)."""
    encore_utilises = fichiers_references(user_id)
    for relatif in fichiers:
        chemin = chemin_piece_jointe(relatif)
        if relatif in encore_utilises or not chemin:
            continue
        try:
            os.remove(chemin)
        except OSError:
            pass


@prive.post("/api/profil/upload")
async def api_profil_upload(request: Request,
                            nom: str = Form(""),
                            fichier: UploadFile = File(...),
                            user: User = Depends(utilisateur_requis)):
    # Validation type PDF
    if not (fichier.filename or "").lower().endswith(".pdf"):
        return JSONResponse({"erreur": "Seuls les fichiers PDF sont acceptés"}, status_code=400)
    # Si pas de nom fourni : utiliser le nom du fichier (sans extension)
    nom = (nom or "").strip()
    if not nom:
        nom = os.path.splitext(fichier.filename or "Document")[0]
    contenu = await fichier.read()
    if len(contenu) > TAILLE_MAX_PJ:
        return JSONResponse({"erreur": "Fichier trop volumineux (max 5 Mo)"}, status_code=400)
    # Stockage dans le dossier de l'utilisateur ; en base, chemin relatif à UPLOADS_DIR
    relatif = _ecrire_piece_jointe(user.id, fichier.filename, contenu)
    remplacees = ajouter_piece_jointe(user.id, nom, relatif, mode=mode_courant(request))
    _supprimer_si_orpheline(user.id, remplacees)
    return {"ok": True, "nom": nom, "fichier": relatif.split("/", 1)[1]}

@prive.post("/api/profil/piece/supprimer")
def api_profil_piece_supprimer(request: Request, body: dict = Body(...), user: User = Depends(utilisateur_requis)):
    retirees = supprimer_piece_jointe(user.id, body.get("nom", ""), mode=mode_courant(request))
    # Le fichier n'est effacé que si l'autre mode ne s'en sert plus
    _supprimer_si_orpheline(user.id, retirees)
    return {"ok": True}

@prive.get("/api/profil/piece")
def api_profil_piece_get(request: Request, nom: str, user: User = Depends(utilisateur_requis)):
    prof = lire_profil(user.id, mode=mode_courant(request))
    for pj in prof.get("pieces_jointes", []):
        chemin = chemin_piece_jointe(pj.get("fichier", ""))
        if pj.get("nom") == nom and chemin and chemin.is_file():
            return FileResponse(chemin, media_type="application/pdf")
    return JSONResponse({"erreur": "Pièce introuvable"}, status_code=404)


# ─── Compte d'envoi (SMTP de l'utilisateur) ───────────────────────────────────
# Le mot de passe n'est jamais renvoyé : le front ne reçoit que
# mot_de_passe_configure et verifie_le.
@prive.get("/api/compte_envoi")
def api_compte_envoi(user: User = Depends(utilisateur_requis)):
    raison = raison_indisponible()
    return {"disponible": raison is None, "raison": raison or "",
            "compte": compte_envoi_db.lire_compte(user.id),
            "plafond_jour": config.PLAFOND_ENVOIS_JOUR,
            "envois_du_jour": compte_envoi_db.envois_du_jour(user.id)}

@prive.post("/api/compte_envoi")
def api_compte_envoi_enregistrer(body: CompteEnvoiCorps, user: User = Depends(utilisateur_requis)):
    compte_envoi.exiger_chiffrement()
    corps = body.model_dump(exclude={"mot_de_passe"})
    corps["mot_de_passe"] = body.mot_de_passe.get_secret_value() if body.mot_de_passe else None
    existe = compte_envoi_db.lire_compte(user.id) is not None
    champs, mot_de_passe = compte_envoi.preparer(corps, compte_existe=existe)
    return {"ok": True, "compte": compte_envoi_db.enregistrer_compte(user.id, champs, mot_de_passe)}

@prive.post("/api/compte_envoi/supprimer")
def api_compte_envoi_supprimer(user: User = Depends(utilisateur_requis)):
    # Possible même sans clé de chiffrement : rien à déchiffrer
    return {"ok": compte_envoi_db.supprimer_compte(user.id)}

@prive.post("/api/compte_envoi/tester")
def api_compte_envoi_tester(user: User = Depends(utilisateur_requis)):
    """Connexion + authentification puis déconnexion, aucun mail envoyé."""
    return compte_envoi.tester(user.id)

@prive.post("/api/compte_envoi/mode_test")
def api_compte_envoi_mode_test(body: ModeTest, user: User = Depends(utilisateur_requis)):
    """Mode test : les candidatures spontanées partent vers l'adresse
    d'expédition de l'utilisateur, rien n'est enregistré comme contacté."""
    compte = compte_envoi_db.definir_mode_test(user.id, body.actif)
    if compte is None:
        raise ErreurUtilisateur("Configure d'abord ton compte d'envoi.")
    return {"ok": True, "compte": compte}

@prive.post("/api/compte_envoi/mail_test")
def api_compte_envoi_mail_test(body: MailTest | None = None, user: User = Depends(utilisateur_requis)):
    """Mail de test, uniquement vers l'adresse d'expédition du compte."""
    return compte_envoi.envoyer_mail_test(user.id, body.destinataire if body else None)


# ─── France Travail + La Bonne Alternance ────────────────────────────────────

@prive.post("/api/recherche")
def api_recherche(request: Request, body: Recherche | None = None, user: User = Depends(utilisateur_requis)):
    user_id = user.id   # capturé AVANT le thread (le thread n'a pas accès à request)
    ia = config.analyse_ia_active()   # ANALYSE_IA=false : offres insérées « non analysées »
    # Offres traitées au plus, France Travail et LBA confondues ; sans IA,
    # plafond propre (D20), même champ max_analyses
    max_analyses, note = _limite("analyses" if ia else "sans_ia", body.max_analyses if body else None)
    mode = mode_courant(request)   # idem : capturé avant le thread
    traitees = "analysées" if ia else "ajoutées sans analyse"
    from shared.modes import get_mode
    cfg_mode = get_mode(mode)
    profil = lire_profil(user_id, mode=mode)
    exiger_profil(profil)   # 400 tout de suite plutôt qu'une erreur dans le thread

    if not pipelines.demarrer(RECHERCHE, user_id, message="Démarrage..."):
        return JSONResponse({"erreur": "Recherche déjà en cours"}, status_code=400)

    def etat(**champs):
        pipelines.maj(RECHERCHE, user_id, **champs)

    def log(msg):
        pipelines.log(user_id, msg)

    def lancer():
        try:
            # Callback : chaque offre FT analysée est écrite en base au fur et à mesure
            def ecrire_en_base(offre):
                ajouter_candidature(user_id, offre, mode=mode)

            etat(message="Recherche France Travail...")
            if not ia:
                log(f"ℹ️  {config.MESSAGE_IA_DESACTIVEE} Offres ajoutées « non analysées ».")
            log(f"🔍 Recherche France Travail démarrée (au plus {max_analyses} offres {traitees}){note}")
            analysees = lancer_recherche(user_id, profil, analyser=ia, max_analyse=max_analyses,
                                         on_offre=ecrire_en_base, mode=mode, log_fn=log) or []
            reste = max_analyses - len(analysees)
            log(f"✅ France Travail terminé : {len(analysees)} offres {traitees}")

            # LBA (mode alternance). None : LBA ignorée, raison déjà écrite
            # (pas de « Aucune offre LBA » en plus).
            lba = None
            if "lba" not in cfg_mode["sources"]:
                log("ℹ️  LBA ignorée (mode sans alternance)")
            elif reste <= 0:
                log(f"ℹ️  LBA ignorée : limite de {max_analyses} offres {traitees} atteinte")
            else:
                etat(message="Recherche La Bonne Alternance...")
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
                    log(f"  Limite : {reste} offres LBA {traitees} sur {len(nouvelles_lba)}")
                    nouvelles_lba = nouvelles_lba[:reste]

                if nouvelles_lba and not ia:
                    # Sans IA : écrites « non analysées », archivage par mots-clés seulement
                    for offre in nouvelles_lba:
                        marquer_non_analysee(offre, verbeux=False)
                        ajouter_candidature(user_id, offre, mode=mode)
                    log(f"✅ {len(nouvelles_lba)} offres LBA ajoutées sans analyse")
                elif nouvelles_lba:
                    etat(message=f"Analyse de {len(nouvelles_lba)} offres LBA...")
                    log("🧠 Analyse des offres LBA...")
                    ajoutees = 0
                    for i, offre in enumerate(nouvelles_lba, 1):
                        etat(message=f"Analyse LBA {i}/{len(nouvelles_lba)}...",
                             pourcentage=40 + round(i / len(nouvelles_lba) * 60))
                        try:
                            # Pas de pause ici : shared.ia espace déjà les appels Mistral
                            analyse = analyser_offre(offre, profil)
                        except ErreurIAPassagere as e:
                            # Ni écrite ni archivée : elle reviendra au prochain lancement
                            log(f"  ⚠️  Offre LBA sautée, « {offre.get('titre', '?')[:50]} » : {e}. "
                                "Elle reviendra au prochain lancement.")
                            continue
                        # Archivage auto avec raison (mêmes règles qu'analyser_offres, sans log)
                        appliquer_analyse(offre, analyse, verbeux=False)
                        ajouter_candidature(user_id, offre, mode=mode)   # écriture base au fur et à mesure
                        ajoutees += 1
                    log(f"✅ {ajoutees} offres LBA analysées et ajoutées sur {len(nouvelles_lba)}")
            elif lba is not None:
                log("ℹ️  Aucune offre LBA récupérée")

            etat(pourcentage=100, message="Terminé !")
            log("✅ Recherche complète terminée")
        except ErreurIABloquante as e:
            # Clé refusée, modèle non autorisé... : arrêt immédiat, rien d'inventé
            etat(message=f"Erreur : {e}")
            log(f"❌ Recherche arrêtée : {e}")
        except Exception as e:
            etat(message=f"Erreur : {e}")
            log(f"❌ Erreur recherche : {e}")
        finally:
            pipelines.terminer(RECHERCHE, user_id)

    threading.Thread(target=lancer, daemon=True).start()
    reponse = {"status": "démarré", "max_analyses": max_analyses}
    if "lba" in cfg_mode["sources"]:
        if avertissement := lba_ignoree_pour_profil(profil):
            reponse["avertissement"] = avertissement
    return reponse

@prive.get("/api/statut_recherche")
def api_statut_recherche(user: User = Depends(utilisateur_requis)):
    return pipelines.etat(RECHERCHE, user.id)

@prive.get("/api/statut_pipelines")
def api_statut_pipelines(user: User = Depends(utilisateur_requis)):
    """État des deux pipelines de l'utilisateur en une requête (polling du front)."""
    return {"recherche": pipelines.etat(RECHERCHE, user.id),
            "spontanees": pipelines.etat(SPONTANEES, user.id)}

@prive.post("/api/generer_lettre")
def api_generer_lettre(body: OffreId, request: Request, user: User = Depends(utilisateur_requis)):
    offre = lire_candidature(user.id, body.id, mode=mode_courant(request))
    if not offre:
        return JSONResponse({"erreur": "Offre introuvable"}, status_code=404)
    if not config.analyse_ia_active():
        return JSONResponse({"erreur": "Génération de lettre indisponible : l'IA est désactivée "
                                       "(ANALYSE_IA=false). Écris la lettre toi-même ou réactive l'IA."},
                            status_code=503)
    profil = lire_profil(user.id, mode=mode_courant(request))
    lettre = generer_lettre(offre, profil, mode=mode_courant(request))
    modifier_candidature(user.id, body.id, {"lettre": lettre, "statut": "en_cours"}, mode=mode_courant(request))
    return {"lettre": lettre}

@prive.post("/api/analyser")
def api_analyser(body: OffreId, request: Request, user: User = Depends(utilisateur_requis)):
    offre = lire_candidature(user.id, body.id, mode=mode_courant(request))
    if not offre:
        return JSONResponse({"erreur": "Offre introuvable"}, status_code=404)
    if not config.analyse_ia_active():
        return JSONResponse({"erreur": "Analyse indisponible : l'IA est désactivée (ANALYSE_IA=false)."},
                            status_code=503)
    profil = lire_profil(user.id, mode=mode_courant(request))
    # ErreurIA : réponse 502/503 (gestionnaire plus haut), l'offre n'est pas touchée
    analyse = analyser_offre(offre, profil, mode=mode_courant(request))
    modifs = {
        "score":          analyse["score"],
        "verdict":        analyse["verdict"],
        "eligible":       analyse["eligible"],
        "points_forts":   analyse["points_forts"],
        "points_faibles": analyse["points_faibles"],
        "resume_analyse": analyse["resume"],
    }
    if analyse.get("statut_auto") == "archive":
        modifs["statut"] = "archive"
    modifier_candidature(user.id, body.id, modifs, mode=mode_courant(request))
    return analyse

@prive.post("/api/maj_statut")
def api_maj_statut(body: MajStatut, request: Request, user: User = Depends(utilisateur_requis)):
    modifs = {"statut": body.statut}
    if body.statut in ["envoye", "reponse", "entretien", "refus"]:
        offre = lire_candidature(user.id, body.id, mode=mode_courant(request))
        if offre and not offre.get("date_candidature"):
            modifs["date_candidature"] = maintenant_utc()
    modifier_candidature(user.id, body.id, modifs, mode=mode_courant(request))
    return {"ok": True}

@prive.post("/api/archiver")
def api_archiver(body: OffreId, request: Request, user: User = Depends(utilisateur_requis)):
    modifier_candidature(user.id, body.id, {"statut": "archive"}, mode=mode_courant(request))
    return {"ok": True}

@prive.post("/api/offre/archivage")
def api_offre_archivage(body: Archivage, request: Request, user: User = Depends(utilisateur_requis)):
    """Gère la raison d'archivage et le désarchivage d'une offre."""
    if body.desarchiver:
        modifs = {"statut": "nouveau", "raison_archivage": ""}
    else:
        # Archive avec la raison choisie (et s'assure qu'elle reste archivée)
        modifs = {"statut": "archive", "raison_archivage": body.raison}
    modifier_candidature(user.id, body.id, modifs, mode=mode_courant(request))
    return {"ok": True}

@prive.post("/api/sauvegarder")
def api_sauvegarder(body: Sauvegarde, request: Request, user: User = Depends(utilisateur_requis)):
    modifs = {}
    if body.lettre is not None:            modifs["lettre"] = body.lettre
    if body.email_candidature is not None: modifs["email_candidature"] = body.email_candidature
    if body.objet_email is not None:       modifs["objet_email"] = body.objet_email
    modifier_candidature(user.id, body.id, modifs, mode=mode_courant(request))
    return {"ok": True}

@prive.post("/api/telecharger_pdf")
def api_telecharger_pdf(body: TelechargerPdf, request: Request, user: User = Depends(utilisateur_requis)):
    """Génère le PDF de la lettre et renvoie l'URL de téléchargement."""
    mode = mode_courant(request)
    offre = lire_candidature(user.id, body.id, mode=mode)
    if not offre:
        return JSONResponse({"erreur": "Non trouvé"}, status_code=404)
    lettre = body.lettre or offre.get("lettre")
    if not lettre:
        return JSONResponse({"erreur": "Vide"}, status_code=400)
    profil = lire_profil(user.id, mode=mode)
    fichier = generer_pdf_lettre(offre, lettre, profil, user.id)
    ancien = enregistrer_lettre_pdf(user.id, body.id, fichier, mode=mode)
    # Le PDF précédent de cette candidature est remplacé : on le supprime
    chemin_ancien = chemin_lettre_pdf(ancien or "")
    if chemin_ancien and ancien != fichier:
        try:
            os.remove(chemin_ancien)
        except OSError:
            pass
    return {"ok": True, "url": f"/api/lettre_pdf/{body.id}", "nom": nom_telechargement(offre, profil)}

@prive.get("/api/lettre_pdf/{ref_offre}")
def api_lettre_pdf(ref_offre: str, request: Request, user: User = Depends(utilisateur_requis)):
    """Renvoie le PDF d'une candidature de l'utilisateur connecté, en pièce
    jointe. Celui d'un autre utilisateur est introuvable (404)."""
    mode = mode_courant(request)
    relatif = lire_lettre_pdf(user.id, ref_offre, mode=mode)
    chemin = chemin_lettre_pdf(relatif)
    # Défense en profondeur : le fichier doit être dans le dossier de l'utilisateur
    if not (chemin and relatif.startswith(f"user_{user.id}/") and chemin.is_file()):
        return JSONResponse({"erreur": "PDF introuvable"}, status_code=404)
    offre = lire_candidature(user.id, ref_offre, mode=mode) or {}
    nom = nom_telechargement(offre, lire_profil(user.id, mode=mode))
    return FileResponse(chemin, media_type="application/pdf", filename=nom)


# ─── Spontanées — Suivi des candidatures ──────────────────────────────────────
@prive.get("/api/spontanees/suivi")
def api_spontanees_suivi(request: Request, user: User = Depends(utilisateur_requis)):
    return lire_entreprises_envoyees(user.id)


@prive.post("/api/spontanees/suivi/statut")
def api_spontanees_statut(request: Request, body: dict = Body(...), user: User = Depends(utilisateur_requis)):
    ok = modifier_statut_suivi(user.id, body.get("id"), body.get("statut", ""))
    return {"ok": ok}


# ─── Spontanées — Stats ───────────────────────────────────────────────────────

@prive.get("/api/spontanees/stats")
def api_spontanees_stats(request: Request, user: User = Depends(utilisateur_requis)):
    # Lecture des stats depuis la base
    stats = calculer_stats(user.id)
    # Maximums utiles des lancements (le serveur les applique aussi)
    from database.entreprises_db import compter_a_scraper
    from spontanees.envoyeur import compter_a_envoyer
    stats["a_scraper"] = compter_a_scraper(user.id)
    stats["a_envoyer"] = compter_a_envoyer(user.id, mode_courant(request))
    from database.entreprises_db import compter_a_valider
    stats["a_valider"] = compter_a_valider(user.id)
    # On ajoute l'état du pipeline de l'utilisateur, géré en mémoire
    etat = pipelines.etat(SPONTANEES, user.id)
    stats.update({cle: etat[cle] for cle in ("en_cours", "etape", "message", "pourcentage", "mode_test")})
    return stats

@prive.post("/api/spontanees/stop")
def api_spontanees_stop(user: User = Depends(utilisateur_requis)):
    """Arrête le pipeline spontané de l'utilisateur connecté, et lui seul."""
    en_cours = pipelines.demander_arret(user.id)
    if en_cours:
        pipelines.log(user.id, "⏹️  Arrêt demandé par l'utilisateur")
    return {"ok": True, "en_cours": en_cours}


def _lancer_spontanees(user_id: int, etape: str, message: str, debut_log: str,
                       travail, fin_message: str, fin_log: str, nom_erreur: str, **etat):
    """Lance une étape du pipeline spontané dans un thread, pour cet utilisateur.
    travail(stop_event, log_fn, on_progress) fait le vrai travail.
    Retourne une réponse 400 si un pipeline spontané de l'utilisateur tourne déjà."""
    if not pipelines.demarrer(SPONTANEES, user_id, etape=etape, message=message, **etat):
        return JSONResponse({"erreur": "Pipeline déjà en cours"}, status_code=400)
    arret = pipelines.evenement_arret(user_id)

    def log(msg):
        pipelines.log(user_id, msg)

    def on_progress(pct, message=None):
        champs = {"pourcentage": pct}
        if message:
            champs["message"] = message
        pipelines.maj(SPONTANEES, user_id, **champs)

    def lancer():
        log(debut_log)
        try:
            travail(arret, log, on_progress)
            if arret.is_set():
                pipelines.maj(SPONTANEES, user_id, message="Arrêté — données sauvegardées")
            else:
                pipelines.maj(SPONTANEES, user_id, message=fin_message)
                log(fin_log)
        except Exception as e:
            pipelines.maj(SPONTANEES, user_id, message=f"Erreur {nom_erreur} : {e}")
            log(f"❌ Erreur {nom_erreur} : {e}")
        finally:
            pipelines.terminer(SPONTANEES, user_id, etape=None)

    threading.Thread(target=lancer, daemon=True).start()
    return {"status": "démarré"}


def _avec_limite(reponse, **limite):
    """Ajoute la limite effective à la réponse d'un lancement réussi."""
    if isinstance(reponse, dict):
        reponse.update(limite)
    return reponse

@prive.post("/api/spontanees/fetch")
def api_spontanees_fetch(body: Fetch | None = None, user: User = Depends(utilisateur_requis)):
    user_id = user.id
    maximum, note = _limite("entreprises", body.max_entreprises if body else None)
    # Même profil que fetch_entreprises (mode alternance) : LBA d'abord, puis Sirene
    from shared.domaines import avertissement_non_couverts, domaines_du_profil
    profil = lire_profil(user_id)
    avertissement = " ".join(filter(None, [
        lba_ignoree_pour_profil(profil),
        avertissement_non_couverts(domaines_du_profil(profil), "sirene")]))

    def travail(arret, log, on_progress):
        from spontanees.fetch_entreprises import main as fetch_main
        fetch_main(stop_event=arret, on_progress=on_progress, user_id=user_id,
                   max_entreprises=maximum, log_fn=log)

    return _avec_limite(_lancer_spontanees(
        user_id, "fetch", "Récupération des entreprises en Île-de-France...",
        f"▶ Fetch entreprises démarré (au plus {maximum} nouvelles entreprises){note}", travail,
        "Fetch terminé !", "✅ Fetch terminé", "fetch"), max_entreprises=maximum,
        **({"avertissement": avertissement} if avertissement else {}))

@prive.post("/api/spontanees/scraper")
def api_spontanees_scraper(body: Scraper | None = None, user: User = Depends(utilisateur_requis)):
    user_id = user.id
    from database.entreprises_db import compter_a_scraper
    disponibles = compter_a_scraper(user_id)
    if not disponibles:
        raise ErreurUtilisateur("Aucune entreprise à scraper : lance d'abord « Récupérer ».")
    maximum, note = _limite("scrapees", body.max_scrapees if body else None, disponibles)

    def travail(arret, log, on_progress):
        from spontanees.scraper_emails import main as scraper_main
        scraper_main(stop_event=arret, log_fn=log, user_id=user_id, on_progress=on_progress,
                     max_scrapees=maximum)

    return _avec_limite(_lancer_spontanees(
        user_id, "scraper", "Scraping des emails...",
        f"▶ Scraper emails démarré (au plus {maximum} entreprises){note}", travail,
        "Scraping terminé !", "✅ Scraping terminé", "scraper"), max_scrapees=maximum)

# ─── Emails non validés par l'IA : jamais envoyés tels quels (D15) ────────────
@prive.get("/api/spontanees/a_valider")
def api_spontanees_a_valider(user: User = Depends(utilisateur_requis)):
    from database.entreprises_db import lire_a_valider
    return lire_a_valider(user.id)

@prive.post("/api/spontanees/valider")
def api_spontanees_valider(body: ValiderEmails, user: User = Depends(utilisateur_requis)):
    """Validation manuelle des emails d'une entreprise, une à la fois."""
    from database.entreprises_db import valider_emails
    if not valider_emails(user.id, body.id):
        return JSONResponse({"erreur": "Entreprise introuvable ou sans email à valider"}, status_code=404)
    return {"ok": True}

@prive.post("/api/spontanees/revalider")
def api_spontanees_revalider(body: Revalider | None = None, user: User = Depends(utilisateur_requis)):
    """Relance la validation par l'IA des entreprises aux emails non validés."""
    user_id = user.id
    if not config.analyse_ia_active():
        raise ErreurUtilisateur("Validation par l'IA indisponible : l'IA est désactivée (ANALYSE_IA=false). "
                                "Valide les emails à la main.")
    from database.entreprises_db import compter_a_valider
    disponibles = compter_a_valider(user_id)
    if not disponibles:
        raise ErreurUtilisateur("Aucun email en attente de validation.")
    maximum, note = _limite("revalidations", body.max_revalidations if body else None, disponibles)

    def travail(arret, log, on_progress):
        from spontanees.scraper_emails import revalider
        revalider(user_id, stop_event=arret, log_fn=log, on_progress=on_progress, max_n=maximum)

    return _avec_limite(_lancer_spontanees(
        user_id, "revalider", "Validation IA des emails...",
        f"▶ Validation IA démarrée (au plus {maximum} entreprises){note}", travail,
        "Validation terminée !", "✅ Validation terminée", "validation"), max_revalidations=maximum)

@prive.post("/api/spontanees/envoyer")
def api_spontanees_envoyer(body: Envoyer, request: Request, user: User = Depends(utilisateur_requis)):
    user_id = user.id
    mode = mode_courant(request)   # capturé avant le thread
    # Plafond de sécurité par lancement (réputation du compte d'envoi)
    # Refus clair AVANT tout lancement : pas de clé (503), pas de compte ou
    # compte jamais vérifié (400), plafond du jour déjà atteint (400), rien à envoyer (400)
    compte = compte_envoi.exiger_compte_verifie(user_id)
    if compte_envoi_db.envois_du_jour(user_id) >= config.PLAFOND_ENVOIS_JOUR:
        raise ErreurUtilisateur(f"Plafond de {config.PLAFOND_ENVOIS_JOUR} mails par jour atteint : "
                                "les envois reprendront demain.")
    from spontanees.envoyeur import compter_a_envoyer
    disponibles = compter_a_envoyer(user_id, mode)
    if not disponibles:
        raise ErreurUtilisateur("Rien à envoyer : aucune entreprise avec un email non contacté dans ce mode.")
    limite, note = _limite("mails", body.limite, disponibles)
    # Mode test : option du compte d'envoi, ou demandé pour ce lancement
    test = bool(body.test or compte["mode_test"])
    if test:
        message = f"🧪 MODE TEST : envoi vers {compte['adresse']} (limite : {limite})..."
        debut = f"▶ Envoi démarré, limite {limite}{note}. 🧪 MODE TEST : tout part vers {compte['adresse']}"
    else:
        message = f"Envoi en cours (limite : {limite})..."
        debut = f"▶ Envoi démarré, limite {limite}{note}"

    def travail(arret, log, on_progress):
        from spontanees.envoyeur import main as env_main
        env_main(limite=limite, test=test, stop_event=arret, log_fn=log,
                 user_id=user_id, on_progress=on_progress, mode=mode)

    reponse = _lancer_spontanees(user_id, "envoyer", message, debut, travail,
                                 "Envoi de test terminé !" if test else "Envoi terminé !",
                                 "✅ Envoi terminé", "envoi", mode_test=test)
    return _avec_limite(reponse, limite=limite, mode_test=test)

@prive.get("/api/spontanees/statut")
def api_spontanees_etat(user: User = Depends(utilisateur_requis)):
    return pipelines.etat(SPONTANEES, user.id)


# ─── Documentation de l'API (connecté uniquement) ─────────────────────────────
@prive.get("/openapi.json", include_in_schema=False)
def openapi_json():
    return app.openapi()

@prive.get("/docs", include_in_schema=False)
def docs():
    return get_swagger_ui_html(openapi_url="/openapi.json", title=app.title + " : API")


# Inclus après la déclaration de toutes les routes privées
app.include_router(prive)


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Chasseur Alternance (FastAPI) sur http://localhost:5002\n")
    uvicorn.run("main:app", host="0.0.0.0", port=5002, reload=True)
