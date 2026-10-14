"""
france_travail/generateur.py
============================
Lettre de motivation (D106) : la personne écrit sa lettre type dans son
profil, avec des balises ; l'IA (IA_MODELE_LETTRE) n'écrit que le
paragraphe personnalisé, affiché et modifiable avant d'être inséré.

Balises de la lettre type, remplacées en Python sauf {paragraphe} :
  {entreprise}          nom de l'entreprise de l'offre
  {poste}               intitulé du poste
  {date}                date du jour, en toutes lettres
  {contact_entreprise}  bloc destinataire (nom de l'entreprise, puis lieu)
  {paragraphe}          paragraphe rédigé par l'IA (ou à la main)
  {paragraphe_entreprise}  ancien nom de {paragraphe}, toujours accepté
Sans lettre type, ou sans {paragraphe} : message qui renvoie au profil,
aucune lettre générée en entier en secours.
"""

import re
import string

from database.dates import maintenant_affichage
from shared.erreurs import CHAMPS_IDENTITE, ErreurUtilisateur, exiger_profil
from shared.ia import appeler_structure
from shared.schemas_ia import ParagrapheIA

# Exemples de lettre type par mode, proposés dans le profil (bouton « Partir
# d'un exemple ») : génériques, sans date, sans diplôme, sans accord de genre.
# Ils ne servent jamais de lettre en secours.
LETTRES_PAR_DEFAUT = {
    "alternance": """\
{contact_entreprise}

Le {date}

Objet : Candidature en alternance, {poste}

Madame, Monsieur,

Actuellement en formation et à la recherche d'une alternance, je vous adresse ma candidature pour rejoindre {entreprise}.

{paragraphe}

Mon parcours et ma motivation m'amènent à vouloir mettre mes compétences au service de votre structure, dans le cadre de mon alternance. Avec sérieux, implication et l'envie d'apprendre, je m'investirai pleinement dans les missions qui me seront confiées.

Un entretien serait l'occasion de vous présenter mon parcours plus en détail.

Dans l'attente de votre retour, je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.
""",
    "job": """\
{contact_entreprise}

Le {date}

Objet : Candidature, {poste}

Madame, Monsieur,

Je vous adresse ma candidature pour le poste de {poste} chez {entreprise}.

{paragraphe}

Le sérieux, la ponctualité et l'esprit d'équipe guident ma façon de travailler, et je prends vite mes repères sur un nouveau poste comme avec de nouvelles consignes. Mes disponibilités figurent dans mon CV.

Un entretien serait l'occasion d'en parler plus en détail.

Dans l'attente de votre retour, je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.
""",
    "stage": """\
{contact_entreprise}

Le {date}

Objet : Candidature pour un stage, {poste}

Madame, Monsieur,

Actuellement en formation, je recherche un stage conventionné et vous adresse ma candidature pour rejoindre {entreprise}.

{paragraphe}

Ce stage serait l'occasion de mettre en pratique ce que j'apprends et de contribuer concrètement à vos projets, avec sérieux et l'envie d'apprendre. Les dates et la durée du stage figurent dans mon CV.

Un entretien serait l'occasion de vous présenter mon parcours plus en détail.

Dans l'attente de votre retour, je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.
""",
}


def lettre_par_defaut(mode: str) -> str:
    """Exemple de lettre type du mode (proposé dans le profil, jamais utilisé seul)."""
    return LETTRES_PAR_DEFAUT.get(mode, LETTRES_PAR_DEFAUT["alternance"])


BALISES_LETTRE = ("entreprise", "poste", "date", "contact_entreprise", "paragraphe", "paragraphe_entreprise")
BALISES_PARAGRAPHE = ("paragraphe", "paragraphe_entreprise")
ALLER_AU_PROFIL = "Profil, section « Lettre de motivation type »"


class LettreTypeInvalide(ErreurUtilisateur):
    pass


def preparer_lettre_type(modele):
    """
    Vérifie une lettre type avant de l'utiliser avec str.format.
    Tolère les espaces dans les balises (« { poste } »), refuse toute autre
    accolade avec un message lisible (LettreTypeInvalide). Retourne le
    modèle normalisé.
    """
    modele = re.sub(r"\{\s*(" + "|".join(BALISES_LETTRE) + r")\s*\}", r"{\1}", modele)
    permises = ", ".join("{" + b + "}" for b in BALISES_LETTRE[:5])
    try:
        champs = [(champ, spec, conv) for _, champ, spec, conv in string.Formatter().parse(modele)
                  if champ is not None]
    except ValueError:
        raise LettreTypeInvalide(
            "Ta lettre type contient une accolade { ou } isolée. "
            f"Seules les balises {permises} sont permises : corrige-la dans {ALLER_AU_PROFIL}.")
    for champ, spec, conv in champs:
        if champ not in BALISES_LETTRE or spec or conv:
            raise LettreTypeInvalide(
                f"Ta lettre type contient une balise inconnue : {{{champ}}}. "
                f"Seules {permises} sont permises : corrige-la dans {ALLER_AU_PROFIL}.")
    return modele


