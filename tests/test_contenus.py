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


def _paragraphe(profil, mode="alternance"):
    """Paragraphe rédigé avec l'exemple de lettre type du mode (D106)."""
    return generateur.rediger_paragraphe(OFFRE, profil, mode, lettre_type=generateur.lettre_par_defaut(mode))


def _prompts(ia):
    return "\n".join(m["content"] for appel in ia.appels for m in appel["messages"])


# ─── Prompts ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("mode", ["alternance", "job", "stage"])
def test_prompts_sans_mention_d_un_utilisateur_reel(ia, mode):
    _paragraphe(PROFIL, mode)
    ia.reponse = '{"score": 7, "eligible": true, "points_forts": [], "points_faibles": [], "domaine": "Vente", "resume": "ok", "niveau_requis": "non_precise", "duree_mois": null, "date_debut_offre": null, "alternance_seulement": false, "niveau_exigence": "non_precise"}'
    analyseur.analyser_offre(OFFRE, PROFIL, mode=mode)
    texte = _prompts(ia)
    assert len(ia.appels) == 2
    _sans_mention_reelle(texte, f"prompts {mode}")
    assert not ANNEE.search(texte)


def test_prompt_de_lettre_neutre_et_fonde_sur_le_profil(ia):
    _paragraphe(PROFIL)
    texte = _prompts(ia)
    assert "personne candidate" in texte and "neutre" in texte
    assert "Excel, Accueil" in texte                       # bagage réel du profil
    assert "n'invente rien" in texte


def test_analyse_job_tire_les_preferences_du_profil(ia):
    ia.reponse = '{"score": 7, "eligible": true, "points_forts": [], "points_faibles": [], "domaine": "Vente", "resume": "ok", "niveau_requis": "non_precise", "duree_mois": null, "date_debut_offre": null, "alternance_seulement": false, "niveau_exigence": "non_precise"}'
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


REPONSE = '{"score": 7, "eligible": true, "points_forts": [], "points_faibles": [], "domaine": "Vente", "resume": "ok", "niveau_requis": "non_precise", "duree_mois": null, "date_debut_offre": null, "alternance_seulement": false, "niveau_exigence": "non_precise"}'
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
    assert '"score": <entier de 0 à 10>' in texte and '"niveau_exigence"' in texte
    assert '"eligible"' not in texte                          # le modèle ne décide plus de l'éligibilité (D99)
    assert len(texte) < 4500                                  # description tronquée à 300 caractères
    assert "Camille" not in texte and "06 00" not in texte    # identité inutile à la notation


def test_prompt_stage(ia):
    ia.reponse = REPONSE
    analyseur.analyser_offre(OFFRE, PROFIL_STAGE, mode="stage")
    texte = _prompts(ia)
    assert "offre de stage" in texte and "MISSIONS-DU-PROFIL" in texte
    assert "du 4 janvier 2027 au 25 juin 2027 (25 semaines)" in texte
    assert "Licence 3 informatique" in texte and "Université X" in texte
    assert "Hors domaine" in texte and "duree_mois" in texte and "date_debut_offre" in texte
    assert "nettement supérieur" not in texte and "dates sont incompatibles" not in texte   # vérifiés en Python
    assert "réserve 8 à 10" in texte
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


# ─── Lettre type et paragraphe personnalisé (D106) ───────────────────────────
LETTRE_TYPE = "{contact_entreprise}\nObjet : {poste}\nMadame, Monsieur,\nJ'aime {entreprise}.\n{paragraphe}\nCordialement."


@pytest.mark.parametrize("mode", ["alternance", "job", "stage"])
def test_paragraphe_par_le_modele_de_lettre(ia, mode):
    assert _paragraphe(PROFIL, mode) == "ACME, votre contexte me parle."
    assert ia.appels[-1]["model"] == "ministral-3:8b"
    assert ia.appels[-1]["format"]["title"] == "ParagrapheIA" and ia.appels[-1]["options"]["temperature"] == 0.6
    assert f"candidate à {generateur.POSTE_PAR_MODE[mode]}" in ia.textes()


def test_prompt_du_paragraphe(ia):
    generateur.rediger_paragraphe(OFFRE, {**PROFIL, "missions": "MISSIONS-VISEES"}, "stage", lettre_type=LETTRE_TYPE)
    texte = ia.textes(0)
    for attendu in ("MISSIONS-VISEES", "Vente en magasin", "3 à 5 phrases", "première personne",
                    "ce qui l'attire dans cette entreprise et ce poste", "élément réel de son profil",
                    "pas de formule de politesse",
                    "ni markdown, ni tiret cadratin, ni esperluette, ni le mot « expertise »",
                    "J'aime", '{"paragraphe": "<le paragraphe>"}'):
        assert attendu in texte, attendu
    assert "{paragraphe}" not in texte and "{entreprise}" not in texte   # balises retirées du rappel de la lettre


