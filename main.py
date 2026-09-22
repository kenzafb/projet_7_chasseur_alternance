"""
main.py — Chasseur d'Alternance (FastAPI)
=========================================
Remplace app.py (Flask). Mêmes routes, mêmes modules métier importés.

Lancement :
    uvicorn main:app --reload --port 5002
    → http://localhost:5002
    → doc API auto-générée : http://localhost:5002/docs

Différences avec Flask :
  - render_template  → templates.TemplateResponse
  - jsonify(x)       → on retourne directement x (dict / list)
  - request.get_json → modèle Pydantic en paramètre
  - send_file        → FileResponse
Les pipelines longs tournent toujours dans des threads avec stop_event
(inchangé par rapport à Flask : tes fonctions métier sont synchrones).
"""

import os
import json
import threading
import collections
from datetime import datetime

from fastapi import FastAPI, Request, Body, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from auth.routes import router as auth_router
from auth.securite import utilisateur_courant, mode_courant
from database.candidatures_db import lire_candidatures, lire_candidature, modifier_candidature, ajouter_candidature
from database.profil_db import lire_profil, sauvegarder_profil, ajouter_piece_jointe, supprimer_piece_jointe
from database.entreprises_db import calculer_stats, lire_entreprises_envoyees, modifier_statut_suivi
from pydantic import BaseModel
from dotenv import load_dotenv

# ─── Modules métier (inchangés) ───────────────────────────────────────────────
from france_travail.main import (
    lancer_recherche, charger_candidatures, sauvegarder_candidatures,
)
from france_travail.generateur import generer_lettre
from france_travail.analyseur import analyser_offre, score_to_verdict
from france_travail.pdf_generator import generer_pdf_lettre
from france_travail.scraper_lba import chercher_offres_lba

load_dotenv()

app = FastAPI(title="Chasseur d'Alternance", version="15")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Sessions signées (cookie de connexion). La clé vient du .env en prod.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "dev-secret-a-changer-en-prod"),
    max_age=60 * 60 * 24 * 14,   # session valable 14 jours
)
app.include_router(auth_router)

# ─── États des pipelines ──────────────────────────────────────────────────────
etat_recherche  = {"en_cours": False, "message": "Prêt", "pourcentage": 0}
etat_spontanees = {"en_cours": False, "etape": None, "message": "Prêt", "pourcentage": 0}
_stop_event     = threading.Event()

FICHIER_ENRICHIES = "data/entreprises_enrichies.json"
FICHIER_RAW       = "data/entreprises_raw.json"

# ─── Logs ─────────────────────────────────────────────────────────────────────
_logs = collections.deque(maxlen=80)

def log(msg):
    _logs.append({"t": datetime.now().strftime("%H:%M:%S"), "msg": msg})
    print(msg)


# ─── Modèles de requête (remplacent request.get_json) ─────────────────────────
class OffreId(BaseModel):
    id: str

class MajStatut(BaseModel):
    id: str
    statut: str

class Sauvegarde(BaseModel):
    id: str
    lettre: str | None = None
    email_candidature: str | None = None
    objet_email: str | None = None

class TelechargerPdf(BaseModel):
    id: str
    lettre: str | None = None

class Envoyer(BaseModel):
    limite: int = 10
    test: bool = False


# ─── Page + logs ──────────────────────────────────────────────────────────────

@app.get("/")
def index(request: Request):
    user = utilisateur_courant(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "base.html", {"mode": mode_courant(request)})

@app.get("/api/logs")
def api_logs():
    return list(_logs)

