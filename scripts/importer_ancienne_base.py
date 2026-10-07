"""
scripts/importer_ancienne_base.py
=================================
Importe les comptes et profils de l'ancienne base SQLite dans une base neuve
au schéma Alembic. Remplace database/migration.py.

Ce qui est importé : les users 1, 3 et 4 (ids et hashs de mot de passe
conservés tels quels, donc mêmes identifiants de connexion) et tous leurs
profils, tous modes confondus. Rien d'autre : ni le user 2, ni les
candidatures, ni les entreprises, ni les fichiers JSON de dédoublonnage.

Pièces jointes : l'ancienne base stocke des chemins relatifs à la racine du
projet ("data/uploads/user_1/cv.pdf"), la nouvelle des chemins relatifs à
UPLOADS_DIR ("user_1/cv.pdf"). Les fichiers ne sont ni déplacés ni renommés ;
ceux qui manquent ou n'ont pas d'extension sont signalés.

Sécurité :
  - la source est ouverte en lecture seule (sqlite3, URI mode=ro) ;
  - refus si source et cible sont le même fichier ;
  - refus si la cible contient déjà des users ;
  - --dry-run : affiche ce qui serait importé, n'écrit rien (pas même la
    création de la cible).

Lancement (à la racine du projet) :
  python scripts/importer_ancienne_base.py --source data/chasseur.db --cible data/chasseur_v2.db --dry-run
  python scripts/importer_ancienne_base.py --source data/chasseur.db --cible data/chasseur_v2.db
--cible accepte un chemin de fichier SQLite ou une URL SQLAlchemy.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote

# Lancement direct (python scripts/...) : la racine du projet doit être importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from shared import config  # noqa: E402
from database.connexion import creer_moteur  # noqa: E402
from database.models import Profil, User  # noqa: E402
from database.schema import migrer  # noqa: E402

USERS_A_IMPORTER = (1, 3, 4)

# Préfixe des chemins de pièces jointes dans l'ancienne base (relatifs à la racine)
ANCIEN_PREFIXE = PurePosixPath("data/uploads")

# Colonnes de profils à reprendre : celles du nouveau schéma, hors clé technique
COLONNES_PROFIL = [c.name for c in Profil.__table__.columns if c.name != "id"]
COLONNES_JSON_PROFIL = {c.name for c in Profil.__table__.columns
                        if c.type.__class__.__name__ == "JSON"}


class Refus(Exception):
    """Condition de sécurité non remplie : rien n'est écrit."""


# ─── Cible ────────────────────────────────────────────────────────────────────
def url_cible(cible: str) -> str:
    """Chemin de fichier → URL sqlite absolue ; URL laissée telle quelle."""
    if "://" in cible:
        return cible
    return f"sqlite:///{Path(cible).resolve()}"


def fichier_sqlite(url: str) -> Path | None:
    """Fichier d'une URL sqlite (None pour un autre SGBD ou une base en mémoire)."""
    u = make_url(url)
    if u.get_backend_name() != "sqlite" or not u.database or u.database == ":memory:":
        return None
    return Path(u.database).resolve()


def meme_fichier(a: Path, b: Path) -> bool:
    if a.exists() and b.exists():
        return os.path.samefile(a, b)
    return a.resolve() == b.resolve()


def nombre_users_cible(url: str) -> int:
    """Nombre de users déjà dans la cible (0 si elle n'existe pas encore).
    Ne crée pas le fichier SQLite s'il est absent."""
    fichier = fichier_sqlite(url)
    if fichier is not None and not fichier.exists():
        return 0
    if fichier is not None:
        # Lecture seule : ni création, ni écriture
        connexion = sqlite3.connect(f"file:{quote(str(fichier))}?mode=ro", uri=True)
        try:
            existe = connexion.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
            return connexion.execute("SELECT COUNT(*) FROM users").fetchone()[0] if existe else 0
        finally:
            connexion.close()
    moteur = creer_moteur(url)
    try:
        if not inspect(moteur).has_table("users"):
            return 0
        with moteur.connect() as connexion:
            return connexion.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
    finally:
        moteur.dispose()


