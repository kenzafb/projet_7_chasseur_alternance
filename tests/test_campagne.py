"""D213 : campagne automatique. Faux scraper, faux envoi SMTP, faux Telegram,
fausse horloge, fausses commandes système : rien de vrai ne part jamais
(conftest fait échouer tout appel réel)."""

import subprocess
import sys
import types
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import spontanees.envoi as envoi
from database import campagnes_db, compte_envoi_db
from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
from database.entreprises_db import deja_envoyee, marquer_postule_lba, sauvegarder_entreprises
from shared import config, extinction, reseau, telegram
from shared.erreurs import ErreurUtilisateur
from shared.pipelines import ANALYSE, SPONTANEES, Pipelines
from shared.telegram import Clic
from shared.verrous import CAMPAGNE, Verrou, nom_pipeline, occupes
from spontanees import campagne as C
from tests.conftest import compte_verifie

PARIS = ZoneInfo("Europe/Paris")
MODE = "stage"


class FausseHorloge:
    def __init__(self, heure=9):
        self.t = datetime(2026, 11, 26, heure, 0, tzinfo=PARIS)

    def maintenant(self):
        return self.t

    def dormir(self, secondes):
        self.t += timedelta(seconds=secondes)


class FauxTelegram:
    """Note les messages ; reponse(telegram) rend les clics à chaque lecture.
    Une lecture longue fait avancer l'horloge."""

    def __init__(self, horloge, reponse=None):
        self.horloge, self.reponse = horloge, reponse or (lambda t: [])
        self.messages, self.boutons, self.accuses, self.retires, self.confirmes = [], {}, [], [], 0
        self.panne = False
        self.coupe = lambda: False       # connexion coupée (D218)

    def envoyer(self, texte, boutons=None):
        if self.panne or self.coupe():
            raise telegram.ErreurTelegram("Telegram injoignable")
        self.messages.append(texte)
        for titre, donnee in boutons or []:
            self.boutons.setdefault(titre, []).append(donnee)
        return len(self.messages)

    def clics(self, attente=0):
        if self.coupe():
            raise telegram.ErreurTelegram("Telegram injoignable")
        if attente:
            self.horloge.dormir(attente)
        return [Clic(str(i), d) for i, d in enumerate(self.reponse(self))]

    def accuser(self, clic, texte=""):
        self.accuses.append(texte)

    def retirer_boutons(self, message_id):
        self.retires.append(message_id)

    def confirmer_lecture(self):
        self.confirmes += 1

    def a_dit(self, texte):
        return any(texte in m for m in self.messages)


def une_fois(titre, rang=0):
    """Clic, une seule fois, sur le bouton `titre` dès qu'il est affiché."""
    fait = []

    def reponse(t):
        if not fait and len(t.boutons.get(titre, [])) > rang:
            fait.append(1)
            return [t.boutons[titre][rang]]
        return []
    return reponse


def plusieurs(*reponses):
    return lambda t: [c for r in reponses for c in r(t)]


@pytest.fixture
def monde(utilisateur, smtp_simule, monkeypatch):
    """Utilisateur prêt à envoyer, faux scraper, fausses sources, faux système."""
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    compte_verifie(smtp_simule, uid, "ada@gmail.com")
    profil = {"prenom": "Ada", "date_debut": "2027-02-08", "date_fin": "2027-04-18"}
    from database.profil_db import sauvegarder_profil
    for mode in ("stage", "job"):
        sauvegarder_profil(uid, profil, mode=mode)
    m = types.SimpleNamespace(uid=uid, client=client, smtp=smtp_simule, scrapees=[], recherches=[], commandes=[], avec_email=lambda nom: True,
                              source=lambda n: [], logind='s "yes"', horloge=FausseHorloge(), coupures=[])
    # Faux réseau (D218) : coupé pendant les intervalles [début, fin) de m.coupures
    m.coupe = lambda: any(a <= m.horloge.t < b for a, b in m.coupures)
    monkeypatch.setattr(reseau, "_joindre", lambda url: not m.coupe())

    def faux_scraper(user_id, stop_event=None, log_fn=None, max_scrapees=None, mode=MODE, **_):
        restantes = [e for e in lire_entreprises(user_id, mode)
                     if not (e["traite"] or e["emails_trouves"] or e["mail_envoye"])][:max_scrapees]
        for e in restantes:
            if stop_event.is_set():
                return
            m.scrapees.append(e["nom_commercial"])
            m.horloge.dormir(60)
            e["traite"] = True
            if m.avec_email(e["nom_commercial"]):
                e["emails_trouves"], e["emails_douteux"] = [f"rh@{e['nom_commercial'].lower()}.fr"], []
            sauvegarder_enrichissement(user_id, [e])

    def fausse_recherche(user_id, stop_event=None, max_entreprises=None, log_fn=None, mode=MODE, **_):
        m.recherches.append(mode)
        ajouter_entreprises(user_id, m.source(len(m.recherches)), mode)

    def faux_systeme(args):
        m.commandes.append(args)
        sortie = {"busctl": m.logind, "pgrep": "1"}.get(args[0], "")
        if "--property=WakeSystem" in args:
            sortie = "yes"
        if "--property=NextElapseUSecRealtime" in args:
            sortie = f"@{int(datetime(2026, 11, 27, 9, 0, tzinfo=PARIS).timestamp())}"
        return subprocess.CompletedProcess(args, 0, sortie, "")

    monkeypatch.setattr(C.recherche_emails, "main", faux_scraper)
    monkeypatch.setattr(C.recherche_emails, "recherche_arretee", False)
    monkeypatch.setattr(C.recuperation, "main", fausse_recherche)
    monkeypatch.setattr("shared.naf.sirene_pour_profil", lambda p: {"rien_a_chercher": False, "avertissement": ""})
    monkeypatch.setattr(extinction, "_executer", faux_systeme)
    monkeypatch.setattr(extinction, "_gestionnaire_peut_reveiller", lambda: True)
    return m


