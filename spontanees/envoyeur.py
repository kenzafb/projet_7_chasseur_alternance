"""
envoyeur.py
===========
Depuis l'application (main.py) :
  from spontanees.envoyeur import main as env_main
  env_main(limite=10, test=True, stop_event=event, log_fn=log, user_id=user_id)

CLI (--user obligatoire) :
  python -m spontanees.envoyeur --user 1 --limite 10 --test

Compte d'envoi : uniquement celui de l'utilisateur qui lance le pipeline
(table comptes_envoi), configuré ET vérifié, sinon rien ne part. Aucun
compte commun dans le .env.

Garde-fous :
  - limite par lancement (paramètre limite) ;
  - plafond par utilisateur et par jour (PLAFOND_ENVOIS_JOUR), tous
    lancements et mails de test confondus : arrêt propre en l'atteignant ;
  - identifiants refusés ou serveur injoignable : arrêt immédiat
    (EnvoiInterrompu), sans essayer les entreprises suivantes.

Système de déduplication (par utilisateur et par mode, en base) :
  - Au démarrage : charge les adresses déjà contactées par CET utilisateur
    dans CE mode (table emails_contactes) + les destinataires enregistrés
    sur ses entreprises du même mode (mail_destinataires). Une adresse
    contactée pour une alternance peut l'être pour un job, pas deux fois
    pour une alternance
  - À chaque envoi réussi : enregistre les destinataires immédiatement
  - L'ancien fichier global data/emails_deja_envoyes.json n'est plus lu
  - Si une entreprise a 2 emails et qu'un seul a déjà été contacté,
    le mail est envoyé uniquement à l'autre
"""

import time
import random
import argparse
from database.dates import maintenant_utc
from shared import config, smtp
from shared.config import chemin_piece_jointe
from shared.chiffrement import ChiffrementIndisponible
from shared.compte_envoi import exiger_compte_verifie
from shared.erreurs import ErreurUtilisateur
from database.compte_envoi_db import liberer_envoi, marquer_verification, reserver_envoi
from database.dedup_db import ajouter_emails_contactes, lire_emails_contactes, normaliser_email

SUJET_FIXE        = "Candidature spontanée en alternance"
LIMITE_PAR_RUN    = config.LIMITE_ENVOIS_PAR_LANCEMENT
PAUSE_ENTRE_MAILS = (30, 90)
SAUVEGARDE_TOUS   = 10

MAIL_TEMPLATE = """\
Bonjour,

Je me permets de vous adresser une candidature spontanée en alternance à partir de la rentrée 2026.

Actuellement en formation, je recherche une entreprise où mettre en pratique mes compétences et m'investir sur la durée. Mon parcours et ma motivation m'amènent à vouloir contribuer concrètement au sein de votre équipe.

Vous trouverez mon CV en pièce jointe. Je reste à votre disposition pour tout échange.

Cordialement,
"""


# ─── Chargement / sauvegarde des entreprises (base) ───────────────────────────

from database.entreprises_db import lire_entreprises, sauvegarder_entreprises

# Utilisateur pour lequel l'envoyeur travaille : passé par l'appelant
# (user_id de la session côté web, --user obligatoire en CLI).
def charger_json(user_id):
    """Lit les entreprises de l'utilisateur depuis la BASE."""
    return lire_entreprises(user_id)


def sauvegarder_json(user_id, data):
    """Réécrit les modifications (mail_envoye, etc.) en BASE pour l'utilisateur."""
    sauvegarder_entreprises(user_id, data)


# ─── Envoi mail ───────────────────────────────────────────────────────────────

class EnvoiInterrompu(Exception):
    """Arrêt du pipeline sur un problème de compte (identifiants refusés,
    serveur injoignable) : message sûr, sans mot de passe."""


def charger_pieces_jointes(pieces_jointes, log_fn=print) -> list[tuple[str, bytes]]:
    """Pièces jointes du profil lues une fois : [(nom affiché, octets)]."""
    pieces = []
    for pj in (pieces_jointes or []):
        chemin = chemin_piece_jointe(pj.get("fichier", ""))
        if not chemin or not chemin.is_file():
            log_fn(f"    [!] Pièce '{pj.get('nom','?')}' introuvable — ignorée")
            continue
        base = (pj.get("nom", "document") or "document").strip().replace(" ", "_")
        nom_affiche = base if base.lower().endswith(".pdf") else base + ".pdf"
        pieces.append((nom_affiche, chemin.read_bytes()))
    return pieces


