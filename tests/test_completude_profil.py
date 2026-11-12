"""Complétude du profil en cinq parties (D144), une règle par mode."""
from shared.completude_profil import completude
from shared.criteres import normaliser_recherche

COMMUN = {"prenom": "Alice", "nom": "Martin", "email": "a@test.fr", "telephone": "0600000000", "ville": "Paris",
          "competences": ["Linux", "Python", "Git"], "experience": "Stage", "pieces_jointes": [{"nom": "cv.pdf"}],
          "lettre_type": "Madame,\n{paragraphe}\nCordialement",
          "recherche": {"domaines": ["M18"], "departements": ["75"], "tailles_spontanees": ["pme"]}}


def _partie(resultat, ident):
    return next(p for p in resultat["parties"] if p["id"] == ident)


def test_stage():
    complet = {**COMMUN, "date_debut": "2027-02-08", "date_fin": "2027-04-18", "etablissement": "IUT",
               "formation": "BUT", "missions": "Admin"}
    assert completude(complet, "stage")["completes"] == 5
    r = completude({**complet, "date_fin": "", "missions": " "}, "stage")
    assert _partie(r, "mode") == {"id": "mode", "titre": "Ton stage", "complet": False, "conseil": "",
                                  "manque": "Il manque la date de fin et les missions visées."}


def test_alternance():
    complet = {**COMMUN, "niveau_vise": "Bac+3",
               "recherche": {**COMMUN["recherche"], "rythme": "3 j / 2 j", "disponibilite": "septembre"}}
    assert completude(complet, "alternance")["completes"] == 5
    r = completude({**complet, "recherche": {**complet["recherche"], "rythme": ""}}, "alternance")
    assert _partie(r, "mode")["manque"] == "Il manque le rythme."


def test_job():
    complet = {**COMMUN, "dispo_horaires": "soirs", "duree_souhaitee": "2 mois"}
    assert completude(complet, "job")["completes"] == 5
    assert _partie(completude({**complet, "duree_souhaitee": ""}, "job"), "mode")["manque"] == "Il manque la durée."


def test_parcours_recherche_documents():
    r = completude({**COMMUN, "competences": ["Linux"], "experience": "", "projets": [],
                    "pieces_jointes": [], "lettre_type": "sans marqueur",
                    "recherche": {"domaines": [], "departements": []}}, "job")
    assert _partie(r, "parcours")["manque"] == "Il manque 2 compétences (3 au moins) et un projet ou une expérience."
    recherche = _partie(r, "recherche")
    assert recherche["manque"] == "Il manque un domaine (ou « indifférent ») et un département."
    assert recherche["conseil"].startswith("Conseil")   # taille : conseillée, pas obligatoire
    assert _partie(r, "documents")["manque"] == "Il manque ton CV et une lettre type avec {paragraphe}."
    # Indifférent choisi explicitement : la partie est complète sans domaine
    ok = completude({**COMMUN, "recherche": {"domaines_indifferent": True, "departements": ["92"]}}, "job")
    assert _partie(ok, "recherche")["complet"] and _partie(ok, "recherche")["conseil"]


def test_normalisation_des_nouvelles_cles():
    assert normaliser_recherche({"domaines": ["M18"], "domaines_indifferent": True})["domaines_indifferent"] is False
    assert normaliser_recherche({"domaines_indifferent": "oui"})["domaines_indifferent"] is False
    assert normaliser_recherche({"rythme": "  3 j / 2 j "})["rythme"] == "3 j / 2 j"
