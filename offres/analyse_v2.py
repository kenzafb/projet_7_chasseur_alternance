"""
offres/analyse_v2.py
====================
Prompt d'analyse v2 (phase 15, étape 3, D170), en deux appels :

  1. extraction : ce que dit le texte de l'offre (niveau, durée, dates,
     alternance seulement, exigences d'expérience, de permis, de
     certification, de diplôme d'État), SANS le profil, sur la description
     entière (plafond de sécurité IA_LONGUEUR_DESCRIPTION, D193) ; chaque valeur est
     ensuite contrôlée contre le texte en Python (D98) ;
  2. jugement : l'adéquation au profil, en un mot (Très bien, Bien, Moyen,
     Faible, Hors sujet), par un arbre de décision ordonné : hors sujet ou
     non, puis adéquation des missions, puis réserves.

Python décide le reste : l'éligibilité (shared/eligibilite.py et
shared/exigences.py, exigences extraites comprises), la note (mot converti),
et les plafonds (niveau souhaité deux crans ou plus au-dessus du profil :
Moyen au plus).
"""

import re
import time

from offres.analyse import (POINTS_FORTS, REGLES, SYSTEME, _court, appliquer_eligibilite, coupure_description,
                            journaliser_coupure, score_to_verdict)
from shared.domaines_experience import simplifier as simplifier_texte
from shared.erreurs import exiger_profil
from shared.exigences import PERMIS_SANS_CATEGORIE, annees_dans_texte
from shared.ia import appeler_structure
from shared.journal import journaliser
from shared.schemas_ia import ExtractionOffre, JugementOffre

NOTES = {"Très bien": 9, "Bien": 7, "Moyen": 5, "Faible": 3, "Hors sujet": 1}
PLAFOND_NIVEAU_SOUHAITE = "Moyen"

# ─── 1. Extraction, sans le profil ────────────────────────────────────────────
EXTRACTION = (
    "Recopie ce que dit le texte de l'offre ci-dessous, sans rien juger ni deviner. null (ou non_precise, ou "
    "false, ou []) si le texte ne le dit pas.\n"
    "- niveau_requis : niveau d'études demandé au candidat (« école d'ingénieurs », « Master 2 », « Bac+5 » = "
    "bac+5 ; « Master 1 », « Bac+4 » = bac+4 ; « licence », « Bac+3 » = bac+3 ; « BTS », « DUT », « Bac+2 » = "
    "bac+2 ; « Bac » = bac). L'intitulé du poste n'est pas un niveau d'études ;\n"
    "- niveau_exigence : exige si le texte écrit exigé, obligatoire, impératif, requis ou indispensable à côté du "
    "niveau ; souhaite sinon ; non_precise sans niveau ;\n"
    "- duree_mois : durée du contrat ou du stage, en mois (6 mois = 6, 10 semaines = 2.5) ;\n"
    "- date_debut_offre : date ou mois de début, avec l'année ;\n"
    "- alternance_seulement : true si l'offre n'est proposée qu'en alternance ou apprentissage ;\n"
    "- experience_exigee_annees : années d'expérience exigées (« 2 ans minimum », « 3 ans d'expérience exigée ») ; "
    "null si elle est seulement souhaitée ou si un débutant est accepté ;\n"
    "- experience_exigee_domaine : métier ou secteur de l'expérience exigée, recopié mot pour mot du texte, sans la "
    "durée ; null si le texte n'en donne pas ;\n"
    "- permis_exige : code du permis exigé (B, C, CE...) ; null s'il est seulement souhaité ;\n"
    "- certifications_exigees : certifications exigées (CACES et sa catégorie, SSIAP, carte professionnelle, BAFA, "
    "PSC1, habilitation électrique...) ;\n"
    "- diplome_etat_exige : true si un diplôme d'État est exigé.\n\n"
    'Réponds uniquement avec cet objet JSON : {"niveau_requis": ..., "niveau_exigence": ..., "duree_mois": ..., '
    '"date_debut_offre": ..., "alternance_seulement": ..., "experience_exigee_annees": ..., "experience_exigee_domaine": ..., "permis_exige": ..., '
    '"certifications_exigees": [...], "diplome_etat_exige": ...}'
)


