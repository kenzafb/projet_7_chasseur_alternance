"""Accueil d'un mode (D144) : ce qui attend, la recherche en bref et
l'avancement du profil, propres à l'utilisateur et au mode."""

from database.candidatures_db import ajouter_candidature
from routes.accueil import date_en_lettres, phrase_du_mode, salutation


def _offre(uid, ref, score, verdict="bon", statut="nouveau", mode="alternance"):
    ajouter_candidature(uid, {"id": ref, "titre": f"Poste {ref}", "entreprise": f"Ent {ref}", "score": score,
                              "verdict": verdict, "statut": statut}, mode=mode)


def test_a_faire_et_en_bref(utilisateur):
    client, uid = utilisateur("a@test.fr", prenom="Alice")
    _offre(uid, "B1", 8)
    _offre(uid, "B2", 6)
    _offre(uid, "M", 5)
    _offre(uid, "N", None, verdict="non_analysee")
    _offre(uid, "X", 9, statut="archive")                # écartée : ni à faire, ni à regarder
    client.post("/api/offre/postuler", json={"id": "M", "date": "2026-01-05"})   # à relancer (plus de 7 jours)
    d = client.get("/api/accueil").json()
    assert d["prenom"] == "Alice" and d["salutation"] in ("Bonjour", "Bonsoir")
    offre, relance, a_noter = d["a_faire"]
    assert offre["titre"] == "2 offres te correspondent bien" and offre["id"] == "B1"
    assert "Poste B1, notée 8/10" in offre["texte"] and offre["page"] == "offres"
    assert relance["titre"] == "Relance Ent M" and "5 janvier" in relance["texte"]
    assert a_noter["genre"] == "a_noter" and a_noter["nombre"] == 1 and a_noter["titre"] == "1 nouvelle offre à noter"
    assert d["en_bref"] == {"offres_a_regarder": 3, "candidatures_envoyees": 1, "reponses_recues": 0}
    assert d["profil"]["total"] == 5 and len(d["profil"]["parties"]) == 5


def test_isole_par_utilisateur_et_par_mode(utilisateur):
    _, a = utilisateur("a@test.fr")
    _offre(a, "A1", 9)
    _offre(a, "S1", 9, mode="stage")
    client_b, _ = utilisateur("b@test.fr")
    assert client_b.get("/api/accueil").json()["a_faire"] == []
    client_a, _ = utilisateur("c@test.fr")
    d = client_a.get("/api/accueil?mode=stage").json()
    assert d["en_bref"]["offres_a_regarder"] == 0


def test_sans_ia_pas_de_notation_proposee(utilisateur, monkeypatch):
    from shared import config
    client, uid = utilisateur("a@test.fr")
    _offre(uid, "N", None, verdict="non_analysee")
    monkeypatch.setattr(config, "analyse_ia_active", lambda: False)
    assert client.get("/api/accueil").json()["a_faire"] == []


def test_salutation_dates_et_phrase():
    assert [salutation(h) for h in (4, 5, 17, 18)] == ["Bonsoir", "Bonjour", "Bonjour", "Bonsoir"]
    assert date_en_lettres("2027-02-08") == "8 février 2027"
    assert date_en_lettres("2027-04-01", annee=False) == "1er avril"
    assert date_en_lettres("n'importe quoi") == ""
    assert phrase_du_mode({"date_debut": "2027-02-08", "date_fin": "2027-04-18"}, "stage") == \
        "Ton stage : du 8 février au 18 avril 2027."
    assert phrase_du_mode({"recherche": {"disponibilite": "septembre 2027"}}, "alternance") == \
        "Ton alternance : à partir de septembre 2027."
    assert phrase_du_mode({}, "job") == ""