def entreprises(n, prefixe="Ent"):
    return [{"siret": f"{prefixe}{i}", "nom": f"{prefixe}{i}", "nom_commercial": f"{prefixe}{i}"} for i in range(n)]


def lancer(m, reponse=None, modes=("stage",), avec_telegram=True, **reglages):
    reglages.setdefault("fin", "rien")
    m.telegram = FauxTelegram(m.horloge, reponse) if avec_telegram else None
    if m.telegram:
        m.telegram.coupe = m.coupe
    m.campagne = C.Campagne(m.uid, modes, C.Reglages(**{"cible": 3, **reglages}).verifier(), m.telegram, m.horloge)
    return m.campagne.executer()


def destinataires(m):
    return [to for _, _, to, _ in m.smtp.messages]


def actions(m):
    """Extinctions et veilles demandées au système (les vérifications mises à part)."""
    return [c for c in m.commandes if "poweroff" in c or "suspend" in c]


# ─── Préparation ──────────────────────────────────────────────────────────────
def test_pas_assez_d_entreprises_nouvelle_recherche(monde):
    ajouter_entreprises(monde.uid, entreprises(1), MODE)
    monde.source = lambda n: entreprises(2, "Neuve") if n == 1 else []
    b = lancer(monde, une_fois("Envoyer"))
    assert monde.recherches == ["stage"]
    assert monde.scrapees == ["Ent0", "Neuve0", "Neuve1"]
    assert b["stage"]["examinees"] == 3 and b["stage"]["raison"] == "cible atteinte" and b["stage"]["envoyes"] == 3


def test_plus_rien_a_trouver_s_arrete(monde):
    ajouter_entreprises(monde.uid, entreprises(1), MODE)
    b = lancer(monde, une_fois("Envoyer"))
    assert b["stage"]["raison"] == "plus d'entreprise à trouver" and b["stage"]["envoyes"] == 1


def test_cible_deja_prete_rien_a_chercher(monde):
    ajouter_entreprises(monde.uid, entreprises(5), MODE)
    lancer(monde)
    assert len(monde.scrapees) == 5          # un seul lot (5) suffit pour 3
    monde.scrapees.clear()
    lancer(monde)
    assert monde.scrapees == [] and monde.recherches == []


@pytest.mark.parametrize("reglages, raison", [
    ({"max_entreprises": 4}, "nombre maximal d'entreprises examinées atteint (4)"),
    ({"duree_max_min": 3}, "durée maximale atteinte (3 min)")])
def test_garde_fous(monde, reglages, raison):
    ajouter_entreprises(monde.uid, entreprises(50), MODE)
    monde.avec_email = lambda nom: False
    b = lancer(monde, **reglages)
    assert b["stage"]["raison"] == raison and len(monde.scrapees) <= 5
    assert monde.telegram.a_dit(raison) and monde.smtp.messages == []


def test_panne_de_la_recherche_web(monde, monkeypatch):
    ajouter_entreprises(monde.uid, entreprises(20), MODE)

    def panne(nom):
        monkeypatch.setattr(C.recherche_emails, "recherche_arretee", True)
        return False
    monde.avec_email = panne
    b = lancer(monde)
    assert b["stage"]["raison"] == "recherche web en panne" and len(monde.scrapees) == 1


def test_erreur_d_une_source_n_arrete_pas_le_mode_suivant(monde, monkeypatch):
    ajouter_entreprises(monde.uid, entreprises(3), "job")

    def casse(*a, **k):
        raise ConnectionError("réseau")
    monkeypatch.setattr(C.recuperation, "main", casse)
    b = lancer(monde, une_fois("Envoyer"), modes=("stage", "job"))
    assert b["stage"]["raison"].startswith("erreur pendant la recherche") and b["job"]["envoyes"] == 3


def test_mode_au_profil_incomplet_passe(monde):
    """Dates du stage vides : refus de l'interface, le mode est passé, pas les autres."""
    from database.profil_db import sauvegarder_profil
    sauvegarder_profil(monde.uid, {"date_debut": "", "date_fin": ""}, mode="stage")
    ajouter_entreprises(monde.uid, entreprises(3), "job")
    b = lancer(monde, une_fois("Envoyer"), modes=("stage", "job"))
    assert "erreur" in b["stage"] and b["job"]["envoyes"] == 3


