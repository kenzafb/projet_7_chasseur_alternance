"""
scripts/importer_contacts_historiques.py
========================================
Importe l'historique des adresses déjà contactées (data/emails_deja_envoyes.json,
ancien dédoublonnage global d'avant la refonte) comme contactées en mode
alternance pour un utilisateur. Revient sur D1 (phase 6a).

Le fichier a été construit à l'origine depuis le dossier Envoyés de Gmail :
il peut contenir des adresses qui ne sont pas des candidatures. Chaque
adresse est donc classée d'après l'ancienne base (data/chasseur.db, ouverte
en lecture seule) :
  a. présente dans une entreprise marquée envoyée (emails trouvés ou
     destinataires du mail) : une candidature, date connue ;
  b. présente dans une entreprise de l'ancienne base, non marquée envoyée ;
  c. absente de l'ancienne base (mail personnel ou autre, probablement).

Import (groupes choisis, a seulement par défaut), dans la base de
DATABASE_URL :
  - les adresses entrent dans emails_contactes en mode alternance (date de
    l'ancien envoi pour le groupe a, inconnue sinon) : l'envoyeur ne les
    vise plus en alternance ;
  - les entreprises de l'utilisateur qui correspondent (même SIRET ou
    SIREN qu'une entreprise de l'ancienne base qui contient l'adresse, ou
    l'adresse parmi leurs emails) sont marquées contactées en alternance,
    « historique », sans toucher à celles déjà envoyées par l'application.
En mode job ou stage, rien n'est bloqué : la page Spontanées affiche
seulement « déjà contactée en alternance ». Relancer l'import ne crée
aucun doublon.

Lancement (à la racine du projet) :
  venv/bin/python scripts/importer_contacts_historiques.py --dry-run
  venv/bin/python scripts/importer_contacts_historiques.py --dry-run --user 1
  venv/bin/python scripts/importer_contacts_historiques.py --user 1               # groupe a
  venv/bin/python scripts/importer_contacts_historiques.py --user 1 --groupes a,b
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

# Lancement direct (python scripts/...) : la racine du projet doit être importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import selectinload  # noqa: E402

from shared import config  # noqa: E402
from database.connexion import SessionLocal  # noqa: E402
from database.dates import JOUR, en_texte, vers_utc  # noqa: E402
from database.dedup_db import normaliser_email  # noqa: E402
from database.insertion import inserer_ou_ignorer  # noqa: E402
from database.models import EmailContacte, Entreprise, EntrepriseMode, User  # noqa: E402
from scripts.importer_ancienne_base import fichier_sqlite, meme_fichier  # noqa: E402

MODE = "alternance"
GROUPES = {
    "a": "dans une entreprise marquée envoyée de l'ancienne base",
    "b": "dans une entreprise de l'ancienne base, non marquée envoyée",
    "c": "absentes de l'ancienne base (mails personnels ou autres, probablement)",
}
NOTE = "contactée avant la refonte (historique)"
EXEMPLES = 5


class Refus(Exception):
    """Condition de sécurité non remplie : rien n'est écrit."""


# ─── Lecture ──────────────────────────────────────────────────────────────────
def lire_historique(fichier: Path) -> list[str]:
    """Adresses du fichier, normalisées (minuscules), sans doublon, triées."""
    donnees = json.loads(Path(fichier).read_text(encoding="utf-8"))
    if not isinstance(donnees, list):
        raise Refus(f"{fichier} : une liste d'adresses est attendue")
    return sorted({normaliser_email(a) for a in donnees if isinstance(a, str)} - {""})


def _json(valeur, defaut):
    try:
        return json.loads(valeur) if isinstance(valeur, str) else (valeur or defaut)
    except ValueError:
        return defaut


def lire_ancienne_base(source: Path) -> list[dict]:
    """Entreprises de l'ancienne base (ouverte en lecture seule) :
    [{nom, siret, siren, envoyee, date, emails}]."""
    connexion = sqlite3.connect(f"file:{quote(str(source))}?mode=ro", uri=True)
    connexion.row_factory = sqlite3.Row
    try:
        lignes = connexion.execute("SELECT nom_commercial, siren, emails_trouves, mail_envoye, mail_envoye_le, extra "
                                   "FROM entreprises ORDER BY id").fetchall()
    finally:
        connexion.close()
    entreprises = []
    for r in lignes:
        extra = _json(r["extra"], {})
        emails = {normaliser_email(a) for a in _json(r["emails_trouves"], []) if isinstance(a, str)}
        emails |= {normaliser_email(a) for a in extra.get("mail_destinataires") or [] if isinstance(a, str)}
        siret = str(extra.get("siret") or "")
        date = None
        if r["mail_envoye"] and r["mail_envoye_le"]:
            try:
                date = vers_utc(r["mail_envoye_le"])   # heure locale de l'ancienne app
            except ValueError:
                date = None
        entreprises.append({"nom": r["nom_commercial"] or extra.get("nom") or "?", "siret": siret,
                            "siren": r["siren"] or siret[:9], "envoyee": bool(r["mail_envoye"]),
                            "date": date, "emails": emails - {""}})
    return entreprises


