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
  - validée d'office : même domaine que le site de l'entreprise, site retenu
    parce que son domaine correspond au nom de l'entreprise (ni annuaire, ni
    sous-domaine d'hébergeur), domaine qui n'est pas un fournisseur
    générique (gmail.com, orange.fr, wix.com...), et préfixe de contact ou
    de recrutement (contact@, rh@, recrutement@...) ;
  - douteuse : tout le reste (autre domaine, messagerie grand public,
    adresse nominative). L'IA (modèle d'extraction) tranche en un appel par
    entreprise, à partir du texte qui entoure chaque adresse sur la page, et
    désigne le meilleur contact (énumérations construites à partir des
    adresses trouvées, revérifiées en Python) ; sans IA, l'adresse reste
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
SECTIONS = ("prefixes_contact", "prefixes_ecartes", "fournisseurs_generiques", "hebergeurs")
# Comment une adresse a été validée (extra.validation_emails), affiché dans l'interface
REGLE, IA, MANUELLE = "regle", "ia", "manuelle"
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


def _dans(domaine: str, domaines) -> bool:
    """domaine est l'un de `domaines` ou l'un de leurs sous-domaines."""
    parties = (domaine or "").lower().strip(".").split(".")
    return any(".".join(parties[i:]) in domaines for i in range(len(parties) - 1))


def generique(domaine: str) -> bool:
    """Fournisseur grand public (gmail.com, orange.fr, wix.com...)."""
    return _dans(domaine, regles()["fournisseurs_generiques"])


def site_fiable(domaine_site: str | None, nom: str) -> bool:
    """Le site a-t-il été retenu parce que son domaine correspond au nom de
    l'entreprise ? Faux pour un annuaire, un sous-domaine d'hébergeur, un
    fournisseur générique, ou un domaine sans rapport avec le nom."""
    if not domaine_site:
        return False
    domaine = domaine_site.lower().removeprefix("www.")
    if _dans(domaine, regles()["hebergeurs"]) or generique(domaine):
        return False
    from spontanees.scraper_emails import analyser_nom, domaine_correspond, est_annuaire
    return not est_annuaire(domaine) and domaine_correspond(domaine, analyser_nom(nom or ""))[0]


def classer(email: str, domaine_site: str | None, fiable: bool = False) -> tuple[str, str]:
    """(VALIDE, ECARTE ou DOUTEUX ; raison lisible) d'après les règles seules.
    fiable : le site correspond au nom de l'entreprise (site_fiable) ; sans
    cela, aucune adresse n'est validée d'office."""
    email = (email or "").strip().lower()
    local, _, domaine = email.rpartition("@")
    r = regles()
    if not local or not domaine or email_exclu(email):
        return ECARTE, "liste d'exclusion"
    if _a_le_prefixe(local, r["prefixes_ecartes"]):
        return ECARTE, "adresse qui ne sert pas à candidater"
    if generique(domaine):
        return DOUTEUX, "fournisseur générique"
    meme_domaine = bool(domaine_site) and domaine_parent(domaine) == domaine_parent(domaine_site)
    if meme_domaine and not fiable:
        return DOUTEUX, "site dont le domaine ne correspond pas au nom de l'entreprise"
    if meme_domaine and _a_le_prefixe(local, r["prefixes_contact"]):
        return VALIDE, "domaine du site, adresse de contact"
    if meme_domaine:
        return DOUTEUX, "domaine du site, adresse nominative ou inhabituelle"
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


def messages_avis(nom: str, domaine_site: str | None, douteuses: list[str], trouvees: list[str],
                  extraits: dict) -> list[dict]:
    """Prompt court pour le modèle d'extraction (un petit modèle) : toutes les
    adresses douteuses d'une entreprise, avec le texte qui les entoure."""
    lignes = "\n".join(f"- {a} : « {extraits.get(a) or 'texte autour non disponible'} »" for a in douteuses)
    prompt = (
        "Des adresses email ont été trouvées sur le site d'une entreprise. Lesquelles peut-on utiliser pour "
        "lui envoyer une candidature spontanée ?\n\n"
        f"Entreprise : {nom or 'inconnue'}\n"
        f"Site de l'entreprise : {domaine_site or 'inconnu'}\n"
        f"Toutes les adresses trouvées : {', '.join(trouvees)}\n\n"
        f"Adresses à juger, avec le texte qui les entoure sur la page :\n{lignes}\n\n"
        "valides : les adresses à juger qui appartiennent à cette entreprise (ou à son groupe) et "
        "permettent de la joindre (contact, accueil, recrutement, dirigeant ou responsable). Laisse de côté "
        "celles d'un autre organisme (agence web, hébergeur, annuaire, client, partenaire, fournisseur), "
        "les adresses techniques ou d'exemple, et celles qui laissent un doute.\n"
        "meilleur_contact : parmi toutes les adresses trouvées, la meilleure pour candidater, ou null.\n\n"
        'Réponds uniquement avec cet objet JSON : {"valides": [<adresses>], "meilleur_contact": <adresse ou null>}'
    )
    return [{"role": "system", "content": "Tu vérifies des adresses email. Tu réponds uniquement par un objet "
                                          "JSON valide, sans texte autour."},
            {"role": "user", "content": prompt}]


