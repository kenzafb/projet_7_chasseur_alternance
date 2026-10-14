"""Validation des emails trouvés par le scraper (phase 7) : règles d'un
fichier de données d'abord (validée ou écartée d'office), l'IA seulement
pour les douteuses, sans IA les douteuses restent non validées."""

import httpx
import pytest

import shared.validation_emails as ve
from tests.conftest import erreur_http


@pytest.mark.parametrize("email, site, decision", [
    ("contact@acme.fr", "acme.fr", ve.VALIDE),
    ("recrutement@acme.fr", "www.acme.fr", ve.VALIDE),
    ("rh.paris@acme.fr", "acme.fr", ve.VALIDE),           # préfixe suivi d'un point
    ("contact2@acme.fr", "acme.fr", ve.VALIDE),           # suivi d'un chiffre
    ("info@paris.acme.fr", "acme.fr", ve.VALIDE),         # sous-domaine du site
    ("Contact@ACME.fr", "acme.fr", ve.VALIDE),            # casse ignorée
    ("camille.martin@acme.fr", "acme.fr", ve.DOUTEUX),    # nominative
    ("contactless@acme.fr", "acme.fr", ve.DOUTEUX),       # « contact » n'est pas un préfixe ici
    ("contact@agence-web.fr", "acme.fr", ve.DOUTEUX),     # autre domaine
    ("acme.paris@gmail.com", "acme.fr", ve.DOUTEUX),      # messagerie grand public
    ("contact@acme.fr", None, ve.DOUTEUX),                # site inconnu
    ("dpo@acme.fr", "acme.fr", ve.ECARTE),                # préfixe écarté
    ("presse.paris@acme.fr", "acme.fr", ve.ECARTE),
    ("noreply@acme.fr", "acme.fr", ve.ECARTE),
    ("votre@email.com", "email.com", ve.ECARTE),          # liste d'exclusion (D47)
    ("x@o123.ingest.sentry.io", "acme.fr", ve.ECARTE),
])
def test_regles(email, site, decision):
    assert ve.classer(email, site)[0] == decision


def test_raisons_lisibles():
    assert ve.classer("x@gmail.com", "acme.fr")[1] == "messagerie grand public"
    assert ve.classer("x@autre.fr", "acme.fr")[1] == "autre domaine que le site"


def test_fichier_de_regles_lisible_et_complet():
    r = ve.regles()
    assert set(r) == set(ve.SECTIONS)
    assert {"contact", "recrutement", "rh"} <= r["prefixes_contact"]
    assert {"dpo", "presse", "noreply"} <= r["prefixes_ecartes"]
    assert "gmail.com" in r["domaines_messagerie"]
    assert not r["prefixes_contact"] & r["prefixes_ecartes"]


def test_section_inconnue_refusee(tmp_path, monkeypatch):
    fichier = tmp_path / "regles.txt"
    fichier.write_text("[prefixes_contact]\ncontact\n[autre]\nx\n", encoding="utf-8")
    monkeypatch.setattr(ve, "FICHIER", fichier)
    ve.regles.cache_clear()
    try:
        with pytest.raises(ValueError, match="section inconnue"):
            ve.regles()
    finally:
        ve.regles.cache_clear()


def test_contexte_autour_de_l_adresse():
    texte = "début " + "a" * 500 + " Écrivez au gérant : Gerant.Acme@gmail.com pour postuler. " + "b" * 500
    extrait = ve.contexte("gerant.acme@gmail.com", texte)
    assert "Écrivez au gérant" in extrait and "pour postuler" in extrait and len(extrait) < 500
    assert ve.contexte("absente@x.fr", texte) == ""


def test_sans_ia_douteux_non_valides(ia):
    tri = ve.trier(["contact@acme.fr", "dpo@acme.fr", "x@gmail.com"], "acme.fr",
                   texte="Joindre x@gmail.com", ia=False)
    assert tri["valides"] == ["contact@acme.fr"] and tri["douteux"] == ["x@gmail.com"]
    assert tri["ecartes"] == [("dpo@acme.fr", "adresse qui ne sert pas à candidater")]
    assert tri["contextes"] == {"x@gmail.com": "Joindre x@gmail.com"}
    assert ia.appels == []