# ─── Source ───────────────────────────────────────────────────────────────────
def ouvrir_source(source: Path) -> sqlite3.Connection:
    connexion = sqlite3.connect(f"file:{quote(str(source))}?mode=ro", uri=True)
    connexion.row_factory = sqlite3.Row
    return connexion


def lire_source(source: Path) -> tuple[list[dict], list[dict]]:
    """Users à importer et leurs profils, lus dans l'ancienne base."""
    connexion = ouvrir_source(source)
    try:
        marques = ",".join("?" * len(USERS_A_IMPORTER))
        users = [dict(r) for r in connexion.execute(
            f"SELECT id, email, mot_de_passe_hash, cree_le FROM users "
            f"WHERE id IN ({marques}) ORDER BY id", USERS_A_IMPORTER)]
        colonnes_source = {r["name"] for r in connexion.execute("PRAGMA table_info(profils)")}
        colonnes = [c for c in COLONNES_PROFIL if c in colonnes_source]
        profils = [dict(r) for r in connexion.execute(
            f"SELECT {', '.join(colonnes)} FROM profils "
            f"WHERE user_id IN ({marques}) ORDER BY user_id, mode", USERS_A_IMPORTER)]
        return users, profils
    finally:
        connexion.close()


# ─── Conversions ──────────────────────────────────────────────────────────────
def date_utc(valeur) -> datetime | None:
    """Anciennes dates (datetime.utcnow() stocké en texte) : naïves, donc UTC."""
    if not valeur:
        return None
    dt = datetime.fromisoformat(str(valeur))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def json_ou_valeur(valeur):
    if isinstance(valeur, str):
        try:
            return json.loads(valeur)
        except ValueError:
            return valeur
    return valeur


def chemin_relatif_uploads(ancien: str) -> str:
    """Ancien chemin de pièce jointe → chemin relatif à UPLOADS_DIR."""
    chemin = PurePosixPath(ancien.replace("\\", "/"))
    uploads = Path(config.UPLOADS_DIR)
    if chemin.is_absolute():
        try:
            return Path(chemin).relative_to(uploads).as_posix()
        except ValueError:
            return str(chemin)
    # Format historique : relatif à la racine du projet ("data/uploads/...")
    if chemin.parts[:len(ANCIEN_PREFIXE.parts)] == ANCIEN_PREFIXE.parts:
        return PurePosixPath(*chemin.parts[len(ANCIEN_PREFIXE.parts):]).as_posix()
    return chemin.as_posix()


def convertir_profil(ligne: dict, rapport: dict) -> dict:
    profil = {}
    for colonne, valeur in ligne.items():
        profil[colonne] = json_ou_valeur(valeur) if colonne in COLONNES_JSON_PROFIL else valeur
    pieces = []
    for pj in profil.get("pieces_jointes") or []:
        relatif = chemin_relatif_uploads(pj.get("fichier", "") or "")
        pieces.append({**pj, "fichier": relatif})
        chemin = config.chemin_piece_jointe(relatif)
        info = (ligne["user_id"], ligne["mode"], pj.get("nom", ""), relatif)
        if chemin is None or not chemin.is_file():
            rapport["manquantes"].append(info)
        else:
            rapport["trouvees"].append(info)
        if not PurePosixPath(relatif).suffix:
            rapport["sans_extension"].append(info)
    profil["pieces_jointes"] = pieces
    return profil


