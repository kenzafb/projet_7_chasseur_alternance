"""scripts/remettre_a_zero.py (D200) : n'efface que les données de recherche
de l'utilisateur demandé ; profil, compte d'envoi, anti-doublon et autres
utilisateurs intacts, lecture seule par défaut, refus si l'application tourne."""

import os
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select, text

from database.connexion import SessionLocal, engine
from database.dedup_db import lire_emails_contactes
from database.models import (Base, Campagne, Candidature, CompteEnvoi, CompteurEnvoi, EmailContacte, Entreprise,
                             EntrepriseMode, OffreVue, Profil)
from scripts import remettre_a_zero
from scripts.remettre_a_zero import Refus, application_lancee, main
from shared import config

MODES = ("alternance", "job", "stage")
EFFACEES = ("campagnes", "candidatures", "entreprises", "entreprises_modes", "offres_vues")


def remplir(user_id: int):
    """Un peu de tout, dans les trois modes, en base et sur le disque."""
    (config.UPLOADS_DIR / f"user_{user_id}").mkdir(parents=True)
    (config.UPLOADS_DIR / f"user_{user_id}" / "cv.pdf").write_bytes(b"cv")
    (config.LETTRES_PDF_DIR / f"user_{user_id}").mkdir(parents=True)
    (config.LETTRES_PDF_DIR / f"user_{user_id}" / "lettre_1.pdf").write_bytes(b"lettre")
    with SessionLocal() as db:
        presents = {p.mode: p for p in db.scalars(select(Profil).where(Profil.user_id == user_id))}
        for mode in MODES:
            p = presents.get(mode) or Profil(user_id=user_id, mode=mode)
            p.formation, p.lettre_type = f"Formation {mode}", "Ma lettre {paragraphe}"
            p.competences, p.reglages = ["Python"], {"limite": 3}
            p.recherche = {"permis": ["B"], "certifications": ["SSIAP 1"]}
            p.pieces_jointes = [{"nom": "CV", "fichier": f"user_{user_id}/cv.pdf"}]
            e = Entreprise(user_id=user_id, siren="123456789", emails_trouves=["rh@acme.fr"],
                           extra={"page_carrieres": "https://acme.fr/jobs", "site_verifie": {"verifie": True}})
            e.modes.append(EntrepriseMode(user_id=user_id, mode=mode, mail_envoye=True,
                                          mail_envoye_le=datetime(2026, 11, 1, tzinfo=timezone.utc),
                                          mail_destinataires=["rh@acme.fr"]))
            db.add_all([p, e, Campagne(user_id=user_id, debut=datetime(2026, 11, 1, tzinfo=timezone.utc)), OffreVue(user_id=user_id, mode=mode, ref_offre="r1"),
                        Candidature(user_id=user_id, mode=mode, ref_offre="r1", verdict="Bien", statut="archive",
                                    marques=["niveau_different"], lettre="Bonjour",
                                    lettre_pdf=f"user_{user_id}/lettre_1.pdf"),
                        EmailContacte(user_id=user_id, mode=mode, email="rh@acme.fr")])
        db.add(CompteEnvoi(user_id=user_id, adresse="a@b.fr", preset="gmail", serveur="smtp.gmail.com", port=465,
                           chiffrement="ssl", identifiant="a@b.fr", mot_de_passe_chiffre="x", mode_test=True))
        db.add(CompteurEnvoi(user_id=user_id, jour=date(2026, 11, 25), nombre=4))
        db.commit()


def photo(user_id=None, tables=None) -> dict:
    """{table: lignes}, d'un utilisateur ou de tous."""
    out = {}
    with SessionLocal() as db:
        for t in Base.metadata.sorted_tables:
            if tables and t.name not in tables:
                continue
            r = select(t).order_by(t.c.id)
            if user_id:
                r = r.where((t.c.id if t.name == "users" else t.c.user_id) == user_id)
            out[t.name] = [tuple(x) for x in db.execute(r)]
    return out


GARDEES = [t.name for t in Base.metadata.sorted_tables if t.name not in EFFACEES]


