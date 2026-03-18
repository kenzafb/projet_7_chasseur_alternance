from weasyprint import HTML as WeasyHTML
from profil import PROFIL
from datetime import datetime
import os

def generer_pdf_lettre(offre, lettre, dossier_output="lettres_pdf"):
    os.makedirs(dossier_output, exist_ok=True)

    p = PROFIL

    # Date en français
    mois = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
    now = datetime.now()
    date_str = f"{now.day} {mois[now.month-1]} {now.year}"

    nom_entreprise = offre.get("entreprise", "Entreprise").replace(" ", "_").replace("/", "-")[:30]
    nom_fichier = f"Lettre_{p['prenom']}_{nom_entreprise}.pdf"
    chemin_pdf = os.path.join(dossier_output, nom_fichier)

    # Conversion texte → paragraphes HTML
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
  @page {{
    size: A4;
    margin: 2cm 2cm 2cm 2cm;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Helvetica', 'Arial', sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1a1a1a;
  }}

  /* En-tête compacte */
  .entete {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 18px;
    padding-bottom: 14px;
    border-bottom: 1px solid #ccc;
  }}

  .expediteur .nom {{
    font-size: 12pt;
    font-weight: bold;
    margin-bottom: 4px;
  }}

  .expediteur .info {{
    font-size: 8.5pt;
    color: #444;
    line-height: 1.6;
  }}

  .destinataire {{
    text-align: right;
  }}

  .destinataire .entreprise {{
    font-size: 10.5pt;
    font-weight: bold;
    margin-bottom: 4px;
  }}

  .destinataire .info {{
    font-size: 8.5pt;
    color: #444;
    line-height: 1.6;
  }}

  .date-lieu {{
    text-align: right;
    font-size: 9.5pt;
    color: #555;
    margin-bottom: 16px;
  }}

  .objet {{
    font-size: 10pt;
    margin-bottom: 20px;
  }}

  .corps p {{
    margin-bottom: 11px;
    text-align: justify;
    font-size: 10.5pt;
  }}

  .signature {{
    margin-top: 28px;
    font-size: 10.5pt;
  }}
</style>
</head>
<body>

<div class="entete">
  <div class="expediteur">
    <div class="nom">{p['prenom']} {p['nom']}</div>
    <div class="info">
      {p['ville']} &bull; {p['telephone']} &bull; {p['email']}<br>
      {p['github']}
    </div>
  </div>
  <div class="destinataire">
    <div class="entreprise">{offre.get('entreprise', 'Entreprise')}</div>
    <div class="info">{offre.get('lieu', '')}</div>
  </div>
</div>

<div class="date-lieu">Paris, le {date_str}</div>

<div class="objet"><strong>Objet :</strong> Candidature — {offre.get('titre', 'Alternance')}</div>

<div class="corps">
{paragraphes}
</div>

</body>
</html>"""

    WeasyHTML(string=html).write_pdf(chemin_pdf)
    return chemin_pdf


if __name__ == "__main__":
    offre_test = {
        "titre": "Alternance DevOps - Administration Linux et Kubernetes (H/F)",
        "entreprise": "TechCorp Paris",
        "lieu": "75 - Paris 9e",
    }

    # Lettre longue pour tester les limites
    lettre_test = """Madame, Monsieur,

Votre offre d'alternance DevOps chez TechCorp Paris a immédiatement retenu mon attention. L'opportunité de rejoindre une équipe infrastructure dans le 9e arrondissement, où j'évolue quotidiennement, et de contribuer concrètement à vos déploiements CI/CD et votre monitoring Prometheus/Grafana correspond parfaitement à mes aspirations professionnelles et à mon parcours technique en pleine construction.

Ma formation DSP DevOps au CNAM Paris, qui délivre 60 ECTS et couvre exactement les mêmes compétences qu'un BTS SIO SISR, m'a permis de développer une solide expertise en administration Linux, notamment sur les distributions Debian, Ubuntu et Arch Linux. Je maîtrise le scripting Bash et Python avec FastAPI pour la création d'API REST, ainsi que Docker et docker-compose pour la containerisation d'applications. Ma connaissance de Git et GitHub et mes compétences en automatisation constituent des atouts directs pour vos missions de déploiement CI/CD. J'ai également travaillé sur des projets impliquant des architectures modernes et des pipelines d'intégration continue que je serais ravie de mettre au service de votre équipe.

Mon projet Grabber illustre parfaitement cette approche DevOps et ma capacité à concevoir des solutions de bout en bout : j'ai développé un système de monitoring complet combinant un script Bash d'audit système, une API REST FastAPI et une interface web responsive pour visualiser les métriques en temps réel avec génération automatique de logs horodatés. Ce projet démontre ma capacité à créer des solutions de surveillance complètes, compétence directement transférable à votre stack Prometheus et Grafana. Par ailleurs, mon outil CLI Node.js pour la gestion automatisée de fichiers docker-compose, avec vérification d'images via l'API Docker Hub et gestion complète des erreurs, témoigne de mon approche pratique et rigoureuse de l'automatisation des déploiements en environnement conteneurisé.

Cette dimension technique s'enracine dans une véritable passion pour l'informatique qui remonte à mon enfance. C'est en découvrant le monde DevOps cette année au CNAM que j'ai trouvé ma voie. Ce qui me motive profondément, c'est de voir l'impact concret de mon travail, de résoudre des problèmes techniques complexes ayant un véritable impact sur les équipes et les utilisateurs finaux, et d'apprendre continuellement au contact de professionnels expérimentés. Je suis du genre à ne pas lâcher un bug avant de l'avoir compris et résolu proprement, à privilégier les solutions robustes sur les raccourcis, et à me passionner totalement pour les projets qui m'engagent pleinement.

Disponible dès septembre 2026 pour cette alternance d'un an en Île-de-France dans le cadre de mon DEUST IOSI, je serais ravie de vous rencontrer pour échanger sur cette opportunité et vous démontrer

Kenza Filali-Bouami"""

    chemin = generer_pdf_lettre(offre_test, lettre_test)
    print(f"PDF genere : {chemin}")
    print(f"Longueur lettre : {len(lettre_test)} caracteres")
