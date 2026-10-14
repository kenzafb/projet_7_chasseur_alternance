"""Contenus envoyés à l'IA ou aux entreprises : aucune mention d'un
utilisateur réel, pas de genre imposé, pas de date en dur, préférences
tirées du profil, trames adaptées au mode."""

import pathlib
import re

import pytest

import spontanees.envoyeur as envoyeur
from france_travail import analyseur, generateur
from france_travail.pdf_generator import construire_html
from shared import config

# Traces d'utilisateurs réels (identité, établissements, expériences,
# préférences personnelles autrefois écrites en dur)
MENTIONS_REELLES = [
    "kenza", "filali", "bouami", "zeinab", "toure", "aïcha", "aicha", "fofana",
    "garage numérique", "orma", "deust", "iosi", "cnam", "devops",
    "linux", "docker", "gardiennage", "billetterie", "téléconseil", "paris 9", "9e",
]
# Accords de genre imposés à la personne candidate
GENRE_IMPOSE = [
    "une candidate", "la candidate", "de la candidate", "rigoureuse", "habituée", "passionnée",
    "sérieux(se)", "ravi(e)", "impliqué(e)", "désireux(se)",
]
ANNEE = re.compile(r"\b20\d\d\b")

PROFIL = {
    "prenom": "Camille", "nom": "Martin", "email": "camille@exemple.fr", "telephone": "06 00 00 00 00",
    "ville": "Lyon", "competences": ["Excel", "Accueil"], "formation": "BTS", "experience": "Vente",
    "recherche": {"domaines": ["informatique"]},
    "types_jobs_ok": "TYPES-OK-DU-PROFIL", "types_jobs_eviter": "TYPES-EVITER-DU-PROFIL",
    "dispo_horaires": "HORAIRES-DU-PROFIL", "mobilite": "MOBILITE-DU-PROFIL",
    "duree_souhaitee": "DUREE-DU-PROFIL", "localisation_pref": "LOCALISATION-DU-PROFIL",
}
OFFRE = {"id": "R1", "titre": "Vendeur", "entreprise": "ACME", "lieu": "Lyon", "description": "Vente en magasin"}


def _sans_mention_reelle(texte, quoi):
    bas = texte.lower()
    for mot in MENTIONS_REELLES + GENRE_IMPOSE:
        assert not re.search(r"(?<![a-z])" + re.escape(mot) + r"(?![a-z])", bas), f"{quoi} : « {mot} »"


def _prompts(ia):
    return "\n".join(m["content"] for appel in ia.appels for m in appel["messages"])


# ─── Prompts ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("mode", ["alternance", "job", "stage"])
def test_prompts_sans_mention_d_un_utilisateur_reel(ia, mode):
    generateur.generer_lettre(OFFRE, PROFIL, mode=mode)
    ia.reponse = '{"score": 7, "eligible": true, "points_forts": [], "points_faibles": [], "domaine": "Vente", "resume": "ok"}'
    analyseur.analyser_offre(OFFRE, PROFIL, mode=mode)
    texte = _prompts(ia)
    assert len(ia.appels) == 2
    _sans_mention_reelle(texte, f"prompts {mode}")
    assert not ANNEE.search(texte)


def test_prompt_de_lettre_neutre_et_fonde_sur_le_profil(ia):
    generateur.generer_lettre(OFFRE, PROFIL, mode="alternance")
    texte = _prompts(ia)
    assert "personne candidate" in texte and "neutre" in texte
    assert "Excel, Accueil" in texte                       # bagage réel du profil
    assert "N'invente AUCUNE compétence" in texte


def test_analyse_job_tire_les_preferences_du_profil(ia):
    ia.reponse = '{"score": 7, "eligible": true, "points_forts": [], "points_faibles": [], "domaine": "Vente", "resume": "ok"}'
    analyseur.analyser_offre(OFFRE, PROFIL, mode="job")
    texte = _prompts(ia)
    for valeur in ("TYPES-OK-DU-PROFIL", "TYPES-EVITER-DU-PROFIL", "HORAIRES-DU-PROFIL",
                   "MOBILITE-DU-PROFIL", "DUREE-DU-PROFIL", "LOCALISATION-DU-PROFIL",
                   "Systèmes d'information et de télécommunication"):
        assert valeur in texte, valeur
    # Plus de préférence personnelle écrite en dur
    for mot in ("calme", "surveillance", "pénibilité", "arrondissement"):
        assert mot not in texte.lower(), mot
    assert "N'applique AUCUNE préférence que le profil n'exprime pas" in texte