def fichiers(dossier):
    return sorted(str(f.relative_to(dossier)) for f in dossier.rglob("*") if f.is_file())


@pytest.fixture
def deux(utilisateur, monkeypatch):
    """Deux utilisateurs remplis ; application arrêtée."""
    _, a = utilisateur("a@test.fr")
    _, b = utilisateur("b@test.fr")
    remplir(a)
    remplir(b)
    monkeypatch.setattr(remettre_a_zero, "application_lancee", lambda *x, **k: [])
    return a, b


def test_autre_utilisateur_et_profil_intacts(deux):
    a, b = deux
    autre, gardees = photo(b), photo(a, GARDEES)
    assert all(autre.values()), "chaque table doit être remplie, sinon le test ne prouve rien"
    assert all(gardees.values())
    assert main(["--utilisateur", str(a), "--appliquer"]) == 0
    assert photo(b) == autre
    assert photo(a, GARDEES) == gardees
    assert photo(a, EFFACEES) == {t: [] for t in photo(a, EFFACEES)}
    assert fichiers(config.LETTRES_PDF_DIR) == [f"user_{b}/lettre_1.pdf"]
    assert fichiers(config.UPLOADS_DIR) == [f"user_{a}/cv.pdf", f"user_{b}/cv.pdf"]
    assert main(["--utilisateur", str(a), "--appliquer"]) == 0   # relancé : plus rien à effacer


def test_lecture_seule_par_defaut(deux, capsys):
    a, _ = deux
    avant, pdf = photo(), fichiers(config.LETTRES_PDF_DIR)
    assert main(["--utilisateur", str(a)]) == 0
    assert photo() == avant and fichiers(config.LETTRES_PDF_DIR) == pdf
    sortie = capsys.readouterr().out
    assert "candidatures (offres, analyses, lettres, suivi) : 3" in sortie
    assert "entreprises (communes aux modes) : 3 (dont 3 avec email, 3 avec site vérifié, 3 avec page carrières)" in sortie
    assert "emails déjà contactés : 3" in sortie and "mode essai activé" in sortie
    assert "Lecture seule : rien n'est effacé" in sortie
    for mode in MODES:
        assert f"    {mode:<11}     1 (dont 1 analysées, 1 archivées, 0 postulées, 1 avec lettre, 1 avec PDF)" in sortie


def test_utilisateur_obligatoire_et_existant(deux, capsys):
    avant = photo()
    for args in ([], ["--appliquer"]):
        with pytest.raises(SystemExit) as e:
            main(args)
        assert e.value.code == 2
    assert main(["--utilisateur", "999"]) == 1
    assert main(["--utilisateur", "999", "--appliquer"]) == 1
    assert "Aucun utilisateur 999" in capsys.readouterr().out
    assert photo() == avant


def test_anti_doublon_complete_avant_l_effacement(deux):
    """Une adresse connue seulement par l'entreprise reste bloquée après, dans son mode."""
    a, b = deux
    with SessionLocal() as db:
        m = db.scalars(select(EntrepriseMode).where(EntrepriseMode.user_id == a, EntrepriseMode.mode == "job")).one()
        m.mail_destinataires = ["rh@acme.fr", " Contact@Acme.fr "]
        db.commit()
    assert main(["--utilisateur", str(a), "--appliquer"]) == 0
    assert lire_emails_contactes(a, "job") == {"rh@acme.fr", "contact@acme.fr"}
    assert lire_emails_contactes(a, "stage") == {"rh@acme.fr"}
    assert lire_emails_contactes(b, "job") == {"rh@acme.fr"}


def test_refus_si_l_application_tourne(deux, monkeypatch, capsys):
    a, _ = deux
    avant = photo()
    monkeypatch.setattr(remettre_a_zero, "application_lancee", lambda *x, **k: ["processus 42 : uvicorn main:app"])
    assert main(["--utilisateur", str(a), "--appliquer"]) == 1
    assert "processus 42" in capsys.readouterr().out
    assert photo() == avant and len(fichiers(config.LETTRES_PDF_DIR)) == 2