def avis_ia(nom: str, domaine_site: str | None, douteuses: list[str], trouvees: list[str],
            extraits: dict | None = None, modele=None, essais: int = 2) -> tuple[list[str], str | None]:
    """Avis du modèle d'extraction sur les adresses douteuses d'une entreprise,
    en un appel : (douteuses retenues, meilleur contact parmi les adresses
    trouvées ou None). Énumérations imposées par le schéma, revérifiées en
    Python. Les erreurs de l'IA remontent (ErreurIABloquante,
    ErreurIAPassagere) : les adresses restent alors douteuses."""
    from shared.ia import appeler_structure
    from shared.schemas_ia import modele_avis_emails
    trouvees = list(dict.fromkeys([*trouvees, *douteuses]))
    avis = appeler_structure(messages_avis(nom, domaine_site, douteuses, trouvees, extraits or {}),
                             modele_avis_emails(douteuses, trouvees), usage="extraction", modele=modele,
                             essais=essais, temperature=0.1)
    valides = [a for a in dict.fromkeys(avis.valides) if a in douteuses]
    meilleur = avis.meilleur_contact if avis.meilleur_contact in trouvees else None
    return valides, meilleur


def trier(emails, domaine_site: str | None, nom: str = "", texte: str = "", ia: bool = True,
          contextes: dict | None = None, log=None, deja_valides=()) -> dict:
    """Trie des adresses : règles, puis un appel à l'IA (ia=True) pour toutes
    les douteuses de l'entreprise.
    texte : texte des pages lues (pour l'extrait autour de chaque adresse) ;
    contextes : extraits déjà connus {adresse: texte} (validation ultérieure) ;
    deja_valides : adresses déjà validées, proposées comme meilleur contact.
    Retourne {"valides", "provenance" {adresse validée: REGLE ou IA},
    "douteux", "ecartes" [(adresse, raison)], "ecartes_ia" (adresses que
    l'IA n'a pas retenues), "contextes" (des douteuses restantes),
    "meilleur_contact", "ia_bloquee" ou "erreur_ia" (message) si l'IA a
    échoué : les douteuses le restent. La validation d'office exige un site
    fiable (site_fiable(domaine_site, nom))."""
    from shared.ia import ErreurIABloquante, ErreurIAPassagere
    contextes = dict(contextes or {})
    resultat = {"valides": [], "provenance": {}, "douteux": [], "ecartes": [], "ecartes_ia": [],
                "contextes": {}, "meilleur_contact": None}
    raisons = {}
    fiable = site_fiable(domaine_site, nom)
    for email in dict.fromkeys(e.strip().lower() for e in emails or [] if e and e.strip()):
        decision, raison = classer(email, domaine_site, fiable)
        if decision == ECARTE:
            resultat["ecartes"].append((email, raison))
        elif decision == VALIDE:
            resultat["valides"].append(email)
            resultat["provenance"][email] = REGLE
        else:
            raisons[email] = raison
            resultat["contextes"][email] = contextes.get(email) or contexte(email, texte)
    douteuses = list(raisons)
    if ia and douteuses:
        try:
            retenues, meilleur = avis_ia(nom, domaine_site, douteuses, [*deja_valides, *resultat["valides"]],
                                         resultat["contextes"])
        except ErreurIABloquante as e:
            resultat["ia_bloquee"] = str(e)
        except ErreurIAPassagere as e:
            resultat["erreur_ia"] = str(e)
        else:
            for email in douteuses:
                if email in retenues:
                    resultat["valides"].append(email)
                    resultat["provenance"][email] = IA
                    if log:
                        log(f"    IA : {email} validée ({raisons[email]})")
                else:
                    resultat["ecartes"].append((email, f"écartée par l'IA ({raisons[email]})"))
                    resultat["ecartes_ia"].append(email)
            douteuses = []
            if meilleur in [*deja_valides, *resultat["valides"]]:
                resultat["meilleur_contact"] = meilleur
    resultat["douteux"] = douteuses
    resultat["contextes"] = {a: resultat["contextes"][a] for a in douteuses}
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
