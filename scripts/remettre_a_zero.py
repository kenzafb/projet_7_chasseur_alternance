"""
scripts/remettre_a_zero.py
==========================
Remet à zéro les données de recherche d'UN utilisateur, dans ses trois
modes (D200), sans toucher aux autres utilisateurs.

Effacé : offres et analyses, lettres (candidatures), offres déjà vues
(offres_vues), entreprises et résultats du scraper (entreprises), leur
sélection, leurs envois et leur suivi (entreprises_modes), campagnes
automatiques (campagnes), lettres PDF de LETTRES_PDF_DIR/user_<id>/.

Gardé : compte, profils et réglages des trois modes, pièces jointes, compte
d'envoi (mode essai compris), compteurs d'envoi, adresses déjà contactées,
fichiers partagés de DATA_DIR. L'anti-doublon de l'envoi lit aussi les
destinataires enregistrés sur les entreprises (spontanees/envoi.py) : ceux
qui manquent à emails_contactes y sont recopiés avant l'effacement.

Par défaut, lecture seule (base ouverte en mode=ro) : ce qui serait effacé,
table par table et mode par mode, et ce qui est gardé. --appliquer refuse
de tourner si l'application est lancée, efface en une seule transaction
(annulée si une ligne à garder a changé), puis supprime les PDF. Sans retour
possible : copier la base avant.

    venv/bin/python scripts/remettre_a_zero.py --utilisateur 1
    venv/bin/python scripts/remettre_a_zero.py --utilisateur 1 --appliquer

Codes de sortie : 0 fait (ou lecture seule), 1 refus ou échec.
"""

import argparse
import hashlib
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import delete, or_, select, text

from database.dedup_db import normaliser_email
from database.models import (Base, Campagne, Candidature, CompteEnvoi, CompteurEnvoi, EmailContacte, Entreprise,
                             EntrepriseMode, OffreVue, Profil, User)
from shared import config
from shared.modes import MODES

# Dans l'ordre d'effacement : l'état par mode avant les entreprises
EFFACEES = (EntrepriseMode, Entreprise, Candidature, OffreVue, Campagne)


class Refus(Exception):
    """Rien n'a été effacé."""


# ─── Application lancée ? ─────────────────────────────────────────────────────
def _arguments(dossier: Path) -> list[str]:
    return [a for a in (dossier / "cmdline").read_bytes().decode(errors="replace").split("\0") if a]


def _lance_l_application(args: list[str]) -> bool:
    """uvicorn (ou gunicorn) main:app, ou python main.py."""
    return "main:app" in args or (bool(args) and "python" in Path(args[0]).name
                                  and any(Path(a).name == "main.py" for a in args[1:]))


def _ouvre(dossier: Path, base: Path) -> bool:
    try:
        return any(os.path.realpath(fd) == str(base) for fd in (dossier / "fd").iterdir())
    except OSError:   # processus d'un autre compte, ou terminé entre-temps
        return False


def application_lancee(base: Path | None, racine: Path = config.BASE_DIR,
                       proc: Path = Path("/proc")) -> list[str]:
    """Processus qui interdisent l'effacement : l'application lancée depuis
    ce projet, ou tout autre processus qui a la base ouverte. Refus si
    /proc ne permet pas de le savoir."""
    if not (proc / "self").exists():
        raise Refus("Impossible de vérifier que l'application est arrêtée (/proc absent).")
    trouves = []
    for dossier in sorted((d for d in proc.iterdir() if d.name.isdigit()), key=lambda d: int(d.name)):
        if int(dossier.name) == os.getpid():
            continue
        try:
            args = _arguments(dossier)
        except OSError:
            continue
        try:
            ici = Path(os.readlink(dossier / "cwd")).resolve() == racine.resolve()
        except OSError:
            ici = True   # dossier illisible : dans le doute, c'est l'application
        if _lance_l_application(args) and ici:
            trouves.append(f"processus {dossier.name} : {' '.join(args)[:100]}")
        elif base and _ouvre(dossier, base):
            trouves.append(f"processus {dossier.name}, base ouverte : {' '.join(args)[:100]}")
    return trouves


def fichier_base(url: str) -> Path | None:
    return Path(url.removeprefix("sqlite:///")).resolve() if url.startswith("sqlite:///") else None


# ─── Fichiers ─────────────────────────────────────────────────────────────────
def lettres_pdf(user_id: int) -> tuple[list[Path], list[Path]]:
    """(PDF à supprimer, autres fichiers laissés) de LETTRES_PDF_DIR/user_<id>/.
    Refus si ce dossier est un lien, ou s'il touche aux pièces jointes."""
    racine, uploads = config.LETTRES_PDF_DIR.resolve(), config.UPLOADS_DIR.resolve()
    if racine == uploads or racine.is_relative_to(uploads) or uploads.is_relative_to(racine):
        raise Refus("LETTRES_PDF_DIR et UPLOADS_DIR se recouvrent : les pièces jointes seraient en danger.")
    dossier = racine / f"user_{user_id}"
    if dossier.is_symlink():
        raise Refus(f"{dossier} est un lien : fichiers non supprimés.")
    fichiers = sorted(dossier.iterdir()) if dossier.is_dir() else []
    pdf = [f for f in fichiers if f.is_file() and not f.is_symlink() and f.suffix.lower() == ".pdf"]
    return pdf, [f for f in fichiers if f not in pdf]


