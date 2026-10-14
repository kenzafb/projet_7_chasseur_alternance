import re
import string
from database.dates import maintenant_affichage
from shared.ia import appeler_structure
from shared.schemas_ia import LettreIA
from shared.erreurs import ErreurUtilisateur, exiger_profil, CHAMPS_IDENTITE

# ─── Lettre de motivation fixe ────────────────────────────────────────────────
# Seuls {contact_entreprise} et {paragraphe_entreprise} sont générés par l'IA.
# Trame par défaut de chaque mode, utilisée quand le profil n'a pas sa propre
# lettre type : générique, sans date, sans diplôme, sans accord de genre.

LETTRES_PAR_DEFAUT = {
    "alternance": """\
{contact_entreprise}

Le {date}

Objet : Candidature en alternance

Madame, Monsieur,

Actuellement en formation et à la recherche d'une alternance, je vous adresse ma candidature pour rejoindre votre équipe.

{paragraphe_entreprise}

Mon parcours et ma motivation m'amènent à vouloir mettre mes compétences au service de votre structure, dans le cadre de mon alternance. Avec sérieux, implication et l'envie d'apprendre, je m'investirai pleinement dans les missions qui me seront confiées.

Un entretien serait l'occasion de vous présenter mon parcours plus en détail.

Dans l'attente de votre retour, je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.
""",
    "job": """\
{contact_entreprise}

Le {date}

Objet : Candidature

Madame, Monsieur,

Je vous adresse ma candidature pour le poste que vous proposez.

{paragraphe_entreprise}

Le sérieux, la ponctualité et l'esprit d'équipe guident ma façon de travailler, et je prends vite mes repères sur un nouveau poste comme avec de nouvelles consignes. Mes disponibilités figurent dans mon CV.

Un entretien serait l'occasion d'en parler plus en détail.

Dans l'attente de votre retour, je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.
""",
    "stage": """\
{contact_entreprise}

Le {date}

Objet : Candidature pour un stage

Madame, Monsieur,

Actuellement en formation, je recherche un stage conventionné et vous adresse ma candidature pour rejoindre votre équipe.

{paragraphe_entreprise}

Ce stage serait l'occasion de mettre en pratique ce que j'apprends et de contribuer concrètement à vos projets, avec sérieux et l'envie d'apprendre. Les dates et la durée du stage figurent dans mon CV.

Un entretien serait l'occasion de vous présenter mon parcours plus en détail.

Dans l'attente de votre retour, je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.
""",
}


def lettre_par_defaut(mode: str) -> str:
    return LETTRES_PAR_DEFAUT.get(mode, LETTRES_PAR_DEFAUT["alternance"])


# Balises permises dans une lettre type (profil.lettre_type)
BALISES_LETTRE = ("contact_entreprise", "date", "paragraphe_entreprise")


class LettreTypeInvalide(ErreurUtilisateur):
    pass


def preparer_lettre_type(modele):
    """
    Vérifie une lettre type avant de l'utiliser avec str.format.
    Tolère les espaces dans les balises ("{ date }", accepté par le front),
    refuse toute autre accolade avec un message lisible (LettreTypeInvalide).
    Retourne le modèle normalisé.
    """
    modele = re.sub(r"\{\s*(" + "|".join(BALISES_LETTRE) + r")\s*\}", r"{\1}", modele)
    permises = ", ".join("{" + b + "}" for b in BALISES_LETTRE)
    try:
        champs = [(champ, spec, conv) for _, champ, spec, conv in string.Formatter().parse(modele)
                  if champ is not None]
    except ValueError:
        raise LettreTypeInvalide(
            "Ta lettre type contient une accolade { ou } isolée. "
            f"Seules les balises {permises} sont permises : corrige-la dans l'onglet Profil.")
    for champ, spec, conv in champs:
        if champ not in BALISES_LETTRE or spec or conv:
            raise LettreTypeInvalide(
                f"Ta lettre type contient une balise inconnue : {{{champ}}}. "
                f"Seules {permises} sont permises : corrige-la dans l'onglet Profil.")
    return modele


