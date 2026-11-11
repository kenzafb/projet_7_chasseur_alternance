"""
scripts/reinitialiser_mot_de_passe.py
=====================================
Mot de passe oublié, version locale (D123). Lancé par l'administratrice,
sur la base de DATABASE_URL :

    venv/bin/python scripts/reinitialiser_mot_de_passe.py prenom@exemple.fr

Génère un mot de passe temporaire aléatoire, l'enregistre (haché), et
l'affiche une seule fois à l'écran, pour le transmettre à la personne.
À la connexion suivante, elle doit le changer avant tout le reste. Toutes
ses sessions ouvertes sont fermées (le mot de passe change, D122).

Rien n'est écrit ailleurs qu'en base, et seulement le hash : ni journal,
ni fichier. Le mot de passe temporaire ne se retrouve plus après : en cas
de perte, relancer le script. Demande une confirmation (--oui pour s'en
passer). Codes de sortie : 0 fait, 1 compte introuvable ou abandon.
"""

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth.securite import hacher_mot_de_passe  # noqa: E402
from database.connexion import SessionLocal  # noqa: E402
from database.models import User  # noqa: E402

# Sans caractères ambigus (0/O, 1/l/I) : il est dicté ou recopié à la main
ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
GROUPES, TAILLE_GROUPE = 4, 4   # 16 caractères tirés, environ 92 bits


def mot_de_passe_temporaire() -> str:
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(TAILLE_GROUPE)) for _ in range(GROUPES))


def reinitialiser(email: str) -> str | None:
    """Nouveau mot de passe temporaire du compte, None si l'email est inconnu."""
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email.strip().lower()).first()
        if not user:
            return None
        temporaire = mot_de_passe_temporaire()
        user.mot_de_passe_hash = hacher_mot_de_passe(temporaire)
        user.mot_de_passe_temporaire = True
        db.commit()
        return temporaire
    finally:
        db.close()


def main(argv=None, entree=input, afficher=print) -> int:
    parser = argparse.ArgumentParser(description="Donne un mot de passe temporaire à un compte.")
    parser.add_argument("email", help="email de connexion du compte")
    parser.add_argument("--oui", action="store_true", help="sans demander de confirmation")
    args = parser.parse_args(argv)
    email = args.email.strip().lower()
    if not args.oui and entree(f"Réinitialiser le mot de passe de {email} ? Ses sessions seront fermées. (o/N) ") \
            .strip().lower() not in ("o", "oui"):
        afficher("Abandon : rien n'a changé.")
        return 1
    temporaire = reinitialiser(email)
    if temporaire is None:
        afficher(f"Aucun compte avec l'email {email}.")
        return 1
    afficher(f"Mot de passe temporaire de {email} (affiché une seule fois, à transmettre) :")
    afficher(f"    {temporaire}")
    afficher("Il devra être changé à la prochaine connexion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