REPONSE = '{"score": 7, "eligible": true, "points_forts": [], "points_faibles": [], "domaine": "Vente", "resume": "ok"}'
PROFIL_STAGE = {"prenom": "Camille", "formation": "Licence 3 informatique", "etablissement": "Université X",
                "missions": "MISSIONS-DU-PROFIL", "date_debut": "2027-01-04", "date_fin": "2027-06-25",
                "duree_semaines": 25, "recherche": {"domaines": ["M18"]}}


@pytest.mark.parametrize("mode", ["alternance", "job", "stage"])
def test_prompt_court_avec_schema_explicite(ia, mode, monkeypatch):
    ia.reponse = REPONSE
    monkeypatch.setenv("IA_LONGUEUR_DESCRIPTION", "300")
    offre = {**OFFRE, "description": "mot " * 2000}
    analyseur.analyser_offre(offre, PROFIL_STAGE if mode == "stage" else PROFIL, mode=mode)
    texte = _prompts(ia)
    assert '"score": <entier de 1 à 10>' in texte and '"eligible": <true ou false>' in texte
    assert len(texte) < 4500                                  # description tronquée à 300 caractères
    assert "Camille" not in texte and "06 00" not in texte    # identité inutile à la notation


def test_prompt_stage(ia):
    ia.reponse = REPONSE
    analyseur.analyser_offre(OFFRE, PROFIL_STAGE, mode="stage")
    texte = _prompts(ia)
    assert "offre de stage" in texte and "MISSIONS-DU-PROFIL" in texte
    assert "du 4 janvier 2027 au 25 juin 2027 (25 semaines)" in texte
    assert "Licence 3 informatique" in texte and "Université X" in texte
    assert "dates sont incompatibles" in texte and "Hors domaine" in texte
    assert "Systèmes d'information" in texte


def test_prompt_alternance_garde_ses_regles(ia):
    ia.reponse = REPONSE
    analyseur.analyser_offre(OFFRE, {**PROFIL, "niveau_vise": "NIVEAU-VISE", "formation_apporte": "APPORT"})
    texte = _prompts(ia)
    for attendu in ("NIVEAU-VISE", "APPORT", "3 ans d'expérience", "Hors domaine", "point faible mineur",
                    "La date de début et la disponibilité ne comptent pas"):
        assert attendu in texte, attendu


@pytest.mark.parametrize("mode, archive", [("alternance", True), ("stage", False)])
def test_ecole_archivee_en_alternance_seulement(ia, mode, archive):
    ia.reponse = REPONSE
    analyse = analyseur.analyser_offre({**OFFRE, "entreprise": "Epitech"}, PROFIL_STAGE, mode=mode)
    assert (analyse.get("statut_auto") == "archive") is archive


# ─── Trames par défaut ────────────────────────────────────────────────────────
def test_trames_par_defaut_generiques():
    for mode, lettre in generateur.LETTRES_PAR_DEFAUT.items():
        generateur.preparer_lettre_type(lettre)   # balises valides
        _sans_mention_reelle(lettre, f"lettre {mode}")
        assert not ANNEE.search(lettre) and "rentrée" not in lettre.lower()
    for mode in envoyeur.OBJETS_PAR_DEFAUT:
        texte = envoyeur.OBJETS_PAR_DEFAUT[mode] + envoyeur.TRAMES_PAR_DEFAUT[mode]
        _sans_mention_reelle(texte, f"mail {mode}")
        assert not ANNEE.search(texte) and "rentrée" not in texte.lower()
    assert "alternance" in generateur.lettre_par_defaut("alternance").lower()
    for texte in (generateur.lettre_par_defaut("job"), envoyeur.OBJETS_PAR_DEFAUT["job"],
                  envoyeur.TRAMES_PAR_DEFAUT["job"]):
        assert "alternance" not in texte.lower()