# ─── Import ───────────────────────────────────────────────────────────────────
def importer(source: str, cible: str, dry_run: bool = False, sortie=print) -> dict:
    """Lance l'import. Lève Refus si une condition de sécurité n'est pas remplie."""
    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise Refus(f"source introuvable : {source_path}")
    url = url_cible(cible)
    fichier = fichier_sqlite(url)
    if fichier is not None and meme_fichier(source_path, fichier):
        raise Refus("source et cible sont le même fichier")
    deja = nombre_users_cible(url)
    if deja:
        raise Refus(f"la cible contient déjà {deja} user(s) : import refusé")

    users, lignes_profils = lire_source(source_path)
    rapport = {"users": [], "profils": [], "trouvees": [], "manquantes": [],
               "sans_extension": [], "absents": [], "dry_run": dry_run}
    rapport["absents"] = [i for i in USERS_A_IMPORTER if i not in {u["id"] for u in users}]
    profils = [convertir_profil(p, rapport) for p in lignes_profils]
    rapport["users"] = [(u["id"], u["email"]) for u in users]
    rapport["profils"] = [(p["user_id"], p["mode"], p.get("prenom") or "", p.get("nom") or "")
                          for p in profils]

    if not dry_run:
        migrer(url)
        moteur = creer_moteur(url)
        try:
            with Session(moteur) as db, db.begin():
                # Revérifié dans la transaction, au cas où la cible aurait bougé
                if db.query(User).count():
                    raise Refus("la cible contient déjà des users : import refusé")
                for u in users:
                    db.add(User(id=u["id"], email=u["email"],
                                mot_de_passe_hash=u["mot_de_passe_hash"],
                                cree_le=date_utc(u["cree_le"])))
                db.flush()
                for p in profils:
                    db.add(Profil(**p))
        finally:
            moteur.dispose()

    afficher_resume(rapport, source_path, url, sortie)
    return rapport


def afficher_resume(rapport: dict, source: Path, url: str, sortie=print):
    titre = "ESSAI À BLANC (--dry-run) : rien n'a été écrit" if rapport["dry_run"] else "IMPORT TERMINÉ"
    sortie(f"── {titre} ──")
    sortie(f"Source : {source} (lecture seule)")
    sortie(f"Cible  : {url}")
    verbe = "à importer" if rapport["dry_run"] else "importés"
    sortie(f"\nUsers {verbe} : {len(rapport['users'])}")
    for uid, email in rapport["users"]:
        sortie(f"  {uid}  {email}")
    if rapport["absents"]:
        sortie(f"  absents de la source : {', '.join(map(str, rapport['absents']))}")
    sortie(f"\nProfils {verbe} : {len(rapport['profils'])}")
    for uid, mode, prenom, nom in rapport["profils"]:
        sortie(f"  user {uid}  {mode:<10} {prenom} {nom}".rstrip())
    sortie(f"\nPièces jointes trouvées : {len(rapport['trouvees'])}")
    for uid, mode, nom, chemin in rapport["trouvees"]:
        sortie(f"  user {uid} {mode} : {nom} → {chemin}")
    sortie(f"Pièces jointes manquantes : {len(rapport['manquantes'])}")
    for uid, mode, nom, chemin in rapport["manquantes"]:
        sortie(f"  user {uid} {mode} : {nom} → {chemin}")
    sortie(f"Pièces jointes sans extension : {len(rapport['sans_extension'])}")
    for uid, mode, nom, chemin in rapport["sans_extension"]:
        sortie(f"  user {uid} {mode} : {nom} → {chemin}")
    sortie(f"(chemins relatifs à UPLOADS_DIR = {config.UPLOADS_DIR})")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Importe users 1, 3, 4 et leurs profils dans une base neuve.")
    parser.add_argument("--source", required=True, help="ancienne base SQLite (ouverte en lecture seule)")
    parser.add_argument("--cible", required=True, help="nouvelle base : fichier SQLite ou URL SQLAlchemy")
    parser.add_argument("--dry-run", action="store_true", help="affiche ce qui serait importé sans rien écrire")
    args = parser.parse_args(argv)
    try:
        importer(args.source, args.cible, dry_run=args.dry_run)
    except Refus as e:
        print(f"REFUS : {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
