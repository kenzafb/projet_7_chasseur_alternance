"""
spontanees/campagne.py
======================
Campagne automatique d'entreprises à contacter (D213), lancée par
scripts/campagne.py. Pour chaque mode, dans l'ordre :

  1. préparation : recherche des emails par petits lots jusqu'à la cible ;
     file vide : nouvelle recherche d'entreprises ; garde-fous (durée, nombre
     d'entreprises, panne de la recherche web) ;
  2. validation : CAMPAGNE_VALIDATION=telegram, la liste part sur Telegram et
     rien n'est envoyé sans « Envoyer » avant l'heure limite ; auto, l'envoi
     suit la préparation ;
  3. envoi : spontanees.envoi.main, le même que l'interface, restreint à la
     liste (entreprises ET adresses) montrée.

Connexion à internet (D218, D219, shared/reseau.py) : attendue au
démarrage, et dès qu'une recherche, un envoi ou un message échoue faute de
connexion : pause, essai toutes les 30 s, jusqu'à CAMPAGNE_HEURE_BUTOIR ;
revenue avant, la campagne part ou reprend là où elle en était, message
Telegram à l'appui. Sinon : arrêt propre, et message Telegram dès son retour.

Tous les modes sont préparés avant d'attendre les réponses : attendre le
premier bloquerait le suivant. Verrous : la campagne (une seule à la fois) et
« spontanees » de l'utilisateur, partagé avec l'interface et tenu seulement
pendant une recherche ou un envoi, pas pendant l'attente d'une réponse.
"""

import os
import queue
import secrets
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from database import campagnes_db
from database.compte_envoi_db import envois_du_jour
from database.dates import maintenant_affichage
from database.entreprises_db import compter_a_scraper, lire_entreprises
from database.profil_db import lire_profil
from shared import config, extinction
from shared.chiffrement import ChiffrementIndisponible
from shared.erreurs import ErreurUtilisateur
from shared.journal import journaliser
from shared.modes import get_mode
from shared.pipelines import SPONTANEES
from shared.reseau import ESSAI_S, HEURE_BUTOIR, Reseau
from shared.telegram import Clic, ErreurTelegram, Telegram
from shared.verrous import CAMPAGNE, Verrou, nom_pipeline, occupes
from spontanees import envoi, recherche_emails, recuperation

LOT = 5                          # entreprises par lot de recherche d'emails
NOUVELLES_ENTREPRISES = 100      # par nouvelle recherche Sirene, LBA
PAUSE_ENVOIS = (120, 300)        # secondes entre deux mails
ATTENTE_INTERFACE_S = 15 * 60    # l'interface tient le verrou : attente au plus
ATTENTE_TELEGRAM_S = 25          # interrogation longue
DELAI_EXTINCTION_S = 120
REPRISE_ECOUTE_S = 5             # Telegram injoignable : avant de réessayer
RETOUR_MAX_S = 12 * 3600       # arrêt faute de connexion : message au retour, attendu au plus
AVANT_PROCHAINE_S = 10 * 60    # ... et fini avant la prochaine campagne, que le minuteur lance
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
VALIDATIONS = ("telegram", "auto")
FINS = ("demander", "eteindre", "veille", "rien")
LIBELLES_FIN = {extinction.ETEINDRE: "Extinction", extinction.VEILLE: "Mise en veille"}


class CampagneEnCours(Exception):
    """Une autre campagne tient le verrou."""


# ─── Réglages ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Reglages:
    cible: int = 30
    validation: str = "telegram"
    heure_limite: str = "16:00"
    duree_max_min: int = 120
    max_entreprises: int = 200
    fin: str = "demander"
    fin_attente_min: int = 60
    heure_butoir: str = HEURE_BUTOIR

    def verifier(self) -> "Reglages":
        if self.validation not in VALIDATIONS:
            raise ErreurUtilisateur(f"CAMPAGNE_VALIDATION : {' ou '.join(VALIDATIONS)}, pas « {self.validation} ».")
        if self.fin not in FINS:
            raise ErreurUtilisateur(f"CAMPAGNE_FIN : {', '.join(FINS)}, pas « {self.fin} ».")
        for variable, heure, exemple in (("CAMPAGNE_HEURE_LIMITE", self.heure_limite, "16:00"),
                                         ("CAMPAGNE_HEURE_BUTOIR", self.heure_butoir, "13:00")):
            try:
                datetime.strptime(heure, "%H:%M")
            except ValueError:
                raise ErreurUtilisateur(f"{variable} : une heure comme {exemple}.") from None
        if min(self.cible, self.duree_max_min, self.max_entreprises) < 1 or self.fin_attente_min < 0:
            raise ErreurUtilisateur("Réglages de la campagne : des nombres positifs sont attendus.")
        return self


