# ─────────────────────────────────────────────
# PROFIL DE KENZA
# Ce fichier est le cerveau du chasseur.
# Toutes les décisions de l'IA (scoring,
# lettre de motivation, email) sont basées
# sur ces informations.
# ─────────────────────────────────────────────

PROFIL = {

    # ── Infos personnelles ──────────────────
    "prenom": "Kenza",
    "nom": "Filali-Bouami",
    "email": "kenzafb@icloud.com",
    "telephone": "07 50 87 21 76",
    "ville": "Paris 9e",
    "linkedin": "https://www.linkedin.com/in/kenza-filali-bouami/",
    "github": "https://github.com/kenzafb",

    # ── Formation ───────────────────────────
    "formation": """
- DSP DevOps (Bac +1) — Développement et exploitation de parcs informatiques, CNAM Paris (2025-2026, 60 ECTS)
- Candidate au DEUST IOSI parcours Technicien Développement, Sécurité et Exploitation (rentrée septembre 2026)
- Licence de Gestion L1, Université Paris 1 Panthéon-Sorbonne (2024-2025)
- Baccalauréat Général Mathématiques & SES, Lycée Maximilien Perret (2024)
""",

    # ── Compétences techniques ───────────────
    "competences": [
        "Linux Debian/Ubuntu/Arch Linux",
        "Administration systèmes et réseaux",
        "Bash scripting et automatisation",
        "Python (FastAPI, Flask, API REST)",
        "Docker et docker-compose",
        "Git et GitHub",
        "HTML5/CSS3 JavaScript",
        "TCP/IP DNS DHCP SSH",
        "Node.js",
        "WordPress CMS",
        "C algorithmique",
        "Intelligence artificielle (Ollama, LLM, API Anthropic)",
        "Virtualisation (VirtualBox VMware)",
    ],

    # ── Projets GitHub ───────────────────────
    "projets": [
        {
            "nom": "Grabber — Monitoring système",
            "url": "github.com/kenzafb/projet-grabber-devops",
            "description": "Script Bash d'audit système + API REST FastAPI + interface web responsive pour visualisation des métriques en temps réel"
        },
        {
            "nom": "Docker-Compose CLI Tool",
            "url": "github.com/kenzafb/projet_2_javascript",
            "description": "CLI Node.js pour automatiser la gestion de fichiers docker-compose.yml avec vérification d'images via l'API Docker Hub"
        },
        {
            "nom": "Chatbot IA local",
            "url": "github.com/kenzafb/projet_5_chatbot",
            "description": "Chatbot avec interface web Flask, mémoire de conversation, modèle Llama 3.1 tournant 100% en local via Ollama"
        },
        {
            "nom": "Email AI Assistant",
            "url": "github.com/kenzafb/email-ai-assistant",
            "description": "Assistant IA qui surveille Gmail, classe les emails et répond automatiquement. Interface web de validation, surveillance toutes les X minutes"
        },
        {
            "nom": "Auburn & Cream — Site vitrine",
            "url": "github.com/kenzafb/auburn-cream-coffee",
            "description": "Site multi-pages mobile-first HTML/CSS pur, conçu en équipe de 3"
        },
    ],

    # ── Expérience pro ───────────────────────
    "experience": """
- Stagiaire Technicienne au Garage Numérique (mars-avril 2026) : maintenance informatique, installation Linux,
  développement web (WordPress/HTML-CSS), relation public non-techniciens
- Téléenquêtrice chez Alyce (septembre 2025) : collecte structurée de données, outils numériques
- Enquêtrice terrain RATP chez Alyce (mai 2025) : protocoles rigoureux, autonomie
""",

    # ── Langues ──────────────────────────────
    "langues": "Français (natif), Anglais (B2), Espagnol (A2), Arabe (A1)",

    # ── Disponibilité ────────────────────────
    "disponibilite": "Disponible en alternance dès septembre 2026, Paris & Île-de-France. Niveau actuel : Bac+1 (DSP DevOps CNAM). Intègre un DEUST IOSI (Bac+2) en alternance à la rentrée septembre 2026.",

    # ── Paragraphe personnel ─────────────────
    # Utilisé comme base pour les lettres de motivation
    "paragraphe_perso": """
Passionnée d'informatique depuis l'enfance — des jeux vidéo aux premiers outils, l'envie de comprendre
comment les choses fonctionnent a toujours été là. C'est cette année, en formation DevOps au CNAM,
que j'ai découvert que ce monde était aussi le mien. Ce qui m'anime : voir le résultat concret de mon
travail, résoudre des problèmes qui ont un vrai impact, et apprendre quelque chose de nouveau chaque jour.
Je suis du genre à ne pas lâcher un bug avant de l'avoir compris, à chercher la solution propre plutôt
que le raccourci, et à perdre la notion du temps quand un projet m'absorbe vraiment. En alternance,
je cherche exactement ça : un environnement où je peux contribuer concrètement, progresser vite,
et ne jamais être dans la routine.
""",

    # ── Critères de recherche ────────────────
    "recherche": {
        "titre_poste": [
            "alternance devops",
            "alternance administrateur systèmes",
            "alternance technicien systèmes réseaux",
            "alternance développeur",
            "alternance support informatique",
            "alternance iosi",
            "alternance linux",
            "alternance infrastructure",
	    "alternance bts sio",
            "alternance bts sio sisr",
  	    "alternance bts sio slam",
 	    "alternance bts informatique",
   	    "alternance bts réseaux",
            "alternance but informatique",
            "alternance but réseaux télécommunications",
            "alternance technicien informatique",
            "alternance administrateur réseaux",
            "alternance helpdesk",
            "alternance support technique",
            "alternance technicien systèmes",
        ],

        "localisation": "Paris Île-de-France",
        "type_contrat": "alternance",
        "disponibilite": "septembre 2026",
    }
}
