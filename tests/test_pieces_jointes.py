"""Pièces jointes : nom nettoyé, raccourci avec son extension, unique (bug 8) ;
suppression qui garde un fichier encore utilisé par l'autre mode (bug 9)."""

import pytest

from database.profil_db import ajouter_piece_jointe, lire_profil
from shared import config

PDF = b"%PDF-1.4 contenu de test"


def _envoyer(client, nom_fichier, contenu=PDF, nom=""):
    r = client.post("/api/profil/upload", data={"nom": nom},
                    files={"fichier": (nom_fichier, contenu, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def _fichiers(user_id):
    dossier = config.UPLOADS_DIR / f"user_{user_id}"
    return sorted(p.name for p in dossier.iterdir()) if dossier.exists() else []


@pytest.fixture
def ada(utilisateur):
    return utilisateur("ada@test.fr", prenom="Ada", nom="Lovelace")


def test_nom_long_garde_l_extension(ada):
    client, user_id = ada
    long = "Programme_" + "tres_long_" * 30 + ".pdf"
    reponse = _envoyer(client, long)
    (nom_disque,) = _fichiers(user_id)
    assert nom_disque.endswith(".pdf")
    assert len(nom_disque) <= 60 + 1 + 8 + 4
    assert nom_disque.startswith("Programme_tres_long_")
    assert reponse["fichier"] == nom_disque
    assert lire_profil(user_id)["pieces_jointes"][0]["fichier"] == f"user_{user_id}/{nom_disque}"
    r = client.get("/api/profil/piece", params={"nom": reponse["nom"]})
    assert r.status_code == 200 and r.content == PDF


@pytest.mark.parametrize("nom_origine,debut", [
    ("../../etc/passwd.pdf", "passwd_"),
    ("C:\\Users\\moi\\CV final.PDF", "CV_final_"),
    ("Ça été créé.pdf", "Ca_ete_cree_"),
    ("....pdf", "document_"),
])
def test_nom_nettoye(ada, nom_origine, debut):
    client, user_id = ada
    _envoyer(client, nom_origine)
    (nom_disque,) = _fichiers(user_id)
    assert nom_disque.startswith(debut) and nom_disque.endswith(".pdf")


def test_deux_fichiers_de_meme_nom_ne_s_ecrasent_pas(ada):
    client, user_id = ada
    _envoyer(client, "CV.pdf", b"%PDF version 1", nom="CV long")
    _envoyer(client, "CV.pdf", b"%PDF version 2", nom="CV court")
    assert len(_fichiers(user_id)) == 2
    assert client.get("/api/profil/piece", params={"nom": "CV long"}).content == b"%PDF version 1"
    assert client.get("/api/profil/piece", params={"nom": "CV court"}).content == b"%PDF version 2"


def test_suppression_garde_le_fichier_utilise_par_l_autre_mode(ada):
    client, user_id = ada
    _envoyer(client, "CV.pdf", nom="CV")
    relatif = lire_profil(user_id)["pieces_jointes"][0]["fichier"]
    # Le profil job référence le même fichier (cas des profils importés)
    ajouter_piece_jointe(user_id, "Mon CV", relatif, mode="job")

    client.post("/api/profil/piece/supprimer", json={"nom": "CV"})
    assert lire_profil(user_id)["pieces_jointes"] == []
    assert config.chemin_piece_jointe(relatif).is_file()   # toujours utilisé en job

    client.post("/api/mode", json={"mode": "job"})
    client.post("/api/profil/piece/supprimer", json={"nom": "Mon CV"})
    assert not config.chemin_piece_jointe(relatif).exists()   # plus personne ne s'en sert


def test_remplacer_une_piece_supprime_l_ancien_fichier(ada):
    client, user_id = ada
    _envoyer(client, "CV.pdf", b"%PDF v1", nom="CV")
    _envoyer(client, "CV.pdf", b"%PDF v2", nom="CV")
    assert len(_fichiers(user_id)) == 1
    assert client.get("/api/profil/piece", params={"nom": "CV"}).content == b"%PDF v2"