# ─── Validation ───────────────────────────────────────────────────────────────
def test_sans_reponse_rien_n_est_envoye(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    b = lancer(monde)
    assert monde.smtp.messages == [] and compte_envoi_db.envois_du_jour(monde.uid) == 0
    assert b["stage"]["validation"] == "sans réponse" and "envoyes" not in b["stage"]
    assert monde.horloge.maintenant().hour == 16                                # l'heure limite
    assert len(envoi.pretes(monde.uid, MODE)) == 3                              # prêtes dans l'interface
    assert monde.telegram.a_dit("rh@ent0.fr") and monde.telegram.a_dit("rien n'est envoyé")


def test_heure_limite_deja_passee(monde):
    monde.horloge = FausseHorloge(19)
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    b = lancer(monde, une_fois("Envoyer"))
    assert monde.smtp.messages == [] and b["stage"]["validation"] == "heure limite passée"


def test_envoyer(monde):
    ajouter_entreprises(monde.uid, entreprises(8), MODE)
    b = lancer(monde, une_fois("Envoyer"))
    assert b["stage"]["envoyes"] == 3 and destinataires(monde) == [["rh@ent0.fr"], ["rh@ent1.fr"], ["rh@ent2.fr"]]
    envoyees = [e for e in lire_entreprises(monde.uid, MODE) if e["mail_envoye"]]
    assert [e["mail_destinataires"] for e in envoyees] == destinataires(monde)     # suivi de l'interface
    assert compte_envoi_db.envois_du_jour(monde.uid) == 3


def test_pauses_de_2_a_5_minutes(monde, monkeypatch):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    pauses = []
    monkeypatch.setattr(envoi.random, "uniform", lambda a, b: pauses.append((a, b)) or 130)
    debut = monde.horloge.maintenant()
    lancer(monde, une_fois("Envoyer"))
    assert pauses == [(120, 300)] * 2 and monde.horloge.maintenant() - debut >= timedelta(seconds=260)


def test_double_clic_un_seul_envoi(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    lancer(monde, lambda t: t.boutons.get("Envoyer", [])[:1] * 2)
    assert len(monde.smtp.messages) == 3


def test_voir_d_abord_n_envoie_rien_puis_envoyer(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    lancer(monde, une_fois("Voir d'abord"))
    assert monde.smtp.messages == [] and monde.telegram.a_dit("rien n'est parti") and monde.telegram.a_dit("Objet : ")
    monde.horloge = FausseHorloge()                     # le lendemain
    lancer(monde, plusieurs(une_fois("Voir d'abord"), une_fois("Envoyer", 1)))
    assert len(monde.smtp.messages) == 3


def test_bouton_d_une_autre_campagne_refuse(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    lancer(monde, lambda t: ["envoyer:abcdef123456"])
    assert monde.smtp.messages == [] and "Ce bouton n'est plus valable." in monde.telegram.accuses


def test_resume_non_parti_rien_n_est_envoye(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    horloge = monde.horloge
    monde.telegram = FauxTelegram(horloge)
    monde.telegram.panne = True
    b = C.Campagne(monde.uid, ["stage"], C.Reglages(cible=3, fin="rien"), monde.telegram, horloge).executer()
    assert monde.smtp.messages == [] and b["stage"]["validation"] == "message non parti"


def test_seules_les_entreprises_et_adresses_approuvees_partent(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)

    def ajout_puis_clic(t):
        if not t.boutons.get("Envoyer") or t.accuses:
            return []
        liste = lire_entreprises(monde.uid, MODE)
        liste[0]["emails_trouves"] = ["autre@ent0.fr", "rh@ent0.fr"]          # adresse ajoutée après le résumé
        liste[1]["emails_trouves"] = ["remplacee@ent1.fr"]                    # plus l'adresse approuvée
        sauvegarder_enrichissement(monde.uid, liste[:2])
        ajouter_entreprises(monde.uid, entreprises(1, "Apres"), MODE)
        derniere = lire_entreprises(monde.uid, MODE)[-1]
        derniere.update(emails_trouves=["rh@apres.fr"], emails_douteux=[])
        sauvegarder_enrichissement(monde.uid, [derniere])
        return t.boutons["Envoyer"][:1]
    lancer(monde, ajout_puis_clic)
    assert destinataires(monde) == [["rh@ent0.fr"], ["rh@ent2.fr"]]


def test_entreprise_contactee_entre_temps(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)

    def depuis_l_interface(t):
        if not t.boutons.get("Envoyer") or t.accuses:
            return []
        e = lire_entreprises(monde.uid, MODE)[0]
        e["mail_envoye"] = True
        sauvegarder_entreprises(monde.uid, [e], MODE)
        return t.boutons["Envoyer"][:1]
    lancer(monde, depuis_l_interface)
    assert destinataires(monde) == [["rh@ent1.fr"], ["rh@ent2.fr"]]


def test_auto_envoie_sans_attendre(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    b = lancer(monde, validation="auto", avec_telegram=False)
    assert b["stage"]["envoyes"] == 3 and len(monde.smtp.messages) == 3


# ─── Mode essai, plafond ──────────────────────────────────────────────────────
def test_mode_essai_respecte(monde):
    compte_envoi_db.definir_mode_test(monde.uid, True)
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    b = lancer(monde, une_fois("Envoyer"))
    assert destinataires(monde) == [["ada@gmail.com"]] * 3 and b["stage"]["essai"] is True
    assert monde.telegram.a_dit("MODE ESSAI") and not any(e["mail_envoye"] for e in lire_entreprises(monde.uid, MODE))


def test_essai_coupe_apres_le_resume_rien_ne_part(monde):
    """Annoncé en essai : jamais d'envoi réel sans l'avoir annoncé."""
    compte_envoi_db.definir_mode_test(monde.uid, True)
    ajouter_entreprises(monde.uid, entreprises(3), MODE)

    def coupe(t):
        if not t.boutons.get("Envoyer") or t.accuses:
            return []
        compte_envoi_db.definir_mode_test(monde.uid, False)
        return t.boutons["Envoyer"][:1]
    b = lancer(monde, coupe)
    assert monde.smtp.messages == [] and "mode essai a été coupé" in b["stage"]["erreur"]


def test_plafond_du_jour_atteint(monde, monkeypatch):
    monkeypatch.setattr(config, "PLAFOND_ENVOIS_JOUR", 2)
    for _ in range(2):
        compte_envoi_db.reserver_envoi(monde.uid, 2)
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    b = lancer(monde, une_fois("Envoyer"))
    assert monde.smtp.messages == [] and "Plafond de 2 mails" in b["stage"]["erreur"]


def test_plafond_partage_entre_les_modes(monde, monkeypatch):
    """30 + 30 pour un plafond de 50 : le deuxième mode n'en propose que ce qui reste."""
    monkeypatch.setattr(config, "PLAFOND_ENVOIS_JOUR", 4)
    ajouter_entreprises(monde.uid, entreprises(3, "Stage"), "stage")
    ajouter_entreprises(monde.uid, entreprises(3, "Job"), "job")
    b = lancer(monde, plusieurs(une_fois("Envoyer"), une_fois("Envoyer", 1)), modes=("stage", "job"))
    assert (b["stage"]["envoyes"], b["job"]["proposees"], b["job"]["envoyes"]) == (3, 1, 1)
    assert len(monde.smtp.messages) == 4


def test_anti_doublon_par_mode(monde):
    """Même adresse dans deux entreprises : une fois par mode, deux modes."""
    for mode in ("stage", "job"):
        ajouter_entreprises(monde.uid, entreprises(2), mode)
    liste = lire_entreprises(monde.uid, "stage")
    for e in liste:
        e.update(emails_trouves=["rh@groupe.fr"], emails_douteux=[], traite=True)
    sauvegarder_enrichissement(monde.uid, liste)
    assert len(envoi.pretes(monde.uid, "stage")) == 1
    lancer(monde, plusieurs(une_fois("Envoyer"), une_fois("Envoyer", 1)), modes=("stage", "job"))
    assert destinataires(monde) == [["rh@groupe.fr"], ["rh@groupe.fr"]]


# ─── Verrous, base partagée ───────────────────────────────────────────────────
def test_deux_lancements_simultanes(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    autre = Verrou(CAMPAGNE)
    assert autre.prendre()
    with pytest.raises(C.CampagneEnCours):
        lancer(monde, validation="auto")
    assert monde.scrapees == [] and monde.smtp.messages == [] and campagnes_db.derniere(monde.uid) is None
    autre.liberer()
    assert lancer(monde, validation="auto")["stage"]["envoyes"] == 3


def test_verrou_entre_deux_processus(tmp_path, monkeypatch):
    """Un vrai second processus ; le verrou tombe avec lui, même tué."""
    monkeypatch.setattr(config, "VERROUS_DIR", tmp_path / "v")
    code = ("import sys,time; from pathlib import Path; from shared import config; config.VERROUS_DIR=Path(sys.argv[1]);"
            "from shared.verrous import Verrou; v=Verrou('campagne'); print(v.prendre(), flush=True); time.sleep(60)")
    p = subprocess.Popen([sys.executable, "-c", code, str(tmp_path / "v")], cwd=config.BASE_DIR, stdout=subprocess.PIPE,
                         text=True)
    try:
        assert p.stdout.readline().strip() == "True"
        assert not Verrou(CAMPAGNE).prendre() and occupes() == [CAMPAGNE]
    finally:
        p.kill()
        p.wait()
    assert Verrou(CAMPAGNE).prendre()


def test_interface_refusee_pendant_la_campagne_et_inversement(monde, client, utilisateur, pipelines_neufs):
    c, uid = utilisateur("b@test.fr", prenom="Bob")
    c.mode = MODE
    ajouter_entreprises(uid, entreprises(1), MODE)
    verrou = Verrou(nom_pipeline(SPONTANEES, uid))
    assert verrou.prendre()
    r = c.post("/api/spontanees/scraper")
    assert r.status_code == 400 and "Campagne automatique en cours" in r.json()["erreur"]
    verrou.liberer()
    # Interface occupée : la campagne attend puis passe, sans rien envoyer
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    assert pipelines_neufs.demarrer(SPONTANEES, monde.uid, mode=MODE)
    b = lancer(monde, validation="auto")
    assert b["stage"]["raison"] == "interface occupée" and monde.scrapees == [] and monde.smtp.messages == []
    pipelines_neufs.terminer(SPONTANEES, monde.uid)
    assert occupes() == []


def test_verrou_rendu_a_la_fin_d_un_traitement(tmp_path):
    p = Pipelines()
    for _ in range(3):
        assert p.demarrer(ANALYSE, 1)
        assert not Pipelines().demarrer(ANALYSE, 1)      # un autre processus
        p.terminer(ANALYSE, 1)
    assert occupes() == []


def test_l_interface_est_libre_pendant_l_attente(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    vus = []

    def regarde(t):
        if t.boutons.get("Envoyer"):
            vus.append(occupes())
        return []
    lancer(monde, regarde)
    assert vus[-1] == [CAMPAGNE]


def test_l_envoi_n_ecrase_pas_ce_qu_un_autre_processus_a_ecrit(monde, monkeypatch):
    """Avant D213, l'envoi réécrivait tout le mode avec l'état lu au départ."""
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    liste = lire_entreprises(monde.uid, MODE)
    for e in liste:
        e.update(emails_trouves=[f"rh@{e['nom_commercial'].lower()}.fr"], emails_douteux=[])
    sauvegarder_enrichissement(monde.uid, liste)

    def ailleurs(*a):
        troisieme = lire_entreprises(monde.uid, MODE)[2]
        troisieme["mail_envoye"], troisieme["mail_note"] = True, "depuis l'interface"
        sauvegarder_entreprises(monde.uid, [troisieme], MODE)
        return 0
    monkeypatch.setattr(envoi.random, "uniform", ailleurs)
    envoi.main(monde.uid, limite=2, mode=MODE)
    troisieme = lire_entreprises(monde.uid, MODE)[2]
    assert troisieme["mail_envoye"] and troisieme["mail_note"] == "depuis l'interface"
    assert deja_envoyee(monde.uid, troisieme["_id"], MODE) and marquer_postule_lba(monde.uid, 0, None, MODE) is False


def test_base_wal_et_attente_des_verrous(tmp_path, monkeypatch):
    """Un lecteur n'est pas bloqué par une écriture en cours, un second
    écrivain attend au lieu d'échouer."""
    import threading
    import time
    from sqlalchemy import text
    import database.connexion as cx
    monkeypatch.setattr(cx, "MODE_JOURNAL", "WAL")
    moteur = cx.creer_moteur(f"sqlite:///{tmp_path / 'w.db'}")
    with moteur.begin() as c:
        assert c.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert c.execute(text("PRAGMA busy_timeout")).scalar() == 30_000
        c.execute(text("CREATE TABLE t (x INTEGER)"))
    ecrit = threading.Event()

    def longue_ecriture():
        with moteur.begin() as c:
            c.execute(text("INSERT INTO t VALUES (1)"))
            ecrit.set()
            time.sleep(0.4)
    fil = threading.Thread(target=longue_ecriture, daemon=True)
    fil.start()
    assert ecrit.wait(5)
    with moteur.connect() as c:
        assert c.execute(text("SELECT count(*) FROM t")).scalar() == 0      # lu sans attendre
    with moteur.begin() as c:
        c.execute(text("INSERT INTO t VALUES (2)"))                         # attend l'autre
    fil.join(5)
    with moteur.connect() as c:
        assert c.execute(text("SELECT count(*) FROM t")).scalar() == 2
    moteur.dispose()


# ─── Arrêt, journal, notifications ────────────────────────────────────────────
def test_arret_propre_pendant_l_envoi(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)

    def clic_puis_arret(t):
        if t.boutons.get("Envoyer") and not t.accuses:
            return t.boutons["Envoyer"][:1]
        if monde.smtp.messages:
            monde.campagne.arret = True
        return []
    b = lancer(monde, clic_puis_arret)
    assert b["stage"]["envoyes"] == 1 and campagnes_db.derniere(monde.uid)["etat"] == "arretee"
    assert sum(e["mail_envoye"] for e in lire_entreprises(monde.uid, MODE)) == 1


def test_journal_et_bilan_retrouves_dans_l_interface(monde, utilisateur):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    lancer(monde, une_fois("Envoyer"))
    c = campagnes_db.derniere(monde.uid)
    assert c["etat"] == "terminee" and c["fin"] and c["bilan"]["stage"]["envoyes"] == 3
    assert "Campagne commencée" in c["journal"] and "rh@ent0.fr" in c["journal"]
    autre, _ = utilisateur("b@test.fr", prenom="Bob")
    assert autre.get("/api/spontanees/campagne").json() is None            # jamais celle d'un autre
    assert 'data-campagne hidden' in autre.get("/stage").text


def test_campagne_tuee_marquee_interrompue(monde):
    vieille = campagnes_db.ouvrir(monde.uid)
    campagnes_db.ouvrir(monde.uid)
    from database.connexion import SessionLocal
    from database.models import Campagne
    with SessionLocal() as db:
        assert db.get(Campagne, vieille).etat == "interrompue"


def test_notifications(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    lancer(monde, une_fois("Envoyer"))
    for texte in ("Campagne commencée", "recherche finie (cible atteinte)", "3 entreprises examinées, 3 avec un email",
                  "3 emails prêts", "3 emails envoyés", "Campagne terminée"):
        assert monde.telegram.a_dit(texte), texte


# ─── Fin : extinction, veille ─────────────────────────────────────────────────
ETEINDRE, VEILLE = "Éteindre le PC", "Mettre en veille jusqu'à la prochaine campagne"


def test_demander_eteindre(monde):
    b = lancer(monde, une_fois(ETEINDRE), fin="demander")
    assert actions(monde) == [["systemctl", "--no-ask-password", "poweroff"]] and b is not None
    assert monde.telegram.a_dit("Extinction dans 2 minutes") and monde.telegram.confirmes == 1


def test_veille_avec_reveil(monde):
    lancer(monde, une_fois(VEILLE), fin="demander")
    (commande,) = actions(monde)
    assert commande[0] == "systemd-run" and commande[-3:] == ["systemctl", "--no-ask-password", "suspend"]
    assert monde.telegram.a_dit("Réveil le 27/11 à 09:00")


@pytest.mark.parametrize("titre", [ETEINDRE, VEILLE])
def test_annuler(monde, titre):
    lancer(monde, plusieurs(une_fois(titre), une_fois("Annuler")), fin="demander")
    assert actions(monde) == [] and monde.telegram.a_dit("annulée")


def test_sans_clic_rien(monde):
    debut = monde.horloge.maintenant()
    lancer(monde, fin="demander", fin_attente_min=30)
    assert actions(monde) == [] and monde.horloge.maintenant() - debut >= timedelta(minutes=30)


@pytest.mark.parametrize("fin, mot", [("eteindre", "poweroff"), ("veille", "suspend")])
def test_fin_automatique_annulable(monde, fin, mot):
    lancer(monde, fin=fin)
    assert len(actions(monde)) == 1 and mot in actions(monde)[0]
    monde.commandes.clear()
    lancer(monde, une_fois("Annuler"), fin=fin)
    assert actions(monde) == []


def test_fin_rien_aucun_bouton(monde):
    lancer(monde, fin="rien")
    assert ETEINDRE not in monde.telegram.boutons and monde.commandes == []


@pytest.mark.parametrize("type_", ["analyse", "recherche", "spontanees"])
def test_jamais_si_un_traitement_tourne(monde, type_):
    """Celui de n'importe quel utilisateur, y compris démarré pendant les 2 minutes."""
    verrou = Verrou(nom_pipeline(type_, 99))
    assert verrou.prendre()
    lancer(monde, une_fois(ETEINDRE), fin="demander", fin_attente_min=5)
    assert actions(monde) == [] and monde.telegram.a_dit("un traitement tourne encore")
    verrou.liberer()

    def demarre_pendant(t):
        if t.a_dit("dans 2 minutes"):
            verrou.prendre()
        return une(t)
    une = une_fois(ETEINDRE)
    lancer(monde, demarre_pendant, fin="demander", fin_attente_min=5)
    assert actions(monde) == [] and monde.telegram.a_dit("a démarré entre-temps")
    verrou.liberer()


def test_jamais_pendant_un_envoi(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)

    def pendant(t):
        if t.boutons.get("Envoyer") and not t.accuses:
            return t.boutons["Envoyer"][:1]
        if monde.campagne._envoi_en_cours:
            return t.boutons[ETEINDRE][:1]
        return []
    lancer(monde, pendant, fin="demander", fin_attente_min=5)
    assert len(monde.smtp.messages) == 3 and actions(monde) == []
    assert "Campagne en cours : proposé à la fin." in monde.telegram.accuses


def test_eteindre_avec_des_envois_en_attente(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    b = lancer(monde, une_fois(ETEINDRE), fin="demander")
    assert len(actions(monde)) == 1 and monde.smtp.messages == []
    assert b["stage"]["validation"] == "extinction demandée" and len(envoi.pretes(monde.uid, MODE)) == 3
    assert monde.telegram.a_dit("ne partiront pas")


def test_envoyer_pendant_le_compte_a_rebours_annule(monde):
    ajouter_entreprises(monde.uid, entreprises(3), MODE)

    def envoyer_tard(t):
        return envoyer(t) if t.a_dit("dans 2 minutes") else []
    envoyer = une_fois("Envoyer")
    lancer(monde, plusieurs(une_fois(ETEINDRE), envoyer_tard), fin="demander", fin_attente_min=5)
    assert actions(monde) == [] and len(monde.smtp.messages) == 3


def test_sans_message_d_annulation_pas_d_extinction(monde):
    class Muet(FauxTelegram):
        def envoyer(self, texte, boutons=None):
            if "dans 2 minutes" in texte:
                raise telegram.ErreurTelegram("Telegram injoignable")
            return super().envoyer(texte, boutons)
    t = Muet(monde.horloge)
    C.Campagne(monde.uid, ["stage"], C.Reglages(cible=1, fin="eteindre"), t, monde.horloge).executer()
    assert actions(monde) == []


def test_autorisation_manquante(monde):
    monde.logind = 's "challenge"'
    lancer(monde, fin="eteindre")
    assert actions(monde) == [] and monde.telegram.a_dit("règle polkit")


def test_pas_de_veille_sans_reveil(monde, monkeypatch):
    monkeypatch.setattr(extinction, "_gestionnaire_peut_reveiller", lambda: False)
    lancer(monde, fin="veille")
    assert actions(monde) == [] and monde.telegram.a_dit("ne se réveillerait pas")


def test_capacite_de_reveil_lue(tmp_path, monkeypatch):
    monkeypatch.setattr(extinction, "PROC", tmp_path)
    monkeypatch.setenv("MANAGERPID", "7")
    (tmp_path / "7").mkdir()
    for valeur, attendu in (("0000000800000000", True), ("0000000000000000", False)):
        (tmp_path / "7" / "status").write_text(f"Name:\tsystemd\nCapEff:\t{valeur}\n")
        assert extinction._gestionnaire_peut_reveiller() is attendu


# ─── Telegram : qui a cliqué, secrets ─────────────────────────────────────────
class _Reponse:
    def __init__(self, corps):
        self.corps = corps

    def json(self):
        return self.corps


def _clic(update, auteur, chat, donnee="envoyer:x"):
    return {"update_id": update, "callback_query": {"id": str(update), "from": {"id": auteur}, "data": donnee,
                                                    "message": {"message_id": 1, "chat": {"id": chat}}}}


def test_seul_mon_identifiant_est_accepte(monkeypatch):
    majs = [_clic(1, 42, 42), _clic(2, 666, 666), _clic(3, 666, 42), _clic(4, 42, -100), {"update_id": 5, "message": {}},
            {"update_id": 6, "callback_query": {"id": "6", "from": {"id": 42}, "data": "envoyer:x"}}]
    charges = []
    monkeypatch.setattr(telegram, "_poster", lambda url, charge, delai: charges.append(charge) or _Reponse(
        {"ok": True, "result": majs}))
    t = telegram.Telegram("JETON", "42")
    assert [c.id for c in t.clics()] == ["1"]
    t.clics()
    assert charges[1]["offset"] == 7                        # les autres sont lus, donc oubliés


def test_jeton_jamais_dans_une_erreur(monkeypatch):
    def panne(url, charge, delai):
        raise telegram.requests.ConnectionError(f"échec vers {url}")
    monkeypatch.setattr(telegram, "_poster", panne)
    t = telegram.Telegram("SECRET123", "42")
    with pytest.raises(telegram.ErreurTelegram) as e:
        t.envoyer("x")
    assert "SECRET123" not in str(e.value) and e.value.__cause__ is None
    monkeypatch.setattr(telegram, "_poster", lambda *a: _Reponse({"ok": False, "description": "bad SECRET123"}))
    with pytest.raises(telegram.ErreurTelegram) as e:
        t.envoyer("x")
    assert "SECRET123" not in str(e.value)


def test_message_long_decoupe_boutons_sous_le_dernier(monkeypatch):
    charges = []
    monkeypatch.setattr(telegram, "_poster", lambda url, c, d: charges.append(c) or _Reponse(
        {"ok": True, "result": {"message_id": len(charges)}}))
    texte = "\n".join(f"{i}. " + "x" * 90 for i in range(100))
    assert telegram.Telegram("J", "42").envoyer(texte, [("Envoyer", "envoyer:1")]) == len(charges) > 1
    assert all(len(c["text"]) <= 4000 for c in charges) and "\n".join(c["text"] for c in charges) == texte
    assert [("reply_markup" in c) for c in charges] == [False] * (len(charges) - 1) + [True]


@pytest.mark.parametrize("chat", ["-100123", "moi", "4²"])
def test_identifiant_de_groupe_refuse(monkeypatch, chat):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "J")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", chat)
    with pytest.raises(telegram.ErreurTelegram):
        telegram.depuis_env()


# ─── Réponse aux clics avant toute action (D214) ──────────────────────────────
class _Serveur:
    """Faux serveur Telegram, sous le vrai client : note chaque appel dans
    l'ordre ; a_l_envoi(serveur, boutons) ajoute des clics après un message."""

    def __init__(self, monkeypatch, a_l_envoi):
        import threading
        self.faits, self.attente, self.a_l_envoi, self.n = [], [], a_l_envoi, 0
        self.change = threading.Condition()
        monkeypatch.setattr(telegram, "_poster", self._poster)

    def noter(self, *fait):
        with self.change:
            self.faits.append(fait)
            self.change.notify_all()

    def cliquer(self, donnee):
        self.n += 1
        self.attente.append(_clic(self.n, 42, 42, donnee))

    def reponses(self):
        return [f[1] for f in self.faits if f[0] == "reponse"]

    def attendre_reponses(self, nombre):
        with self.change:
            return self.change.wait_for(lambda: len(self.reponses()) >= nombre, timeout=5)

    def _poster(self, url, charge, delai):
        methode, resultat = url.rsplit("/", 1)[1], True
        if methode == "getUpdates":
            with self.change:
                if not self.attente:
                    self.change.wait(0.01)
            resultat, self.attente = self.attente, []
        elif methode == "answerCallbackQuery":
            self.noter("reponse", charge["text"])
        elif methode == "sendMessage":
            self.noter("message", charge["text"])
            resultat = {"message_id": len(self.faits)}
            boutons = {b["text"]: b["callback_data"] for b in charge.get("reply_markup", {}).get("inline_keyboard", [[]])[0]}
            self.a_l_envoi(self, boutons)
        return _Reponse({"ok": True, "result": resultat})


class _HorlogeFixe:
    """Toujours 9 h : seuls les clics font avancer la campagne."""

    def maintenant(self):
        return datetime(2026, 11, 26, 9, 0, tzinfo=PARIS)

    def dormir(self, secondes):
        import time
        time.sleep(0.005)


def avec_serveur(monde, monkeypatch, a_l_envoi, modes=("stage",), ecoute=True, horloge=None):
    serveur = _Serveur(monkeypatch, a_l_envoi)
    vrai = envoi.envoyer_mail

    def envoyer_mail(*a, **k):
        serveur.noter("mail")
        return vrai(*a, **k)
    monkeypatch.setattr(envoi, "envoyer_mail", envoyer_mail)
    monkeypatch.setattr(C, "PAUSE_ENVOIS", (0, 0))
    c = C.Campagne(monde.uid, modes, C.Reglages(cible=2, fin="rien").verifier(), telegram.Telegram("J", "42"),
                   horloge or _HorlogeFixe(), ecoute=ecoute)
    return serveur, c


@pytest.mark.parametrize("ecoute", [True, False])
def test_reponse_au_clic_avant_l_envoi(monde, monkeypatch, ecoute):
    ajouter_entreprises(monde.uid, entreprises(2), MODE)
    serveur, c = avec_serveur(monde, monkeypatch, lambda s, b: "Voir d'abord" in b and s.cliquer(b["Envoyer"]),
                              ecoute=ecoute)
    c.executer()
    noms = [f[0] for f in serveur.faits]
    assert noms.count("mail") == 2 and serveur.reponses() == ["Envoi noté."]
    assert noms.index("reponse") < noms.index("mail")


@pytest.mark.parametrize("ecoute", [True, False])
def test_tous_les_clics_ont_leur_reponse_avant_la_premiere_action(monde, monkeypatch, ecoute):
    """« Voir d'abord » envoie un long message : il ne retarde pas la réponse au clic suivant."""
    ajouter_entreprises(monde.uid, entreprises(2), MODE)

    def deux_clics(s, b):
        if "Voir d'abord" in b:
            with s.change:
                s.cliquer(b["Voir d'abord"])
                s.cliquer(b["Envoyer"])
    serveur, c = avec_serveur(monde, monkeypatch, deux_clics, ecoute=ecoute)
    c.executer()
    reponses = [i for i, f in enumerate(serveur.faits) if f[0] == "reponse"]
    vu = next(i for i, f in enumerate(serveur.faits) if f[0] == "message" and "👀" in f[1])
    assert serveur.reponses() == ["Rien n'est parti.", "Envoi noté."] and max(reponses) < vu


def test_reponse_pendant_la_recherche_du_mode_suivant(monde, monkeypatch):
    """« Envoyer » du stage pendant que job cherche ses emails : réponse immédiate,
    l'envoi suit la recherche."""
    ajouter_entreprises(monde.uid, entreprises(2), MODE)
    ajouter_entreprises(monde.uid, entreprises(2, "Job"), "job")
    serveur, c = avec_serveur(monde, monkeypatch, lambda s, b: "Voir d'abord" in b and s.cliquer(b["Envoyer"]),
                              modes=("stage", "job"))
    vrai, vu = C.recherche_emails.main, []

    def lente(*a, mode=MODE, **k):
        if mode == "job":
            vu.append(serveur.attendre_reponses(1) and serveur.reponses() == ["Envoi noté."])
        return vrai(*a, mode=mode, **k)
    monkeypatch.setattr(C.recherche_emails, "main", lente)
    b = c.executer()
    assert vu == [True] and b["stage"]["envoyes"] == b["job"]["envoyes"] == 2


def test_reponse_pendant_l_envoi_d_un_mail(monde, monkeypatch):
    ajouter_entreprises(monde.uid, entreprises(2), MODE)
    boutons = {}

    def premier_clic(s, b):
        if "Voir d'abord" in b:
            boutons.update(b)
            s.cliquer(b["Envoyer"])
    serveur, c = avec_serveur(monde, monkeypatch, premier_clic)
    vrai, vu = envoi.envoyer_mail, []

    def mail_lent(*a, **k):
        if not vu:
            serveur.cliquer(boutons["Envoyer"])          # second clic, pendant le mail
            vu.append(serveur.attendre_reponses(2))
        return vrai(*a, **k)
    monkeypatch.setattr(envoi, "envoyer_mail", mail_lent)
    b = c.executer()
    assert vu == [True] and serveur.reponses() == ["Envoi noté.", "Ce bouton n'est plus valable."]
    assert b["stage"]["envoyes"] == 2


def test_ecoute_survit_a_une_panne(monde, monkeypatch):
    monkeypatch.setattr(C, "REPRISE_ECOUTE_S", 0)
    ajouter_entreprises(monde.uid, entreprises(2), MODE)
    serveur, c = avec_serveur(monde, monkeypatch, lambda s, b: "Voir d'abord" in b and s.cliquer(b["Envoyer"]))
    lire, n = c.recevoir, []

    def capricieux(attente=0):
        n.append(1)
        if len(n) in (1, 2):
            raise telegram.ErreurTelegram("Telegram injoignable (essai)")
        return lire(attente)
    monkeypatch.setattr(c, "recevoir", capricieux)
    assert c.executer()["stage"]["envoyes"] == 2
    assert campagnes_db.derniere(monde.uid)["journal"].count("injoignable (essai)") == 1
    assert c._ecoute is None                                  # arrêtée avec la campagne


# ─── Réel ou essai, à côté du bouton (D214) ───────────────────────────────────
@pytest.mark.parametrize("essai, dit, tu", [
    (False, "ENVOI RÉEL aux entreprises", "MODE ESSAI"),
    (True, "MODE ESSAI : les mails arriveront chez toi", "ENVOI RÉEL")])
def test_resume_dit_reel_ou_essai(monde, essai, dit, tu):
    """Le réglage est celui que l'interface écrit et affiche (comptes_envoi.mode_test)."""
    client = monde.client
    r = client.post("/api/compte_envoi/mode_test", json={"actif": essai})
    assert r.json()["compte"]["mode_test"] is essai
    ajouter_entreprises(monde.uid, entreprises(3), MODE)
    lancer(monde, plusieurs(une_fois("Voir d'abord"), une_fois("Envoyer", 1)))
    avec_bouton = [m for m in monde.telegram.messages if "📬" in m or "👀" in m]
    assert len(avec_bouton) == 2 and all(dit in m and tu not in m for m in avec_bouton)
    assert avec_bouton[0].endswith(dit)                       # juste au-dessus des boutons, même en liste longue
    assert (destinataires(monde) == [["ada@gmail.com"]] * 3) is essai
    assert client.get("/api/compte_envoi").json()["compte"]["mode_test"] is essai


# ─── Script et réglages ───────────────────────────────────────────────────────
@pytest.mark.parametrize("variable, valeur", [
    ("CAMPAGNE_VALIDATION", "peut-etre"), ("CAMPAGNE_FIN", "boum"), ("CAMPAGNE_HEURE_LIMITE", "25h"),
    ("CAMPAGNE_DUREE_MAX_MIN", "deux"), ("CAMPAGNE_MAX_ENTREPRISES", "0")])
def test_reglage_illisible_rien_ne_demarre(monkeypatch, variable, valeur):
    monkeypatch.setenv(variable, valeur)
    with pytest.raises(ErreurUtilisateur):
        C.reglages_env()


def test_defauts_et_variables_documentees(monkeypatch):
    for v in C._VARIABLES.values():
        monkeypatch.delenv(v, raising=False)
    r = C.reglages_env()
    assert (r.validation, r.heure_limite, r.fin, r.cible) == ("telegram", "16:00", "demander", 30)
    texte = (config.BASE_DIR / ".env.example").read_text(encoding="utf-8")
    for v in (*C._VARIABLES.values(), "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        assert f"\n{v}=" in texte
    assert "\nTELEGRAM_BOT_TOKEN=\n" in texte and "\nTELEGRAM_CHAT_ID=\n" in texte


def test_script(monde, monkeypatch, capsys):
    from scripts import campagne as script
    for v in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", *C._VARIABLES.values()):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(script.signal, "signal", lambda *a: None)
    assert script.main(["--utilisateur", str(monde.uid)]) == 1 and "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err
    monkeypatch.setenv("CAMPAGNE_VALIDATION", "auto")
    monkeypatch.setenv("CAMPAGNE_FIN", "eteindre")
    assert script.main(["--utilisateur", str(monde.uid)]) == 1            # extinction sans annulation possible
    monkeypatch.setenv("CAMPAGNE_FIN", "rien")
    assert script.main(["--utilisateur", "999"]) == 1
    assert script.main(["--utilisateur", str(monde.uid), "--modes", "stage,autre"]) == 1
    autre = Verrou(CAMPAGNE)
    autre.prendre()
    assert script.main(["--utilisateur", str(monde.uid), "--modes", "stage"]) == 3
    autre.liberer()
    monkeypatch.setattr(envoi, "PAUSE_ENTRE_MAILS", (0, 0))
    ajouter_entreprises(monde.uid, entreprises(2), MODE)
    monkeypatch.setattr(C, "PAUSE_ENVOIS", (0, 0))
    assert script.main(["--utilisateur", str(monde.uid), "--modes", "stage", "--cible", "2"]) == 0
    assert len(monde.smtp.messages) == 2


# ─── Fichiers de déploiement ──────────────────────────────────────────────────
def test_unites_et_regle_polkit():
    deploy = config.BASE_DIR / "deploy"
    minuteur = (deploy / "systemd" / "chasseur-campagne.timer").read_text(encoding="utf-8")
    for ligne in ("OnCalendar=Mon..Fri *-*-* 07:00:00", "Persistent=true", "WakeSystem=true"):
        assert ligne in minuteur
    service = (deploy / "systemd" / "chasseur-campagne.service").read_text(encoding="utf-8")
    assert "scripts/campagne.py --utilisateur 1 --modes stage,job --cible 30" in service
    import re
    regle = (deploy / "polkit" / "50-chasseur-extinction.rules").read_text(encoding="utf-8")
    assert set(re.findall(r"org\.freedesktop[\w.-]+", regle)) == {"org.freedesktop.login1.power-off",
                                                                 "org.freedesktop.login1.suspend"}
    assert 'subject.user === "UTILISATEUR"' in regle