def messages_extraction(offre: dict, longueur: int | None = None) -> list[dict]:
    from shared.config import ia_longueur_description
    longueur = longueur or ia_longueur_description()
    description = _court(offre.get("description"), longueur)
    texte = (f"=== TEXTE DE L'OFFRE ===\nTitre : {offre.get('titre', '')}\n"
             f"Description : {description}\n=== FIN ===\n\n{EXTRACTION}")
    return [{"role": "system", "content": "Tu recopies des informations d'une offre d'emploi. Tu réponds uniquement "
                                          "par un objet JSON valide, sans texte autour."},
            {"role": "user", "content": texte}]


# ─── 2. Jugement, avec le profil ──────────────────────────────────────────────
DEFINITIONS = (
    "Les cinq mots, du meilleur au pire :\n"
    "- Très bien : les missions sont celles que le candidat vise, plusieurs de ses compétences servent directement ;\n"
    "- Bien : missions proches de ce qu'il vise, au moins une de ses compétences sert ;\n"
    "- Moyen : même domaine, mais missions assez différentes de ce qu'il vise ;\n"
    "- Faible : lien faible avec son profil, peu de compétences en commun ;\n"
    "- Hors sujet : à écarter (étape 1)."
)

ETAPE_1 = {
    "alternance": ("le poste réel est dans un tout autre domaine que ceux recherchés (un domaine voisin n'est pas "
                   "hors sujet) ; ou il correspond exactement à ce que le candidat écrit préférer éviter ; ou c'est un "
                   "poste senior (confirmé, architecte, chef de service)"),
    "stage": ("le poste réel est dans un tout autre domaine que ceux recherchés (un domaine voisin n'est pas hors "
              "sujet) ; ou ce n'est pas un stage pour un étudiant (emploi salarié, formation payante)"),
    "job": ("le poste fait partie des types de jobs que le candidat écrit vouloir éviter ; ou il contredit une "
            "contrainte écrite du profil de façon certaine. Un poste qui n'est pas dans les types qui conviennent "
            "n'est PAS hors sujet pour autant"),
}
ETAPE_2 = {
    "alternance": ("compare les missions réelles (pas le seul titre) au niveau visé, à la formation et aux "
                   "compétences : Très bien ou Bien si elles y correspondent, Moyen si c'est le bon domaine avec des "
                   "missions différentes, Faible si le lien est mince"),
    "stage": ("compare les missions réelles (pas le seul titre) aux missions visées et aux compétences : Très bien "
              "ou Bien si elles y correspondent, Moyen si c'est le bon domaine avec des missions différentes, Faible "
              "si le lien est mince"),
    "job": ("compare le poste aux types de jobs qui conviennent : Très bien ou Bien s'il en fait partie, Moyen s'il "
            "est acceptable sans être souhaité (le profil le tolère), Faible s'il est peu adapté (physique, loin, "
            "horaires peu compatibles) sans être à éviter"),
}


# Stage : « à éviter » facultatif (D201). Sans lui, le prompt reste celui mesuré par le banc
EVITER_STAGE = " ; ou il correspond exactement à ce que le candidat écrit préférer éviter"


def etape_1(profil: dict, mode: str) -> str:
    eviter = mode == "stage" and (profil.get("criteres_eviter") or "").strip()
    return ETAPE_1[mode] + (EVITER_STAGE if eviter else "")


