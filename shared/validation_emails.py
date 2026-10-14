"""
shared/validation_emails.py
===========================
Validation des emails trouvés par le scraper (phase 7) : d'abord des
règles sans IA, l'IA seulement pour les cas douteux.

Règles dans shared/referentiels/validation_emails.txt, fichier de données
à compléter sans toucher au code (préfixes de contact, préfixes écartés,
messageries grand public), en plus de la liste d'exclusion de D47
(shared/referentiels/emails_exclus.txt) :
  - écartée d'office : adresse exclue, ou préfixe écarté (dpo@, presse@...) ;
  - validée d'office : même domaine que le site de l'entreprise et préfixe
    de contact ou de recrutement (contact@, rh@, recrutement@...) ;
  - douteuse : tout le reste (autre domaine, messagerie grand public,
    adresse nominative). L'IA (modèle d'extraction) tranche, à partir du
    texte qui entoure l'adresse sur la page ; sans IA, l'adresse reste
    « non validée » : jamais envoyée automatiquement (D15), à valider à la
    main ou à repasser à l'IA plus tard.

Une entreprise garde dans emails_trouves ses adresses validées et ses
adresses douteuses ; emails_douteux liste ces dernières (avec le texte qui
les entoure, contextes_emails, pour une validation ultérieure sans relire
le site). Seules les validées partent. Entreprise d'avant la phase 7
(emails_non_valides sans emails_douteux) : toutes ses adresses sont douteuses.
"""

import re
from functools import lru_cache
from pathlib import Path

from shared.emails_exclus import email_exclu

FICHIER = Path(__file__).resolve().parent / "referentiels" / "validation_emails.txt"

VALIDE, ECARTE, DOUTEUX = "valide", "ecarte", "douteux"
SECTIONS = ("prefixes_contact", "prefixes_ecartes", "domaines_messagerie")
RAYON_CONTEXTE = 200   # caractères gardés de part et d'autre de l'adresse


@lru_cache(maxsize=1)
def regles() -> dict[str, frozenset]:
    """{section: valeurs} du fichier de règles."""
    valeurs = {s: set() for s in SECTIONS}
    section = None
    for ligne in FICHIER.read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#", 1)[0].strip().lower()
        if not ligne:
            continue
        if ligne.startswith("[") and ligne.endswith("]"):
            section = ligne[1:-1]
            if section not in valeurs:
                raise ValueError(f"{FICHIER.name} : section inconnue [{section}]")
            continue
        if section is None:
            raise ValueError(f"{FICHIER.name} : valeur hors section : {ligne}")
        valeurs[section].add(ligne)
    return {s: frozenset(v) for s, v in valeurs.items()}


def _a_le_prefixe(local: str, prefixes) -> bool:
    """local vaut un préfixe, ou commence par un préfixe suivi de . - _ ou d'un chiffre."""
    return any(local == p or (local.startswith(p) and (local[len(p)] in ".-_" or local[len(p)].isdigit()))
               for p in prefixes)


def domaine_parent(domaine: str) -> str:
    """« www.acme.fr », « rh.acme.fr » -> « acme.fr » (deux derniers niveaux)."""
    parties = (domaine or "").lower().strip(".").removeprefix("www.").split(".")
    return ".".join(parties[-2:]) if len(parties) >= 2 else ".".join(parties)


def classer(email: str, domaine_site: str | None) -> tuple[str, str]:
    """(VALIDE, ECARTE ou DOUTEUX ; raison lisible) d'après les règles seules."""
    email = (email or "").strip().lower()
    local, _, domaine = email.rpartition("@")
    r = regles()
    if not local or not domaine or email_exclu(email):
        return ECARTE, "liste d'exclusion"
    if _a_le_prefixe(local, r["prefixes_ecartes"]):
        return ECARTE, "adresse qui ne sert pas à candidater"
    meme_domaine = bool(domaine_site) and domaine_parent(domaine) == domaine_parent(domaine_site)
    if meme_domaine and _a_le_prefixe(local, r["prefixes_contact"]):
        return VALIDE, "domaine du site, adresse de contact"
    if meme_domaine:
        return DOUTEUX, "domaine du site, adresse nominative ou inhabituelle"
    if domaine in r["domaines_messagerie"]:
        return DOUTEUX, "messagerie grand public"
    if not domaine_site:
        return DOUTEUX, "site de l'entreprise inconnu"
    return DOUTEUX, "autre domaine que le site"


def contexte(email: str, texte: str, rayon: int = RAYON_CONTEXTE) -> str:
    """Texte de la page autour de la première occurrence de l'adresse (vide si absente)."""
    if not texte or not email:
        return ""
    m = re.search(re.escape(email), texte, flags=re.IGNORECASE)
    if not m:
        return ""
    extrait = texte[max(0, m.start() - rayon):m.end() + rayon]
    return " ".join(extrait.split())