# ─── Classement ───────────────────────────────────────────────────────────────
def classer(adresses, anciennes) -> dict:
    """{groupe: {adresse: {"date", "entreprises"}}} pour les groupes a, b, c."""
    par_adresse = {}
    for e in anciennes:
        for a in e["emails"]:
            par_adresse.setdefault(a, []).append(e)
    groupes = {g: {} for g in GROUPES}
    for a in adresses:
        liees = par_adresse.get(a, [])
        envoyees = [e for e in liees if e["envoyee"]]
        if envoyees:
            dates = [e["date"] for e in envoyees if e["date"]]
            groupes["a"][a] = {"date": min(dates) if dates else None, "entreprises": envoyees}
        elif liees:
            groupes["b"][a] = {"date": None, "entreprises": liees}
        else:
            groupes["c"][a] = {"date": None, "entreprises": []}
    return groupes


def afficher_classement(groupes: dict, sortie=print):
    total = sum(len(g) for g in groupes.values())
    sortie(f"Adresses du fichier : {total}")
    for g, libelle in GROUPES.items():
        sortie(f"\n({g}) {len(groupes[g])} adresses {libelle}")
        for a, infos in list(groupes[g].items())[:EXEMPLES]:
            noms = ", ".join(sorted({e["nom"] for e in infos["entreprises"]}))[:60]
            date = f" le {en_texte(infos['date'], JOUR)}" if infos["date"] else ""
            sortie(f"    {a}" + (f"  ({noms}{date})" if noms else ""))
        if len(groupes[g]) > EXEMPLES:
            sortie(f"    ... et {len(groupes[g]) - EXEMPLES} autres")


# ─── Import ───────────────────────────────────────────────────────────────────
def importer(groupes: dict, user_id: int, choisis, appliquer: bool) -> dict:
    """Adresses des groupes choisis contactées en alternance pour user_id,
    entreprises correspondantes marquées. appliquer=False : rien n'est
    écrit (bilan de ce qui le serait). Retourne le bilan."""
    adresses = {a: infos for g in choisis for a, infos in groupes[g].items()}
    bilan = {"adresses": len(adresses), "adresses_nouvelles": 0, "entreprises_marquees": 0,
             "deja_envoyees": 0, "deja_historiques": 0}
    db = SessionLocal()
    try:
        if db.get(User, user_id) is None:
            raise Refus(f"utilisateur {user_id} introuvable dans la base cible")
        connues = {c.email for c in db.query(EmailContacte).filter_by(user_id=user_id, mode=MODE)}
        bilan["adresses_nouvelles"] = sum(1 for a in adresses if a not in connues)

        # Entreprises de l'utilisateur concernées, avec les adresses qui les relient
        sirets, sirens = {}, {}
        for a, infos in adresses.items():
            for e in infos["entreprises"]:
                if e["siret"]:
                    sirets.setdefault(e["siret"], set()).add(a)
                if e["siren"]:
                    sirens.setdefault(e["siren"], set()).add(a)
        a_marquer = []
        for e in (db.query(Entreprise).filter_by(user_id=user_id)
                    .options(selectinload(Entreprise.modes)).order_by(Entreprise.id)):
            siret = (e.extra or {}).get("siret") or ""
            siren = e.siren or siret[:9]
            liees = set(sirets.get(siret, ())) | set(sirens.get(siren, ()))
            liees |= {normaliser_email(x) for x in e.emails_trouves or []} & adresses.keys()
            if liees:
                a_marquer.append((e, sorted(liees)))

        for e, liees in a_marquer:
            m = next((x for x in e.modes if x.mode == MODE), None)
            if m is not None and m.mail_envoye:
                bilan["deja_historiques" if m.historique else "deja_envoyees"] += 1
                continue
            bilan["entreprises_marquees"] += 1
            if not appliquer:
                continue
            if m is None:
                m = EntrepriseMode(user_id=user_id, mode=MODE, statut_suivi="envoye")
                e.modes.append(m)
            dates = [adresses[a]["date"] for a in liees if adresses[a]["date"]]
            m.mail_envoye, m.historique = True, True
            m.mail_envoye_le = min(dates) if dates else None
            m.mail_destinataires = liees
            m.mail_note = NOTE

        if appliquer:
            inserer_ou_ignorer(db, EmailContacte,
                               [{"user_id": user_id, "mode": MODE, "email": a, "contacte_le": infos["date"]}
                                for a, infos in sorted(adresses.items())],
                               ["user_id", "mode", "email"])
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    return bilan