def test_un_appel_par_entreprise_pour_les_douteux(ia):
    ia.reponse = '{"valides": ["gerant@gmail.com"], "meilleur_contact": "gerant@gmail.com"}'
    tri = ve.trier(["contact@acme.fr", "gerant@gmail.com", "contact@agence.fr"], "acme.fr", nom="ACME",
                   texte="Le gérant : gerant@gmail.com. Site réalisé par contact@agence.fr")
    assert tri["valides"] == ["contact@acme.fr", "gerant@gmail.com"] and tri["douteux"] == []
    assert tri["ecartes"] == [("contact@agence.fr", "écartée par l'IA (autre domaine que le site)")]
    assert tri["meilleur_contact"] == "gerant@gmail.com"
    assert len(ia.appels) == 1 and ia.appels[0]["model"] == "ministral-3:3b"
    texte = ia.textes(0)
    assert "Entreprise : ACME" in texte and "- gerant@gmail.com : « Le gérant" in texte
    assert "contact@acme.fr" in texte                      # proposée comme meilleur contact
    corps = ia.appels[0]
    assert corps["options"]["temperature"] == 0.1
    proprietes = corps["format"]["properties"]
    assert proprietes["valides"]["items"]["enum"] == ["gerant@gmail.com", "contact@agence.fr"]
    assert proprietes["meilleur_contact"]["enum"] == ["contact@acme.fr", "gerant@gmail.com", "contact@agence.fr", None]


def test_pas_d_appel_sans_douteuse(ia):
    tri = ve.trier(["contact@acme.fr"], "acme.fr")
    assert tri["valides"] == ["contact@acme.fr"] and ia.appels == [] and tri["meilleur_contact"] is None


@pytest.mark.parametrize("reponse", [
    '{"valides": ["inventee@x.fr"], "meilleur_contact": null}',     # adresse hors énumération
    '{"valides": [], "meilleur_contact": "inventee@x.fr"}',
    '{"valides": "a@gmail.com", "meilleur_contact": null}',
])
def test_adresse_inventee_refusee(ia, reponse):
    ia.reponse = reponse
    tri = ve.trier(["a@gmail.com"], "acme.fr")
    assert tri["douteux"] == ["a@gmail.com"] and tri["valides"] == [] and len(ia.appels) == 2   # redemandée


def test_meilleur_contact_ecarte_ignore(ia):
    ia.reponse = '{"valides": [], "meilleur_contact": "a@gmail.com"}'
    tri = ve.trier(["a@gmail.com"], "acme.fr")
    assert tri["meilleur_contact"] is None and tri["ecartes"][0][0] == "a@gmail.com"


def test_ia_bloquante_douteuses_gardees(ia):
    ia.panne = lambda corps: httpx.ConnectError("refused")
    tri = ve.trier(["a@gmail.com", "b@gmail.com"], "acme.fr")
    assert tri["douteux"] == ["a@gmail.com", "b@gmail.com"] and len(ia.demarrages) == 1 and ia.appels == []
    assert "IA locale injoignable" in tri["ia_bloquee"]


def test_ia_passagere_douteuses_gardees(ia):
    ia.file = [erreur_http(503), erreur_http(503)]
    tri = ve.trier(["a@gmail.com", "b@gmail.com"], "acme.fr")
    assert tri["douteux"] == ["a@gmail.com", "b@gmail.com"] and "erreur_ia" in tri
    assert set(tri["contextes"]) == {"a@gmail.com", "b@gmail.com"}


def test_entreprise_d_avant_la_phase_7():
    ancienne = {"emails_trouves": ["a@x.fr", "b@x.fr"], "emails_non_valides": True}
    assert ve.emails_douteux(ancienne) == ["a@x.fr", "b@x.fr"] and ve.emails_valides(ancienne) == []
    nouvelle = {"emails_trouves": ["a@x.fr", "b@y.fr"], "emails_non_valides": True, "emails_douteux": ["b@y.fr"]}
    assert ve.emails_douteux(nouvelle) == ["b@y.fr"] and ve.emails_valides(nouvelle) == ["a@x.fr"]
    assert ve.emails_douteux({"emails_trouves": ["a@x.fr"]}) == []
