"""Copie de sections du profil entre modes (phase 9, D117 et D118) :
sections copiables, aperçu, confirmation avant écrasement, isolation entre
utilisateurs, pièces jointes partagées par référence."""

import pytest

from database.profil_db import ajouter_piece_jointe, lire_profil, sauvegarder_profil
from shared import config
from shared.copie_profil import MODES_DU_CHAMP, SECTIONS, sections_copiables

PDF = b"%PDF-1.4 contenu de test"


def _cles(source, cible):
    return [s["cle"] for s in sections_copiables(source, cible)]


def _stage(uid):
    sauvegarder_profil(uid, {
        "prenom": "Ada", "nom": "Lovelace", "email": "ada@perso.fr", "telephone": "0600000000", "ville": "Paris",
        "linkedin": "linkedin.com/in/ada", "github": "github.com/ada", "formation": "BUT informatique",
        "niveau_etudes": "Bac+2", "experience": "Stage chez X", "competences": ["Python", "Linux"],
        "projets": [{"nom": "Chasseur", "url": "github.com/ada/c", "description": "Robot"}, {"nom": "", "url": "",
                                                                                              "description": ""}],
        "lettre_type": "Madame, Monsieur, {paragraphe}", "email_objet": "Candidature de {prenom}",
        "email_type": "Bonjour, {prenom} {nom}", "date_debut": "2027-04-01", "date_fin": "2027-06-30",
        "missions": "Développement", "portfolio": "https://ada.fr", "etablissement": "IUT",
        "recherche": {"domaines": ["M18"]}, "langues": "Anglais"}, mode="stage")


def _client(c, mode):
    c.mode = mode
    return c


# ─── Sections copiables ───────────────────────────────────────────────────────
def test_sections_copiables_selon_les_modes():
    tout = ["identite", "liens", "formation", "experience", "competences", "projets", "lettre_type", "email",
            "pieces_jointes"]
    assert _cles("stage", "alternance") == tout
    assert _cles("alternance", "stage") == tout
    # Formation et niveau d'études « actuel » : pas en job (niveau « obtenu »)
    assert _cles("stage", "job") == [c for c in tout if c != "formation"]
    assert _cles("job", "alternance") == [c for c in tout if c != "formation"]
    # Jamais ce qui est propre au mode, ni ce dont le sens change
    champs = {c for _, _, cs in SECTIONS for c in cs}
    for propre in ("recherche", "date_debut", "date_fin", "missions", "etablissement", "duree_souhaitee",
                   "types_jobs_ok", "niveau_vise", "formation_apporte", "criteres_eviter", "analyse_auto",
                   "langues", "dispo_horaires", "mobilite", "localisation_pref"):
        assert propre not in champs and propre not in MODES_DU_CHAMP


