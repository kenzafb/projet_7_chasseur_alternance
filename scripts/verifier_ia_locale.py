"""
scripts/verifier_ia_locale.py
=============================
Vérifie l'IA locale (Ollama ou tout serveur compatible OpenAI), à lancer
par l'humain, Ollama démarré :

    venv/bin/python scripts/verifier_ia_locale.py
    venv/bin/python scripts/verifier_ia_locale.py --modeles ministral-3:8b,ministral-3:3b,qwen3.5:9b
    venv/bin/python scripts/verifier_ia_locale.py --user 1 --mode stage --nombre 5
    venv/bin/python scripts/verifier_ia_locale.py --lettre --modeles a,b,c [--offre <id>]

1. Vérifie que le serveur répond (IA_BASE_URL) et liste ses modèles.
2. Lit dans la base, en LECTURE SEULE, les offres « non analysées » les
   plus récentes (3 par défaut) et le profil de leur utilisateur, et un
   email douteux en attente de validation (à défaut, un cas fictif).
3. Pour chaque modèle : le test de démarrage de shared/ia.py (petit schéma,
   réponse JSON valide sans texte de réflexion ; chargement du modèle mesuré
   à part), puis l'analyse de chaque offre et la validation de l'email douteux.
   Un modèle qui échoue au test de démarrage n'est pas essayé plus loin.
   Un seul essai par réponse : on mesure ce que le modèle répond du
   premier coup.
4. Affiche un tableau comparatif sur les mêmes offres : temps, JSON valide
   ou non, score, verdict, niveau requis, exigence et durée tels que le
   modèle les a lus dans l'offre puis contrôlés contre son texte (D98), et la raison d'inéligibilité décidée en Python (D94) ;
   puis l'avis sur l'email.

--lettre : à la place, pour une offre (--offre <id>, sinon la plus récente
des offres non analysées), rédige le paragraphe de lettre avec chaque
modèle et affiche les textes sous des étiquettes A, B, C... tirées au
hasard ; la correspondance étiquette-modèle n'est donnée qu'à la toute fin,
pour une lecture à l'aveugle.

Rien n'est écrit en base. Sans --modeles : IA_MODELE_ANALYSE pour les
offres et IA_MODELE_EXTRACTION pour l'email. ANALYSE_IA=false dans le .env
est ignoré pour ce test. Sur processeur, compter une à deux minutes par
offre et par modèle, plus le chargement de chaque modèle.

Code de sortie 0 si le serveur répond et qu'au moins un modèle a donné
une réponse valide, 1 sinon.
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import config  # noqa: E402  (charge le .env)

# Cas fictif si la base n'a aucun email douteux en attente
CAS_FICTIF = {"nom": "Boulangerie Martin (cas fictif)", "domaine_site": "boulangerie-martin.fr",
              "email": "contact@pixel-agence.fr",
              "contexte": "Mentions légales. Site réalisé par Pixel Agence, contact@pixel-agence.fr, "
                          "agence web à Lyon. Hébergeur : OVH."}


def url_lecture_seule(url: str) -> str:
    """sqlite:////chemin/base.db -> URL SQLite ouverte en lecture seule."""
    if not url.startswith("sqlite:///"):
        raise ValueError("Seule une base SQLite (DATABASE_URL=sqlite:///...) est prise en charge.")
    chemin = url.removeprefix("sqlite:///")
    return f"sqlite:///file:{chemin}?mode=ro&uri=true"


