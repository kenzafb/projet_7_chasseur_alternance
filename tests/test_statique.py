"""Fichiers statiques : version dans les URL (cache navigateur), et
correspondance entre les sélecteurs des modules JS et les templates."""

import hashlib
import json
import re

import pytest

import shared.statique as statique
from shared import config


def _page(client):
    r = client.get("/alternance")
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


# ─── Sélecteurs des modules JS ───────────────────────────────────────────────
# Les modules repèrent les éléments par id, attribut data-* ou classe. Chaque
# sélecteur écrit dans un JS doit viser un élément qui existe : dans les
# templates, ou dans le balisage que les JS génèrent eux-mêmes.
_JS = {p.name: p.read_text(encoding="utf-8") for p in sorted((config.STATIC_DIR / "js").glob("*.js"))}
_TEMPLATES = "\n".join(p.read_text(encoding="utf-8") for p in sorted(config.TEMPLATES_DIR.rglob("*.html")))
_CHAINES = re.compile(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`((?:[^`\\]|\\.)*)`', re.S)
_ATTRIBUT = re.compile(r'\[([a-z][\w-]*)(?:\s*=\s*"([^"]*)")?\]')


def _selecteurs():
    """(module, type, nom, valeur) de chaque id, attribut ou classe cherché
    par querySelector, querySelectorAll, getElementById, closest ou matches,
    ou rangé dans une table de sélecteurs ([data-list="..."] etc.)."""
    trouves = set()
    for module, source in _JS.items():
        for m in re.finditer(r'getElementById\(\s*["\']([\w-]+)["\']', source):
            trouves.add((module, "id", m.group(1), None))
        for m in _CHAINES.finditer(source):
            chaine = next(g for g in m.groups() if g is not None)
            debut = source[max(0, m.start() - 40):m.start()]
            appel = re.search(r'(querySelector(?:All)?|closest|matches)\(\s*$', debut)
            if not (appel or re.match(r'^\s*[.#\[]', chaine)) or "<" in chaine:
                continue   # ni sélecteur ni entrée d'une table de sélecteurs
            for nom, valeur in _ATTRIBUT.findall(chaine):
                valeur = None if not valeur or "${" in valeur else valeur
                trouves.add((module, "attribut", nom, valeur))
            sans_attributs = _ATTRIBUT.sub("", chaine)
            for nom in re.findall(r'(?<![\w-])#([A-Za-z][\w-]*)', sans_attributs):
                trouves.add((module, "id", nom, None))
            for nom in re.findall(r'(?<![\w$-])\.([A-Za-z][\w-]*)', sans_attributs):
                trouves.add((module, "classe", nom, None))
    return sorted(trouves, key=lambda t: tuple(map(str, t)))


def _balisage_js():
    """Balisage généré par les modules : le texte de leurs balises ouvrantes."""
    return "\n".join(re.findall(r"<[a-z][^<>]*>", "\n".join(_JS.values())))


def _existe(type_, nom, valeur, html):
    if type_ == "id":
        return re.search(rf'\bid="{re.escape(nom)}"', html)
    if type_ == "classe":
        return re.search(rf'\bclass="[^"]*(?<![\w-]){re.escape(nom)}(?![\w-])', html)
    if valeur is None:
        return re.search(rf'(?<![\w-]){re.escape(nom)}(?=[\s=>/])', html)
    return re.search(rf'(?<![\w-]){re.escape(nom)}="{re.escape(valeur)}"', html)


def test_les_selecteurs_trouves_sont_nombreux():
    """Garde-fou du test suivant : l'extraction voit bien les sélecteurs."""
    trouves = _selecteurs()
    assert len(trouves) > 60
    assert ("app.js", "attribut", "data-runbar", None) in trouves
    assert ("app.js", "attribut", "data-list", "offres") in trouves   # table LISTES_RECHERCHE
    assert ("spontanees.js", "attribut", "data-sp-mode-test", None) in trouves


def test_chaque_selecteur_des_modules_existe():
    html = _TEMPLATES + "\n" + _balisage_js()
    absents = [f"{module} : {type_} {nom}{'=' + valeur if valeur else ''}"
               for module, type_, nom, valeur in _selecteurs()
               if not _existe(type_, nom, valeur, html)]
    assert not absents, "\n".join(absents)