def test_meme_mode_ou_mode_inconnu_refuses(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Ada")
    assert client.get("/api/profil/copie/sections", params={"source": "alternance"}).status_code == 400
    assert client.get("/api/profil/copie/sections", params={"source": "pirate"}).status_code == 400
    r = client.get("/api/profil/copie/sections", params={"source": "stage"})
    assert r.status_code == 200 and r.json()["source_existe"] is False


# ─── Aperçu et copie ──────────────────────────────────────────────────────────
def test_apercu_puis_copie_vers_un_mode_vide(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    _stage(uid)
    _client(client, "job")
    r = client.post("/api/profil/copie/apercu", json={"source": "stage", "sections": ["competences", "projets"]})
    assert r.status_code == 200
    comp, proj = r.json()["sections"]
    assert comp["champs"][0]["copie"] == ["Python", "Linux"] and comp["champs"][0]["actuel"] == []
    assert not comp["a_confirmer"]
    assert proj["champs"][0]["copie"] == [{"nom": "Chasseur", "url": "github.com/ada/c", "description": "Robot"}]
    r = client.post("/api/profil/copie", json={"source": "stage", "sections": ["competences", "projets", "liens"]})
    assert r.status_code == 200 and r.json()["copiees"] == ["competences", "projets", "liens"]
    job = lire_profil(uid, mode="job")
    assert job["competences"] == ["Python", "Linux"] and job["github"] == "github.com/ada"
    assert job["projets"][0]["nom"] == "Chasseur"
    # Rien d'autre : ni les champs propres au stage, ni la recherche
    assert job["portfolio"] == "https://ada.fr"                          # avec les liens (D120)
    assert job["missions"] == "" and job["recherche"] == {} and job["langues"] == ""
    # La source n'est pas touchée
    assert lire_profil(uid, mode="stage")["missions"] == "Développement"


def test_identite_et_formation(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    _stage(uid)
    _client(client, "alternance")
    sauvegarder_profil(uid, {"prenom": "", "nom": "", "email": ""}, mode="alternance")
    r = client.post("/api/profil/copie/apercu", json={"source": "stage", "sections": ["identite", "formation"]})
    ident = r.json()["sections"][0]
    assert {x["champ"]: x["copie"] for x in ident["champs"]}["email"] == "ada@perso.fr"
    r = client.post("/api/profil/copie", json={"source": "stage", "sections": ["identite", "formation"],
                                               "ecraser": ["identite", "formation"]})
    assert r.status_code == 200
    alt = lire_profil(uid, mode="alternance")
    assert (alt["prenom"], alt["email"], alt["formation"], alt["niveau_etudes"]) == (
        "Ada", "ada@perso.fr", "BUT informatique", "Bac+2")


def test_section_remplie_demande_confirmation(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    _stage(uid)
    sauvegarder_profil(uid, {"competences": ["Java"], "experience": "Stage chez X"}, mode="alternance")
    _client(client, "alternance")
    r = client.post("/api/profil/copie/apercu", json={"source": "stage", "sections": ["competences", "experience"]})
    comp, exp = r.json()["sections"]
    assert comp["a_confirmer"] and comp["champs"][0]["actuel"] == ["Java"]
    assert not exp["a_confirmer"] and exp["identique"]                 # même valeur : rien à perdre
    r = client.post("/api/profil/copie", json={"source": "stage", "sections": ["competences"]})
    assert r.status_code == 400 and "confirme l'écrasement" in r.json()["erreur"]
    assert lire_profil(uid, mode="alternance")["competences"] == ["Java"]   # rien écrit
    r = client.post("/api/profil/copie", json={"source": "stage", "sections": ["competences"],
                                               "ecraser": ["competences"]})
    assert r.status_code == 200 and lire_profil(uid, mode="alternance")["competences"] == ["Python", "Linux"]


def test_email_avec_balise_du_stage_refuse_hors_stage(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    _stage(uid)
    sauvegarder_profil(uid, {"email_type": "Stage du {date_debut} au {date_fin}"}, mode="stage")
    _client(client, "job")
    r = client.post("/api/profil/copie/apercu", json={"source": "stage", "sections": ["email"]})
    assert "{date_debut}" in r.json()["sections"][0]["erreur"]
    r = client.post("/api/profil/copie", json={"source": "stage", "sections": ["email"], "ecraser": ["email"]})
    assert r.status_code == 400 and lire_profil(uid, mode="job").get("email_type", "") == ""


def test_section_non_copiable_ou_source_absente(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    _client(client, "job")
    r = client.post("/api/profil/copie", json={"source": "stage", "sections": ["competences"]})
    assert r.status_code == 400 and "Aucun profil" in r.json()["erreur"]
    _stage(uid)
    for sections in (["formation"], ["recherche"], []):                 # formation : pas en job
        r = client.post("/api/profil/copie", json={"source": "stage", "sections": sections})
        assert r.status_code == 400


# ─── Isolation ────────────────────────────────────────────────────────────────
def test_copie_seulement_entre_les_modes_du_meme_utilisateur(utilisateur):
    _, uid_ada = utilisateur("a@test.fr", prenom="Ada")
    _stage(uid_ada)
    bob, uid_bob = utilisateur("b@test.fr", prenom="Bob")
    _client(bob, "alternance")
    # Bob n'a pas de profil de stage : il ne reçoit jamais celui d'Ada
    r = bob.post("/api/profil/copie/apercu", json={"source": "stage", "sections": ["competences"]})
    assert r.json()["sections"][0]["champs"][0]["copie"] == []
    r = bob.post("/api/profil/copie", json={"source": "stage", "sections": ["competences"],
                                            "user_id": uid_ada})          # champ ignoré
    assert r.status_code == 400
    assert lire_profil(uid_bob, mode="alternance").get("competences", []) == []
    assert lire_profil(uid_ada, mode="alternance").get("competences", []) == []   # Ada non touchée


def test_routes_protegees():
    from fastapi.testclient import TestClient
    from main import app
    anonyme = TestClient(app)
    r = anonyme.post("/api/profil/copie?mode=job", json={"source": "stage", "sections": ["competences"]},
                     follow_redirects=False)
    assert r.status_code in (302, 303, 401)


# ─── Pièces jointes : références partagées (D118) ─────────────────────────────
def _envoyer(client, nom):
    r = client.post("/api/profil/upload", data={"nom": nom}, files={"fichier": (f"{nom}.pdf", PDF, "application/pdf")})
    assert r.status_code == 200, r.text


def _fichiers(uid):
    dossier = config.UPLOADS_DIR / f"user_{uid}"
    return sorted(p.name for p in dossier.iterdir()) if dossier.exists() else []


def test_pieces_jointes_partagees_par_reference(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    _stage(uid)
    _envoyer(_client(client, "stage"), "CV")
    assert len(_fichiers(uid)) == 1
    _envoyer(_client(client, "job"), "Ancien CV")
    r = client.post("/api/profil/copie", json={"source": "stage", "sections": ["pieces_jointes"],
                                               "ecraser": ["pieces_jointes"]})
    assert r.status_code == 200
    stage, job = lire_profil(uid, mode="stage"), lire_profil(uid, mode="job")
    assert job["pieces_jointes"] == stage["pieces_jointes"]               # même référence, pas de copie
    assert len(_fichiers(uid)) == 1                                        # ancien CV du job effacé (orphelin)
    assert client.get("/api/profil/piece", params={"nom": "CV"}).content == PDF
    # Supprimée en job : le fichier reste pour le stage
    assert client.post("/api/profil/piece/supprimer", json={"nom": "CV"}).status_code == 200
    assert len(_fichiers(uid)) == 1
    assert _client(client, "stage").get("/api/profil/piece", params={"nom": "CV"}).content == PDF
    # Supprimée aussi en stage : plus personne ne la référence, fichier effacé
    client.post("/api/profil/piece/supprimer", json={"nom": "CV"})
    assert _fichiers(uid) == []


def test_piece_remplacee_dans_un_mode_ne_change_pas_l_autre(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    _stage(uid)
    _envoyer(_client(client, "stage"), "CV")
    _client(client, "alternance").post("/api/profil/copie", json={"source": "stage", "sections": ["pieces_jointes"]})
    avant = lire_profil(uid, mode="stage")["pieces_jointes"]
    r = client.post("/api/profil/upload", data={"nom": "CV"},
                    files={"fichier": ("CV.pdf", b"%PDF nouvelle version", "application/pdf")})
    assert r.status_code == 200
    assert lire_profil(uid, mode="stage")["pieces_jointes"] == avant      # le stage garde l'ancien fichier
    assert client.get("/api/profil/piece", params={"nom": "CV"}).content == b"%PDF nouvelle version"
    assert len(_fichiers(uid)) == 2


def test_ajouter_piece_jointe_reste_par_mode(utilisateur):
    _, uid = utilisateur("a@test.fr", prenom="Ada")
    ajouter_piece_jointe(uid, "CV", f"user_{uid}/cv.pdf", mode="stage")
    assert lire_profil(uid, mode="job") == {}


# ─── Interface (D119) ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("mode", ["alternance", "job", "stage"])
def test_bouton_et_fenetre_sur_la_page_profil_de_chaque_mode(utilisateur, mode):
    client, _ = utilisateur("a@test.fr", prenom="Ada")
    page = client.get(f"/{mode}").text
    for attribut in ("data-copie-ouvrir", "data-copie-modal", "data-copie-sources", "data-copie-apercu-liste",
                     "data-copie-valider"):
        assert attribut in page, attribut
    assert "Copier depuis un autre mode" in page


# ─── Portfolio dans la carte Identité (D120) ──────────────────────────────────
@pytest.mark.parametrize("mode", ["alternance", "job", "stage"])
def test_portfolio_dans_la_carte_identite_de_chaque_mode(utilisateur, mode):
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    _stage(uid)
    page = client.get(f"/{mode}").text
    assert page.count('data-profil="portfolio"') == 1
    debut = page.index('<h3 class="profil-card__title">Identité</h3>')
    identite = page[debut:page.index("data-mode-section=", debut)]          # jusqu'à la carte suivante
    assert 'data-profil="portfolio"' in identite
    assert page[:debut].rsplit("data-mode-section=", 1)[1].startswith('"commun"')


def test_portfolio_du_stage_conserve_et_copiable(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Ada")
    _stage(uid)
    assert lire_profil(uid, mode="stage")["portfolio"] == "https://ada.fr"
    assert "portfolio" in next(s for s in sections_copiables("stage", "alternance") if s["cle"] == "liens")["champs"]
    r = _client(client, "alternance").post("/api/profil/copie", json={"source": "stage", "sections": ["liens"]})
    assert r.status_code == 200 and lire_profil(uid, mode="alternance")["portfolio"] == "https://ada.fr"
    assert lire_profil(uid, mode="stage")["portfolio"] == "https://ada.fr"