def lire_donnees(url: str, nombre: int, user_id=None, mode=None) -> tuple[list[dict], dict | None]:
    """[(offre, profil, mode)] des offres non analysées les plus récentes, et
    un email douteux en attente, lus en lecture seule."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from database.candidatures_db import NON_ANALYSEE, candidature_vers_dict
    from database.models import Candidature, Entreprise, Profil
    from database.profil_db import profil_vers_dict
    from shared.validation_emails import emails_douteux

    moteur = create_engine(url_lecture_seule(url))
    try:
        with Session(moteur) as db:
            requete = db.query(Candidature).filter(Candidature.verdict == NON_ANALYSEE,
                                                   Candidature.statut != "archive")
            if user_id:
                requete = requete.filter(Candidature.user_id == user_id)
            if mode:
                requete = requete.filter(Candidature.mode == mode)
            offres = []
            for c in requete.order_by(Candidature.date_trouvee.desc().nullslast(), Candidature.id.desc()):
                p = db.query(Profil).filter_by(user_id=c.user_id, mode=c.mode).first()
                if not p:
                    continue
                offres.append({"offre": candidature_vers_dict(c), "profil": profil_vers_dict(p), "mode": c.mode,
                               "user_id": c.user_id})
                if len(offres) >= nombre:
                    break
            cas = None
            requete = db.query(Entreprise)
            if user_id:
                requete = requete.filter(Entreprise.user_id == user_id)
            for e in requete.order_by(Entreprise.id.desc()):
                extra = e.extra or {}
                douteux = emails_douteux({"emails_trouves": e.emails_trouves or [],
                                          "emails_douteux": extra.get("emails_douteux"),
                                          "emails_non_valides": extra.get("emails_non_valides")})
                if douteux:
                    site = e.site_web or extra.get("url_scrapee") or ""
                    cas = {"nom": e.nom_commercial or extra.get("nom", "") or "?", "email": douteux[0],
                           "domaine_site": _domaine(site),
                           "contexte": (extra.get("contextes_emails") or {}).get(douteux[0], "")}
                    break
    finally:
        moteur.dispose()
    return offres, cas


def lire_offre(url: str, ref: str, user_id=None, mode=None) -> dict | None:
    """Une offre précise (identifiant affiché dans l'application, analysée
    ou non) et le profil de son utilisateur, lus en lecture seule."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from database.candidatures_db import candidature_vers_dict
    from database.models import Candidature, Profil
    from database.profil_db import profil_vers_dict

    moteur = create_engine(url_lecture_seule(url))
    try:
        with Session(moteur) as db:
            requete = db.query(Candidature).filter(Candidature.ref_offre == ref)
            if user_id:
                requete = requete.filter(Candidature.user_id == user_id)
            if mode:
                requete = requete.filter(Candidature.mode == mode)
            for c in requete.order_by(Candidature.id.desc()):
                p = db.query(Profil).filter_by(user_id=c.user_id, mode=c.mode).first()
                if p:
                    return {"offre": candidature_vers_dict(c), "profil": profil_vers_dict(p), "mode": c.mode,
                            "user_id": c.user_id}
    finally:
        moteur.dispose()
    return None


ETIQUETTES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def comparer_lettres(o: dict, modeles: list[str], sortie=print, tirage=None) -> int:
    """Paragraphe de lettre rédigé par chaque modèle pour l'offre o, affiché
    sous des étiquettes tirées au hasard ; correspondance à la toute fin.
    tirage : fonction qui mélange une liste en place (random.shuffle)."""
    import random

    from france_travail.generateur import rediger_elements
    from shared import ia
    from shared.ia import ErreurIA, ErreurIABloquante

    sortie(f"\nOffre [{o['mode']}, utilisateur {o['user_id']}] {o['offre']['id']} : {o['offre']['titre'][:70]}")
    textes = {}
    for modele in modeles:
        sortie(f"  {modele} : rédaction...")
        try:
            ia.verifier_demarrage(modele)
            debut = time.monotonic()
            textes[modele] = (rediger_elements(o["offre"], o["profil"], o["mode"], modele, essais=1)
                              .paragraphe_entreprise, _secondes(debut))
        except ErreurIABloquante as e:
            sortie(f"  ❌ {modele} : {e}")
        except ErreurIA as e:
            textes[modele] = (f"(pas de paragraphe : {e})", "-")
    if len(modeles) > len(ETIQUETTES):
        sortie("❌ Trop de modèles pour les étiquettes A à Z.")
        return 1
    etiquettes = list(ETIQUETTES[:len(textes)])
    (tirage or random.shuffle)(etiquettes)
    correspondance = dict(zip(etiquettes, textes))          # étiquette -> modèle
    sortie("\nParagraphes, à lire à l'aveugle :")
    for etiquette in sorted(correspondance):
        sortie(f"\n── {etiquette} ──\n{textes[correspondance[etiquette]][0]}")
    sortie("\n" + "\n" * 3 + "Correspondance (à lire après le jugement) :")
    for etiquette in sorted(correspondance):
        modele = correspondance[etiquette]
        sortie(f"  {etiquette} = {modele} ({textes[modele][1]})")
    sortie("\nRien n'a été écrit en base.")
    return 0 if textes else 1


