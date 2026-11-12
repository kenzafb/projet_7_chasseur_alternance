"""
routes/parametres.py
====================
Page Paramètres, commune aux trois modes (D122) : compte de connexion
(email, mot de passe) et compte d'envoi SMTP de l'utilisateur.
"""

from typing import Literal

from fastapi import Body, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from auth.securite import utilisateur_requis
from database import compte_envoi_db
from database.models import User
from routes.commun import routeur_prive
from shared import compte_envoi, config
from shared.chiffrement import raison_indisponible
from shared.erreurs import ErreurUtilisateur

router = routeur_prive()


class CompteEnvoiCorps(BaseModel):
    """Configuration du compte d'envoi. mot_de_passe : en écriture seule,
    absent ou vide = garder celui déjà enregistré."""
    model_config = ConfigDict(extra="forbid")
    preset: Literal["gmail", "autre"]
    adresse: str = Field(max_length=255)
    nom_affiche: str = Field("", max_length=150)
    serveur: str = Field("", max_length=255)
    port: int | None = None
    chiffrement: Literal["ssl", "starttls"] | None = None
    identifiant: str = Field("", max_length=255)
    mot_de_passe: SecretStr | None = None

class ModeTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actif: bool

class MailTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destinataire: str | None = Field(None, max_length=255)



# ─── Compte de connexion (page Paramètres, D122) ──────────────────────────────
# Communs aux trois modes : aucun paramètre « mode » n'est lu.
@router.get("/api/compte")
def api_compte(user: User = Depends(utilisateur_requis)):
    return {"email": user.email}


@router.post("/api/compte/mot_de_passe")
def api_compte_mot_de_passe(request: Request, body: dict = Body(...), user: User = Depends(utilisateur_requis)):
    from auth.compte import changer_mot_de_passe
    from auth.securite import ouvrir_session
    a_jour = changer_mot_de_passe(user.id, str(body.get("ancien") or ""), str(body.get("nouveau") or ""),
                                  str(body.get("confirmation") or ""))
    # Cette session reste ouverte (nouvelle empreinte) ; les autres sont fermées
    ouvrir_session(request, a_jour)
    return {"ok": True}


@router.post("/api/compte/email")
def api_compte_email(body: dict = Body(...), user: User = Depends(utilisateur_requis)):
    from auth.compte import changer_email
    return {"ok": True, "email": changer_email(user.id, str(body.get("email") or ""),
                                               str(body.get("mot_de_passe") or ""))}


# ─── Compte d'envoi (SMTP de l'utilisateur) ───────────────────────────────────
# Le mot de passe n'est jamais renvoyé : le front ne reçoit que
# mot_de_passe_configure et verifie_le.
@router.get("/api/compte_envoi")
def api_compte_envoi(user: User = Depends(utilisateur_requis)):
    raison = raison_indisponible()
    return {"disponible": raison is None, "raison": raison or "",
            "compte": compte_envoi_db.lire_compte(user.id),
            "plafond_jour": config.PLAFOND_ENVOIS_JOUR,
            "envois_du_jour": compte_envoi_db.envois_du_jour(user.id)}

@router.post("/api/compte_envoi")
def api_compte_envoi_enregistrer(body: CompteEnvoiCorps, user: User = Depends(utilisateur_requis)):
    compte_envoi.exiger_chiffrement()
    corps = body.model_dump(exclude={"mot_de_passe"})
    corps["mot_de_passe"] = body.mot_de_passe.get_secret_value() if body.mot_de_passe else None
    existe = compte_envoi_db.lire_compte(user.id) is not None
    champs, mot_de_passe = compte_envoi.preparer(corps, compte_existe=existe)
    return {"ok": True, "compte": compte_envoi_db.enregistrer_compte(user.id, champs, mot_de_passe)}

@router.post("/api/compte_envoi/supprimer")
def api_compte_envoi_supprimer(user: User = Depends(utilisateur_requis)):
    # Possible même sans clé de chiffrement : rien à déchiffrer
    return {"ok": compte_envoi_db.supprimer_compte(user.id)}

@router.post("/api/compte_envoi/tester")
def api_compte_envoi_tester(user: User = Depends(utilisateur_requis)):
    """Connexion + authentification puis déconnexion, aucun mail envoyé."""
    return compte_envoi.tester(user.id)

@router.post("/api/compte_envoi/mode_test")
def api_compte_envoi_mode_test(body: ModeTest, user: User = Depends(utilisateur_requis)):
    """Mode test : les candidatures spontanées partent vers l'adresse
    d'expédition de l'utilisateur, rien n'est enregistré comme contacté."""
    compte = compte_envoi_db.definir_mode_test(user.id, body.actif)
    if compte is None:
        raise ErreurUtilisateur("Configure d'abord ton compte d'envoi.")
    return {"ok": True, "compte": compte}

@router.post("/api/compte_envoi/mail_test")
def api_compte_envoi_mail_test(body: MailTest | None = None, user: User = Depends(utilisateur_requis)):
    """Mail de test, uniquement vers l'adresse d'expédition du compte."""
    return compte_envoi.envoyer_mail_test(user.id, body.destinataire if body else None)