def _date_du_jour():
    mois = ["janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    today = maintenant_affichage()
    return f"{today.day} {mois[today.month - 1]} {today.year}"


def _nettoyer_contact(contact):
    """
    Supprime les lignes parasites qu'un LLM peut glisser dans le bloc contact :
    dates, lignes "Objet :", formules de politesse, etc.
    Ne garde que les 3 premières lignes utiles au maximum.
    """
    PARASITES = re.compile(
        r'(?i)^(paris\s*,?\s*le|objet\s*:|madame|monsieur|le\s+\d|'
        r'candidature|cordialement|sincères|bonjour|\d{1,2}\s+\w+\s+20\d{2})',
    )
    lignes = [l.strip() for l in contact.splitlines() if l.strip()]
    lignes_propres = [l for l in lignes if not PARASITES.match(l)]
    return "\n".join(lignes_propres[:3]).strip()


# ─── Prompt de la lettre, écrit pour un petit modèle local ────────────────────
POSTE_PAR_MODE = {"alternance": "une alternance", "job": "un job", "stage": "un stage"}

CONSIGNE_PAR_MODE = {
    "alternance": "- relie les compétences RÉELLES de la personne (bagage ci-dessous) aux missions du poste ;\n",
    "job": ("- mets en avant des qualités utiles pour un job court : fiabilité, sérieux, polyvalence, sens du "
            "contact, capacité à apprendre vite et à s'intégrer dans une équipe ;\n"
            "- pas de compétence technique pointue, sauf si le poste la demande explicitement ;\n"),
    "stage": "- relie les missions visées par la personne et son bagage (ci-dessous) aux missions du poste ;\n",
}


def bagage_candidat(profil, mode="alternance") -> str:
    """Ce que la lettre peut citer du profil, rien d'autre (aucune invention)."""
    def court(texte, n=200):
        return " ".join(str(texte or "").split())[:n]
    lignes = []
    if mode == "stage":
        lignes.append(("Missions visées", court(profil.get("missions"), 300)))
        lignes.append(("Formation", court(profil.get("formation"))))
    lignes.append(("Compétences", ", ".join(profil.get("competences", []) or [])))
    if mode != "stage":
        lignes.append(("Formation", court(profil.get("formation"))))
    lignes.append(("Expérience", court(profil.get("experience"))))
    projets = [court(f"{p.get('nom', '')} : {p.get('description', '')}", 150)
               for p in (profil.get("projets") or [])[:2] if p.get("nom") or p.get("description")]
    lignes.append(("Projets", " | ".join(projets)))
    texte = "\n".join(f"- {libelle} : {valeur}" for libelle, valeur in lignes if valeur)
    return texte or "- Rien de renseigné : reste sur l'intérêt pour l'entreprise, sans inventer de compétence."


def construire_messages_lettre(offre, profil, mode="alternance") -> list[dict]:
    """Messages envoyés à l'IA pour les deux éléments rédigés de la lettre."""
    from shared.config import ia_longueur_description
    description = " ".join((offre.get("description", "") or "").split())[:ia_longueur_description()]
    prompt = (
        f"Tu aides une personne candidate à personnaliser sa lettre de motivation pour "
        f"{POSTE_PAR_MODE.get(mode, 'une alternance')}. Rédige deux éléments.\n\n"
        "OFFRE\n"
        f"Entreprise : {offre.get('entreprise', '') or 'non précisée'} ({offre.get('lieu', '') or 'lieu non précisé'})\n"
        f"Poste : {offre.get('titre', '')}\n"
        f"Description : {description}\n\n"
        f"BAGAGE DE LA PERSONNE\n{bagage_candidat(profil, mode)}\n\n"
        "1. contact_entreprise : bloc destinataire en 2 lignes, le nom de l'entreprise puis la ville "
        "(ex. « ACME Solutions\\n75010 Paris »). Rien d'autre : ni date, ni objet, ni formule de politesse.\n"
        "2. paragraphe_entreprise : un seul paragraphe de 2 à 3 phrases, 350 caractères au plus :\n"
        "- ne commence pas par « Je » : commence par le nom de l'entreprise, « Votre » ou « C'est » ;\n"
        "- montre un intérêt précis pour cette entreprise ou ce poste (activité, missions, contexte) ;\n"
        f"{CONSIGNE_PAR_MODE.get(mode, CONSIGNE_PAR_MODE['alternance'])}"
        "- écris à la première personne : c'est la personne candidate qui parle au recruteur (« j'ai », « mon », "
        "« votre entreprise ») ; jamais « vous » pour parler d'elle, et l'entreprise n'est pas attirée par elle, "
        "c'est elle qui s'intéresse à l'entreprise ;\n"
        "- N'invente AUCUNE compétence ni expérience absente du bagage : ne cite que des compétences et des outils "
        "écrits dans le bagage ou dans l'offre ;\n"
        "- la personne est en formation ou débutante : pas de mot comme « expertise », « expert » ou « maîtrise "
        "parfaite » ;\n"
        "- texte brut : aucune mise en forme (ni astérisques, ni dièses, ni tirets de liste, ni gras) ;\n"
        "- écris de façon neutre : aucun adjectif ni participe accordé au genre de la personne candidate "
        "(« j'ai le sens de la rigueur » plutôt qu'un adjectif comme « je suis rigoureux ») ;\n"
        "- ton direct et sincère, sans superlatifs (« incroyable », « idéal », « parfait ») ;\n"
        "- ne parle ni de la formation, ni de la disponibilité, ni des dates : la lettre le dit déjà.\n\n"
        "Réponds uniquement avec cet objet JSON :\n"
        '{"contact_entreprise": "<nom de l\'entreprise\\nville>", "paragraphe_entreprise": "<2 à 3 phrases>"}'
    )
    return [{"role": "system", "content": "Tu rédiges en français. Tu réponds uniquement par un objet JSON "
                                          "valide, sans texte autour."},
            {"role": "user", "content": prompt}]


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


def rediger_elements(offre, profil, mode="alternance", modele=None, essais=2) -> LettreIA:
    """Les deux éléments rédigés par l'IA (bloc destinataire, paragraphe sur
    l'entreprise), sans assemblage. Réponse hors schéma redemandée une fois ;
    ErreurIABloquante et ErreurIAPassagere remontent : pas de lettre sans
    paragraphe rédigé."""
    return appeler_structure(construire_messages_lettre(offre, profil, mode), LettreIA, usage="lettre",
                             modele=modele, essais=essais, temperature=0.6)


def generer_lettre(offre, profil, mode="alternance", modele=None):
    """
    Demande à l'IA (modèle de l'usage « lettre », ou `modele`) uniquement :
    1. Le bloc contact de l'entreprise (coin haut gauche de la lettre)
    2. Le paragraphe de personnalisation (~3 phrases max)

    Assemble ensuite la lettre complète avec le template fixe.
    Lève ProfilIncomplet ou LettreTypeInvalide (erreurs 400) AVANT tout
    appel à l'IA.
    """
    exiger_profil(profil, CHAMPS_IDENTITE)
    template = preparer_lettre_type(profil.get("lettre_type") or lettre_par_defaut(mode))
    nom_entreprise = offre.get("entreprise", "")

    reponse = rediger_elements(offre, profil, mode, modele)
    contact    = sans_markdown(reponse.contact_entreprise) or nom_entreprise
    paragraphe = sans_markdown(reponse.paragraphe_entreprise) or reponse.paragraphe_entreprise

    # ── Nettoyage défensif du bloc contact ────────────────────────────────
    contact = _nettoyer_contact(contact)
    # Entreprise masquée par France Travail (~1 offre sur 2) :
    # on bascule sur une formule neutre plutôt qu'un nom bidon.
    noms_vides = {"", "inconnue", "inconnu", "non précisé", "non precise",
                  "non renseigné", "non renseigne", "n/a", "na"}
    if not contact or nom_entreprise.strip().lower() in noms_vides:
        ville = (offre.get("lieu", "") or "").strip()
        contact = "À l'attention du service recrutement"
        if ville:
            contact += "\n" + ville

    lettre = template.format(
        contact_entreprise=contact,
        date=_date_du_jour(),
        paragraphe_entreprise=paragraphe,
    )
    return lettre