def _domaine(site: str) -> str | None:
    from urllib.parse import urlparse
    if not site:
        return None
    return urlparse(site if "://" in site else "https://" + site).netloc.lower().removeprefix("www.") or None


def _secondes(debut: float) -> str:
    return f"{time.monotonic() - debut:.0f} s"


def _tableau(entetes: list[str], lignes: list[list[str]]) -> list[str]:
    largeurs = [max(len(str(x)) for x in [h] + [l[i] for l in lignes]) for i, h in enumerate(entetes)]
    def ligne(valeurs):
        return "  ".join(str(v).ljust(n) for v, n in zip(valeurs, largeurs)).rstrip()
    return [ligne(entetes), ligne(["-" * n for n in largeurs])] + [ligne(l) for l in lignes]


def main(argv=None, sortie=print) -> int:
    parser = argparse.ArgumentParser(description="Vérifie l'IA locale et compare des modèles, sans rien écrire.")
    parser.add_argument("--modeles", help="modèles à comparer, séparés par des virgules")
    parser.add_argument("--nombre", "--offres", dest="nombre", type=int, default=3,
                        help="offres non analysées à essayer (défaut 3)")
    parser.add_argument("--lettre", action="store_true",
                        help="comparer à l'aveugle le paragraphe de lettre de chaque modèle")
    parser.add_argument("--offre", help="identifiant de l'offre pour --lettre (défaut : la plus récente en attente)")
    parser.add_argument("--user", type=int, help="seulement les offres de cet utilisateur")
    parser.add_argument("--mode", choices=["alternance", "job", "stage"], help="seulement les offres de ce mode")
    args = parser.parse_args(argv)

    from france_travail.analyseur import analyser_offre
    from shared import ia
    from shared.ia import ErreurIA, ErreurIABloquante, ErreurIAPassagere, IAInjoignable, ReponseInvalide
    from shared.validation_emails import avis_ia

    if not config.analyse_ia_active():
        sortie("ℹ️  ANALYSE_IA=false dans le .env : ignoré pour ce test (rien n'est écrit en base).")
        os.environ["ANALYSE_IA"] = "true"

    sortie(f"Serveur d'IA : {config.ia_base_url()} (API {config.ia_api()})")
    for usage in config.USAGES_IA:
        sortie(f"  IA_MODELE_{usage.upper():<10} = {config.modele_ia(usage)}")

    # 1. Le serveur répond-il ?
    try:
        disponibles = ia.lister_modeles()
    except IAInjoignable as e:
        sortie(f"❌ {e} Lance-le (ollama serve, ou le service ollama) puis relance ce script.")
        return 1
    except ErreurIABloquante as e:
        sortie(f"❌ Le serveur refuse la liste des modèles : {e}")
        return 1
    except ErreurIAPassagere as e:
        sortie(f"⚠️  Liste des modèles indisponible : {e}")
        disponibles = None
    if disponibles is not None:
        sortie(f"✅ Le serveur répond. Modèles installés ({len(disponibles)}) :")
        for m in disponibles:
            sortie(f"  - {m}")

    if args.lettre:
        modeles = ([m.strip() for m in args.modeles.split(",") if m.strip()] if args.modeles
                   else [config.modele_ia("lettre")])
        for m in modeles:
            if disponibles is not None and m not in disponibles:
                sortie(f"⚠️  « {m} » n'est pas installé : ollama pull {m}")
        try:
            if args.offre:
                o = lire_offre(config.DATABASE_URL, args.offre, args.user, args.mode)
            else:
                o = next(iter(lire_donnees(config.DATABASE_URL, 1, args.user, args.mode)[0]), None)
        except Exception as e:
            sortie(f"❌ Base illisible ({type(e).__name__}) : {e}")
            return 1
        if o is None:
            sortie(f"❌ Offre introuvable{f' : {args.offre}' if args.offre else ' (aucune offre non analysée)'}.")
            return 1
        return comparer_lettres(o, modeles, sortie)

    if args.modeles:
        modeles = [m.strip() for m in args.modeles.split(",") if m.strip()]
        pour_email = {m: m for m in modeles}
    else:
        modeles = [config.modele_ia("analyse")]
        pour_email = {modeles[0]: config.modele_ia("extraction")}
    for m in dict.fromkeys(modeles + list(pour_email.values())):
        if disponibles is not None and m not in disponibles:
            sortie(f"⚠️  « {m} » n'est pas installé : ollama pull {m}")

    # 2. Données réelles, lecture seule
    try:
        offres, cas = lire_donnees(config.DATABASE_URL, max(1, args.nombre), args.user, args.mode)
    except Exception as e:
        sortie(f"❌ Base illisible ({type(e).__name__}) : {e}")
        return 1
    if not offres:
        sortie("ℹ️  Aucune offre « non analysée » (avec un profil) dans la base : analyse non essayée.")
    else:
        sortie(f"\n{len(offres)} offre(s) non analysée(s), lues en lecture seule :")
        for i, o in enumerate(offres, 1):
            sortie(f"  O{i}  [{o['mode']}, utilisateur {o['user_id']}] {o['offre']['titre'][:70]}")
    if cas is None:
        cas = CAS_FICTIF
    sortie(f"Email douteux : {cas['email']} ({cas['nom']}, site {cas['domaine_site'] or 'inconnu'})")

    # 3. Essais, modèle par modèle (un seul modèle chargé à la fois)
    lignes_offres, lignes_email, valides = [], [], 0
    for modele in dict.fromkeys(modeles):
        sortie(f"\n── {modele} ──")
        try:
            # Test de démarrage : chargement du modèle, schéma imposé, réflexion coupée
            duree = ia.verifier_demarrage(modele)
            sortie(f"  ✅ Test de démarrage (chargement compris, schéma JSON, sans réflexion) : {duree:.0f} s")
        except ErreurIABloquante as e:
            sortie(f"  ❌ {e}")
            continue
        except ErreurIAPassagere as e:
            sortie(f"  ⚠️  Test de démarrage en échec passager : {e}")
            continue
        for i, o in enumerate(offres, 1):
            debut = time.monotonic()
            try:
                a = analyser_offre(o["offre"], o["profil"], mode=o["mode"], modele=modele, essais=1)
                duree = a.get("duree_mois")
                ligne = [modele, f"O{i}", _secondes(debut), "oui", f"{a['score']}/10", a["verdict"],
                         a.get("niveau_requis") or "-", a.get("niveau_exigence") or "-",
                         f"{duree:g}" if duree else "-",
                         (a.get("raison_ineligibilite") or "-")[:60], a["domaine"][:24]]
                valides += 1
            except ReponseInvalide as e:
                ligne = [modele, f"O{i}", _secondes(debut), "non", "-", "-", "-", "-", "-", "-", str(e)[:40]]
            except ErreurIAPassagere as e:
                ligne = [modele, f"O{i}", _secondes(debut), "-", "-", "-", "-", "-", "-", "-", f"échec : {str(e)[:40]}"]
            except ErreurIABloquante as e:
                sortie(f"  ❌ {e}")
                break
            lignes_offres.append(ligne)
            sortie("  " + "  ".join(ligne))
        modele_email = pour_email.get(modele)
        if modele_email:
            debut = time.monotonic()
            try:
                retenues, meilleur = avis_ia(cas["nom"], cas["domaine_site"], [cas["email"]], [],
                                             {cas["email"]: cas["contexte"]}, modele=modele_email, essais=1)
                avis = "valide" if retenues else "écartée"
                ligne = [modele_email, cas["email"], _secondes(debut), "oui",
                         avis + (", meilleur contact" if meilleur == cas["email"] else "")]
                valides += 1
            except ReponseInvalide:
                ligne = [modele_email, cas["email"], _secondes(debut), "non", "-"]
            except ErreurIA as e:
                ligne = [modele_email, cas["email"], _secondes(debut), "-", f"échec : {str(e)[:40]}"]
            lignes_email.append(ligne)
            sortie("  email : " + "  ".join(ligne[2:]))

    # 4. Tableaux comparatifs
    if lignes_offres:
        sortie("\nAnalyse des offres (un seul essai par réponse) :")
        for l in _tableau(["Modèle", "Offre", "Temps", "JSON valide", "Score", "Verdict", "Niveau requis",
                           "Exigence", "Durée (mois)", "Inéligible (Python)", "Domaine ou erreur"],
                          lignes_offres):
            sortie("  " + l)
    if lignes_email:
        sortie("\nValidation de l'email douteux :")
        for l in _tableau(["Modèle", "Adresse", "Temps", "JSON valide", "Avis"], lignes_email):
            sortie("  " + l)
    sortie("\nRien n'a été écrit en base.")
    return 0 if valides else 1


if __name__ == "__main__":
    sys.exit(main())
