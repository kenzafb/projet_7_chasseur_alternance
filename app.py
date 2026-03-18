from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
from main import lancer_recherche, charger_candidatures, sauvegarder_candidatures
from generateur import generer_lettre, generer_email
from analyseur import analyser_offre
from pdf_generator import generer_pdf_lettre
from datetime import datetime
from envoi_gmail import envoyer_candidature
import threading
import os

load_dotenv()
app = Flask(__name__)

# État de la recherche en cours
etat_recherche = {"en_cours": False, "message": ""}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/candidatures")
def api_candidatures():
    return jsonify(charger_candidatures())

@app.route("/api/recherche", methods=["POST"])
def api_recherche():
    if etat_recherche["en_cours"]:
        return jsonify({"erreur": "Recherche déjà en cours"}), 400

    def lancer():
        etat_recherche["en_cours"] = True
        etat_recherche["message"] = "Recherche des offres..."
        try:
            lancer_recherche(analyser=True, max_analyse=999)
            etat_recherche["message"] = "Terminé !"
        except Exception as e:
            etat_recherche["message"] = f"Erreur : {e}"
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

@app.route("/api/generer_email", methods=["POST"])
def api_generer_email():
    data = request.get_json()
    offre_id = data.get("id")
    candidatures = charger_candidatures()
    offre = next((c for c in candidatures if c["id"] == offre_id), None)
    if not offre:
        return jsonify({"erreur": "Offre introuvable"}), 404
    email = generer_email(offre)
    for c in candidatures:
        if c["id"] == offre_id:
            c["email_candidature"] = email
            break
    sauvegarder_candidatures(candidatures)
    return jsonify({"email": email})

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
            c["score"] = analyse.get("score", 5)
            c["verdict"] = analyse.get("verdict", "moyen")
            c["points_forts"] = analyse.get("points_forts", [])
            c["points_faibles"] = analyse.get("points_faibles", [])
            c["resume_analyse"] = analyse.get("resume", "")
            break
    sauvegarder_candidatures(candidatures)
    return jsonify(analyse)

@app.route("/api/maj_statut", methods=["POST"])
def api_maj_statut():
    data = request.get_json()
    offre_id = data.get("id")
    statut = data.get("statut")
    lettre = data.get("lettre", None)
    candidatures = charger_candidatures()
    for c in candidatures:
        if c["id"] == offre_id:
            c["statut"] = statut
            if lettre is not None:
                c["lettre"] = lettre
            if statut in ["envoye", "reponse", "entretien", "refus"]:
                from datetime import datetime
                if not c.get("date_candidature"):
                    c["date_candidature"] = datetime.now().strftime("%Y-%m-%d")
            break
    sauvegarder_candidatures(candidatures)
    return jsonify({"ok": True})

@app.route("/api/sauvegarder", methods=["POST"])
def api_sauvegarder():
    data = request.get_json()
    offre_id = data.get("id")
    candidatures = charger_candidatures()
    for c in candidatures:
        if c["id"] == offre_id:
            if "lettre" in data:
                c["lettre"] = data["lettre"]
            if "email_candidature" in data:
                c["email_candidature"] = data["email_candidature"]
            if "objet_email" in data:
                c["objet_email"] = data["objet_email"]
            break
    sauvegarder_candidatures(candidatures)
    return jsonify({"ok": True})

@app.route("/api/telecharger_pdf", methods=["POST"])
def api_telecharger_pdf():
    data = request.get_json()
    offre_id = data.get("id")
    lettre = data.get("lettre", "")
    candidatures = charger_candidatures()
    offre = next((c for c in candidatures if c["id"] == offre_id), None)
    if not offre:
        return jsonify({"erreur": "Offre introuvable"}), 404
    if not lettre:
        lettre = offre.get("lettre", "")
    if not lettre:
        return jsonify({"erreur": "Lettre vide"}), 404
    chemin = generer_pdf_lettre(offre, lettre)
    return send_file(chemin, as_attachment=True, download_name=f"Lettre_{offre['entreprise'][:20]}.pdf")

@app.route("/api/envoyer_candidature", methods=["POST"])
def api_envoyer_candidature():
    data = request.get_json()
    offre_id = data.get("id")
    destinataire = data.get("destinataire", "")
    objet = data.get("objet", "")
    candidatures = charger_candidatures()
    offre = next((c for c in candidatures if c["id"] == offre_id), None)
    if not offre:
        return jsonify({"succes": False, "erreur": "Offre introuvable"}), 404
    lettre = offre.get("lettre", "")
    email_texte = offre.get("email_candidature", "")
    if not lettre or not email_texte:
        return jsonify({"succes": False, "erreur": "Genere d'abord la lettre et l'email"}), 400
    if not destinataire:
        return jsonify({"succes": False, "erreur": "Adresse email manquante"}), 400
    succes = envoyer_candidature(offre, lettre, email_texte, destinataire, objet)
    if succes:
        for c in candidatures:
            if c["id"] == offre_id:
                c["statut"] = "envoye"
                if not c.get("date_candidature"):
                    c["date_candidature"] = datetime.now().strftime("%Y-%m-%d")
                break
        sauvegarder_candidatures(candidatures)
    return jsonify({"succes": succes})

if __name__ == "__main__":
    print("\n🚀 Chasseur Alternance démarré !")
    print("   Interface : http://localhost:5002\n")
    app.run(debug=False, port=5002)
