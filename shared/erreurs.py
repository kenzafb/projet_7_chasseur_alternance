"""
shared/erreurs.py
=================
Erreurs dues aux données de l'utilisateur (profil incomplet, lettre type
invalide...). Leur message est écrit pour être montré tel quel : main.py
les renvoie en 400 JSON {"erreur": message}.
"""

# Champs du profil sans lesquels on ne peut pas signer une lettre
CHAMPS_IDENTITE = ("prenom", "nom", "email")

LIBELLES_CHAMPS = {
    "prenom": "prénom",
    "nom": "nom",
    "email": "email",
}


class ErreurUtilisateur(Exception):
    """Erreur à afficher à l'utilisateur (réponse 400)."""


class ProfilIncomplet(ErreurUtilisateur):
    def __init__(self, champs=(), message=None):
        self.champs = list(champs)
        if message is None:
            libelles = ", ".join(LIBELLES_CHAMPS.get(c, c) for c in self.champs)
            message = f"Profil incomplet : renseigne {libelles} dans l'onglet Profil."
        super().__init__(message)


def exiger_profil(profil, champs=()):
    """
    Lève ProfilIncomplet si le profil est absent (None ou vide : aucun profil
    enregistré pour ce mode) ou si l'un des champs demandés est vide.
    """
    if not profil:
        raise ProfilIncomplet(message="Aucun profil pour ce mode : remplis d'abord l'onglet Profil.")
    manquants = [c for c in champs if not str(profil.get(c) or "").strip()]
    if manquants:
        raise ProfilIncomplet(manquants)
