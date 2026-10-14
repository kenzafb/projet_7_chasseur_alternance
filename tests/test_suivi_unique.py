"""Tableau de suivi unique (D107) : offres postulées et candidatures
spontanées envoyées, lues dans leurs tables d'origine, statut modifiable
depuis le tableau, isolé par utilisateur et par mode."""

from datetime import date, timedelta

import pytest

from database.candidatures_db import ajouter_candidature, lire_candidature
from database.entreprises_db import (lire_entreprises, lire_entreprises_envoyees, sauvegarder_enrichissement,
                                     sauvegarder_entreprises)
from shared import config
from tests.test_envoyeur import entreprises


@pytest.fixture
def alice(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    for ref, titre in (("O1", "Dev"), ("O2", "Admin"), ("O3", "Pas postulée")):
        ajouter_candidature(uid, {"id": ref, "titre": titre, "entreprise": f"Ent {ref}", "lien": f"https://ft/{ref}",
                                  "statut": "nouveau"})
    entreprises(uid, 2)
    liste = lire_entreprises(uid)
    liste[0]["site_web"] = "ent0.fr"
    sauvegarder_enrichissement(uid, liste)
    liste = lire_entreprises(uid)
    liste[0].update(mail_envoye=True, mail_envoye_le="2026-10-10 09:00", mail_destinataires=["rh0@ent0.fr"])
    sauvegarder_entreprises(uid, liste)
    return client, uid


def test_une_seule_liste_offres_et_spontanees(alice):
    client, uid = alice
    hier = (date.today() - timedelta(days=1)).isoformat()
    client.post("/api/offre/postuler", json={"id": "O1", "date": hier})
    client.post("/api/offre/postuler", json={"id": "O2", "date": "2026-09-01"})
    lignes = client.get("/api/suivi").json()
    assert [(l["type"], l["id"]) for l in lignes] == [("offre", "O1"), ("spontanee", str(lire_entreprises(uid)[0]["_id"])),
                                                      ("offre", "O2")]                  # par date, la plus récente d'abord
    o1, sp, o2 = lignes
    assert (o1["entreprise"], o1["poste"], o1["date"], o1["statut"], o1["lien"]) == ("Ent O1", "Dev", hier, "envoye", "https://ft/O1")
    assert o2["statut"] == "a_relancer"                         # envoyée depuis plus de 7 jours : calculé
    assert lire_candidature(uid, "O2")["statut"] == "envoye"    # rien d'écrit par le calcul
    assert (sp["poste"], sp["date"], sp["contact"], sp["lien"]) == ("Candidature spontanée", "2026-10-10",
                                                                    "rh0@ent0.fr", "https://ent0.fr")


def test_statut_change_dans_la_table_d_origine(alice):
    client, uid = alice
    client.post("/api/offre/postuler", json={"id": "O1"})
    sp = str(lire_entreprises(uid)[0]["_id"])
    assert client.post("/api/suivi/statut", json={"type": "offre", "id": "O1", "statut": "entretien"}).json()["ok"]
    assert lire_candidature(uid, "O1")["statut"] == "entretien"
    assert client.post("/api/suivi/statut", json={"type": "spontanee", "id": sp, "statut": "reponse"}).json()["ok"]
    assert lire_entreprises_envoyees(uid, "alternance")[0]["statut_suivi"] == "reponse"
    # Refus : bounce sur une offre, offre non postulée, statut inconnu, identifiant bizarre
    for corps in ({"type": "offre", "id": "O1", "statut": "bounce"}, {"type": "offre", "id": "O3", "statut": "refus"},
                  {"type": "spontanee", "id": sp, "statut": "nouveau"}, {"type": "spontanee", "id": "x", "statut": "refus"}):
        assert client.post("/api/suivi/statut", json=corps).status_code == 404, corps
    assert client.post("/api/suivi/statut", json={"type": "autre", "id": "O1", "statut": "refus"}).status_code == 422


def test_isolation_utilisateur_et_mode(alice, utilisateur):
    client, uid = alice
    client.post("/api/offre/postuler", json={"id": "O1"})
    sp = str(lire_entreprises(uid)[0]["_id"])
    client_b, _ = utilisateur("b@test.fr", prenom="Bob")
    assert client_b.get("/api/suivi").json() == []
    assert client_b.post("/api/suivi/statut", json={"type": "offre", "id": "O1", "statut": "refus"}).status_code == 404
    assert client_b.post("/api/suivi/statut", json={"type": "spontanee", "id": sp, "statut": "refus"}).status_code == 404
    client.mode = "job"
    assert client.get("/api/suivi").json() == []
    assert lire_candidature(uid, "O1")["statut"] == "envoye"


def test_interface_une_seule_page():
    base = (config.TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
    assert 'data-page="spontanees-suivi"' not in base and 'data-page="candidatures"' in base
    page = (config.TEMPLATES_DIR / "partials" / "candidatures.html").read_text(encoding="utf-8")
    for colonne in ("Entreprise", "Poste", "Type", "Candidature", "Statut", "Offre ou contact"):
        assert f"<span>{colonne}</span>" in page
    js = (config.STATIC_DIR / "js" / "candidatures.js").read_text(encoding="utf-8")
    assert "api.suivi()" in js and "api.suiviStatut(" in js
    assert not (config.STATIC_DIR / "js" / "suivi.js").exists()
    offres = (config.STATIC_DIR / "js" / "offres.js").read_text(encoding="utf-8")
    assert 'new Event("candidatures:maj")' in offres     # le suivi suit « J'ai postulé » sans rechargement


def test_options_du_statut_neutres():
    """D111 : la couleur du statut s'appliquait aussi aux options de la liste."""
    css = (config.STATIC_DIR / "css" / "pages.css").read_text(encoding="utf-8")
    assert ".suivi-statut option { color: var(--txt); background-color: var(--surface);" in css
    assert ".st-refus      { color: var(--rouge);" in css               # le menu fermé garde sa couleur