# ─── Inventaire ───────────────────────────────────────────────────────────────
def _lignes(db, modele, user_id: int) -> list:
    return list(db.scalars(select(modele).where(modele.user_id == user_id).order_by(modele.id)))


def destinataires_a_garder(db, user_id: int) -> list[tuple[str, str, object]]:
    """[(mode, adresse, date)] : adresses que l'envoi connaît par les
    entreprises du mode et qui ne sont pas dans emails_contactes."""
    connues = {(c.mode, normaliser_email(c.email)) for c in _lignes(db, EmailContacte, user_id)}
    manquantes = {}
    for m in _lignes(db, EntrepriseMode, user_id):
        for a in (m.mail_destinataires or []) if m.mail_envoye else []:
            cle = (m.mode, normaliser_email(a))
            if cle[1] and cle not in connues:
                manquantes.setdefault(cle, m.mail_envoye_le)
    return [(mode, adresse, date) for (mode, adresse), date in sorted(manquantes.items(), key=lambda x: x[0])]


def _par_mode(lignes, afficher, details=None):
    presents = Counter(x.mode for x in lignes)
    for mode in [*MODES, *sorted(set(presents) - set(MODES))]:
        suite = details([x for x in lignes if x.mode == mode]) if details and presents[mode] else ""
        afficher(f"    {mode:<11} {presents[mode]:>5}{suite}")


def _details_offres(lignes) -> str:
    compte = {"analysées": sum(1 for c in lignes if c.verdict and c.verdict != "non_analysee"),
              "archivées": sum(1 for c in lignes if c.statut == "archive"),
              "postulées": sum(1 for c in lignes if c.date_candidature),
              "avec lettre": sum(1 for c in lignes if c.lettre),
              "avec PDF": sum(1 for c in lignes if c.lettre_pdf)}
    return " (dont " + ", ".join(f"{n} {nom}" for nom, n in compte.items()) + ")"


def _details_modes(lignes) -> str:
    from database.entreprises_db import NOTE_LBA
    sans_adresse = sum(1 for m in lignes if m.mail_envoye and m.mail_note == NOTE_LBA)
    return (f" (dont {sum(1 for m in lignes if m.mail_envoye)} contactées"
            + (f", dont {sans_adresse} par le formulaire LBA, sans adresse : plus aucune trace ensuite"
               if sans_adresse else "") + ")")


def inventaire(db, user_id: int, afficher=print):
    """Affiche ce qui est effacé et ce qui est gardé. Refus si l'utilisateur n'existe pas."""
    user = db.get(User, user_id)
    if user is None:
        raise Refus(f"Aucun utilisateur {user_id}.")
    pdf, autres = lettres_pdf(user_id)
    afficher(f"Utilisateur {user_id} ({user.email}), tous modes")
    afficher("── Effacé ──")
    lignes = _lignes(db, Candidature, user_id)
    afficher(f"  candidatures (offres, analyses, lettres, suivi) : {len(lignes)}")
    _par_mode(lignes, afficher, _details_offres)
    lignes = _lignes(db, OffreVue, user_id)
    afficher(f"  offres_vues (offres déjà proposées) : {len(lignes)}")
    _par_mode(lignes, afficher)
    lignes = _lignes(db, EntrepriseMode, user_id)
    afficher(f"  entreprises_modes (sélection, envoi, suivi) : {len(lignes)}")
    _par_mode(lignes, afficher, _details_modes)
    lignes = _lignes(db, Entreprise, user_id)
    extras = [e.extra or {} for e in lignes]
    afficher(f"  entreprises (communes aux modes) : {len(lignes)} (dont {sum(1 for e in lignes if e.emails_trouves)} "
             f"avec email, {sum(1 for x in extras if (x.get('site_verifie') or {}).get('verifie'))} avec site vérifié, "
             f"{sum(1 for x in extras if x.get('page_carrieres'))} avec page carrières)")
    afficher(f"  lettres PDF de {config.LETTRES_PDF_DIR / f'user_{user_id}'} : {len(pdf)} fichier(s)")
    afficher("── Gardé ──")
    profils = {p.mode: p for p in _lignes(db, Profil, user_id)}
    afficher(f"  profils et réglages : {len(profils)}")
    for mode, p in profils.items():
        afficher(f"    {mode:<11} {len(p.pieces_jointes or [])} pièce(s) jointe(s)")
    dossier = config.UPLOADS_DIR / f"user_{user_id}"
    afficher(f"  fichiers de {dossier} : {sum(1 for f in dossier.rglob('*') if f.is_file()) if dossier.is_dir() else 0}")
    compte = db.scalar(select(CompteEnvoi).where(CompteEnvoi.user_id == user_id))
    afficher("  compte d'envoi : " + (f"1, mode essai {'activé' if compte.mode_test else 'coupé'}" if compte else "aucun"))
    afficher(f"  compteurs d'envoi : {len(_lignes(db, CompteurEnvoi, user_id))} jour(s)")
    lignes = _lignes(db, EmailContacte, user_id)
    afficher(f"  emails déjà contactés : {len(lignes)}")
    _par_mode(lignes, afficher)
    ajouts = destinataires_a_garder(db, user_id)
    afficher(f"    connus seulement par les entreprises, recopiés ici avant l'effacement : {len(ajouts)}")
    for f in autres:
        afficher(f"  laissé : {f}")
    partages = sorted(f.name for f in config.DATA_DIR.glob("lba_*")) if config.DATA_DIR.is_dir() else []
    afficher(f"  fichiers partagés de {config.DATA_DIR} : {', '.join(partages) or 'aucun'}")
    for modele in EFFACEES:
        n = len(list(db.scalars(select(modele.id).where(modele.user_id != user_id))))
        afficher(f"  {modele.__tablename__} des autres utilisateurs : {n}")