def messages_validation(email: str, nom: str, domaine_site: str | None, extrait: str) -> list[dict]:
    """Prompt court pour le modèle d'extraction (un petit modèle)."""
    prompt = (
        "Une adresse email a été trouvée sur le site d'une entreprise. Peut-on s'en servir pour lui "
        "envoyer une candidature spontanée ?\n\n"
        f"Entreprise : {nom or 'inconnue'}\n"
        f"Site de l'entreprise : {domaine_site or 'inconnu'}\n"
        f"Adresse : {email}\n"
        f"Texte autour de l'adresse sur la page : « {extrait or 'non disponible'} »\n\n"
        "valide = true si l'adresse appartient à cette entreprise (ou à son groupe) et permet de la "
        "joindre : contact, accueil, recrutement, dirigeant ou responsable.\n"
        "valide = false si elle appartient à un autre organisme (agence web, hébergeur, annuaire, "
        "client, partenaire, fournisseur), si c'est une adresse technique ou d'exemple, ou en cas de doute.\n\n"
        'Réponds uniquement avec cet objet JSON : {"valide": <true ou false>}'
    )
    return [{"role": "system", "content": "Tu vérifies des adresses email. Tu réponds uniquement par un objet "
                                          "JSON valide, sans texte autour."},
            {"role": "user", "content": prompt}]


def valider_par_ia(email: str, nom: str, domaine_site: str | None, extrait: str, modele=None,
                   essais: int = 2) -> bool:
    """Avis du modèle d'extraction sur une adresse douteuse. Les erreurs de
    l'IA remontent (ErreurIABloquante, ErreurIAPassagere) : l'adresse reste
    alors douteuse."""
    from shared.ia import appeler_structure
    from shared.schemas_ia import ValidationEmail
    return appeler_structure(messages_validation(email, nom, domaine_site, extrait), ValidationEmail,
                             usage="extraction", modele=modele, essais=essais, temperature=0).valide


def trier(emails, domaine_site: str | None, nom: str = "", texte: str = "", ia: bool = True,
          contextes: dict | None = None, log=None) -> dict:
    """Trie des adresses : règles, puis IA pour les douteuses (ia=True).
    texte : texte des pages lues (pour l'extrait autour de chaque adresse) ;
    contextes : extraits déjà connus {adresse: texte} (validation ultérieure).
    Retourne {"valides", "douteux", "ecartes" [(adresse, raison)],
    "contextes" (des douteuses restantes), "ia_bloquee" ou "erreur_ia"
    (message) si l'IA a échoué}. Une erreur bloquante coupe l'IA pour les
    adresses suivantes, une passagère seulement pour l'adresse en cours."""
    from shared.ia import ErreurIABloquante, ErreurIAPassagere
    contextes = dict(contextes or {})
    resultat = {"valides": [], "douteux": [], "ecartes": [], "contextes": {}}
    for email in dict.fromkeys(e.strip().lower() for e in emails or [] if e and e.strip()):
        decision, raison = classer(email, domaine_site)
        if decision == ECARTE:
            resultat["ecartes"].append((email, raison))
            continue
        if decision == VALIDE:
            resultat["valides"].append(email)
            continue
        extrait = contextes.get(email) or contexte(email, texte)
        if ia and "ia_bloquee" not in resultat:
            try:
                if valider_par_ia(email, nom, domaine_site, extrait):
                    resultat["valides"].append(email)
                    if log:
                        log(f"    IA : {email} validée ({raison})")
                else:
                    resultat["ecartes"].append((email, f"écartée par l'IA ({raison})"))
                continue
            except ErreurIABloquante as e:
                resultat["ia_bloquee"] = str(e)
            except ErreurIAPassagere as e:
                resultat["erreur_ia"] = str(e)
        resultat["douteux"].append(email)
        resultat["contextes"][email] = extrait
    return resultat


def emails_douteux(entreprise: dict) -> list[str]:
    """Adresses d'une entreprise (format de lire_entreprises) pas encore
    validées. Entreprise d'avant la phase 7 marquée non validée : toutes."""
    trouves = entreprise.get("emails_trouves") or []
    if entreprise.get("emails_douteux") is not None:
        douteux = set(entreprise["emails_douteux"])
        return [e for e in trouves if e in douteux]
    return list(trouves) if entreprise.get("emails_non_valides") else []


def emails_valides(entreprise: dict) -> list[str]:
    """Adresses validées (par les règles, l'IA ou à la main) : les seules envoyées."""
    douteux = set(emails_douteux(entreprise))
    return [e for e in entreprise.get("emails_trouves") or [] if e not in douteux]
