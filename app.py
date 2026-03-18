from flask import Flask, render_template_string, request, jsonify, send_file
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

HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Chasseur Alternance</title>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet"/>
  <style>
    :root {
      --bg:#0f0f14;--surface:#16161e;--border:#2a2a3a;
      --accent:#6c63ff;--accent2:#ff6584;--green:#4ade80;
      --yellow:#fbbf24;--text:#e8e8f0;--muted:#6b6b8a;--radius:6px;
    }
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:var(--bg);color:var(--text);font-family:'DM Mono',monospace;min-height:100vh;padding:32px 16px}
    .container{max-width:1100px;margin:0 auto}
    header{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid var(--border);flex-wrap:wrap;gap:16px}
    .logo h1{font-family:'Instrument Serif',serif;font-size:2rem;font-weight:400;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
    .logo p{font-size:.7rem;color:var(--muted);margin-top:4px;letter-spacing:.1em;text-transform:uppercase}
    .stats{display:flex;gap:20px;flex-wrap:wrap}
    .stat{text-align:right}
    .stat .n{font-family:'Instrument Serif',serif;font-size:1.8rem;line-height:1}
    .stat .l{font-size:.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
    .stat.total .n{color:var(--accent)}
    .stat.top .n{color:var(--green)}
    .stat.envoy .n{color:var(--yellow)}
    .toolbar{display:flex;gap:10px;margin-bottom:24px;flex-wrap:wrap;align-items:center}
    .btn{padding:8px 18px;border-radius:var(--radius);font-family:'DM Mono',monospace;font-size:.76rem;cursor:pointer;border:1px solid;transition:all .15s;letter-spacing:.04em}
    .btn-primary{background:var(--accent);color:white;border-color:var(--accent)}
    .btn-primary:hover{opacity:.85}
    .btn-secondary{background:transparent;color:var(--muted);border-color:var(--border)}
    .btn-secondary:hover{border-color:var(--accent);color:var(--accent)}
    .btn:disabled{opacity:.4;cursor:not-allowed}
    .search-status{font-size:.75rem;color:var(--muted);padding:6px 12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius)}
    .filtres{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}
    .filtre{padding:5px 12px;border-radius:20px;font-size:.7rem;cursor:pointer;border:1px solid var(--border);background:transparent;color:var(--muted);transition:all .15s;font-family:'DM Mono',monospace}
    .filtre.actif{border-color:var(--accent);color:var(--accent);background:rgba(108,99,255,.1)}
    .offres{display:flex;flex-direction:column;gap:12px}
    .offre{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;transition:border-color .2s}
    .offre:hover{border-color:var(--accent)}
    .offre-header{padding:14px 18px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;gap:12px}
    .offre-left{display:flex;flex-direction:column;gap:4px;flex:1;min-width:0}
    .offre-titre{font-family:'Instrument Serif',serif;font-size:1.05rem;font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .offre-meta{font-size:.7rem;color:var(--muted)}
    .offre-right{display:flex;align-items:center;gap:10px;flex-shrink:0}
    .score{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.8rem;font-weight:500;flex-shrink:0}
    .score.haut{background:rgba(74,222,128,.15);color:var(--green);border:1px solid rgba(74,222,128,.3)}
    .score.moyen{background:rgba(251,191,36,.15);color:var(--yellow);border:1px solid rgba(251,191,36,.3)}
    .score.bas{background:rgba(255,101,132,.15);color:var(--accent2);border:1px solid rgba(255,101,132,.3)}
    .badge-statut{font-size:.62rem;padding:3px 8px;border-radius:20px;border:1px solid;white-space:nowrap}
    .badge-nouveau{color:var(--accent);border-color:rgba(108,99,255,.4);background:rgba(108,99,255,.1)}
    .badge-analyse{color:var(--yellow);border-color:rgba(251,191,36,.4);background:rgba(251,191,36,.1)}
    .badge-envoye{color:var(--green);border-color:rgba(74,222,128,.4);background:rgba(74,222,128,.1)}
    .badge-rejete{color:var(--muted);border-color:var(--border)}
    .offre-body{display:none;padding:18px;border-top:1px solid var(--border)}
    .offre-body.open{display:block}
    .grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    @media(max-width:650px){.grid-2{grid-template-columns:1fr}}
    .section-label{font-size:.62rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:8px}
    .analyse-box{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:12px;font-size:.78rem;line-height:1.6}
    .points{list-style:none;margin-top:6px}
    .points li{font-size:.75rem;color:var(--muted);padding:2px 0}
    .points li::before{content:"→ ";color:var(--accent)}
    .points.faibles li::before{color:var(--accent2)}
    .textarea-lettre{width:100%;min-height:280px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:12px;font-family:'DM Mono',monospace;font-size:.76rem;line-height:1.7;color:var(--text);resize:vertical;outline:none;transition:border-color .2s}
    .textarea-lettre:focus{border-color:var(--accent)}
    .actions{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
    .lien-offre{font-size:.72rem;color:var(--accent);text-decoration:none}
    .lien-offre:hover{text-decoration:underline}
    .empty{text-align:center;padding:60px 20px;color:var(--muted);font-size:.85rem}
    .empty .icon{font-size:2.5rem;margin-bottom:12px}
    .toast{position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:var(--radius);font-size:.78rem;font-family:'DM Mono',monospace;z-index:100;border:1px solid;animation:toastIn .3s ease}
    .toast.ok{background:#0f2318;color:var(--green);border-color:rgba(74,222,128,.3)}
    .toast.err{background:#1f0f14;color:var(--accent2);border-color:rgba(255,101,132,.3)}
    @keyframes toastIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
  </style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo">
      <h1>Chasseur Alternance</h1>
      <p>Kenza Filali-Bouami — Paris & Île-de-France</p>
    </div>
    <div class="stats">
      <div class="stat total"><div class="n" id="statTotal">0</div><div class="l">Offres</div></div>
      <div class="stat top"><div class="n" id="statTop">0</div><div class="l">Score 7+</div></div>
      <div class="stat envoy"><div class="n" id="statEnv">0</div><div class="l">Envoyées</div></div>
    </div>
  </header>

  <div class="toolbar">
    <button class="btn btn-primary" id="btnRecherche" onclick="lancerRecherche()">🔍 Nouvelle recherche</button>
    <button class="btn btn-secondary" onclick="filtrerStatut('tous')">Toutes</button>
    <div class="search-status" id="searchStatus">Prêt</div>
  </div>

  <div class="filtres">
    <button class="filtre actif" onclick="filtrer('tous')">Toutes</button>
    <button class="filtre" onclick="filtrer('haut')">Score 8-10 🌟</button>
    <button class="filtre" onclick="filtrer('moyen')">Score 5-7</button>
    <button class="filtre" onclick="filtrer('nouveau')">Nouvelles</button>
    <button class="filtre" onclick="filtrer('envoye')">Envoyées</button>
  </div>

  <div class="offres" id="offres"></div>
</div>

<script src="/static/app.js"></script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

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
