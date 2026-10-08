"""Fichiers statiques : version dans les URL (cache navigateur), et
correspondance entre les sélecteurs des modules JS et les templates."""

import hashlib
import json
import re

import pytest

import shared.statique as statique
from shared import config


def _page(client):
    r = client.get("/")
    assert r.status_code == 200
    return r.text


def _empreinte(relatif):
    return hashlib.sha256((config.STATIC_DIR / relatif).read_bytes()).hexdigest()[:12]


# ─── Version dans les URL ────────────────────────────────────────────────────
def test_css_et_js_versionnes_par_leur_contenu(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = _page(client)
    for css in ("base.css", "components.css", "pages.css"):
        assert f'href="/static/css/{css}?v={_empreinte("css/" + css)}"' in page
    assert f'src="/static/js/app.js?v={_empreinte("js/app.js")}"' in page


def test_aucune_url_statique_sans_version(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = _page(client)
    for url in re.findall(r'(?:href|src)="(/static/[^"]+)"', page):
        assert "?v=" in url, url
    for gabarit in config.TEMPLATES_DIR.rglob("*.html"):
        assert not re.search(r'(?:href|src)="/static/', gabarit.read_text(encoding="utf-8")), gabarit


def test_import_map_couvre_chaque_module(utilisateur):
    """Les modules s'importent entre eux ("./api.js") : l'import map leur
    donne à tous leur URL versionnée."""
    client, _ = utilisateur("a@test.fr", prenom="Alice")
    page = _page(client)
    bloc = re.search(r'<script type="importmap">(.*?)</script>', page, re.S)
    assert bloc and page.index('type="importmap"') < page.index('type="module"')
    carte = json.loads(bloc.group(1))["imports"]
    modules = sorted(p.name for p in (config.STATIC_DIR / "js").glob("*.js"))
    assert sorted(cle.rsplit("/", 1)[1] for cle in carte) == modules
    for nom in modules:
        assert carte[f"/static/js/{nom}"] == f"/static/js/{nom}?v={_empreinte('js/' + nom)}"


def test_les_imports_des_modules_sont_couverts():
    """Chaque import relatif d'un module vise un fichier de static/js (donc versionné)."""
    for module in (config.STATIC_DIR / "js").glob("*.js"):
        for cible in re.findall(r'from\s+"(\./[^"]+)"', module.read_text(encoding="utf-8")):
            assert (config.STATIC_DIR / "js" / cible).is_file(), (module.name, cible)


def test_version_change_avec_le_contenu(tmp_path, monkeypatch):
    (tmp_path / "js").mkdir()
    fichier = tmp_path / "js" / "x.js"
    fichier.write_text("console.log(1);")
    monkeypatch.setattr(statique, "STATIC_DIR", tmp_path)
    monkeypatch.setattr(statique, "_empreintes", {})
    avant = statique.url_statique("js/x.js")
    assert statique.url_statique("js/x.js") == avant          # stable sans modification
    fichier.write_text("console.log(22);")
    apres = statique.url_statique("js/x.js")
    assert apres != avant and apres.startswith("/static/js/x.js?v=")
    assert json.loads(statique.importmap())["imports"] == {"/static/js/x.js": apres}


def test_url_versionnee_servie(client, utilisateur):
    client_a, _ = utilisateur("a@test.fr", prenom="Alice")
    r = client_a.get(statique.url_statique("js/api.js"))
    assert r.status_code == 200 and "export const api" in r.text
