"""Pages hors session et version téléphone de la refonte (D150)."""

import re

from shared import config


def test_pages_de_connexion_sur_le_gabarit_commun(client):
    for chemin, titre in (("/login", "Bon retour"), ("/register", "Créer un compte"),
                          ("/mot-de-passe-oublie", "Mot de passe oublié ?")):
        page = client.get(chemin).text
        assert f"<h1>{titre}</h1>" in page, chemin
        assert re.search(r'href="/static/css/auth\.css\?v=[0-9a-f]+"', page), chemin
        assert "<style>" not in page and "Space Grotesk" not in page, chemin
        assert "Ton stage, ton alternance ou ton job" in page
    login = client.get("/login").text
    assert '<label for="mot-de-passe">Mot de passe</label>' in login and 'href="/mot-de-passe-oublie">Oublié ?' in login
    assert 'href="/register">Créer un compte avec un code d\'invitation</a>' in login
    assert 'name="email"' in login and 'name="mot_de_passe"' in login


def test_champs_etiquetes_dans_les_formulaires(client):
    """Chaque champ d'un formulaire de connexion est dans un <label>, ou nommé par for=."""
    for chemin in ("/login", "/register"):
        page = client.get(chemin).text
        for champ in re.finditer(r'<input [^>]*>', page):
            avant = page[:champ.start()]
            dans_label = avant.rfind("<label") > avant.rfind("</label>")
            ident = re.search(r'id="([^"]+)"', champ.group(0))
            assert dans_label or (ident and f'for="{ident.group(1)}"' in page), champ.group(0)


def test_barre_d_onglets_du_telephone(utilisateur):
    client, _ = utilisateur("a@test.fr")
    page = client.get("/stage").text
    debut = page.index('class="onglets-tel"')
    barre = page[debut:page.index("</nav>", debut)]
    assert [p for p in re.findall(r'data-page="(\w+)"', barre)] == ["accueil", "offres", "candidatures"]
    assert 'data-plus-bouton aria-expanded="false" aria-controls="plus-tel"' in barre
    plus = page[page.index('id="plus-tel"'):]
    for cible in ("spontanees", "profil", "parametres"):
        assert f'data-page="{cible}"' in plus
    assert 'action="/logout"' in plus
    css = (config.STATIC_DIR / "css" / "base.css").read_text(encoding="utf-8")
    assert ".onglets-tel {" in css and "min-height: 52px" in css


def test_plus_aucun_ancien_nom_de_variable():
    """Les alias du lot 1 (D143) ont disparu : tout passe par les jetons."""
    anciens = r'var\(--(signal|encre|papier|txt|hair|vert|ambre|rouge|violet|f-display|f-body|f-mono|sh-\d|r-sm|r-md|r-lg)\b'
    for dossier, motif in ((config.STATIC_DIR / "css", "*.css"), (config.STATIC_DIR / "js", "*.js"),
                           (config.TEMPLATES_DIR, "**/*.html")):
        for f in dossier.glob(motif):
            assert not re.search(anciens, f.read_text(encoding="utf-8")), f.name