# ─── Effacement ───────────────────────────────────────────────────────────────
def empreinte_gardee(db, user_id: int) -> dict[str, str]:
    """{table: empreinte} de toutes les lignes qui doivent rester telles
    quelles : tables gardées entières, et lignes des autres utilisateurs."""
    effacees = {m.__tablename__ for m in EFFACEES}
    out = {}
    for table in Base.metadata.sorted_tables:
        requete = select(table).order_by(table.c.id)
        if table.name in effacees:
            requete = requete.where(or_(table.c.user_id != user_id, table.c.user_id.is_(None)))
        h = hashlib.sha256()
        for ligne in db.execute(requete):
            h.update(repr(tuple(ligne)).encode())
        out[table.name] = h.hexdigest()
    return out


def effacer(db, user_id: int) -> dict[str, int]:
    """Efface dans la transaction de db, sans la valider : {table: lignes}."""
    for mode, adresse, date in destinataires_a_garder(db, user_id):
        db.add(EmailContacte(user_id=user_id, mode=mode, email=adresse, contacte_le=date))
    db.flush()
    avant = empreinte_gardee(db, user_id)
    bilan = {m.__tablename__: db.execute(delete(m).where(m.user_id == user_id)
                                         .execution_options(synchronize_session=False)).rowcount
             for m in EFFACEES}
    apres = empreinte_gardee(db, user_id)
    changees = [t for t in avant if avant[t] != apres[t]]
    if changees:
        raise Refus(f"Des lignes à garder changeraient ({', '.join(changees)}) : transaction annulée.")
    return bilan


def appliquer(user_id: int, afficher=print) -> int:
    lances = application_lancee(fichier_base(config.DATABASE_URL))
    if lances:
        raise Refus("L'application est lancée ou la base est ouverte, rien n'est effacé :\n  " + "\n  ".join(lances))
    from database.connexion import SessionLocal
    with SessionLocal() as db:
        if db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))   # aucune écriture d'un autre processus jusqu'à la fin
        inventaire(db, user_id, afficher)
        pdf, _ = lettres_pdf(user_id)
        db.expire_all()
        bilan = effacer(db, user_id)
        db.commit()
    afficher("── Fait ──")
    for table, n in bilan.items():
        afficher(f"  {table} : {n} ligne(s) effacée(s)")
    echecs = 0
    for f in pdf:
        try:
            f.unlink()
        except OSError as e:
            echecs += 1
            afficher(f"  PDF non supprimé : {f} ({e.strerror})")
    afficher(f"  {len(pdf) - echecs} PDF supprimé(s)")
    if echecs:
        afficher("Base à jour ; relancer la même commande pour les PDF restants.")
    return 1 if echecs else 0


def main(argv=None, afficher=print) -> int:
    ap = argparse.ArgumentParser(description="Remet à zéro les données de recherche d'un utilisateur.")
    ap.add_argument("--utilisateur", type=int, required=True, help="id de l'utilisateur (obligatoire)")
    ap.add_argument("--appliquer", action="store_true", help="effacer (sinon : lecture seule)")
    args = ap.parse_args(argv)
    try:
        if args.appliquer:
            return appliquer(args.utilisateur, afficher)
        from audit_commun import session_lecture
        with session_lecture() as db:
            inventaire(db, args.utilisateur, afficher)
        afficher("Lecture seule : rien n'est effacé (ajouter --appliquer).")
        return 0
    except Refus as e:
        afficher(f"Refusé : {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
