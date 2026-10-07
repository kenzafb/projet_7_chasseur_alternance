"""PDF de lettre : contenu piégé échappé, aucune ressource chargée, fichiers
par utilisateur au nom unique, téléchargement réservé au propriétaire."""

import pytest

import france_travail.pdf_generator as pdf
from database.candidatures_db import ajouter_candidature

PIEGES = [
    '<img src="file:///etc/passwd">',
    "<script>alert(1)</script>",
    '<link rel="stylesheet" href="http://evil.test/x.css">',
    "<style>@import url(file:///etc/passwd);</style>",
]
LETTRE_PIEGEE = "Madame, Monsieur,\n\n" + "\n".join(PIEGES) + "\n\nCordialement."
PROFIL_PIEGE = {"prenom": PIEGES[0], "nom": "Lovelace", "email": "ada@test.fr",
                "ville": PIEGES[2], "telephone": PIEGES[1], "github": PIEGES[3]}
OFFRE_PIEGEE = {"id": "OFFRE-1", "titre": PIEGES[3], "entreprise": PIEGES[0], "lieu": PIEGES[2]}


@pytest.fixture
def ressources(monkeypatch):
    """Espionne le url_fetcher : toute demande de ressource est notée (et refusée)."""
    demandees = []
    refuser = pdf.refuser_ressource

    def espion(url, *args, **kwargs):
        demandees.append(url)
        return refuser(url)

    monkeypatch.setattr(pdf, "refuser_ressource", espion)
    return demandees


def test_contenu_piege_echappe():
    document = pdf.construire_html(OFFRE_PIEGEE, LETTRE_PIEGEE, PROFIL_PIEGE)
    for balise in ("<img", "<script", "<link"):
        assert balise not in document
    assert document.count("<style>") == 1   # celle du gabarit seulement
    assert "&lt;img src=&quot;file:///etc/passwd&quot;&gt;" in document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document


def test_aucune_ressource_chargee_pour_une_lettre_piegee(utilisateur, ressources, tmp_path):
    client, user_id = utilisateur("ada@test.fr")
    client.post("/api/profil", json=PROFIL_PIEGE)
    ajouter_candidature(user_id, dict(OFFRE_PIEGEE))
    r = client.post("/api/telecharger_pdf", json={"id": "OFFRE-1", "lettre": LETTRE_PIEGEE})
    assert r.status_code == 200
    assert ressources == []
    contenu = client.get(r.json()["url"]).content
    assert contenu.startswith(b"%PDF")
    assert b"root:" not in contenu


def test_url_fetcher_refuse_fichier_et_reseau(ressources, tmp_path):
    """Même du HTML brut (non échappé) ne peut rien charger."""
    brut = ('<html><head><link rel="stylesheet" href="http://evil.test/x.css">'
            '<style>body { background: url(file:///etc/hostname); }</style></head>'
            '<body><img src="file:///etc/passwd"><img src="https://evil.test/a.png">'
            '<p>texte</p></body></html>')
    pdf.rendre_pdf(brut, tmp_path / "brut.pdf")
    assert (tmp_path / "brut.pdf").read_bytes().startswith(b"%PDF")
    assert set(ressources) == {"http://evil.test/x.css", "file:///etc/hostname",
                               "file:///etc/passwd", "https://evil.test/a.png"}


def test_refuser_ressource_leve_toujours():
    with pytest.raises(pdf.RessourceInterdite):
        pdf.refuser_ressource("file:///etc/passwd")


# ─── Rangement et téléchargement ──────────────────────────────────────────────
@pytest.fixture
def homonymes(utilisateur):
    """A et B portent le même nom et ont chacun une offre de même référence."""
    clients = []
    for email in ("a@test.fr", "b@test.fr"):
        client, user_id = utilisateur(email)
        client.post("/api/profil", json={"prenom": "Ada", "nom": "Lovelace", "email": email})
        ajouter_candidature(user_id, {"id": "OFFRE-1", "titre": "Dev", "entreprise": "ACME"})
        clients.append((client, user_id))
    return clients


def _generer(client, texte="Madame, Monsieur,\n\nTexte."):
    r = client.post("/api/telecharger_pdf", json={"id": "OFFRE-1", "lettre": texte})
    assert r.status_code == 200, r.text
    return r.json()


def test_homonymes_ne_s_ecrasent_pas(homonymes, tmp_path):
    (client_a, id_a), (client_b, id_b) = homonymes
    _generer(client_a, "Madame, Monsieur,\n\nLettre de A.")
    _generer(client_b, "Madame, Monsieur,\n\nLettre de B.")
    assert len(list((tmp_path / "pdf" / f"user_{id_a}").glob("*.pdf"))) == 1
    assert len(list((tmp_path / "pdf" / f"user_{id_b}").glob("*.pdf"))) == 1


def test_telechargement_par_le_proprietaire(homonymes):
    (client_a, _), _ = homonymes
    reponse = _generer(client_a)
    r = client_a.get(reponse["url"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="Lettre_Ada_Lovelace_ACME.pdf"'
    assert r.content.startswith(b"%PDF")
    assert "chemin" not in reponse   # plus de chemin serveur renvoyé au navigateur


def test_pdf_de_b_refuse_a_a(utilisateur):
    client_a, _ = utilisateur("a@test.fr")
    client_b, id_b = utilisateur("b@test.fr")
    client_b.post("/api/profil", json={"prenom": "Bob", "nom": "B", "email": "b@test.fr"})
    ajouter_candidature(id_b, {"id": "OFFRE-B", "titre": "Dev", "entreprise": "ACME"})
    url = client_b.post("/api/telecharger_pdf", json={"id": "OFFRE-B", "lettre": "Madame, Monsieur,"}).json()["url"]
    assert client_b.get(url).status_code == 200

    r = client_a.get(url)
    assert r.status_code == 404
    assert not r.content.startswith(b"%PDF")
    for detour in ("/api/lettre_pdf/..%2Fuser_2%2Flettre.pdf", "/api/lettre_pdf/%2Fetc%2Fpasswd"):
        assert client_a.get(detour).status_code == 404


def test_regeneration_remplace_l_ancien_fichier(homonymes, tmp_path):
    (client_a, id_a), _ = homonymes
    _generer(client_a, "Madame, Monsieur,\n\nV1.")
    _generer(client_a, "Madame, Monsieur,\n\nV2.")
    assert len(list((tmp_path / "pdf" / f"user_{id_a}").iterdir())) == 1
