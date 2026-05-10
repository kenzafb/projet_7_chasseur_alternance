# ─────────────────────────────────────────────
# PROFIL — EXEMPLE
# Copiez ce fichier vers shared/profil.py
# et remplissez vos vraies informations.
# shared/profil.py est dans .gitignore
# et ne doit jamais être commité.
# ─────────────────────────────────────────────

PROFIL = {

    # ── Infos personnelles ──────────────────
    "prenom": "VOTRE_PRENOM",
    "nom": "VOTRE_NOM",
    "email": "votre.email@example.com",
    "telephone": "06 00 00 00 00",
    "ville": "Paris",
    "linkedin": "https://www.linkedin.com/in/votre-profil/",
    "github": "https://github.com/votre-pseudo",

    # ── Formation ───────────────────────────
    "formation": """
- Votre formation principale (Bac+X) — Intitulé complet, Établissement (années)
- Votre prochaine formation / formation visée
- Diplôme précédent si pertinent
""",

    # ── Compétences techniques ───────────────
    # Listez vos vraies compétences techniques
    "competences": [
        "Compétence 1",
        "Compétence 2",
        "Compétence 3",
    ],

    # ── Projets GitHub ───────────────────────
    # Les projets les plus pertinents pour votre recherche
    "projets": [
        {
            "nom": "Nom du projet",
            "url": "github.com/votre-pseudo/nom-repo",
            "description": "Description courte et percutante du projet"
        },
        {
            "nom": "Nom du projet 2",
            "url": "github.com/votre-pseudo/nom-repo-2",
            "description": "Description courte et percutante du projet 2"
        },
    ],

    # ── Expérience pro ───────────────────────
    "experience": """
- Intitulé poste chez Entreprise (période) : description des missions
- Intitulé poste chez Entreprise 2 (période) : description des missions
""",

    # ── Langues ──────────────────────────────
    "langues": "Français (natif), Anglais (B2)",

    # ── Disponibilité ────────────────────────
    "disponibilite": "Disponible en alternance dès septembre 2026, Paris & Île-de-France.",

    # ── Paragraphe personnel ─────────────────
    # Utilisé comme base pour les lettres de motivation.
    # Rédigez-le à la première personne, ton direct, sans superlatifs.
    "paragraphe_perso": """
Votre paragraphe de motivation personnelle ici.
Ce texte sert de base à l'IA pour générer la partie personnalisée
de vos lettres. Soyez authentique et précis sur ce qui vous motive.
""",

    # ── Critères de recherche ────────────────
    "recherche": {
        "titre_poste": [
            "alternance devops",
            "alternance administrateur systèmes",
            # Ajoutez vos mots-clés de recherche
        ],

        "localisation": "Paris Île-de-France",
        "type_contrat": "alternance",
        "disponibilite": "septembre 2026",
    }
}