def test_assemblage_en_python():
    profil = {**PROFIL, "lettre_type": LETTRE_TYPE}
    lettre = generateur.assembler_lettre({**OFFRE, "lieu": "Lyon"}, profil, "  Mon   paragraphe.  ")
    assert lettre == "ACME\nLyon\nObjet : Vendeur\nMadame, Monsieur,\nJ'aime ACME.\nMon paragraphe.\nCordialement."
    ancienne = {**PROFIL, "lettre_type": "Le {date}\n{paragraphe_entreprise}"}       # ancien nom de la balise
    assert generateur.assembler_lettre(OFFRE, ancienne, "P.").endswith("\nP.")


@pytest.mark.parametrize("lettre_type, message", [
    ("", "Écris d'abord ta lettre type"),
    ("Madame, Monsieur, {entreprise}.", "n'a pas de balise {paragraphe}"),
])
def test_sans_lettre_type_ni_paragraphe_rien_n_est_genere(ia, lettre_type, message):
    profil = {**PROFIL, "lettre_type": lettre_type}
    with pytest.raises(generateur.LettreTypeInvalide, match=message):
        generateur.rediger_paragraphe(OFFRE, profil, "alternance")
    with pytest.raises(generateur.LettreTypeInvalide, match="Lettre de motivation type"):
        generateur.assembler_lettre(OFFRE, profil, "P.")
    assert ia.appels == []


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


# ─── Lettre : première personne, rien d'inventé, texte brut (après comparaison) ──
def test_consignes_de_la_lettre(ia):
    _paragraphe(PROFIL, "stage")
    texte = _prompts(ia)
    assert "première personne" in texte and "jamais « vous » pour parler d'elle" in texte
    assert "ne cite que des compétences et outils présents dans le profil ou l'offre" in texte
    assert "« expertise »" in texte and "ni markdown" in texte


@pytest.mark.parametrize("brut, propre", [
    ("**Orange SA**, votre projet *réseau* me parle.", "Orange SA, votre projet réseau me parle."),
    ("## ACME\n- 75010 Paris", "ACME\n75010 Paris"),
    ("Voir [le site](https://acme.fr) et `Python`.", "Voir le site et Python."),
    ("__ACME__ recrute ; mon_projet reste tel quel.", "ACME recrute ; mon_projet reste tel quel."),
    ("Un tiret-d'union, un 2 * 3 sans gras.", "Un tiret-d'union, un 2 3 sans gras."),
])
def test_markdown_retire(brut, propre):
    assert generateur.sans_markdown(brut) == propre


def test_paragraphe_nettoye(ia):
    ia.reponse = '{"paragraphe": "**ACME** — votre projet & vos équipes *me* parlent.\\n- Je veux apprendre."}'
    assert _paragraphe(PROFIL) == "ACME, votre projet et vos équipes me parlent. Je veux apprendre."


@pytest.mark.parametrize("mode", ["alternance", "job", "stage"])
def test_points_forts_tires_du_profil_seulement(mode):
    """D104 : le 3b citait « C/C++/Qt », « VoIP », absents du profil."""
    texte = analyseur.construire_messages(OFFRE, PROFIL, mode)[1]["content"]
    assert "points_forts : seulement des compétences, projets ou expériences écrits dans le PROFIL" in texte
    assert "jamais une compétence de l'offre absente du profil" in texte
    assert "Aucune compétence du profil ne correspond à l'offre" in texte


# ─── D108 : entreprise inconnue, balises laissées à compléter ────────────────
@pytest.mark.parametrize("nom", ["Inconnue", "", "  ", "non renseigné"])
def test_entreprise_inconnue_balises_laissees(nom):
    profil = {**PROFIL, "lettre_type": LETTRE_TYPE}
    lettre = generateur.assembler_lettre({**OFFRE, "entreprise": nom, "lieu": "Lyon"}, profil, "P.")
    assert lettre.startswith("{contact_entreprise}\nObjet : Vendeur") and "J'aime {entreprise}." in lettre
    assert generateur.marqueurs_a_completer(lettre) == ["entreprise", "contact_entreprise"]
    assert generateur.marqueurs_a_completer(generateur.assembler_lettre(OFFRE, profil, "P.")) == []


def test_route_signale_les_balises_a_completer(utilisateur, ia):
    from database.candidatures_db import ajouter_candidature
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    client.post("/api/profil", json={**PROFIL, "lettre_type": LETTRE_TYPE})
    ajouter_candidature(uid, {"id": "R1", "titre": "Dev", "entreprise": "Inconnue", "lieu": "Paris"})
    r = client.post("/api/lettre/assembler", json={"id": "R1", "paragraphe": "P."}).json()
    assert r["a_completer"] == ["entreprise", "contact_entreprise"]
    assert r["message"] == "Nom de l'entreprise inconnu, à compléter"
    js = (config.STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    assert "<mark>" in js and "Nom de l'entreprise inconnu, à compléter" in js