def test_transaction_annulee_si_une_ligne_a_garder_change(deux, capsys):
    """Ligne croisée : l'effacement en cascade toucherait un autre utilisateur."""
    a, b = deux
    with SessionLocal() as db:
        e = db.scalars(select(Entreprise).where(Entreprise.user_id == a)).first()
        db.add(EntrepriseMode(user_id=b, entreprise_id=e.id, mode="autre"))
        db.commit()
    avant = photo()
    assert main(["--utilisateur", str(a), "--appliquer"]) == 1
    assert "entreprises_modes" in capsys.readouterr().out
    assert photo() == avant and len(fichiers(config.LETTRES_PDF_DIR)) == 2


def test_echec_en_cours_rien_d_efface(deux, monkeypatch):
    a, _ = deux
    with engine.begin() as cx:
        cx.execute(text("CREATE TRIGGER bloque BEFORE DELETE ON offres_vues BEGIN SELECT RAISE(ABORT, 'non'); END"))
    avant = photo()
    with pytest.raises(Exception, match="non"):
        main(["--utilisateur", str(a), "--appliquer"])
    assert photo() == avant and len(fichiers(config.LETTRES_PDF_DIR)) == 2


def test_fichiers_autres_que_pdf_et_dossiers_douteux(deux, monkeypatch, tmp_path):
    a, _ = deux
    dossier = config.LETTRES_PDF_DIR / f"user_{a}"
    (dossier / "notes.txt").write_text("garder")
    (dossier / "lien.pdf").symlink_to(config.UPLOADS_DIR / f"user_{a}" / "cv.pdf")
    avant = photo()
    with monkeypatch.context() as m:
        m.setattr(config, "LETTRES_PDF_DIR", config.UPLOADS_DIR)
        assert main(["--utilisateur", str(a), "--appliquer"]) == 1
    assert photo() == avant
    assert main(["--utilisateur", str(a), "--appliquer"]) == 0
    assert sorted(f.name for f in dossier.iterdir()) == ["lien.pdf", "notes.txt"]
    assert (config.UPLOADS_DIR / f"user_{a}" / "cv.pdf").read_bytes() == b"cv"


# ─── Détection de l'application, dans un faux /proc ───────────────────────────
def processus(proc, pid, args, cwd, ouverts=()):
    d = proc / str(pid)
    (d / "fd").mkdir(parents=True)
    (d / "cmdline").write_bytes("\0".join(args).encode() + b"\0")
    (d / "cwd").symlink_to(cwd)
    for i, f in enumerate(ouverts):
        (d / "fd" / str(i)).symlink_to(f)


@pytest.mark.parametrize("args, attendu", [
    (["venv/bin/python", "venv/bin/uvicorn", "main:app", "--port", "5002"], True),
    (["uvicorn", "main:app", "--reload"], True),
    (["python3", "main.py"], True),
    (["vim", "main.py"], False),
    (["bash", "-c", "echo main:app"], False),
])
def test_application_lancee_par_sa_commande(tmp_path, args, attendu):
    proc, projet, ailleurs = tmp_path / "proc", tmp_path / "projet", tmp_path / "ailleurs"
    for d in (proc / "self", projet, ailleurs):
        d.mkdir(parents=True)
    processus(proc, 10, args, projet)
    processus(proc, 11, args, ailleurs)   # le même programme d'un autre projet
    trouves = application_lancee(None, projet, proc)
    assert [t.split(" :")[0] for t in trouves] == (["processus 10"] if attendu else [])


def test_base_ouverte_par_un_autre_processus(tmp_path):
    proc, base = tmp_path / "proc", tmp_path / "b.db"
    (proc / "self").mkdir(parents=True)
    base.write_bytes(b"")
    processus(proc, 10, ["sqlitebrowser"], tmp_path, [base])
    processus(proc, os.getpid(), ["python", "main.py"], tmp_path, [base])   # soi-même : ignoré
    assert application_lancee(base, tmp_path, proc) == ["processus 10, base ouverte : sqlitebrowser"]


def test_sans_proc_refus(tmp_path):
    with pytest.raises(Refus, match="/proc absent"):
        application_lancee(None, tmp_path, tmp_path / "absent")