def messages_jugement(offre: dict, profil: dict, mode: str, longueur: int) -> list[dict]:
    intro, contexte, _ = REGLES.get(mode, REGLES["alternance"])
    regles = (
        "Décide en suivant ces étapes dans l'ordre ; arrête-toi à la première qui décide.\n"
        f"Étape 1 : Hors sujet seulement si {etape_1(profil, mode)}. En cas de doute, ce n'est pas Hors sujet : passe à "
        "l'étape 2.\n"
        f"Étape 2 : sinon, {ETAPE_2[mode]}.\n"
        "Étape 3 : réserves. Si l'offre demande une compétence importante absente du profil, descends d'un cran "
        "(Très bien devient Bien, Bien devient Moyen, Moyen devient Faible), une seule fois.\n"
        "Le niveau d'études, la durée, les dates, le permis et les certifications sont vérifiés à part : n'en "
        "tiens pas compte.\n\n" + DEFINITIONS
    )
    texte = (
        f"{intro}\n\n=== PROFIL DU CANDIDAT ===\n{contexte(profil)}\n\n"
        f"=== OFFRE ===\nTitre : {offre.get('titre', '')}\nEntreprise : {offre.get('entreprise', '') or 'non précisée'}\n"
        f"Lieu : {offre.get('lieu', '') or 'non précisé'}\nDescription : {_court(offre.get('description'), longueur)}\n"
        f"=== FIN ===\n\n{regles}\n\n{POINTS_FORTS}\n"
        "domaine : catégorie métier courte, ou exactement « Hors domaine » si l'étape 1 décide.\n"
        "hors_sujet_car : si tu choisis Hors sujet, recopie mot pour mot la phrase du profil qui l'impose "
        "(domaines recherchés, ce qu'il préfère éviter, types de jobs à éviter) ; sinon « aucune ».\n\n"
        'Réponds uniquement avec cet objet JSON : {"categorie": "<Très bien, Bien, Moyen, Faible ou Hors sujet>", '
        '"hors_sujet_car": "<phrase du profil ou aucune>", '
        '"points_forts": [<3 phrases courtes au plus>], "points_faibles": [<2 phrases courtes au plus>], '
        '"domaine": "<2 à 4 mots>", "resume": "<12 mots au plus>"}'
    )
    return [{"role": "system", "content": SYSTEME}, {"role": "user", "content": texte}]


# ─── Python : contrôle, éligibilité, note, plafonds ───────────────────────────
FENETRE_EXPERIENCE = (120, 80)     # caractères avant et après le domaine extrait
_MOIS_ECRITS = re.compile(r"(\d{1,3})\s*mois\b")


def _fenetres(domaine: str, texte: str) -> list[str]:
    """Passages du texte (minuscules, sans accents) autour du domaine qui parlent d'expérience."""
    t, d = simplifier_texte(texte), simplifier_texte(domaine)
    avant, apres = FENETRE_EXPERIENCE
    passages = [t[max(0, m.start() - avant):m.end() + apres] for m in re.finditer(rf"(?<![a-z0-9]){re.escape(d)}(?![a-z0-9])", t)]
    return [p for p in passages if "experience" in p]


def domaine_dans_texte(domaine, texte: str) -> str:
    """Domaine extrait, gardé seulement si le texte l'écrit tel quel près du
    mot « expérience » (D211) ; "" sinon."""
    domaine = " ".join(str(domaine or "").replace("(", " ").replace(")", " ").split()).strip(" .,;:-")
    if domaine.lower() in ("", "null", "aucun", "aucune") or len(domaine) > 80:
        return ""
    return domaine if _fenetres(domaine, texte) else ""


def ligne_domaine(domaine: str, texte: str) -> str:
    """Ligne d'un domaine extrait sans nombre d'années : complète la ligne
    « exigée » de France Travail, ou seule si le passage porte un mot
    d'exigence et aucun mot de souhait (mois lus dans ce passage)."""
    from shared.eligibilite import MARQUEURS_SOUHAIT
    from shared.exigences import MARQUEURS_EXIGENCE, experience_demandee
    if experience_demandee(texte) is not None:
        return f"Expérience : Expérience exigée - {domaine} (exigée)"
    for passage in _fenetres(domaine, texte):
        if MARQUEURS_EXIGENCE.search(passage) and not MARQUEURS_SOUHAIT.search(passage):
            m = _MOIS_ECRITS.search(passage)
            return f"Expérience : {m.group(1)} Mois - {domaine} (exigée)" if m else \
                f"Expérience : Expérience exigée - {domaine} (exigée)"
    return ""