def exiger_lettre_type(profil: dict) -> str:
    """Lettre type du profil, vérifiée, avec la balise du paragraphe. Sinon
    LettreTypeInvalide (400) qui renvoie au profil, avant tout appel à l'IA."""
    modele = (profil.get("lettre_type") or "").strip()
    if not modele:
        raise LettreTypeInvalide(
            f"Écris d'abord ta lettre type dans {ALLER_AU_PROFIL}, avec {{paragraphe}} à l'endroit où "
            "doit aller le paragraphe personnalisé. L'IA n'écrit que ce paragraphe.")
    modele = preparer_lettre_type(modele)
    if not any("{" + b + "}" in modele for b in BALISES_PARAGRAPHE):
        raise LettreTypeInvalide(
            f"Ta lettre type n'a pas de balise {{paragraphe}} : ajoute-la dans {ALLER_AU_PROFIL}, "
            "à l'endroit où doit aller le paragraphe personnalisé.")
    return modele


def _date_du_jour():
    mois = ["janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    today = maintenant_affichage()
    return f"{today.day} {mois[today.month - 1]} {today.year}"


# Entreprise masquée par France Travail (environ une offre sur deux)
NOMS_VIDES = {"", "inconnue", "inconnu", "non précisé", "non precise", "non renseigné", "non renseigne", "n/a", "na"}


def entreprise_connue(offre) -> bool:
    return (offre.get("entreprise") or "").strip().lower() not in NOMS_VIDES


def contact_entreprise(offre) -> str:
    """Bloc destinataire écrit en Python : nom de l'entreprise puis lieu.
    Nom inconnu : la balise reste telle quelle, à compléter (D108)."""
    if not entreprise_connue(offre):
        return "{contact_entreprise}"
    return "\n".join(x for x in ((offre.get("entreprise") or "").strip(), (offre.get("lieu") or "").strip()) if x)


# Balises laissées dans la lettre quand l'information manque (D108)
A_COMPLETER = {"entreprise": "Nom de l'entreprise inconnu, à compléter",
               "contact_entreprise": "Nom de l'entreprise inconnu, à compléter"}


def marqueurs_a_completer(lettre: str) -> list[str]:
    """Balises restées dans la lettre assemblée (entreprise inconnue)."""
    return [b for b in A_COMPLETER if "{" + b + "}" in (lettre or "")]


def sans_markdown(texte: str) -> str:
    """Retire la mise en forme markdown qu'un modèle glisse parfois dans la
    lettre : gras et italique (**, __, *, _), code (`), titres (#), puces en
    début de ligne, liens [texte](url) -> texte."""
    t = texte or ""
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"(\*\*|__)(.+?)\1", r"\2", t, flags=re.S)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", t, flags=re.S)
    t = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", t, flags=re.S)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s+", "", t, flags=re.M)
    t = t.replace("`", "").replace("*", "")
    return "\n".join(" ".join(l.split()) for l in t.splitlines()).strip()


def nettoyer_paragraphe(texte: str) -> str:
    """Paragraphe d'un seul bloc, sans markdown, sans tiret cadratin ni
    demi-cadratin (remplacés par une virgule), sans esperluette (« et »)."""
    t = sans_markdown(texte)
    t = re.sub(r"\s*[—–]\s*", ", ", t)
    t = re.sub(r"\s*&\s*", " et ", t)
    t = re.sub(r",\s*,", ",", t)
    return " ".join(t.split())


# ─── Prompt du paragraphe, écrit pour un petit modèle local ──────────────────
POSTE_PAR_MODE = {"alternance": "une alternance", "job": "un job", "stage": "un stage"}


def bagage_candidat(profil, mode="alternance") -> str:
    """Ce que le paragraphe peut citer du profil, rien d'autre (aucune invention)."""
    def court(texte, n=200):
        return " ".join(str(texte or "").split())[:n]
    lignes = []
    if mode == "stage":
        lignes.append(("Missions visées", court(profil.get("missions"), 300)))
    lignes.append(("Formation", court(profil.get("formation"))))
    lignes.append(("Compétences", ", ".join(profil.get("competences", []) or [])))
    lignes.append(("Expérience", court(profil.get("experience"))))
    projets = [court(f"{p.get('nom', '')} : {p.get('description', '')}", 150)
               for p in (profil.get("projets") or [])[:2] if p.get("nom") or p.get("description")]
    lignes.append(("Projets", " | ".join(projets)))
    texte = "\n".join(f"- {libelle} : {valeur}" for libelle, valeur in lignes if valeur)
    return texte or "- Rien de renseigné : reste sur l'intérêt pour l'entreprise, sans inventer de compétence."


