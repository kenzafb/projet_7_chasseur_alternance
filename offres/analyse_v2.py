"""
offres/analyse_v2.py
====================
Prompt d'analyse v2 (phase 15, étape 3, D170), en deux appels :

  1. extraction : ce que dit le texte de l'offre (niveau, durée, dates,
     alternance seulement, exigences d'expérience, de permis, de
     certification, de diplôme d'État), SANS le profil, sur la description
     entière (jusqu'à LONGUEUR_EXTRACTION caractères) ; chaque valeur est
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
from shared.erreurs import exiger_profil
from shared.exigences import PERMIS_SANS_CATEGORIE, annees_dans_texte
from shared.ia import appeler_structure
from shared.schemas_ia import ExtractionOffre, JugementOffre

LONGUEUR_EXTRACTION = 8000         # caractères de description lus par l'extraction
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
    "- permis_exige : code du permis exigé (B, C, CE...) ; null s'il est seulement souhaité ;\n"
    "- certifications_exigees : certifications exigées (CACES et sa catégorie, SSIAP, carte professionnelle, BAFA, "
    "PSC1, habilitation électrique...) ;\n"
    "- diplome_etat_exige : true si un diplôme d'État est exigé.\n\n"
    'Réponds uniquement avec cet objet JSON : {"niveau_requis": ..., "niveau_exigence": ..., "duree_mois": ..., '
    '"date_debut_offre": ..., "alternance_seulement": ..., "experience_exigee_annees": ..., "permis_exige": ..., '
    '"certifications_exigees": [...], "diplome_etat_exige": ...}'
)


def messages_extraction(offre: dict, longueur: int = LONGUEUR_EXTRACTION) -> list[dict]:
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


def messages_jugement(offre: dict, profil: dict, mode: str, longueur: int) -> list[dict]:
    intro, contexte, _ = REGLES.get(mode, REGLES["alternance"])
    regles = (
        "Décide en suivant ces étapes dans l'ordre ; arrête-toi à la première qui décide.\n"
        f"Étape 1 : Hors sujet seulement si {ETAPE_1[mode]}. En cas de doute, ce n'est pas Hors sujet : passe à "
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
def lignes_extraites(extraction: dict, offre: dict) -> list[str]:
    """Exigences extraites, gardées seulement si le texte de l'offre les porte,
    écrites comme les lignes structurées (shared/exigences.py)."""
    from shared.exigences import DIPLOME_ETAT, familles
    texte = offre.get("description") or ""
    bas = texte.lower()
    out = []
    annees = extraction.get("experience_exigee_annees")
    if annees and int(annees) in annees_dans_texte(texte):   # en chiffres, en lettres, en fourchette (D176)
        out.append(f"Expérience : {int(annees)} An(s) (exigée)")
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


def analyser_offre_v2(offre, profil, mode="alternance", modele=None, essais=2, temperature=0.1,
                      longueur_jugement=None, longueur_extraction=LONGUEUR_EXTRACTION) -> dict:
    """Analyse v2 : même format de résultat que offres.analyse.analyser_offre,
    plus « categorie », « extraction », « secondes » (des deux appels)."""
    from shared.config import ia_longueur_description
    exiger_profil(profil)
    debut = time.monotonic()
    longueur_jugement = longueur_jugement or ia_longueur_description()
    extraction = appeler_structure(messages_extraction(offre, longueur_extraction), ExtractionOffre, usage="analyse",
                                   modele=modele,
                                   essais=essais, temperature=temperature).model_dump()
    jugement = appeler_structure(messages_jugement(offre, profil, mode, longueur_jugement),
                                 JugementOffre, usage="analyse", modele=modele, essais=essais,
                                 temperature=temperature).model_dump()
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
