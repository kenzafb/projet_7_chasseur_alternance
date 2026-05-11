from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
from france_travail.main import lancer_recherche, charger_candidatures, sauvegarder_candidatures
from france_travail.generateur import generer_lettre
from france_travail.analyseur import analyser_offre
from france_travail.pdf_generator import generer_pdf_lettre
from datetime import datetime
import threading
import collections
import json
import os

load_dotenv()
app = Flask(__name__)

# ─── États des pipelines ──────────────────────────────────────────────────────
etat_recherche  = {"en_cours": False, "message": "Prêt"}
etat_spontanees = {"en_cours": False, "etape": None, "message": "Prêt"}
_stop_event     = threading.Event()

FICHIER_ENRICHIES = "data/entreprises_enrichies.json"
FICHIER_RAW       = "data/entreprises_raw.json"

# ─── Logs ─────────────────────────────────────────────────────────────────────
_logs = collections.deque(maxlen=80)

def log(msg):
    _logs.append({"t": datetime.now().strftime("%H:%M:%S"), "msg": msg})
    print(msg)

@app.route("/api/logs")
def api_logs():
    return jsonify(list(_logs))

# ─── Routes principales ───────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/candidatures")
def api_candidatures():
    return jsonify(charger_candidatures())

# ─── France Travail ───────────────────────────────────────────────────────────

@app.route("/api/recherche", methods=["POST"])
def api_recherche():
    if etat_recherche["en_cours"]:
        return jsonify({"erreur": "Recherche déjà en cours"}), 400

    def lancer():
        etat_recherche["en_cours"] = True
        etat_recherche["message"] = "Recherche des offres..."
        log("🔍 Recherche France Travail démarrée")
        try:
            lancer_recherche(analyser=True, max_analyse=999)
            etat_recherche["message"] = "Terminé !"
            log("✅ Recherche France Travail terminée")
        except Exception as e:
            etat_recherche["message"] = f"Erreur : {e}"
            log(f"❌ Erreur recherche : {e}")
        finally:
            etat_recherche["en_cours"] = False

    threading.Thread(target=lancer, daemon=True).start()
    return jsonify({"status": "démarré"})

@app.route("/api/statut_recherche")
def api_statut_recherche():
    return jsonify(etat_recherche)

@app.route("/api/generer_lettre", methods=["POST"])
def api_generer_lettre():
    data = request.get_json()
    offre_id = data.get("id")
    candidatures = charger_candidatures()
    offre = next((c for c in candidatures if c["id"] == offre_id), None)
    if not offre:
        return jsonify({"erreur": "Offre introuvable"}), 404
    lettre = generer_lettre(offre)
    for c in candidatures:
        if c["id"] == offre_id:
            c["lettre"] = lettre
            c["statut"] = "en_cours"
            break
    sauvegarder_candidatures(candidatures)
    return jsonify({"lettre": lettre})

@app.route("/api/analyser", methods=["POST"])
def api_analyser():
    data = request.get_json()
    offre_id = data.get("id")
    candidatures = charger_candidatures()
    offre = next((c for c in candidatures if c["id"] == offre_id), None)
    if not offre:
        return jsonify({"erreur": "Offre introuvable"}), 404
    analyse = analyser_offre(offre)
    for c in candidatures:
        if c["id"] == offre_id:
            c.update({
                "score": analyse.get("score", 5),
                "verdict": analyse.get("verdict", "moyen"),
                "eligible": analyse.get("eligible", True),
                "points_forts": analyse.get("points_forts", []),
                "points_faibles": analyse.get("points_faibles", []),
                "resume_analyse": analyse.get("resume", "")
            })
            if analyse.get("statut_auto") == "archive":
                c["statut"] = "archive"
            break
    sauvegarder_candidatures(candidatures)
    return jsonify(analyse)