@pytest.mark.parametrize("mode", ["alternance", "job"])
def test_lettre_generee_avec_la_trame_du_mode(ia, mode):
    lettre = generateur.generer_lettre(OFFRE, PROFIL, mode=mode)
    assert ("alternance" in lettre.lower()) == (mode == "alternance")
    assert "ACME, votre contexte me parle." in lettre


def test_lettre_type_du_profil_prioritaire(ia):
    profil = {**PROFIL, "lettre_type": "Ma trame. {paragraphe_entreprise}"}
    assert generateur.generer_lettre(OFFRE, profil, mode="job").startswith("Ma trame. ACME")


# ─── Mail de candidature spontanée ────────────────────────────────────────────
def test_objet_et_corps_tires_du_profil_du_mode():
    profil = {**PROFIL, "email_objet": "Mon objet\nBcc: x@y.fr", "email_type": "Mon message."}
    assert envoyeur.objet_et_corps(profil, "job") == ("Mon objet\nBcc: x@y.fr", "Mon message.")
    objet, corps = envoyeur.objet_et_corps(PROFIL, "job")
    assert objet == "Candidature spontanée"
    assert corps.startswith(envoyeur.TRAMES_PAR_DEFAUT["job"])
    assert corps.endswith("Camille Martin\n06 00 00 00 00\ncamille@exemple.fr")
    objet, _ = envoyeur.objet_et_corps({}, "alternance")
    assert objet == "Candidature spontanée en alternance"


def test_objet_du_profil_dans_le_mail_envoye(utilisateur, smtp_simule, monkeypatch):
    from database.entreprises_db import ajouter_entreprises, lire_entreprises, sauvegarder_enrichissement
    from tests.conftest import compte_verifie
    client, user_id = utilisateur("ada@test.fr", prenom="Ada", nom="L")
    compte_verifie(smtp_simule, user_id, "ada@gmail.com")
    client.mode = "job"
    client.post("/api/profil", json={"email_objet": "Objet job\r\nBcc: espion@x.fr", "email_type": "Corps job"})
    assert client.get("/api/profil").json()["email_objet"].startswith("Objet job")
    ajouter_entreprises(user_id, [{"siret": "S1", "nom": "ACME"}], mode="job")
    liste = lire_entreprises(user_id, "job")
    liste[0]["emails_trouves"] = ["rh@acme.fr"]
    sauvegarder_enrichissement(user_id, liste)

    envoyeur.main(user_id, limite=1, mode="job")
    (_, _, to, message), = smtp_simule.messages
    assert to == ["rh@acme.fr"]
    assert message["Subject"] == "Objet job Bcc: espion@x.fr"   # une seule ligne : pas d'en-tête injecté
    assert message["Bcc"] is None
    assert message.get_content().strip() == "Corps job"


def test_pdf_sans_lieu_ni_objet_en_dur():
    html = construire_html({"titre": "", "entreprise": "ACME"}, "Madame, Monsieur,\n\nTexte.", PROFIL)
    assert "Lyon, le" in html and "Paris" not in html
    assert "Alternance" not in html
    html = construire_html(OFFRE, "Madame, Monsieur,", {**PROFIL, "ville": ""})
    assert '<div class="date-lieu">Le ' in html


# ─── Code actif ───────────────────────────────────────────────────────────────
def test_code_actif_sans_mention_d_un_utilisateur_reel():
    racine = pathlib.Path(config.BASE_DIR)
    fichiers = [racine / "main.py", racine / "README.md", racine / ".env.example"]
    for dossier in ("auth", "database", "france_travail", "scripts", "shared", "spontanees",
                    "static", "templates", "alembic"):
        fichiers += [f for f in (racine / dossier).rglob("*")
                     if f.suffix in (".py", ".js", ".html", ".css") and f.name != "profil.py"]
    noms = ["kenza", "filali", "bouami", "zeinab", "fofana", "garage numérique", "deust", "iosi", "cnam"]
    for chemin in fichiers:
        texte = chemin.read_text(encoding="utf-8").lower()
        for nom in noms:
            assert nom not in texte, f"{chemin.relative_to(racine)} : « {nom} »"