def afficher_bilan(bilan: dict, user_id: int, choisis, appliquer: bool, sortie=print):
    sortie(f"\n── {'IMPORT TERMINÉ' if appliquer else 'IMPORT À BLANC'} : user {user_id}, "
           f"groupes {', '.join(choisis)}, mode {MODE} ──")
    verbe = "ajoutées" if appliquer else "à ajouter"
    sortie(f"Adresses : {bilan['adresses']}, dont {bilan['adresses_nouvelles']} {verbe} "
           f"aux adresses contactées en {MODE}")
    sortie(f"Entreprises de la nouvelle base {'marquées' if appliquer else 'à marquer'} "
           f"« déjà contactées en {MODE} » : {bilan['entreprises_marquees']}")
    if bilan["deja_envoyees"]:
        sortie(f"  {bilan['deja_envoyees']} déjà envoyées par l'application, laissées telles quelles")
    if bilan["deja_historiques"]:
        sortie(f"  {bilan['deja_historiques']} déjà marquées par un import précédent")


# ─── Lancement ────────────────────────────────────────────────────────────────
def verifier_cible(source: Path):
    """Refus si la base cible (DATABASE_URL) est l'ancienne base elle-même."""
    cible = fichier_sqlite(config.DATABASE_URL)
    if cible is not None and meme_fichier(cible, Path(source)):
        raise Refus(f"DATABASE_URL désigne l'ancienne base ({source}) : réglez-la sur la nouvelle base")


def lancer(fichier, source, user_id=None, groupes="a", dry_run=False, sortie=print) -> dict:
    choisis = [g.strip() for g in groupes.split(",") if g.strip()]
    if not choisis or any(g not in GROUPES for g in choisis):
        raise Refus(f"groupes inconnus : {groupes} (choix : a, b, c, séparés par des virgules)")
    if not dry_run and user_id is None:
        raise Refus("--user est obligatoire pour l'import réel")
    source = Path(source)
    if not source.is_file():
        raise Refus(f"ancienne base introuvable : {source}")
    verifier_cible(source)
    classement = classer(lire_historique(fichier), lire_ancienne_base(source))
    titre = "ESSAI À BLANC (--dry-run) : rien n'est écrit" if dry_run else "IMPORT"
    sortie(f"── {titre} ──")
    sortie(f"Fichier : {fichier}")
    sortie(f"Ancienne base : {source} (lecture seule)")
    sortie(f"Base cible : {config.DATABASE_URL}\n")
    afficher_classement(classement, sortie)
    resultat = {"classement": classement, "bilan": None}
    if user_id is not None:
        resultat["bilan"] = importer(classement, user_id, choisis, appliquer=not dry_run)
        afficher_bilan(resultat["bilan"], user_id, choisis, not dry_run, sortie)
    return resultat


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Importe l'historique des adresses contactées (mode alternance).")
    parser.add_argument("--fichier", default=str(config.DATA_DIR / "emails_deja_envoyes.json"),
                        help="liste JSON des adresses (défaut : data/emails_deja_envoyes.json)")
    parser.add_argument("--source", default=str(config.DATA_DIR / "chasseur.db"),
                        help="ancienne base SQLite, ouverte en lecture seule (défaut : data/chasseur.db)")
    parser.add_argument("--user", type=int, help="utilisateur de la nouvelle base (obligatoire pour importer)")
    parser.add_argument("--groupes", default="a", help="groupes à importer : a, b, c (défaut : a)")
    parser.add_argument("--dry-run", action="store_true", help="classe et compte, n'écrit rien")
    args = parser.parse_args(argv)
    try:
        lancer(args.fichier, args.source, args.user, args.groupes, args.dry_run)
    except Refus as e:
        print(f"REFUS : {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