@app.route("/api/maj_statut", methods=["POST"])
def api_maj_statut():
    data = request.get_json()
    offre_id = data.get("id")
    statut = data.get("statut")
    candidatures = charger_candidatures()
    for c in candidatures:
        if c["id"] == offre_id:
            c["statut"] = statut
            if statut in ["envoye", "reponse", "entretien", "refus"]:
                if not c.get("date_candidature"):
                    c["date_candidature"] = datetime.now().strftime("%Y-%m-%d")
            break
    sauvegarder_candidatures(candidatures)
    return jsonify({"ok": True})

@app.route("/api/archiver", methods=["POST"])
def api_archiver():
    data = request.get_json()
    offre_id = data.get("id")
    cands = charger_candidatures()
    for c in cands:
        if c["id"] == offre_id:
            c["statut"] = "archive"
            break
    sauvegarder_candidatures(cands)
    return jsonify({"ok": True})

@app.route("/api/sauvegarder", methods=["POST"])
def api_sauvegarder():
    data = request.get_json()
    offre_id = data.get("id")
    candidatures = charger_candidatures()
    for c in candidatures:
        if c["id"] == offre_id:
            if "lettre" in data: c["lettre"] = data["lettre"]
            if "email_candidature" in data: c["email_candidature"] = data["email_candidature"]
            if "objet_email" in data: c["objet_email"] = data["objet_email"]
            break
    sauvegarder_candidatures(candidatures)
    return jsonify({"ok": True})

@app.route("/api/telecharger_pdf", methods=["POST"])
def api_telecharger_pdf():
    data = request.get_json()
    offre_id = data.get("id")
    cands = charger_candidatures()
    offre = next((c for c in cands if c["id"] == offre_id), None)
    if not offre: return jsonify({"erreur": "Non trouvé"}), 404
    lettre = data.get("lettre") or offre.get("lettre")
    if not lettre: return jsonify({"erreur": "Vide"}), 400
    chemin = generer_pdf_lettre(offre, lettre)
    return jsonify({"ok": True, "chemin": chemin})

# ─── Spontanées — Stats ───────────────────────────────────────────────────────

@app.route("/api/spontanees/stats")
def api_spontanees_stats():
    stats = {
        "raw": 0, "avec_email": 0, "mail_generee": 0, "mail_envoye": 0,
        "en_cours": etat_spontanees["en_cours"],
        "etape": etat_spontanees["etape"],
        "message": etat_spontanees["message"],
        "dernieres": []
    }
    fichier = FICHIER_ENRICHIES if os.path.exists(FICHIER_ENRICHIES) else FICHIER_RAW
    if os.path.exists(fichier):
        try:
            with open(fichier, "r", encoding="utf-8") as f:
                entreprises = json.load(f)
            stats["raw"]          = len(entreprises)
            stats["avec_email"]   = sum(1 for e in entreprises if e.get("emails_trouves"))
            stats["mail_generee"] = sum(1 for e in entreprises if e.get("mail_generee"))
            stats["mail_envoye"]  = sum(1 for e in entreprises if e.get("mail_envoye"))
            recentes = [e for e in entreprises if e.get("mail_envoye") or e.get("mail_generee")][-5:]
            stats["dernieres"] = [
                {
                    "nom": (e.get("nom_commercial") or e.get("nom", "?"))[:40],
                    "ville": e.get("ville", ""),
                    "email": (e.get("emails_trouves") or [""])[0],
                    "envoye": e.get("mail_envoye", False),
                    "date": e.get("mail_envoye_le", "")
                }
                for e in recentes
            ]
        except Exception:
            pass
    return jsonify(stats)

# ─── Spontanées — Stop ────────────────────────────────────────────────────────

@app.route("/api/spontanees/stop", methods=["POST"])
def api_spontanees_stop():
    _stop_event.set()
    etat_spontanees["message"] = "Arrêt demandé — sauvegarde en cours..."
    log("⏹️  Arrêt demandé par l'utilisateur")
    return jsonify({"ok": True})