def lignes_extraites(extraction: dict, offre: dict) -> list[str]:
    """Exigences extraites, gardées seulement si le texte de l'offre les porte,
    écrites comme les lignes structurées (shared/exigences.py)."""
    from shared.exigences import DIPLOME_ETAT, familles
    texte = offre.get("description") or ""
    bas = texte.lower()
    out = []
    annees = extraction.get("experience_exigee_annees")
    domaine = domaine_dans_texte(extraction.get("experience_exigee_domaine"), texte)
    suite = f" - {domaine}" if domaine else ""
    if annees and int(annees) in annees_dans_texte(texte):   # en chiffres, en lettres, en fourchette (D176)
        out.append(f"Expérience : {int(annees)} An(s){suite} (exigée)")
    elif domaine and (ligne := ligne_domaine(domaine, texte)):
        out.append(ligne)
    permis = (extraction.get("permis_exige") or "").strip().upper()
    if re.fullmatch(r"[A-Z][A-Z0-9]{0,2}", permis) and re.search(rf"permis\s*(?:de conduire\s*)?{permis.lower()}\b", bas):
        out.append(f"Permis : {permis} (exigé)")
    elif permis and re.search(r"\bpermis\b", bas):
        # Catégorie non retrouvée dans le texte (« permis C » extrait, « permis D »
        # ou « permis transport en commun » écrit) : un permis est exigé, sans
        # catégorie sûre (D175)
        out.append(f"Permis : {PERMIS_SANS_CATEGORIE} - catégorie non lue (exigé)")
    for c in extraction.get("certifications_exigees") or []:
        for famille in familles(c):
            if famille in familles(texte):
                out.append(f"Compétence : {famille} (indispensable)")
    if extraction.get("diplome_etat_exige") and DIPLOME_ETAT.search(texte):
        out.append("Formation : Diplôme d'État (indispensable)")
    return list(dict.fromkeys(out))


# Champs du profil qui peuvent rendre une offre hors sujet, par mode
CHAMPS_EXCLUSION = {"job": ("types_jobs_eviter",), "stage": ("criteres_eviter",),
                    "alternance": ("criteres_eviter",)}


def hors_sujet_justifie(raison: str, profil: dict, mode: str) -> bool:
    """La phrase citée par le modèle vient-elle d'un champ d'exclusion du
    profil (ou, hors job, des domaines recherchés) ? Au moins deux mots de 4
    lettres ou plus de la citation doivent s'y trouver."""
    from offres.analyse import _domaines
    from spontanees.site_officiel import simplifier
    mots = [m for m in simplifier(raison).split() if len(m) >= 4]
    if not mots or simplifier(raison) in ("aucune", "aucun"):
        return False
    sources = [str(profil.get(c) or "") for c in CHAMPS_EXCLUSION.get(mode, ())]
    if mode != "job":
        sources.append(_domaines(profil))
    texte = f" {simplifier(' '.join(sources))} "
    return sum(1 for m in mots if f" {m} " in texte) >= min(2, len(mots))


def appliquer_plafonds(result: dict, profil: dict) -> dict:
    """Niveau seulement souhaité, deux crans ou plus au-dessus du profil :
    Moyen au plus (remplace le malus de v1)."""
    from shared.eligibilite import ECART_NIVEAU_BLOQUANT, LIBELLES, ecart_niveau
    ecart = ecart_niveau(result, profil)
    if (result.get("niveau_exigence") == "souhaite" and ecart and ecart[0] >= ECART_NIVEAU_BLOQUANT
            and result["score"] > NOTES[PLAFOND_NIVEAU_SOUHAITE]):
        result["score"] = NOTES[PLAFOND_NIVEAU_SOUHAITE]
        result["points_faibles"] = [f"{LIBELLES[ecart[1]]} souhaité, profil {LIBELLES[ecart[2]]}"] + \
            result["points_faibles"][:2]
    return result


NUM_CTX_ANALYSE = 4096       # D194 : plus grand prompt mesuré 2 271 tokens, réponse 265 au plus
SORTIE_ANALYSE = 512         # tokens réservés à la réponse (265 au plus mesurés)