@app.get("/api/candidatures")
def api_candidatures(request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    return lire_candidatures(user.id, mode=mode_courant(request))


# ─── Profil utilisateur ───────────────────────────────────────────────────────
@app.get("/api/mode")
def api_get_mode(request: Request):
    """Mode actuel (alternance/job) + son label et sa couleur."""
    from shared.modes import get_mode
    cle = mode_courant(request)
    m = get_mode(cle)
    return {"mode": cle, "label": m["label"], "couleur": m["couleur"]}


@app.post("/api/mode")
def api_set_mode(request: Request, body: dict = Body(...)):
    """Bascule le mode de chasse dans la session."""
    from shared.modes import MODES, MODE_DEFAUT
    nouveau = body.get("mode", MODE_DEFAUT)
    if nouveau not in MODES:
        return JSONResponse({"erreur": "Mode inconnu"}, status_code=400)
    request.session["mode"] = nouveau
    return {"ok": True, "mode": nouveau}


@app.get("/api/domaines")
def api_domaines():
    """Liste des domaines disponibles pour le choix dans le profil."""
    from shared.domaines import labels_domaines
    return labels_domaines()


@app.get("/api/profil")
def api_get_profil(request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    return lire_profil(user.id, mode=mode_courant(request))


@app.post("/api/profil")
def api_post_profil(request: Request, body: dict = Body(...)):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    ok = sauvegarder_profil(user.id, body, mode=mode_courant(request))
    return {"ok": ok}


# ─── Pièces jointes du profil ─────────────────────────────────────────────────
import re as _re
from pathlib import Path

DOSSIER_UPLOADS = Path("data/uploads")
TAILLE_MAX_PJ = 5 * 1024 * 1024  # 5 Mo

def _nom_fichier_sur(nom: str) -> str:
    """Nettoie un nom de fichier (anti path-traversal)."""
    nom = nom.replace("\\", "/").split("/")[-1]
    nom = _re.sub(r"[^A-Za-z0-9._-]", "_", nom)
    return nom[:80] or "fichier.pdf"

@app.post("/api/profil/upload")
async def api_profil_upload(request: Request,
                            nom: str = Form(""),
                            fichier: UploadFile = File(...)):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    # Validation type PDF
    if not (fichier.filename or "").lower().endswith(".pdf"):
        return JSONResponse({"erreur": "Seuls les fichiers PDF sont acceptés"}, status_code=400)
    # Si pas de nom fourni : utiliser le nom du fichier (sans extension)
    nom = (nom or "").strip()
    if not nom:
        import os as _os
        nom = _os.path.splitext(fichier.filename or "Document")[0]
    contenu = await fichier.read()
    if len(contenu) > TAILLE_MAX_PJ:
        return JSONResponse({"erreur": "Fichier trop volumineux (max 5 Mo)"}, status_code=400)
    # Stockage dans le dossier de l'utilisateur
    dossier = DOSSIER_UPLOADS / f"user_{user.id}"
    dossier.mkdir(parents=True, exist_ok=True)
    nom_fichier = _nom_fichier_sur(fichier.filename)
    chemin = dossier / nom_fichier
    with open(chemin, "wb") as out:
        out.write(contenu)
    ajouter_piece_jointe(user.id, nom, str(chemin), mode=mode_courant(request))
    return {"ok": True, "nom": nom, "fichier": nom_fichier}

@app.post("/api/profil/piece/supprimer")
def api_profil_piece_supprimer(request: Request, body: dict = Body(...)):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    nom = body.get("nom", "")
    # Retrouve le chemin pour supprimer le fichier du disque
    prof = lire_profil(user.id, mode=mode_courant(request))
    for pj in prof.get("pieces_jointes", []):
        if pj.get("nom") == nom and pj.get("fichier"):
            try:
                os.remove(pj["fichier"])
            except OSError:
                pass
    supprimer_piece_jointe(user.id, nom, mode=mode_courant(request))
    return {"ok": True}

@app.get("/api/profil/piece")
def api_profil_piece_get(request: Request, nom: str):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    prof = lire_profil(user.id, mode=mode_courant(request))
    for pj in prof.get("pieces_jointes", []):
        if pj.get("nom") == nom and pj.get("fichier") and os.path.exists(pj["fichier"]):
            return FileResponse(pj["fichier"], media_type="application/pdf")
    return JSONResponse({"erreur": "Pièce introuvable"}, status_code=404)


# ─── France Travail + La Bonne Alternance ────────────────────────────────────

@app.post("/api/recherche")
def api_recherche(request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    if etat_recherche["en_cours"]:
        return JSONResponse({"erreur": "Recherche déjà en cours"}, status_code=400)

    user_id = user.id   # capturé AVANT le thread (le thread n'a pas accès à request)
    mode = mode_courant(request)   # idem : capturé avant le thread
    from shared.modes import get_mode
    cfg_mode = get_mode(mode)
    profil = lire_profil(user_id, mode=mode)

    def lancer():
        etat_recherche["en_cours"] = True
        etat_recherche["pourcentage"] = 0
        try:
            # Callback : chaque offre FT analysée est écrite en base au fur et à mesure
            def ecrire_en_base(offre):
                ajouter_candidature(user_id, offre, mode=mode)

            etat_recherche["message"] = "Recherche France Travail..."
            log("🔍 Recherche France Travail démarrée")
            lancer_recherche(analyser=True, max_analyse=999, on_offre=ecrire_en_base, profil=profil, mode=mode)
            log("✅ France Travail terminé")

            if "lba" in cfg_mode["sources"]:
                etat_recherche["message"] = "Recherche La Bonne Alternance..."
                log("🔍 Recherche La Bonne Alternance démarrée")
                from shared.domaines import lba_romes
                _cles = (profil or {}).get("recherche", {}).get("domaines", [])
                offres_lba = chercher_offres_lba(lba_romes(_cles))
            else:
                log("ℹ️  LBA ignorée (mode sans alternance)")
                offres_lba = []

            if offres_lba:
                # Déduplication : refs déjà présentes en base pour cet utilisateur
                ids_existants = {c["id"] for c in lire_candidatures(user_id, mode=mode)}
                nouvelles_lba = [o for o in offres_lba if o["id"] not in ids_existants]
                log(f"  {len(nouvelles_lba)} nouvelles offres LBA (hors doublons FT)")

                if nouvelles_lba:
                    etat_recherche["message"] = f"Analyse de {len(nouvelles_lba)} offres LBA..."
                    log("🧠 Analyse des offres LBA...")
                    for i, offre in enumerate(nouvelles_lba, 1):
                        try:
                            etat_recherche["message"] = f"Analyse LBA {i}/{len(nouvelles_lba)}..."
                            etat_recherche["pourcentage"] = 40 + round(i / len(nouvelles_lba) * 60)
                            analyse = analyser_offre(offre, profil)
                            score = analyse.get("score", 5)
                            offre.update({
                                "score":          score,
                                "verdict":        score_to_verdict(score),
                                "eligible":       analyse.get("eligible", True),
                                "points_forts":   analyse.get("points_forts", []),
                                "points_faibles": analyse.get("points_faibles", []),
                                "domaine":        analyse.get("domaine", "Autre IT"),
                                "resume_analyse": analyse.get("resume", ""),
                            })
                            # Archivage auto avec raison (même logique que analyser_offres)
                            titre_l = offre.get("titre", "").lower()
                            desc_l  = offre.get("description", "").lower()
                            offre["raison_archivage"] = ""
                            if "boeth" in desc_l or "maazi" in desc_l or "situation de handicap" in desc_l:
                                offre["statut"] = "archive"; offre["raison_archivage"] = "public_specifique"
                            elif analyse.get("statut_auto") == "archive":
                                offre["statut"] = "archive"; offre["raison_archivage"] = "ecole_cfa"
                            elif offre.get("domaine") == "Hors IT":
                                offre["statut"] = "archive"; offre["raison_archivage"] = "hors_it"
                            elif "stage" in titre_l:
                                offre["statut"] = "archive"; offre["raison_archivage"] = "stage"
                            elif not offre.get("eligible", True) and score <= 2:
                                offre["statut"] = "archive"; offre["raison_archivage"] = "note_basse"
                        except Exception as e:
                            log(f"  ⚠️ Erreur analyse LBA {offre.get('titre', '?')[:40]} : {e}")
                        ajouter_candidature(user_id, offre, mode=mode)   # écriture base au fur et à mesure
                    log(f"✅ {len(nouvelles_lba)} offres LBA ajoutées et analysées")
            else:
                log("ℹ️  Aucune offre LBA récupérée")

            etat_recherche["pourcentage"] = 100
            etat_recherche["message"] = "Terminé !"
            log("✅ Recherche complète terminée")
        except Exception as e:
            etat_recherche["message"] = f"Erreur : {e}"
            log(f"❌ Erreur recherche : {e}")
        finally:
            etat_recherche["en_cours"] = False

    threading.Thread(target=lancer, daemon=True).start()
    return {"status": "démarré"}

@app.get("/api/statut_recherche")
def api_statut_recherche():
    return etat_recherche

@app.post("/api/generer_lettre")
def api_generer_lettre(body: OffreId, request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    offre = lire_candidature(user.id, body.id, mode=mode_courant(request))
    if not offre:
        return JSONResponse({"erreur": "Offre introuvable"}, status_code=404)
    profil = lire_profil(user.id, mode=mode_courant(request))
    lettre = generer_lettre(offre, profil, mode=mode_courant(request))
    modifier_candidature(user.id, body.id, {"lettre": lettre, "statut": "en_cours"}, mode=mode_courant(request))
    return {"lettre": lettre}

@app.post("/api/analyser")
def api_analyser(body: OffreId, request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    offre = lire_candidature(user.id, body.id, mode=mode_courant(request))
    if not offre:
        return JSONResponse({"erreur": "Offre introuvable"}, status_code=404)
    profil = lire_profil(user.id, mode=mode_courant(request))
    analyse = analyser_offre(offre, profil)
    modifs = {
        "score":          analyse.get("score", 5),
        "verdict":        analyse.get("verdict", "moyen"),
        "eligible":       analyse.get("eligible", True),
        "points_forts":   analyse.get("points_forts", []),
        "points_faibles": analyse.get("points_faibles", []),
        "resume_analyse": analyse.get("resume", ""),
    }
    if analyse.get("statut_auto") == "archive":
        modifs["statut"] = "archive"
    modifier_candidature(user.id, body.id, modifs, mode=mode_courant(request))
    return analyse

@app.post("/api/maj_statut")
def api_maj_statut(body: MajStatut, request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    modifs = {"statut": body.statut}
    if body.statut in ["envoye", "reponse", "entretien", "refus"]:
        offre = lire_candidature(user.id, body.id, mode=mode_courant(request))
        if offre and not offre.get("date_candidature"):
            modifs["date_candidature"] = datetime.now().strftime("%Y-%m-%d")
    modifier_candidature(user.id, body.id, modifs, mode=mode_courant(request))
    return {"ok": True}

@app.post("/api/archiver")
def api_archiver(body: OffreId, request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    modifier_candidature(user.id, body.id, {"statut": "archive"}, mode=mode_courant(request))
    return {"ok": True}

@app.post("/api/offre/archivage")
def api_offre_archivage(request: Request, body: dict = Body(...)):
    """Gère la raison d'archivage et le désarchivage d'une offre."""
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    offre_id = body.get("id")
    if not offre_id:
        return JSONResponse({"erreur": "id manquant"}, status_code=400)
    modifs = {}
    if body.get("desarchiver"):
        modifs["statut"] = "nouveau"
        modifs["raison_archivage"] = ""
    elif body.get("raison") is not None:
        modifs["raison_archivage"] = body.get("raison")
        modifs["statut"] = "archive"   # on s'assure qu'elle reste archivée
    if modifs:
        modifier_candidature(user.id, offre_id, modifs, mode=mode_courant(request))
    return {"ok": True}

@app.post("/api/sauvegarder")
def api_sauvegarder(body: Sauvegarde, request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    modifs = {}
    if body.lettre is not None:            modifs["lettre"] = body.lettre
    if body.email_candidature is not None: modifs["email_candidature"] = body.email_candidature
    if body.objet_email is not None:       modifs["objet_email"] = body.objet_email
    modifier_candidature(user.id, body.id, modifs, mode=mode_courant(request))
    return {"ok": True}

@app.post("/api/telecharger_pdf")
def api_telecharger_pdf(body: TelechargerPdf, request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    offre = lire_candidature(user.id, body.id, mode=mode_courant(request))
    if not offre:
        return JSONResponse({"erreur": "Non trouvé"}, status_code=404)
    lettre = body.lettre or offre.get("lettre")
    if not lettre:
        return JSONResponse({"erreur": "Vide"}, status_code=400)
    profil = lire_profil(user.id, mode=mode_courant(request))
    chemin = generer_pdf_lettre(offre, lettre, profil)
    return {"ok": True, "chemin": chemin}


# ─── Spontanées — Suivi des candidatures ──────────────────────────────────────
@app.get("/api/spontanees/suivi")
def api_spontanees_suivi(request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    return lire_entreprises_envoyees(user.id)


@app.post("/api/spontanees/suivi/statut")
def api_spontanees_statut(request: Request, body: dict = Body(...)):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    ok = modifier_statut_suivi(user.id, body.get("id"), body.get("statut", ""))
    return {"ok": ok}


# ─── Spontanées — Stats ───────────────────────────────────────────────────────

@app.get("/api/spontanees/stats")
def api_spontanees_stats(request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    # Lecture des stats depuis la BASE (le JSON n'est plus lu ici)
    stats = calculer_stats(user.id)
    # On ajoute l'état du pipeline, géré en mémoire
    stats["en_cours"] = etat_spontanees["en_cours"]
    stats["etape"]    = etat_spontanees["etape"]
    stats["message"]  = etat_spontanees["message"]
    stats["pourcentage"] = etat_spontanees.get("pourcentage", 0)
    return stats

@app.post("/api/spontanees/stop")
def api_spontanees_stop():
    _stop_event.set()
    etat_spontanees["message"] = "Arrêt demandé — sauvegarde en cours..."
    log("⏹️  Arrêt demandé par l'utilisateur")
    return {"ok": True}

@app.post("/api/spontanees/fetch")
def api_spontanees_fetch(request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    user_id = user.id
    if etat_spontanees["en_cours"]:
        return JSONResponse({"erreur": "Pipeline déjà en cours"}, status_code=400)

    def lancer():
        _stop_event.clear()
        etat_spontanees.update({"en_cours": True, "etape": "fetch",
                                "message": "Récupération des entreprises IT IDF...",
                                "pourcentage": 0})
        log("▶ Fetch entreprises démarré")
        def on_progress(pct, message=None):
            etat_spontanees["pourcentage"] = pct
            if message:
                etat_spontanees["message"] = message
        try:
            from spontanees.fetch_entreprises import main as fetch_main
            fetch_main(stop_event=_stop_event, on_progress=on_progress, user_id=user_id)
            etat_spontanees["message"] = "Fetch terminé !"
            log("✅ Fetch terminé")
        except Exception as e:
            etat_spontanees["message"] = f"Erreur fetch : {e}"
            log(f"❌ Erreur fetch : {e}")
        finally:
            etat_spontanees.update({"en_cours": False, "etape": None})

    threading.Thread(target=lancer, daemon=True).start()
    return {"status": "démarré"}

@app.post("/api/spontanees/scraper")
def api_spontanees_scraper(request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    user_id = user.id
    if etat_spontanees["en_cours"]:
        return JSONResponse({"erreur": "Pipeline déjà en cours"}, status_code=400)

    def lancer():
        _stop_event.clear()
        etat_spontanees.update({"en_cours": True, "etape": "scraper",
                                "message": "Scraping des emails...",
                                "pourcentage": 0})
        log("▶ Scraper emails démarré")
        def on_progress(pct, message=None):
            etat_spontanees["pourcentage"] = pct
            if message:
                etat_spontanees["message"] = message
        try:
            from spontanees.scraper_emails import main as scraper_main
            scraper_main(stop_event=_stop_event, log_fn=log, user_id=user_id, on_progress=on_progress)
            if _stop_event.is_set():
                etat_spontanees["message"] = "Arrêté — données sauvegardées"
            else:
                etat_spontanees["message"] = "Scraping terminé !"
                log("✅ Scraping terminé")
        except Exception as e:
            etat_spontanees["message"] = f"Erreur scraper : {e}"
            log(f"❌ Erreur scraper : {e}")
        finally:
            etat_spontanees.update({"en_cours": False, "etape": None})

    threading.Thread(target=lancer, daemon=True).start()
    return {"status": "démarré"}

@app.post("/api/spontanees/envoyer")
def api_spontanees_envoyer(body: Envoyer, request: Request):
    user = utilisateur_courant(request)
    if not user:
        return JSONResponse({"erreur": "Non connecté"}, status_code=401)
    user_id = user.id
    if etat_spontanees["en_cours"]:
        return JSONResponse({"erreur": "Pipeline déjà en cours"}, status_code=400)

    # Plafond de sécurité : jamais plus de 50 mails par run (réputation Gmail)
    limite = max(1, min(int(body.limite or 10), 50))
    def lancer():
        _stop_event.clear()
        etat_spontanees.update({"en_cours": True, "etape": "envoyer",
                                "message": f"Envoi en cours (limite: {limite})...",
                                "pourcentage": 0})
        log(f"▶ Envoi démarré — limite {limite} {'[TEST]' if body.test else ''}")
        def on_progress(pct, message=None):
            etat_spontanees["pourcentage"] = pct
            if message:
                etat_spontanees["message"] = message
        try:
            from spontanees.envoyeur import main as env_main
            env_main(limite=limite, test=body.test, stop_event=_stop_event, log_fn=log, user_id=user_id, on_progress=on_progress)
            if _stop_event.is_set():
                etat_spontanees["message"] = "Arrêté — données sauvegardées"
            else:
                etat_spontanees["message"] = "Envoi terminé !"
                log("✅ Envoi terminé")
        except Exception as e:
            etat_spontanees["message"] = f"Erreur envoi : {e}"
            log(f"❌ Erreur envoi : {e}")
        finally:
            etat_spontanees.update({"en_cours": False, "etape": None})

    threading.Thread(target=lancer, daemon=True).start()
    return {"status": "démarré"}

@app.get("/api/spontanees/statut")
def api_spontanees_statut():
    return etat_spontanees


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Chasseur Alternance (FastAPI) sur http://localhost:5002\n")
    uvicorn.run("main:app", host="0.0.0.0", port=5002, reload=True)
