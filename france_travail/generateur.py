import re
import os
import json
from datetime import datetime
from mistralai.client import Mistral
from dotenv import load_dotenv

load_dotenv()

client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
MODELE_LETTRE = "mistral-large-latest"

# ─── Lettre de motivation fixe ────────────────────────────────────────────────
# Seuls {contact_entreprise} et {paragraphe_entreprise} sont générés par l'IA.
# Tout le reste est rédigé par Kenza et ne change jamais.

LETTRE_TEMPLATE = """\
{contact_entreprise}

Le {date}

Objet : Candidature en alternance

Madame, Monsieur,

Actuellement en formation et à la recherche d'une alternance, je vous adresse ma candidature pour rejoindre votre équipe.

{paragraphe_entreprise}

Mon parcours et ma motivation m'amènent à vouloir mettre mes compétences au service de votre structure, dans le cadre de mon alternance. Sérieux(se), impliqué(e) et désireux(se) d'apprendre, je m'investirai pleinement dans les missions qui me seront confiées.

Je serais ravi(e) de vous présenter mon parcours plus en détail lors d'un entretien.

Dans l'attente de votre retour, je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.
"""


def _date_du_jour():
    mois = ["janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    today = datetime.today()
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


def generer_lettre(offre, profil=None, mode="alternance"):
    """
    Demande à Gemini uniquement :
    1. Le bloc contact de l'entreprise (coin haut gauche de la lettre)
    2. Le paragraphe de personnalisation (~3 phrases max)

    Assemble ensuite la lettre complète avec le template fixe.
    """
    nom_entreprise = offre.get("entreprise", "")
    titre_poste    = offre.get("titre", "")
    lieu           = offre.get("lieu", "")
    description    = (offre.get("description", "") or "")[:800]

    # Compétences réelles du candidat (depuis son profil) — pour ne PAS coder en dur l'IT
    _profil = profil or {}
    _comps = _profil.get("competences", []) or []
    _comps_txt = ", ".join(_comps) if _comps else ""
    _formation = (_profil.get("formation", "") or "").strip()
    _experience = (_profil.get("experience", "") or "").strip()
    _bagage = []
    if _comps_txt:   _bagage.append(f"Compétences : {_comps_txt}")
    if _formation:   _bagage.append(f"Formation : {_formation[:200]}")
    if _experience:  _bagage.append(f"Expérience : {_experience[:200]}")
    bagage_candidat = "\n".join(_bagage) if _bagage else "Voir le profil du candidat."

    # L'élément 2 (paragraphe entreprise) dépend du mode
    if mode == "job":
        element2 = (
            "=== ÉLÉMENT 2 — PARAGRAPHE_ENTREPRISE ===\n"
            "Un seul paragraphe de 2 à 3 phrases MAX (350 caractères max).\n"
            "Règles impératives :\n"
            "- NE commence PAS par 'Je'. Commence par le nom de l'entreprise, 'Votre', 'C'est', etc.\n"
            "- Montre un intérêt concret pour CETTE entreprise ou ce poste (secteur, mission, contexte).\n"
            "- Mets en avant les QUALITÉS HUMAINES adaptées à un job court : fiabilité, sérieux, "
            "polyvalence, sens du contact, rigueur, capacité à apprendre vite et à s'intégrer dans une équipe.\n"
            "- N'utilise PAS de compétences techniques pointues (Docker, Python, Linux, scripting...) "
            "SAUF si le poste les demande EXPLICITEMENT (ex. saisie informatique, support). "
            "Pour un poste manuel, de vente, d'accueil ou de manutention, ne parle PAS d'informatique.\n"
            "- Ton simple, direct et sincère, sans superlatifs ('passionnée', 'incroyable').\n"
            "- Ne mentionne PAS la formation ni la disponibilité (déjà dans le corps de la lettre).\n"
            "Exemple (manutention) : \"Votre entreprise recherche des profils fiables et rapides ; "
            "rigoureuse et habituée au travail en équipe, je m'investis pleinement dans les missions confiées.\"\n\n"
        )
    else:
        element2 = (
            "=== ÉLÉMENT 2 — PARAGRAPHE_ENTREPRISE ===\n"
            "Un seul paragraphe de 2 à 3 phrases MAX (350 caractères max).\n"
            "Règles impératives :\n"
            "- NE commence PAS par 'Je'. Commence par le nom de l'entreprise, 'Votre', 'C'est', etc.\n"
            "- Montre un intérêt spécifique pour cette entreprise (secteur, missions, taille, contexte).\n"
            "- Relie les compétences RÉELLES de la candidate (ci-dessous) au contexte du poste. "
            "N'invente PAS de compétences qu'elle n'a pas.\n"
            f"  Bagage du candidat :\n{bagage_candidat}\n"
            "- Ton direct et professionnel, sans superlatifs ('passionnée', 'incroyable', 'parfaite').\n"
            "- Ne mentionne PAS la formation, les projets personnels, ni la disponibilité "
            "(déjà dans le corps de la lettre).\n"
            "Exemple : \"ORMA INFORMATIQUE, votre spécialisation en infrastructures correspond "
            "à mes compétences en administration Linux et Docker, consolidées lors de mon stage "
            "au Garage Numérique.\"\n\n"
        )

    prompt = (
        "Tu aides une candidate à personnaliser sa lettre de motivation.\n"
        "Génère UNIQUEMENT ces 2 éléments en JSON valide, sans backticks ni texte autour.\n\n"

        "=== OFFRE ===\n"
        f"Entreprise : {nom_entreprise} — {lieu}\n"
        f"Poste : {titre_poste}\n"
        f"Description : {description}\n\n"

        "=== ÉLÉMENT 1 — CONTACT_ENTREPRISE ===\n"
        "Bloc destinataire pour le coin supérieur gauche de la lettre. 2-3 lignes MAX.\n"
        "Format : nom de l'entreprise ligne 1, ville ou adresse ligne 2.\n"
        "Exemple : \"ACME Solutions\\n75010 Paris\"\n"
        "INTERDIT : date, 'Objet :', formule de politesse, 'Paris le', tout autre élément de lettre.\n"
        "UNIQUEMENT le nom et la ville, rien d'autre.\n\n"

        f"{element2}"

        "Réponds UNIQUEMENT en JSON valide :\n"
        "{\"contact_entreprise\": \"...\", \"paragraphe_entreprise\": \"...\"}"
    )


    try:
        response = client.chat.complete(
            model=MODELE_LETTRE,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.6,
        )
        finish = response.choices[0].finish_reason
        texte = re.sub(r'```json\s*', '', response.choices[0].message.content or "")
        texte = re.sub(r'```\s*', '', texte).strip()
        if finish != "stop":
            print(f"  ⚠️  Mistral finish_reason={finish} — réponse potentiellement tronquée")
        result = json_parse(texte)

        contact    = result.get("contact_entreprise", nom_entreprise)
        paragraphe = result.get("paragraphe_entreprise", "")

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

        # ── Alerte si paragraphe manquant ─────────────────────────────────────
        if not paragraphe:
            print(f"  ⚠️  paragraphe_entreprise vide pour '{nom_entreprise}' — JSON reçu : {result}")

    except Exception as e:
        print(f"  Erreur génération IA : {e}")
        contact    = nom_entreprise
        paragraphe = ""

    template = (profil or {}).get("lettre_type") or LETTRE_TEMPLATE
    lettre = template.format(
        contact_entreprise=contact,
        date=_date_du_jour(),
        paragraphe_entreprise=paragraphe,
    )
    return lettre


def json_parse(texte):
    """
    Parse JSON avec double fallback :
    1. json.loads direct
    2. Extraction regex si le JSON est tronqué (ex: string non fermée)
    """
    try:
        return json.loads(texte)
    except Exception:
        pass

    # Fallback : extraction champ par champ avec regex
    result = {}
    for champ in ("contact_entreprise", "paragraphe_entreprise"):
        m = re.search(rf'"{champ}"\s*:\s*"((?:[^"\\]|\\.)*)"', texte)
        if m:
            result[champ] = m.group(1).replace("\\n", "\n")

    if result:
        print(f"  [json_parse] récupération partielle via regex : {list(result.keys())}")
        return result

    print(f"  ⚠️  json_parse échec total — texte reçu : {texte[:300]!r}")
    return {}