# ─── Spontanées — Lancement des étapes ───────────────────────────────────────

@app.route("/api/spontanees/fetch", methods=["POST"])
def api_spontanees_fetch():
    if etat_spontanees["en_cours"]:
        return jsonify({"erreur": "Pipeline déjà en cours"}), 400

    def lancer():
        _stop_event.clear()
        etat_spontanees.update({"en_cours": True, "etape": "fetch",
                                 "message": "Récupération des entreprises IT IDF..."})
        log("▶ Fetch entreprises démarré")
        try:
            from spontanees.fetch_entreprises import main as fetch_main
            fetch_main(stop_event=_stop_event)
            etat_spontanees["message"] = "Fetch terminé !"
            log("✅ Fetch terminé")
        except Exception as e:
            etat_spontanees["message"] = f"Erreur fetch : {e}"
            log(f"❌ Erreur fetch : {e}")
        finally:
            etat_spontanees.update({"en_cours": False, "etape": None})

    threading.Thread(target=lancer, daemon=True).start()
    return jsonify({"status": "démarré"})

@app.route("/api/spontanees/scraper", methods=["POST"])
def api_spontanees_scraper():
    if etat_spontanees["en_cours"]:
        return jsonify({"erreur": "Pipeline déjà en cours"}), 400

    def lancer():
        _stop_event.clear()
        etat_spontanees.update({"en_cours": True, "etape": "scraper",
                                 "message": "Scraping des emails..."})
        log("▶ Scraper emails démarré")
        try:
            from spontanees.scraper_emails import main as scraper_main
            scraper_main(stop_event=_stop_event, log_fn=log)
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
    return jsonify({"status": "démarré"})

@app.route("/api/spontanees/generer", methods=["POST"])
def api_spontanees_generer():
    if etat_spontanees["en_cours"]:
        return jsonify({"erreur": "Pipeline déjà en cours"}), 400

    def lancer():
        _stop_event.clear()
        etat_spontanees.update({"en_cours": True, "etape": "generer",
                                 "message": "Génération des mails personnalisés..."})
        log("▶ Génération mails démarrée")
        try:
            from spontanees.generateur_mail import main as gen_main
            gen_main(stop_event=_stop_event, log_fn=log)
            if _stop_event.is_set():
                etat_spontanees["message"] = "Arrêté — données sauvegardées"
            else:
                etat_spontanees["message"] = "Génération terminée !"
                log("✅ Génération terminée")
        except Exception as e:
            etat_spontanees["message"] = f"Erreur génération : {e}"
            log(f"❌ Erreur génération : {e}")
        finally:
            etat_spontanees.update({"en_cours": False, "etape": None})

    threading.Thread(target=lancer, daemon=True).start()
    return jsonify({"status": "démarré"})

@app.route("/api/spontanees/envoyer", methods=["POST"])
def api_spontanees_envoyer():
    if etat_spontanees["en_cours"]:
        return jsonify({"erreur": "Pipeline déjà en cours"}), 400

    data = request.get_json() or {}
    limite = int(data.get("limite", 10))
    test   = bool(data.get("test", False))

    def lancer():
        _stop_event.clear()
        etat_spontanees.update({"en_cours": True, "etape": "envoyer",
                                 "message": f"Envoi en cours (limite: {limite})..."})
        log(f"▶ Envoi démarré — limite {limite} {'[TEST]' if test else ''}")
        try:
            from spontanees.envoyeur import main as env_main
            env_main(limite=limite, test=test, stop_event=_stop_event, log_fn=log)
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
    return jsonify({"status": "démarré"})

@app.route("/api/spontanees/statut")
def api_spontanees_statut():
    return jsonify(etat_spontanees)

# ─── Lancement ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🚀 Chasseur Alternance démarré sur http://localhost:5002\n")
    app.run(debug=False, port=5002)