def envoyer_mail(compte: dict, destinataires: list[str], objet: str, corps: str, pieces=()):
    """Envoie un mail avec le compte de l'utilisateur. Lève smtp.ErreurSmtp."""
    message = smtp.construire_message(compte, destinataires, objet, corps, pieces)
    smtp.envoyer_message(compte, message, destinataires)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(user_id, limite=LIMITE_PAR_RUN, test=False, stop_event=None, log_fn=None, on_progress=None, mode="alternance"):
    """Envoie les candidatures spontanées de l'utilisateur avec SON compte.
    Retourne {"envoyes", "echecs", "arret"} ; arret vaut None (file vidée),
    "limite", "plafond" ou "stop". Lève EnvoiInterrompu sur un problème
    de compte, ErreurUtilisateur ou ChiffrementIndisponible avant tout envoi."""
    _log = log_fn or print
    plafond = config.PLAFOND_ENVOIS_JOUR

    _log(f"Envoyeur | mode={mode} | limite={limite} | plafond du jour={plafond} | test={test}")

    # Compte d'envoi de CET utilisateur, configuré et vérifié (sinon : erreur)
    compte = exiger_compte_verifie(user_id)
    _log(f"Compte d'envoi : {compte['adresse']}")

    # Profil de l'utilisateur : son mail type (fallback sur MAIL_TEMPLATE)
    from database.profil_db import lire_profil
    _profil = lire_profil(user_id, mode=mode)
    corps_mail = (_profil.get("email_type") or "").strip() or MAIL_TEMPLATE
    objet_mail = SUJET_FIXE
    pieces = charger_pieces_jointes(_profil.get("pieces_jointes", []), log_fn=_log)

    bilan = {"envoyes": 0, "echecs": 0, "arret": None}

    entreprises = charger_json(user_id)

    # ── Déduplication : adresses contactées + champ mail_destinataires ───────
    emails_deja_envoyes = lire_emails_contactes(user_id, mode)
    nb_contactes = len(emails_deja_envoyes)

    # Ajoute aussi les destinataires enregistrés sur les entreprises du mode (au cas où)
    for e in entreprises:
        if e.get("mode") == mode and e.get("mail_envoye") and e.get("mail_destinataires"):
            for addr in e["mail_destinataires"]:
                emails_deja_envoyes.add(normaliser_email(addr))

    _log(f"Déduplication : {nb_contactes} adresses déjà contactées + "
         f"{len(emails_deja_envoyes) - nb_contactes} depuis les entreprises "
         f"= {len(emails_deja_envoyes)} total")

    # ── Queue ─────────────────────────────────────────────────────────────────
    a_envoyer = [
        e for e in entreprises
        if e.get("emails_trouves") and not e.get("mail_envoye")
    ]

    deja_envoyes = sum(1 for e in entreprises if e.get("mail_envoye"))
    _log(f"Queue : {len(a_envoyer)} à envoyer | {deja_envoyes} déjà envoyés")

    if not a_envoyer:
        _log("✅ Rien à envoyer.")
        return bilan

    envoyes = 0
    echecs  = 0
    traites = 0

    def bilan_final(arret):
        bilan.update(envoyes=envoyes, echecs=echecs, arret=arret)
        return bilan

    for e in entreprises:
        if stop_event and stop_event.is_set():
            _log("⏹️  Arrêt — sauvegarde en cours...")
            sauvegarder_json(user_id, entreprises)
            return bilan_final("stop")

        if envoyes >= limite:
            _log(f"⏹️  Limite de {limite} mails atteinte.")
            bilan["arret"] = "limite"
            break

        if not e.get("emails_trouves") or e.get("mail_envoye"):
            continue

        nom = (e.get("nom_commercial") or e.get("nom", "?"))[:50]

        # ── Déduplication : ne garder que les emails pas encore contactés ─────
        emails_bruts = e.get("emails_trouves", [])
        emails_uniques = list(dict.fromkeys(
            normaliser_email(addr) for addr in emails_bruts
            if addr and addr.strip()
        ))
        emails_nouveaux = [
            addr for addr in emails_uniques
            if addr not in emails_deja_envoyes
        ]

        if not emails_nouveaux:
            _log(f"  ⏭️  {nom} — tous les emails déjà contactés, skip")
            # Marquer quand même comme traité pour ne plus y revenir
            e["mail_envoye"]        = True
            e["mail_envoye_le"]     = maintenant_utc()
            e["mail_destinataires"] = []
            e["mail_note"]          = "skip — tous emails déjà contactés"
            continue

        nb_ignores = len(emails_uniques) - len(emails_nouveaux)
        if nb_ignores > 0:
            _log(f"  ℹ️  {nb_ignores} email(s) ignoré(s) (déjà contactés)")

        destinataires = [compte["adresse"]] if test else emails_nouveaux

        # Plafond quotidien : réservé avant l'envoi, rendu si le mail ne part pas
        jour = reserver_envoi(user_id, plafond)
        if jour is None:
            _log(f"⏹️  Plafond de {plafond} mails par jour atteint : arrêt, "
                 "les envois reprendront demain.")
            bilan["arret"] = "plafond"
            break

        idx   = deja_envoyes + traites + 1
        total = deja_envoyes + len(a_envoyer)
        _log(f"[{idx}/{total}] {nom} → {', '.join(destinataires)}")

        try:
            envoyer_mail(compte, destinataires, objet_mail, corps_mail, pieces)
            ok = True
        except smtp.ErreurSmtp as erreur:
            liberer_envoi(user_id, jour)
            if erreur.categorie != smtp.MESSAGE:
                # Problème de compte ou de serveur : inutile d'essayer les suivantes
                if erreur.categorie == smtp.AUTH:
                    marquer_verification(user_id, False)
                sauvegarder_json(user_id, entreprises)
                bilan_final("erreur")
                conseil = (" Vérifie le compte d'envoi dans ton profil, puis relance "
                           "« Tester la connexion »." if erreur.categorie == smtp.AUTH else "")
                _log(f"⏹️  Envoi arrêté après {envoyes} mail(s) : problème de compte ou de serveur.")
                raise EnvoiInterrompu(f"{erreur}{conseil}") from None
            _log(f"    [❌] {erreur}")
            ok = False

        if ok:
            _log(f"  ✅ Envoyé à {len(destinataires)} adresse(s)")
            if not test:
                e["mail_envoye"]        = True
                e["mail_envoye_le"]     = maintenant_utc()
                e["mail_destinataires"] = destinataires

                # Mise à jour immédiate de la déduplication (en base)
                ajouter_emails_contactes(user_id, mode, destinataires)
                for addr in destinataires:
                    emails_deja_envoyes.add(addr)

            envoyes += 1
            _total_envoi = min(len(a_envoyer), limite)
            if on_progress and _total_envoi:
                _pct = round(envoyes / _total_envoi * 100)
                on_progress(min(_pct, 100), f"{envoyes}/{_total_envoi} mails envoyés")
        else:
            _log(f"  ❌ Échec envoi")
            echecs += 1

        traites += 1

        if traites % SAUVEGARDE_TOUS == 0:
            sauvegarder_json(user_id, entreprises)
            avec = sum(1 for x in entreprises if x.get("emails_trouves"))
            _log(f"  💾 Sauvegarde — {envoyes} envoyés, {echecs} échecs")

        if envoyes < limite and traites < len(a_envoyer):
            if not (stop_event and stop_event.is_set()):
                pause = random.uniform(*PAUSE_ENTRE_MAILS)
                _log(f"  ⏸️  Pause {pause:.0f}s...")
                time.sleep(pause)

    sauvegarder_json(user_id, entreprises)
    _log(f"✅ Envoi terminé — {envoyes} envoyés, {echecs} échecs")
    _log(f"   Emails dans la base de dédup : {len(emails_deja_envoyes)}")
    return bilan_final(bilan["arret"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limite", type=int, default=LIMITE_PAR_RUN)
    parser.add_argument("--test",   action="store_true")
    parser.add_argument("--user",   type=int, required=True,
                        help="ID de l'utilisateur pour lequel envoyer")
    args = parser.parse_args()
    try:
        main(limite=args.limite, test=args.test, user_id=args.user)
    except (ErreurUtilisateur, ChiffrementIndisponible, EnvoiInterrompu) as e:
        raise SystemExit(f"❌ {e}")
