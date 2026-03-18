from weasyprint import HTML as WeasyHTML
from profil import PROFIL
from datetime import datetime
import os

def generer_pdf_lettre(offre, lettre, dossier_output="lettres_pdf"):
    os.makedirs(dossier_output, exist_ok=True)
    p = PROFIL

    mois = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
    now = datetime.now()
    date_str = f"{now.day} {mois[now.month-1]} {now.year}"

    nom_entreprise = offre.get("entreprise", "Entreprise").replace(" ", "_").replace("/", "-")[:30]
    nom_fichier = f"Lettre_{p['prenom']}_{nom_entreprise}.pdf"
    chemin_pdf = os.path.join(dossier_output, nom_fichier)

    # Nom entreprise — si inconnu, on met "À l'attention du service recrutement"
    entreprise_brute = offre.get("entreprise", "")
    if not entreprise_brute or entreprise_brute.lower() in ["inconnue", "inconnu", "", "none"]:
        entreprise_affichee = "À l'attention du service recrutement"
        lieu_affiche = offre.get("lieu", "")
    else:
        entreprise_affichee = entreprise_brute
        lieu_affiche = offre.get("lieu", "")

    paragraphes = ""
    for para in lettre.strip().split("\n\n"):
        para = para.strip()
        if para:
            paragraphes += f"<p>{para.replace(chr(10), '<br>')}</p>\n"

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"/>
<style>
  @page {{ size: A4; margin: 2cm 2cm 2cm 2cm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Helvetica', 'Arial', sans-serif; font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; }}
  .entete {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid #ccc; }}
  .expediteur .nom {{ font-size: 12pt; font-weight: bold; margin-bottom: 4px; }}
  .expediteur .info {{ font-size: 8.5pt; color: #444; line-height: 1.6; }}
  .destinataire {{ text-align: right; }}
  .destinataire .entreprise {{ font-size: 10.5pt; font-weight: bold; margin-bottom: 4px; }}
  .destinataire .info {{ font-size: 8.5pt; color: #444; line-height: 1.6; }}
  .date-lieu {{ text-align: right; font-size: 9.5pt; color: #555; margin-bottom: 16px; }}
  .objet {{ font-size: 10pt; margin-bottom: 20px; }}
  .corps p {{ margin-bottom: 11px; text-align: justify; font-size: 10.5pt; }}
</style>
</head>
<body>
<div class="entete">
  <div class="expediteur">
    <div class="nom">{p['prenom']} {p['nom']}</div>
    <div class="info">{p['ville']} &bull; {p['telephone']} &bull; {p['email']}<br>{p['github']}</div>
  </div>
  <div class="destinataire">
    <div class="entreprise">{entreprise_affichee}</div>
    <div class="info">{lieu_affiche}</div>
  </div>
</div>
<div class="date-lieu">Paris, le {date_str}</div>
<div class="objet"><strong>Objet :</strong> Candidature — {offre.get('titre', 'Alternance')}</div>
<div class="corps">{paragraphes}</div>
</body>
</html>"""

    WeasyHTML(string=html).write_pdf(chemin_pdf)
    return chemin_pdf