def construire_messages_paragraphe(offre, profil, mode="alternance", lettre_type="") -> list[dict]:
    """Messages envoyés à l'IA pour le seul paragraphe personnalisé."""
    from shared.config import ia_longueur_description
    description = " ".join((offre.get("description", "") or "").split())[:ia_longueur_description()]
    reste = " ".join(re.sub(r"\{[^}]*\}", " ", lettre_type or "").split())[:1200]
    prompt = (
        f"Tu aides une personne candidate à {POSTE_PAR_MODE.get(mode, 'une alternance')} à écrire le paragraphe "
        "personnalisé de sa lettre de motivation. Le reste de la lettre est déjà écrit.\n\n"
        "=== TEXTE DE L'OFFRE ===\n"
        f"Entreprise : {offre.get('entreprise', '') or 'non précisée'} ({offre.get('lieu', '') or 'lieu non précisé'})\n"
        f"Poste : {offre.get('titre', '')}\n"
        f"Description : {description}\n"
        "=== FIN DE L'OFFRE ===\n\n"
        f"=== PROFIL DE LA PERSONNE ===\n{bagage_candidat(profil, mode)}\n\n"
        f"=== RESTE DE LA LETTRE (ne pas le redire) ===\n{reste or '(vide)'}\n\n"
        "Écris UN paragraphe de 3 à 5 phrases :\n"
        "- à la première personne : c'est la personne candidate qui parle au recruteur (« je », « mon ») ; "
        "jamais « vous » pour parler d'elle ;\n"
        "- ce qui l'attire dans cette entreprise et ce poste, en t'appuyant sur le texte de l'offre ;\n"
        "- le lien avec un élément réel de son profil (compétence, projet ou expérience écrit ci-dessus) ; "
        "n'invente rien et ne cite que des compétences et outils présents dans le profil ou l'offre ;\n"
        "- écris de façon neutre : aucun adjectif ni participe accordé au genre de la personne candidate ;\n"
        "- pas de formule de politesse, et rien de ce que dit déjà le reste de la lettre ;\n"
        "- texte brut : ni markdown, ni tiret cadratin, ni esperluette, ni le mot « expertise ».\n\n"
        'Réponds uniquement avec cet objet JSON : {"paragraphe": "<le paragraphe>"}'
    )
    return [{"role": "system", "content": "Tu rédiges en français. Tu réponds uniquement par un objet JSON "
                                          "valide, sans texte autour."},
            {"role": "user", "content": prompt}]


def rediger_paragraphe(offre, profil, mode="alternance", modele=None, essais=2, lettre_type=None) -> str:
    """Paragraphe personnalisé rédigé par l'IA (IA_MODELE_LETTRE, ou
    `modele`), nettoyé. Profil incomplet ou lettre type sans {paragraphe} :
    erreur 400 AVANT tout appel à l'IA (lettre_type donnée : pas de contrôle
    du profil, pour le script de vérification). Les erreurs de l'IA
    remontent : rien n'est inventé."""
    if lettre_type is None:
        exiger_profil(profil, CHAMPS_IDENTITE)
        lettre_type = exiger_lettre_type(profil)
    reponse = appeler_structure(construire_messages_paragraphe(offre, profil, mode, lettre_type), ParagrapheIA,
                                usage="lettre", modele=modele, essais=essais, temperature=0.6)
    return nettoyer_paragraphe(reponse.paragraphe) or reponse.paragraphe


def assembler_lettre(offre, profil, paragraphe: str) -> str:
    """Lettre type du profil, balises remplacées en Python, avec le
    paragraphe validé par la personne. Sans IA."""
    exiger_profil(profil, CHAMPS_IDENTITE)
    modele = exiger_lettre_type(profil)
    paragraphe = " ".join((paragraphe or "").split())
    if not paragraphe:
        raise ErreurUtilisateur("Le paragraphe personnalisé est vide : écris-le ou fais-le rédiger avant de "
                                "l'insérer dans la lettre.")
    # Nom inconnu (« Inconnue », vide) : {entreprise} et {contact_entreprise} restent visibles (D108)
    return modele.format(entreprise=(offre.get("entreprise") or "").strip() if entreprise_connue(offre)
                         else "{entreprise}",
                         poste=(offre.get("titre") or "").strip() or "le poste proposé",
                         date=_date_du_jour(), contact_entreprise=contact_entreprise(offre),
                         paragraphe=paragraphe, paragraphe_entreprise=paragraphe)