def num_ctx_offre(messages_par_appel) -> int:
    """num_ctx unique des deux appels d'une offre (D194) : NUM_CTX_ANALYSE,
    relevé au millier supérieur seulement si le plus grand prompt estimé
    (shared.ia.CARACTERES_PAR_TOKEN) plus la réponse n'y tient pas ; jamais
    plus que PLAFOND_NUM_CTX. Le même pour les deux appels : Ollama ne
    recharge pas le modèle entre eux."""
    from shared.ia import CARACTERES_PAR_TOKEN, PLAFOND_NUM_CTX
    plus_grand = max(sum(len(m["content"]) for m in messages) for messages in messages_par_appel)
    besoin = int(plus_grand / CARACTERES_PAR_TOKEN) + SORTIE_ANALYSE
    if besoin <= NUM_CTX_ANALYSE:
        return NUM_CTX_ANALYSE
    num_ctx = min(-(-besoin // 1024) * 1024, PLAFOND_NUM_CTX)
    journaliser(f"  ℹ️  Prompt long (environ {besoin} tokens avec la réponse) : num_ctx porté de {NUM_CTX_ANALYSE} "
                f"à {num_ctx} pour cette offre")
    return num_ctx


def analyser_offre_v2(offre, profil, mode="alternance", modele=None, essais=2, temperature=0.1,
                      longueur_jugement=None, longueur_extraction=None, num_ctx=None) -> dict:
    """Analyse v2 : même format de résultat que offres.analyse.analyser_offre,
    plus « categorie », « extraction », « secondes » (des deux appels). Les
    deux appels lisent la description entière, sous le plafond de sécurité
    IA_LONGUEUR_DESCRIPTION, avec le même num_ctx (num_ctx_offre, D194). num_ctx=0 : un
    num_ctx par appel, comme avant D193 (mesure seulement)."""
    from shared.config import ia_longueur_description
    exiger_profil(profil)
    debut = time.monotonic()
    longueur_jugement = longueur_jugement or ia_longueur_description()
    longueur_extraction = longueur_extraction or ia_longueur_description()
    m_extraction = messages_extraction(offre, longueur_extraction)
    m_jugement = messages_jugement(offre, profil, mode, longueur_jugement)
    num_ctx = num_ctx_offre((m_extraction, m_jugement)) if num_ctx is None else num_ctx
    extraction = appeler_structure(m_extraction, ExtractionOffre, usage="analyse", modele=modele, essais=essais,
                                   temperature=temperature, num_ctx=num_ctx).model_dump()
    jugement = appeler_structure(m_jugement, JugementOffre, usage="analyse", modele=modele, essais=essais,
                                 temperature=temperature, num_ctx=num_ctx).model_dump()
    # Hors sujet sans phrase du profil qui l'impose : Faible (le petit modèle en abusait, D170)
    if jugement["categorie"] == "Hors sujet" and not hors_sujet_justifie(jugement["hors_sujet_car"], profil, mode):
        jugement["categorie"] = "Faible"
        if jugement["domaine"] == "Hors domaine":
            jugement["domaine"] = "Non classé"
    result = {
        "score": NOTES[jugement["categorie"]], "categorie": jugement["categorie"], "eligible": True,
        "points_forts": jugement["points_forts"][:3], "points_faibles": jugement["points_faibles"][:2],
        "domaine": jugement["domaine"] or "Non classé", "resume": jugement["resume"],
        **{k: extraction[k] for k in ("niveau_requis", "niveau_exigence", "duree_mois", "date_debut_offre",
                                      "alternance_seulement")},
        "extraction": extraction,
        # Gardée même rétrogradée en Faible (D205) ; « aucune » : rien
        "hors_sujet_car": "" if jugement["hors_sujet_car"].strip(" .«»").lower() in ("aucune", "aucun")
        else jugement["hors_sujet_car"].strip(),
    }
    result["verdict"] = score_to_verdict(result["score"])
    # Exigences extraites du texte libre : contrôlées, puis jugées par les mêmes règles Python
    lignes = lignes_extraites(extraction, offre)
    offre_vue = {**offre, "description": (offre.get("description") or "") + "".join(f"\n{x}" for x in lignes)}
    appliquer_eligibilite(result, offre_vue, profil, mode, malus_souhait=False)
    if result["eligible"]:
        appliquer_plafonds(result, profil)
        result["verdict"] = score_to_verdict(result["score"])
    result["exigences_extraites"] = lignes
    # Description plus longue que ce que lit un des deux appels (D189)
    result["description_coupee"] = coupure_description(offre, extraction=longueur_extraction,
                                                       jugement=longueur_jugement)
    journaliser_coupure(offre, result["description_coupee"])
    result["secondes"] = round(time.monotonic() - debut, 2)
    return result