_VARIABLES = {"validation": "CAMPAGNE_VALIDATION", "heure_limite": "CAMPAGNE_HEURE_LIMITE",
              "duree_max_min": "CAMPAGNE_DUREE_MAX_MIN", "max_entreprises": "CAMPAGNE_MAX_ENTREPRISES",
              "fin": "CAMPAGNE_FIN", "fin_attente_min": "CAMPAGNE_FIN_ATTENTE_MIN",
              "heure_butoir": "CAMPAGNE_HEURE_BUTOIR"}


def reglages_env(cible: int = 30) -> Reglages:
    """Réglages des variables CAMPAGNE_* (vides : défauts). Une valeur
    illisible arrête tout : mieux vaut ne rien lancer."""
    r = Reglages(cible=cible)
    for champ, variable in _VARIABLES.items():
        texte = os.getenv(variable, "").strip()
        if not texte:
            continue
        if isinstance(getattr(r, champ), int):
            try:
                valeur = int(texte)
            except ValueError:
                raise ErreurUtilisateur(f"{variable} : un nombre entier est attendu, pas « {texte} ».") from None
        else:
            valeur = texte if champ.startswith("heure_") else texte.lower()
        r = replace(r, **{champ: valeur})
    return r.verifier()


class Horloge:
    """Le temps de la campagne (remplacé dans les tests)."""

    def maintenant(self) -> datetime:
        return maintenant_affichage()

    def dormir(self, secondes: float):
        time.sleep(secondes)


@dataclass
class Attente:
    """Liste prête d'un mode, en attente de « Envoyer »."""
    mode: str
    liste: list[dict]
    test: bool
    jeton: str = field(default_factory=lambda: secrets.token_hex(6))
    message_id: int = 0

    @property
    def annonce(self) -> str:
        """Où partiront les mails, à côté de chaque bouton « Envoyer »."""
        return ("🧪 MODE ESSAI : les mails arriveront chez toi" if self.test
                else "🔴 ENVOI RÉEL aux entreprises")


class _ArretRecherche:
    """stop_event d'une recherche : arrêt demandé, durée écoulée, ou recherche
    web en panne (D187). Regardé entre deux entreprises."""

    def __init__(self, campagne: "Campagne", fin: datetime):
        self.campagne, self.fin = campagne, fin

    def raison(self) -> str:
        if self.campagne.hors_ligne:
            return "pas d'accès internet"
        if self.campagne.arret:
            return "arrêt demandé"
        if self.campagne.horloge.maintenant() >= self.fin:
            return f"durée maximale atteinte ({self.campagne.reglages.duree_max_min} min)"
        if recherche_emails.recherche_arretee:
            return "recherche web en panne"
        return ""

    def is_set(self) -> bool:
        return bool(self.raison())


class _ArretEnvoi:
    """stop_event d'un envoi : sa pause relève les clics Telegram."""

    def __init__(self, campagne: "Campagne"):
        self.campagne = campagne

    def is_set(self) -> bool:
        return self.campagne.arret

    def wait(self, secondes: float) -> bool:
        self.campagne.patienter(secondes)
        return self.is_set()


class _Ecoute(threading.Thread):
    """Lit les clics et y répond dès leur réception, quoi que fasse la campagne
    (recherche d'emails, envoi, pause) : Telegram refuse une réponse tardive.
    Les actions restent à la boucle principale."""

    def __init__(self, campagne: "Campagne"):
        super().__init__(name="ecoute-telegram", daemon=True)
        self.campagne, self.fin = campagne, threading.Event()

    def run(self):
        en_panne = False
        while not self.fin.is_set():
            try:
                self.campagne.recevoir(ATTENTE_TELEGRAM_S)
                en_panne = False
            except Exception as e:   # l'écoute ne doit jamais s'arrêter en silence
                if self.fin.is_set():
                    return
                if not en_panne:     # une ligne par panne, pas une par essai
                    self.campagne.log(f"⚠️  {e if isinstance(e, ErreurTelegram) else type(e).__name__}")
                en_panne = True
                self.fin.wait(REPRISE_ECOUTE_S)


