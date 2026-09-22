"""
database/migration.py
=====================
Importe les données existantes (profil.py + JSON) dans la base SQLite.

SÉCURITÉ :
  - Lecture seule sur les fichiers d'origine (jamais modifiés).
  - Idempotent : relançable sans créer de doublons.
  - Mot de passe demandé dans le terminal (non affiché).

Lancement :
  python -m database.migration
"""

import json
import os
import getpass

from database.connexion import SessionLocal, creer_tables
from database.models import User, Profil, Candidature, Entreprise

# fastapi-users fournit le même hachage que celui utilisé au login
from fastapi_users.password import PasswordHelper

FICHIER_CANDIDATURES = "data/candidatures.json"
FICHIER_ENTREPRISES  = "data/entreprises_enrichies.json"

# Champs entreprises qu'on garde dans la colonne "extra" (non mappés en dur)
CHAMPS_EXTRA = [
    "siret", "code_naf", "adresse", "departement", "taille", "categorie",
    "ca", "dirigeant", "telephone", "url_scrapee", "source_recherche",
    "mail_destinataires", "mail_note", "nom",
]


def charger_profil_py():
    """Importe le dictionnaire PROFIL depuis shared/profil.py."""
    from shared.profil import PROFIL
    return PROFIL


def _contact_en_texte(valeur):
    """contact_rh peut être une chaîne, une liste de noms, ou un dict
    {prenom, nom, poste}. On normalise tout en une chaîne lisible."""
    if not valeur:
        return ""
    if isinstance(valeur, str):
        return valeur
    if isinstance(valeur, list):
        morceaux = []
        for v in valeur:
            if isinstance(v, dict):
                morceaux.append(" ".join(str(v.get(k, "")) for k in ("prenom", "nom") if v.get(k)).strip())
            else:
                morceaux.append(str(v))
        return ", ".join(m for m in morceaux if m)
    if isinstance(valeur, dict):
        nom = " ".join(str(valeur.get(k, "")) for k in ("prenom", "nom") if valeur.get(k)).strip()
        poste = valeur.get("poste", "")
        return f"{nom} ({poste})" if (nom and poste) else (nom or poste or "")
    return str(valeur)


