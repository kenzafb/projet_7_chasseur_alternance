"""Entreprises à contacter (D148) : plafonds dans les réglages avancés du
mode, repris quand le lancement n'en demande pas ; page en trois étapes."""

from routes.commun import limite_appliquee
from shared import config


def test_plafonds_des_entreprises_dans_les_reglages(utilisateur):
    client, uid = utilisateur("a@test.fr")
    r = client.post("/api/reglages", json={"entreprises": 10**6, "scrapees": 7, "mails": 999, "revalidations": 0}).json()
    assert (r["entreprises"], r["scrapees"], r["mails"], r["revalidations"]) == (5000, 7, 50, 1)
    # Sans valeur demandée : le réglage du mode, borné par ce qui est disponible
    assert limite_appliquee("scrapees", None, 100, user_id=uid, mode="alternance") == (7, "")
    assert limite_appliquee("scrapees", None, 3, user_id=uid, mode="alternance")[0] == 3
    assert limite_appliquee("scrapees", None, 100, user_id=uid, mode="stage")[0] == config.LIMITES_LANCEMENT["scrapees"]["defaut"]
    # Une valeur demandée l'emporte
    assert limite_appliquee("scrapees", 12, 100, user_id=uid, mode="alternance")[0] == 12


def test_page_en_trois_etapes(utilisateur):
    client, _ = utilisateur("a@test.fr")
    page = client.get("/alternance").text
    debut = page.index('data-page-content="spontanees"')
    entreprises = page[debut:page.index("</section>\n", page.index('data-par-source', debut))]
    for texte in ("Trouver des entreprises", "Trouver leurs emails", "Envoyer ta candidature", "Prêtes à envoyer",
                  "Via La Bonne Alternance", "Sans contact", "Déjà contactées"):
        assert texte in entreprises, texte
    assert "data-limite=" not in entreprises            # les plafonds sont dans Paramètres
    assert 'data-reglage="mails"' in page and "Scraper" not in entreprises