# ─── Campagne ─────────────────────────────────────────────────────────────────
class Campagne:
    """ecoute : clics lus par un fil à part (_Ecoute) ; sinon, par la boucle
    principale quand elle attend (tests)."""

    def __init__(self, user_id: int, modes, reglages: Reglages, telegram: Telegram | None, horloge=None,
                 ecoute: bool = False, reseau: Reseau | None = None):
        self.user_id, self.modes, self.reglages = user_id, list(modes), reglages
        self.telegram, self.horloge = telegram, horloge or Horloge()
        self.arret = False                 # SIGTERM, Ctrl+C ; ou connexion absente à l'heure butoir
        self.reseau = reseau or Reseau(self.horloge, self.log, arret=lambda: self.arret,
                                       heure_butoir=reglages.heure_butoir)
        self.reseau.au_retour = self._connexion_revenue
        self._lancee = False               # attente de la connexion au démarrage passée
        self.bilan = {}                    # mode -> chiffres
        self.attentes: dict[str, Attente] = {}
        self._recus = queue.SimpleQueue()  # clics auxquels il a été répondu, pas encore relevés
        self._clics: list[Clic] = []       # clics relevés, à traiter par la boucle principale
        self._avec_ecoute = ecoute
        self._ecoute: _Ecoute | None = None
        self._jeton_fin = secrets.token_hex(6)
        self._message_fin = 0
        self._envoi_en_cours = False
        self._parti = False                # extinction ou veille demandée au système
        self._id = None
        self._debut = None

    # ─── Arrêt ────────────────────────────────────────────────────────────────
    @property
    def arret(self) -> bool:
        return self._arret or self.hors_ligne

    @arret.setter
    def arret(self, valeur: bool):
        self._arret = valeur

    @property
    def hors_ligne(self) -> bool:
        """Connexion absente à l'heure butoir : la campagne s'arrête (D219)."""
        return self.reseau.perdu_depuis is not None

    # ─── Journal et messages ──────────────────────────────────────────────────
    def log(self, message: str):
        journaliser(f"[campagne] {message}")
        if self._id is not None:
            try:
                campagnes_db.noter(self._id, message)
            except Exception as e:   # la base occupée ne doit pas arrêter la campagne
                journaliser(f"[campagne] journal non écrit ({type(e).__name__})")

    def notifier(self, texte: str, boutons=None) -> int:
        """Message Telegram ; 0 s'il n'est pas parti (la campagne continue)."""
        self.log(f"📨 {texte.splitlines()[0]}")
        if not self.telegram or self.hors_ligne:
            return 0
        try:
            return self.telegram.envoyer(texte, boutons)
        except ErreurTelegram as e:
            self.log(f"⚠️  {e}")
        # Connexion coupée : pause, puis un second essai (D218)
        if not self.reseau.en_ligne() and self.reseau.attendre("message Telegram"):
            try:
                return self.telegram.envoyer(texte, boutons)
            except ErreurTelegram as e:
                self.log(f"⚠️  {e}")
        return 0

    def _telegram(self, action):
        """Appel Telegram accessoire : un échec est journalisé."""
        try:
            return action()
        except ErreurTelegram as e:
            self.log(f"⚠️  {e}")
            return None

    def _sans_boutons(self, message_id: int):
        if message_id and self.telegram:
            self._telegram(lambda: self.telegram.retirer_boutons(message_id))

    # ─── Clics ────────────────────────────────────────────────────────────────
    def recevoir(self, attente: int = 0):
        """Lit les clics, répond à TOUS avant quoi que ce soit d'autre, puis met
        de côté ceux qui demandent une action. ErreurTelegram si la lecture échoue."""
        a_traiter = []
        for clic in self.telegram.clics(attente):
            reponse, action = self._reponse(clic)
            self._telegram(lambda c=clic, r=reponse: self.telegram.accuser(c, r))
            if action:
                a_traiter.append(clic)
        for clic in a_traiter:
            self._recus.put(clic)

    def _reponse(self, clic: Clic) -> tuple[str, bool]:
        """(texte affiché sur le téléphone, le clic demande une action)."""
        action, _, jeton = clic.donnee.partition(":")
        attente = self._attente_du(jeton)
        if action == "voir" and attente:
            return "Rien n'est parti.", True
        if action == "envoyer" and attente:
            if self.horloge.maintenant() >= self.limite:
                return "Heure limite passée : rien n'est envoyé.", False
            return "Envoi noté.", True
        if action in (extinction.ETEINDRE, extinction.VEILLE, "annuler") and jeton == self._jeton_fin:
            if self._envoi_en_cours or (action != "annuler" and not self._message_fin):
                return "Campagne en cours : proposé à la fin.", False
            return "", True
        return "Ce bouton n'est plus valable.", False

    def _attente_du(self, jeton: str) -> Attente | None:
        return next((a for a in list(self.attentes.values()) if a.jeton == jeton), None)

    def relever(self, attente: int = 0):
        """Relève les clics reçus, en attendant au plus `attente` secondes qu'il
        en vienne un ; « Voir d'abord » est fait tout de suite, le reste attend
        la boucle principale."""
        if self._ecoute is not None:
            self._attendre_un_clic(attente)
        elif not self.telegram:
            self.horloge.dormir(attente)
        else:
            try:
                self.recevoir(attente)
            except ErreurTelegram as e:
                self.log(f"⚠️  {e}")
                self.horloge.dormir(attente)      # pas de boucle serrée
        self._ranger_recus()

    def _ranger_recus(self):
        while not self._recus.empty():
            clic = self._recus.get()
            action, _, jeton = clic.donnee.partition(":")
            if action != "voir":
                self._clics.append(clic)
            elif vue := self._attente_du(jeton):
                self._voir(vue)

    def _attendre_un_clic(self, attente: float):
        fin = self.horloge.maintenant() + timedelta(seconds=attente)
        while self._recus.empty() and not self.arret and self.horloge.maintenant() < fin:
            self.horloge.dormir(0.2)

    def _arreter_ecoute(self):
        if self._ecoute is not None:
            self._ecoute.fin.set()
            self._ecoute = None

    def patienter(self, secondes: float):
        """Attend en relevant les clics."""
        fin = self.horloge.maintenant() + timedelta(seconds=secondes)
        while not self.arret and (reste := (fin - self.horloge.maintenant()).total_seconds()) > 0:
            if self.telegram:
                self.relever(max(1, min(ATTENTE_TELEGRAM_S, int(reste))))
            else:
                self.horloge.dormir(min(reste, 5))

    # ─── Verrou partagé avec l'interface ──────────────────────────────────────
    def _verrou_spontanees(self) -> Verrou | None:
        verrou = Verrou(nom_pipeline(SPONTANEES, self.user_id))
        fin = self.horloge.maintenant() + timedelta(seconds=ATTENTE_INTERFACE_S)
        while not verrou.prendre():
            if self.arret or self.horloge.maintenant() >= fin:
                return None
            self.patienter(20)
        return verrou

    # ─── Déroulé ──────────────────────────────────────────────────────────────
    def executer(self) -> dict:
        """Toute la campagne. CampagneEnCours si une autre tourne."""
        verrou = Verrou(CAMPAGNE)
        if not verrou.prendre():
            raise CampagneEnCours("Une campagne est déjà en cours.")
        try:
            self._deroule()
        finally:
            self._arreter_ecoute()
            verrou.liberer()
        if self.hors_ligne and not self._arret:
            self._prevenir_au_retour()          # verrou libéré : une autre campagne peut partir
        return self.bilan

    def _deroule(self):
        try:
            self._id = campagnes_db.ouvrir(self.user_id)
            self._debut = self.horloge.maintenant()
            self.reseau.fixer_butoir(self._debut)
            heures, minutes = map(int, self.reglages.heure_limite.split(":"))
            self.limite = self.horloge.maintenant().replace(hour=heures, minute=minutes, second=0, microsecond=0)
            if not self.reseau.attendre("démarrage"):
                self.log("⏹️ Campagne arrêtée avant de commencer : pas d'accès internet, rien n'est cherché ni envoyé.")
                campagnes_db.enregistrer_bilan(self._id, self.bilan, "arretee")
                return
            self._lancee = True
            if self.telegram:
                self._telegram(lambda: self.telegram.clics(0))     # clics d'une campagne passée : oubliés
                if self._avec_ecoute:
                    self._ecoute = _Ecoute(self)
                    self._ecoute.start()
            self.notifier(f"▶️ Campagne commencée : {', '.join(self.modes)}, {self.reglages.cible} entreprises par mode"
                          + (f". Réponse attendue avant {self.reglages.heure_limite}."
                             if self.reglages.validation == "telegram" else ". Envoi automatique."))
            for mode in self.modes:
                if self.arret:
                    break
                self._un_mode(mode)
            if self.attentes and not self.arret:
                self._proposer_fin()
                self._attendre_validations()
            etat = "arretee" if self.arret else "terminee"
            campagnes_db.enregistrer_bilan(self._id, self.bilan, etat)
            if self.hors_ligne:
                self.log("⏹️ Campagne arrêtée : pas d'accès internet.")
            elif self.arret:
                self.notifier("⏹️ Campagne arrêtée. " + self._resume())
            elif not self._parti:
                self._fin()
        except Exception as e:
            self.notifier(f"❌ Campagne interrompue par une erreur ({type(e).__name__}). Voir le journal.")
            if self._id is not None:
                campagnes_db.enregistrer_bilan(self._id, self.bilan, "erreur")
            raise

    def _connexion_revenue(self, debut: datetime, revenue: datetime, ou: str):
        """Connexion revenue avant la butoir : message, sans nouvelle attente
        s'il ne part pas (il serait suivi d'une seconde coupure, déjà journalisée)."""
        texte = (f"🌐 Connexion revenue à {revenue:%H:%M}, campagne {'reprise' if self._lancee else 'lancée'} "
                 f"(coupure depuis {debut:%H:%M}).")
        self.log(f"📨 {texte}")
        if self.telegram:
            self._telegram(lambda: self.telegram.envoyer(texte))

    def _prochaine(self) -> tuple[str, datetime | None]:
        """« prochaine campagne vendredi 27/11 à 07:00 », et cet instant."""
        quand = extinction.prochain_lancement()
        if quand is None:
            return f"pas de prochaine campagne programmée ({extinction.MINUTEUR} inactif)", None
        quand = quand.astimezone(self.horloge.maintenant().tzinfo)
        return f"prochaine campagne {JOURS[quand.weekday()]} {quand:%d/%m} à {quand:%H:%M}", quand

    def _prevenir_au_retour(self):
        """Arrêt faute de connexion : message Telegram dès son retour, essayé
        toutes les 30 s, RETOUR_MAX_S au plus et fini avant la prochaine
        campagne ; Ctrl+C ou SIGTERM l'abandonne. Ni recherche ni envoi."""
        perdue, abandon = self.reseau.perdu_depuis, self.reseau.fin_attente
        fin = self.horloge.maintenant() + timedelta(seconds=RETOUR_MAX_S)
        if (prochaine := self._prochaine()[1]) is not None:
            fin = min(fin, prochaine - timedelta(seconds=AVANT_PROCHAINE_S))
        while self.telegram and not self._arret and self.horloge.maintenant() < fin:
            if self.reseau.en_ligne():
                revenue = self.horloge.maintenant()
                texte = (f"🌐 Connexion revenue à {revenue:%H:%M}, trop tard pour aujourd'hui, {self._prochaine()[0]}.\n"
                         f"Campagne du {self._debut:%d/%m à %H:%M} arrêtée à {abandon:%H:%M} : pas d'accès internet "
                         f"depuis {perdue:%H:%M} (heure butoir {self.reglages.heure_butoir}).\n"
                         + (self._resume() if self.bilan else "Rien n'a été cherché ni envoyé."))
                try:
                    self.telegram.envoyer(texte)
                    self.log(f"📨 {texte.splitlines()[0]}")
                    return
                except ErreurTelegram as e:
                    self.log(f"⚠️  {e}")
            self.horloge.dormir(ESSAI_S)
        self.log("Message de fin non envoyé : " + ("pas de Telegram." if not self.telegram else
                                                   "arrêt demandé." if self._arret else "connexion toujours absente."))

    def _noter(self, mode: str, **champs):
        self.bilan.setdefault(mode, {}).update(champs)
        campagnes_db.enregistrer_bilan(self._id, self.bilan)

    def _un_mode(self, mode: str):
        try:
            compte = envoi.verifier_avant_envoi(self.user_id, mode)
        except (ErreurUtilisateur, ChiffrementIndisponible) as e:
            self._noter(mode, erreur=str(e))
            self.notifier(f"❌ {mode} : {e}")
            return
        self._preparer(mode)
        if self.arret:
            return
        # Plafond du jour : ce qui reste, moins ce qui attend déjà une réponse
        reste = config.PLAFOND_ENVOIS_JOUR - envois_du_jour(self.user_id) - sum(
            len(a.liste) for a in self.attentes.values())
        maximum = min(self.reglages.cible, max(0, reste), config.LIMITE_ENVOIS_PAR_LANCEMENT)
        if maximum == 0:
            self._noter(mode, plafond=True)
            self.notifier(f"⏹️ {mode} : plafond de {config.PLAFOND_ENVOIS_JOUR} mails par jour atteint. "
                          "La sélection reste prête dans l'interface.")
            return
        liste = envoi.pretes(self.user_id, mode, maximum)
        self._noter(mode, proposees=len(liste))
        if not liste:
            self.notifier(f"ℹ️ {mode} : aucune entreprise prête, rien à envoyer.")
            return
        if maximum < self.reglages.cible:
            self.log(f"{mode} : {maximum} mails possibles aujourd'hui (plafond de {config.PLAFOND_ENVOIS_JOUR})")
        attente = Attente(mode, liste, bool(compte["mode_test"]))
        if self.reglages.validation == "auto":
            self._envoyer(attente)
        else:
            self._demander(attente)

    # ─── 1. Préparation ───────────────────────────────────────────────────────
    def _preparer(self, mode: str):
        debut = self.horloge.maintenant()
        verrou = self._verrou_spontanees()
        if verrou is None:
            self._noter(mode, raison="interface occupée")
            if not self.arret:
                self.notifier(f"⚠️ {mode} : une recherche ou un envoi tourne dans l'interface, préparation passée.")
            return
        examinees, raison = 0, "cible atteinte"
        avant = len(envoi.pretes(self.user_id, mode))
        try:
            arret = _ArretRecherche(self, debut + timedelta(minutes=self.reglages.duree_max_min))
            recherche_emails.reinitialiser_recherche()
            while len(envoi.pretes(self.user_id, mode, self.reglages.cible)) < self.reglages.cible:
                self.reseau.attendre("recherche")        # tout de suite si la connexion est là
                if raison_arret := arret.raison():
                    raison = raison_arret
                    break
                reste = self.reglages.max_entreprises - examinees
                if reste <= 0:
                    raison = f"nombre maximal d'entreprises examinées atteint ({self.reglages.max_entreprises})"
                    break
                try:
                    file = compter_a_scraper(self.user_id, mode)
                    if not file:
                        if not self._nouvelles_entreprises(mode, arret):
                            if not self.reseau.en_ligne():
                                continue                 # coupure : attendue en haut de la boucle
                            raison = arret.raison() or "plus d'entreprise à trouver"
                            break
                        continue
                    recherche_emails.main(self.user_id, stop_event=arret, log_fn=self.log,
                                          max_scrapees=min(LOT, reste), mode=mode, reseau=self.reseau)
                except Exception as e:   # réseau, source... : le mode s'arrête là, ce qui est prêt reste prêt
                    self.log(f"❌ {mode} : {type(e).__name__} : {e}")
                    if not self.reseau.en_ligne():
                        continue                         # coupure : attendue en haut de la boucle
                    raison = f"erreur pendant la recherche ({type(e).__name__})"
                    break
                faites = file - compter_a_scraper(self.user_id, mode)
                examinees += faites
                self.relever()
                if faites <= 0 and not arret.is_set():
                    raison = "recherche d'emails sans progrès"
                    break
        finally:
            verrou.liberer()
        duree = round((self.horloge.maintenant() - debut).total_seconds() / 60)
        toutes = len(envoi.pretes(self.user_id, mode))
        self._noter(mode, examinees=examinees, emails_trouves=max(0, toutes - avant), pretes=toutes,
                    duree_min=duree, raison=raison)
        signe = "✅" if raison == "cible atteinte" else "⏹️"
        self.notifier(f"{signe} {mode} : recherche finie ({raison}).\n{examinees} entreprises examinées, "
                      f"{max(0, toutes - avant)} avec un email vérifié, {toutes} prêtes, {duree} min.")

    def _nouvelles_entreprises(self, mode: str, arret) -> bool:
        """Nouvelle recherche Sirene et LBA du profil ; vrai si le mode a gagné
        des entreprises."""
        from shared.naf import sirene_pour_profil
        sirene = sirene_pour_profil(lire_profil(self.user_id, mode=mode))
        if sirene["rien_a_chercher"] and "lba" not in get_mode(mode)["sources"]:
            self.log(f"{mode} : {sirene['avertissement']}")
            return False
        avant = len(lire_entreprises(self.user_id, mode))
        self.log(f"{mode} : file vide, nouvelle recherche d'entreprises")
        recuperation.main(self.user_id, stop_event=arret, max_entreprises=NOUVELLES_ENTREPRISES, log_fn=self.log,
                          mode=mode)
        return len(lire_entreprises(self.user_id, mode)) > avant

    # ─── 2. Validation ────────────────────────────────────────────────────────
    def _lignes(self, attente: Attente) -> str:
        return "\n".join(f"{i}. {e['nom']} : {', '.join(e['adresses'])}" for i, e in enumerate(attente.liste, 1))

    def _demander(self, attente: Attente):
        if self.horloge.maintenant() >= self.limite:
            self._noter(attente.mode, validation="heure limite passée")
            self.notifier(f"⏹️ {attente.mode} : {len(attente.liste)} emails prêts, mais l'heure limite "
                          f"({self.reglages.heure_limite}) est passée. Rien n'est envoyé.")
            return
        # Enregistrée avant le message : un clic immédiat est reconnu
        self.attentes[attente.mode] = attente
        attente.message_id = self.notifier(
            f"📬 {attente.mode} : {len(attente.liste)} emails prêts. Réponse avant {self.reglages.heure_limite}.\n"
            f"{attente.annonce}\n\n{self._lignes(attente)}\n\n{attente.annonce}",
            [("Envoyer", f"envoyer:{attente.jeton}"), ("Voir d'abord", f"voir:{attente.jeton}")])
        if not attente.message_id:
            del self.attentes[attente.mode]
            self._noter(attente.mode, validation="message non parti")
            self.log(f"{attente.mode} : liste non envoyée sur Telegram, donc rien ne sera envoyé")

    def _voir(self, attente: Attente):
        profil = lire_profil(self.user_id, mode=attente.mode)
        objet, corps = envoi.objet_et_corps(profil, attente.mode)
        pieces = ", ".join(p.get("nom") or "?" for p in profil.get("pieces_jointes") or []) or "aucune"
        self.notifier(f"👀 {attente.mode}, rien n'est parti.\n{attente.annonce}\nObjet : {objet}\nPièces jointes : {pieces}\n\n{corps}\n\n"
                      f"Entreprises et adresses : page « Entreprises à contacter » de l'application. "
                      f"« Envoyer » reste valable jusqu'à {self.reglages.heure_limite}.",
                      [("Envoyer", f"envoyer:{attente.jeton}")])

    def _attendre_validations(self):
        """Traite les clics jusqu'à l'heure limite ; sans réponse, rien ne part."""
        while self.attentes and not self.arret:
            if not self._clics:
                if self.horloge.maintenant() >= self.limite:
                    self._ranger_recus()      # « Envoi noté. » répondu juste avant l'heure : il compte
                    if self._clics:
                        continue
                    break
                self.relever(max(1, min(ATTENTE_TELEGRAM_S,
                                        int((self.limite - self.horloge.maintenant()).total_seconds()))))
                continue
            clic = self._clics.pop(0)
            action, _, jeton = clic.donnee.partition(":")
            if action == "envoyer":
                attente = next((a for a in self.attentes.values() if a.jeton == jeton), None)
                if attente:      # un second clic n'y trouve plus rien
                    del self.attentes[attente.mode]
                    self._sans_boutons(attente.message_id)
                    self._envoyer(attente)
            elif action in LIBELLES_FIN and self._compte_a_rebours(action):
                return
        self._abandonner("sans réponse" if not self.arret else "campagne arrêtée")

    def _abandonner(self, raison: str):
        for attente in list(self.attentes.values()):
            self._sans_boutons(attente.message_id)
            self._noter(attente.mode, validation=raison)
            self.notifier(f"⏹️ {attente.mode} : {raison}, rien n'est envoyé. Les {len(attente.liste)} entreprises "
                          "restent prêtes dans l'interface.")
        self.attentes.clear()

    # ─── 3. Envoi ─────────────────────────────────────────────────────────────
    def _envoyer(self, attente: Attente):
        mode = attente.mode
        verrou = self._verrou_spontanees()
        if verrou is None:
            self._noter(mode, erreur="interface occupée")
            self.notifier(f"⚠️ {mode} : une recherche ou un envoi tourne dans l'interface, rien n'est envoyé.")
            return
        self._envoi_en_cours = True
        try:
            if not self.reseau.attendre("envoi"):
                raise ErreurUtilisateur("pas d'accès internet, rien n'est envoyé.")
            compte = envoi.verifier_avant_envoi(self.user_id, mode)
            if attente.test and not compte["mode_test"]:
                raise ErreurUtilisateur("le mode essai a été coupé depuis le résumé : relance la campagne pour valider "
                                        "un envoi réel.")
            # Essai annoncé ou activé depuis : essai. Jamais réel sans l'avoir annoncé
            r = envoi.main(self.user_id, limite=len(attente.liste), test=attente.test, stop_event=_ArretEnvoi(self),
                           log_fn=self.log, mode=mode, pause=PAUSE_ENVOIS,
                           autorises={e["id"]: e["adresses"] for e in attente.liste}, reseau=self.reseau)
            self._noter(mode, envoyes=r["envoyes"], echecs=r["echecs"], essai=bool(compte["mode_test"]))
            suite = " Plafond du jour atteint." if r["arret"] == "plafond" else ""
            self.notifier(f"✅ {mode} : {r['envoyes']} emails envoyés, {r['echecs']} échec(s)."
                          + (" 🧪 Mode essai." if compte["mode_test"] else "") + suite)
        except (ErreurUtilisateur, ChiffrementIndisponible, envoi.EnvoiInterrompu) as e:
            self._noter(mode, erreur=str(e))
            self.notifier(f"❌ {mode} : envoi arrêté. {e}")
        finally:
            self._envoi_en_cours = False
            verrou.liberer()

    # ─── Fin : extinction ou veille ───────────────────────────────────────────
    def _resume(self) -> str:
        lignes = []
        for mode, b in self.bilan.items():
            if "envoyes" in b:
                fait = f"{b['envoyes']} envoyés"
            elif mode in self.attentes:
                fait = f"{b.get('proposees', 0)} en attente de ta validation"
            else:
                fait = b.get("erreur") or b.get("validation") or ("plafond atteint" if b.get("plafond") else "rien envoyé")
            lignes.append(f"{mode} : {b.get('examinees', 0)} examinées, {b.get('pretes', 0)} prêtes, {fait}")
        return "\n".join(lignes) or "Rien à signaler."

    def _proposer_fin(self):
        """Message de fin, avec les boutons si CAMPAGNE_FIN=demander."""
        self._sans_boutons(self._message_fin)
        boutons = [("Éteindre le PC", f"{extinction.ETEINDRE}:{self._jeton_fin}"),
                   ("Mettre en veille jusqu'à la prochaine campagne", f"{extinction.VEILLE}:{self._jeton_fin}")]
        titre = "⏳ Préparation terminée, en attente de ta réponse." if self.attentes else "🏁 Campagne terminée."
        self._message_fin = self.notifier(f"{titre}\n{self._resume()}",
                                          boutons if self.reglages.fin == "demander" else None)

    def _fin(self):
        self._proposer_fin()
        if self.reglages.fin in LIBELLES_FIN:
            self._compte_a_rebours(self.reglages.fin)
            return
        if self.reglages.fin != "demander" or not self._message_fin:
            return
        fin = self.horloge.maintenant() + timedelta(minutes=self.reglages.fin_attente_min)
        while not self.arret and (self._clics or self.horloge.maintenant() < fin):
            if not self._clics:
                self.relever(max(1, min(ATTENTE_TELEGRAM_S, int((fin - self.horloge.maintenant()).total_seconds()))))
                continue
            action = self._clics.pop(0).donnee.partition(":")[0]
            if action in LIBELLES_FIN and self._compte_a_rebours(action):
                break
        self._sans_boutons(self._message_fin)

    def _occupe(self) -> str:
        """Ce qui tourne encore (application, autre campagne), ou ""."""
        return ", ".join(occupes(sauf=(CAMPAGNE,)))

    def _annulation(self) -> bool:
        """« Annuler » cliqué, ou « Envoyer » : le PC doit rester allumé."""
        self._ranger_recus()
        return any(c.donnee.startswith(("annuler:", "envoyer:")) for c in self._clics)

    def _annulee(self, libelle: str) -> bool:
        annule = self._annulation() or self.arret
        self._clics = [c for c in self._clics if c.donnee.startswith("envoyer:")]
        if annule:
            self.notifier(f"↩️ {libelle} annulée.")
        return annule

    def _compte_a_rebours(self, action: str) -> bool:
        """Deux minutes pour annuler, puis extinction ou veille. Vrai si elle a
        été demandée au système. Rien sans message reçu : pas d'annulation
        possible. Rien si quelque chose tourne, avant comme après l'attente."""
        libelle = LIBELLES_FIN[action]
        try:
            if occupe := self._occupe():
                raise extinction.ErreurExtinction(f"un traitement tourne encore ({occupe}).")
            reveil = extinction.verifier(action)
            suite = f" Réveil le {reveil.strftime('%d/%m à %H:%M')}." if reveil else ""
            en_attente = " Les envois en attente de ta réponse ne partiront pas." if self.attentes else ""
            message = self.notifier(f"🔌 {libelle} dans 2 minutes.{suite}{en_attente}",
                                    [("Annuler", f"annuler:{self._jeton_fin}")])
            if not message:
                raise extinction.ErreurExtinction("message Telegram non parti, donc pas d'annulation possible.")
            fin = self.horloge.maintenant() + timedelta(seconds=DELAI_EXTINCTION_S)
            while not (self._annulation() or self.arret) and self.horloge.maintenant() < fin:
                self.relever(max(1, min(10, int((fin - self.horloge.maintenant()).total_seconds()))))
            self._sans_boutons(message)
            if self._annulee(libelle):
                return False
            if occupe := self._occupe():
                raise extinction.ErreurExtinction(f"un traitement a démarré entre-temps ({occupe}).")
            extinction.verifier(action)
            if self._annulee(libelle):      # clic auquel il vient d'être répondu
                return False
            if self.attentes:
                self._abandonner("extinction demandée")
                campagnes_db.enregistrer_bilan(self._id, self.bilan, "terminee")
            self._arreter_ecoute()
            if self.telegram:
                self._telegram(self.telegram.confirmer_lecture)
            self.log(f"🔌 {libelle}")
            extinction.agir(action)
            self._parti = True
            return True
        except extinction.ErreurExtinction as e:
            self.notifier(f"⚠️ {libelle} impossible : {e}")
            return False