def migrer():
    creer_tables()
    db = SessionLocal()

    try:
        # ── 1. Compte utilisateur Kenza ───────────────────────────────────────
        profil_py = charger_profil_py()
        email = profil_py.get("email", "kenza@chasseur.local")

        user = db.query(User).filter_by(email=email).first()
        if user:
            print(f"ℹ️  Compte {email} déjà existant (id={user.id}) — on réutilise.")
        else:
            print(f"Création du compte : {email}")
            mdp = getpass.getpass("  Choisis un mot de passe pour ce compte : ")
            mdp2 = getpass.getpass("  Confirme le mot de passe : ")
            if mdp != mdp2:
                print("❌ Les mots de passe ne correspondent pas. Migration annulée.")
                return
            if len(mdp) < 6:
                print("❌ Mot de passe trop court (min 6 caractères). Migration annulée.")
                return
            hash_mdp = PasswordHelper().hash(mdp)
            user = User(email=email, mot_de_passe_hash=hash_mdp)
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"✅ Compte créé (id={user.id})")

        # ── 2. Profil ─────────────────────────────────────────────────────────
        if db.query(Profil).filter_by(user_id=user.id).first():
            print("ℹ️  Profil déjà migré — on saute.")
        else:
            p = Profil(
                user_id          = user.id,
                prenom           = profil_py.get("prenom", ""),
                nom              = profil_py.get("nom", ""),
                email_contact    = profil_py.get("email", ""),
                telephone        = profil_py.get("telephone", ""),
                ville            = profil_py.get("ville", ""),
                linkedin         = profil_py.get("linkedin", ""),
                github           = profil_py.get("github", ""),
                formation        = profil_py.get("formation", ""),
                experience       = profil_py.get("experience", ""),
                langues          = profil_py.get("langues", ""),
                disponibilite    = profil_py.get("disponibilite", ""),
                paragraphe_perso = profil_py.get("paragraphe_perso", ""),
                competences      = profil_py.get("competences", []),
                projets          = profil_py.get("projets", []),
                recherche        = profil_py.get("recherche", {}),
            )
            db.add(p)
            db.commit()
            print("✅ Profil migré")

        # ── 3. Candidatures ───────────────────────────────────────────────────
        if os.path.exists(FICHIER_CANDIDATURES):
            with open(FICHIER_CANDIDATURES, encoding="utf-8") as f:
                candidatures = json.load(f)

            refs_existantes = {
                c.ref_offre for c in
                db.query(Candidature.ref_offre).filter_by(user_id=user.id).all()
            }
            ajoutees = 0
            for c in candidatures:
                ref = c.get("id", "")
                if ref and ref in refs_existantes:
                    continue
                db.add(Candidature(
                    user_id          = user.id,
                    ref_offre        = ref,
                    titre            = c.get("titre", ""),
                    entreprise       = c.get("entreprise", ""),
                    lieu             = c.get("lieu", ""),
                    zone             = c.get("zone", ""),
                    domaine          = c.get("domaine", ""),
                    lien             = c.get("lien", ""),
                    source           = c.get("source", ""),
                    description      = c.get("description", ""),
                    score            = int(c.get("score", 0) or 0),
                    verdict          = c.get("verdict", ""),
                    eligible         = bool(c.get("eligible", True)),
                    points_forts     = c.get("points_forts", []),
                    points_faibles   = c.get("points_faibles", []),
                    resume_analyse   = c.get("resume_analyse", ""),
                    lettre           = c.get("lettre", ""),
                    email_candidature= c.get("email_candidature", ""),
                    objet_email      = c.get("objet_email", ""),
                    statut           = c.get("statut", "nouveau"),
                    date_trouvee     = c.get("date_trouvee", ""),
                    date_candidature = c.get("date_candidature", ""),
                    notes            = c.get("notes", ""),
                ))
                ajoutees += 1
            db.commit()
            print(f"✅ Candidatures migrées : {ajoutees} ajoutées ({len(candidatures)} dans le fichier)")

        # ── 4. Entreprises ────────────────────────────────────────────────────
        if os.path.exists(FICHIER_ENTREPRISES):
            with open(FICHIER_ENTREPRISES, encoding="utf-8") as f:
                entreprises = json.load(f)

            sirens_existants = {
                e.siren for e in
                db.query(Entreprise.siren).filter_by(user_id=user.id).all()
            }
            ajoutees = 0
            for e in entreprises:
                siren = e.get("siren", "")
                if siren and siren in sirens_existants:
                    continue
                extra = {k: e[k] for k in CHAMPS_EXTRA if k in e}
                db.add(Entreprise(
                    user_id        = user.id,
                    nom_commercial = e.get("nom_commercial") or e.get("nom", ""),
                    ville          = e.get("ville", ""),
                    code_postal    = e.get("code_postal", ""),
                    siren          = siren,
                    site_web       = e.get("site_web", ""),
                    secteur        = e.get("code_naf", "") or e.get("categorie", ""),
                    emails_trouves = e.get("emails_trouves", []),
                    telephones     = e.get("telephones", []),
                    contact_rh     = _contact_en_texte(e.get("contact_rh")),
                    traite         = bool(e.get("traite", False)),
                    mail_envoye    = bool(e.get("mail_envoye", False)),
                    mail_envoye_le = e.get("mail_envoye_le", "") or "",
                    extra          = extra,
                ))
                ajoutees += 1
                if ajoutees % 1000 == 0:
                    db.commit()
                    print(f"   ... {ajoutees} entreprises insérées")
            db.commit()
            print(f"✅ Entreprises migrées : {ajoutees} ajoutées ({len(entreprises)} dans le fichier)")

        # ── Récap ─────────────────────────────────────────────────────────────
        print("\n── RÉCAP BASE ──")
        print("  Users        :", db.query(User).count())
        print("  Profils      :", db.query(Profil).count())
        print("  Candidatures :", db.query(Candidature).count())
        print("  Entreprises  :", db.query(Entreprise).count())

    finally:
        db.close()


if __name__ == "__main__":
    migrer()
