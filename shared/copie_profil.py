"""
shared/copie_profil.py
======================
Copie de sections du profil d'un mode vers un autre mode du même
utilisateur (phase 9, D117).

Chaque mode a sa ligne dans la table profils, avec toutes les colonnes ;
l'interface n'en montre qu'une partie selon le mode. Une section n'est
copiable que pour les champs qui existent, avec le même sens, dans le mode
source et dans le mode cible (MODES_DU_CHAMP). Jamais copiés, parce que
propres au mode : critères de recherche (domaines, filtres, réglages des
spontanées), dates, établissement et missions du stage, niveau visé, ce
que la formation apporte, critères à éviter, champs du job, analyse
automatique. Non copiés parce que leur sens change selon le mode :
« langues » (« Atouts / compétences » en job, absente en stage) et le
niveau d'études en job (« obtenu », « actuel » ailleurs). Le portfolio
n'est affiché qu'en stage : rien à copier ailleurs.
"""

from shared.balises_mail import verifier_balises
from shared.erreurs import ErreurUtilisateur
from shared.modes import MODES

TOUS = frozenset(MODES)

# Champ (clé de lire_profil) -> modes où il est affiché avec ce sens
MODES_DU_CHAMP = {
    "prenom": TOUS, "nom": TOUS, "email": TOUS, "telephone": TOUS, "ville": TOUS,
    "linkedin": TOUS, "github": TOUS,
    "formation": frozenset({"alternance", "stage"}),
    "niveau_etudes": frozenset({"alternance", "stage"}),   # « actuel » ; « obtenu » en job
    "experience": TOUS,
    "competences": TOUS, "projets": TOUS,
    "lettre_type": TOUS,
    "email_objet": TOUS, "email_type": TOUS,
}

# (clé, libellé, champs), dans l'ordre de la page Profil
SECTIONS = (
    ("identite", "Identité (prénom, nom, email, téléphone, ville)", ("prenom", "nom", "email", "telephone", "ville")),
    ("liens", "Liens (LinkedIn, GitHub)", ("linkedin", "github")),
    ("formation", "Formation et niveau d'études actuel", ("formation", "niveau_etudes")),
    ("experience", "Expérience professionnelle", ("experience",)),
    ("competences", "Compétences techniques", ("competences",)),
    ("projets", "Projets", ("projets",)),
    ("lettre_type", "Lettre de motivation type", ("lettre_type",)),
    ("email", "Email de candidature spontanée (objet et message)", ("email_objet", "email_type")),
)

LIBELLES_CHAMPS = {
    "prenom": "Prénom", "nom": "Nom", "email": "Email", "telephone": "Téléphone", "ville": "Ville",
    "linkedin": "LinkedIn", "github": "GitHub", "formation": "Formation", "niveau_etudes": "Niveau d'études",
    "experience": "Expérience", "competences": "Compétences", "projets": "Projets", "lettre_type": "Lettre type",
    "email_objet": "Objet du mail", "email_type": "Message du mail",
}


def _rempli(valeur) -> bool:
    if isinstance(valeur, list):
        return any(_rempli(x) for x in valeur)
    if isinstance(valeur, dict):
        return any(_rempli(v) for v in valeur.values())
    return bool(str(valeur or "").strip())


def _valeur(profil: dict, champ: str):
    v = profil.get(champ)
    if champ == "projets":
        return [p for p in (v or []) if _rempli(p)]
    if champ == "competences":
        return list(v or [])
    return v or ""


def verifier_modes(source: str, cible: str):
    if source not in MODES:
        raise ErreurUtilisateur(f"Mode source inconnu : {source}.")
    if source == cible:
        raise ErreurUtilisateur("Choisis un autre mode que celui de cette page.")


def champs_communs(section: str, source: str, cible: str) -> list[str]:
    champs = next((c for k, _, c in SECTIONS if k == section), None)
    if champs is None:
        raise ErreurUtilisateur(f"Section inconnue : {section}.")
    return [c for c in champs if {source, cible} <= MODES_DU_CHAMP[c]]


def sections_copiables(source: str, cible: str) -> list[dict]:
    """Sections proposées de source vers cible : {cle, libelle, champs}."""
    verifier_modes(source, cible)
    return [{"cle": k, "libelle": libelle, "champs": champs_communs(k, source, cible)}
            for k, libelle, _ in SECTIONS if champs_communs(k, source, cible)]


def apercu(profil_source: dict, profil_cible: dict, sections, source: str, cible: str) -> list[dict]:
    """Pour chaque section demandée : valeur actuelle (cible) et valeur
    copiée (source), champ par champ ; « a_confirmer » si la cible est
    remplie et différente (écrasement à confirmer) ; « vide » si la source
    n'a rien ; « erreur » si la copie est impossible (balise de l'email
    inconnue du mode cible)."""
    verifier_modes(source, cible)
    res = []
    for k in dict.fromkeys(sections):
        champs = champs_communs(k, source, cible)
        if not champs:
            raise ErreurUtilisateur(f"Section non copiable de {source} vers {cible} : {k}.")
        lignes = [{"champ": c, "libelle": LIBELLES_CHAMPS[c], "actuel": _valeur(profil_cible, c),
                   "copie": _valeur(profil_source, c)} for c in champs]
        rempli = any(_rempli(x["actuel"]) for x in lignes)
        identique = all(x["actuel"] == x["copie"] for x in lignes)
        erreur = ""
        if k == "email":
            try:
                for x in lignes:
                    verifier_balises(x["copie"], cible)
            except ErreurUtilisateur as e:
                erreur = str(e)
        res.append({"cle": k, "libelle": next(l for c, l, _ in SECTIONS if c == k), "champs": lignes,
                    "a_confirmer": rempli and not identique, "identique": identique,
                    "vide": not any(_rempli(x["copie"]) for x in lignes), "erreur": erreur})
    return res
