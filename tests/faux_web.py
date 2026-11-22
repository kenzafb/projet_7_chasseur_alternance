"""Faux web pour le scraper (phase 15) : pages par URL, robots.txt par site,
redirections ; chaque demande est notée."""

from types import SimpleNamespace

import requests

import spontanees.lecture_site as L


class Reponse:
    def __init__(self, statut=200, texte="", url="", type_="text/html; charset=utf-8"):
        self.status_code, self.text, self.url = statut, texte, url
        self.headers = {"content-type": type_}


class FauxWeb:
    """pages : {url: html | (statut, html) | ("redirection", url)} ; robots : {racine: texte | statut}."""

    def __init__(self, pages=None, robots=None, erreurs=()):
        self.pages = {k.rstrip("/"): v for k, v in (pages or {}).items()}
        self.robots = {k.rstrip("/"): v for k, v in (robots or {}).items()}
        self.erreurs = {e.rstrip("/") for e in erreurs}
        self.demandes = []

    def get(self, url, headers=None, timeout=None, allow_redirects=True, **_):
        self.demandes.append(url)
        cle = url.split("#")[0].rstrip("/")
        if cle in self.erreurs:
            raise requests.ConnectionError("injoignable")
        if cle.endswith("/robots.txt"):
            racine = cle[: -len("/robots.txt")]
            robots = self.robots.get(racine)
            if isinstance(robots, int):              # statut seul (403 : robots refusé)
                return Reponse(robots, "", url, "text/plain")
            return Reponse(200, robots, url, "text/plain") if robots is not None else Reponse(404, "", url)
        page = self.pages.get(cle)
        if page is None:
            return Reponse(404, "introuvable", url)
        if isinstance(page, tuple) and page[0] == "redirection":
            cible = page[1]
            return Reponse(200, self.pages[cible.rstrip("/")], cible)
        if isinstance(page, tuple):
            return Reponse(page[0], page[1], url)
        type_ = "application/xml" if cle.endswith(".xml") else "text/html; charset=utf-8"
        return Reponse(200, page, url, type_)

    def demandes_de(self, racine):
        return [d for d in self.demandes if d.startswith(racine) and not d.endswith("robots.txt")]


def brancher(monkeypatch, web: FauxWeb) -> FauxWeb:
    monkeypatch.setattr(L, "requests", SimpleNamespace(get=web.get, RequestException=requests.RequestException))
    monkeypatch.setattr(L, "PAUSE_S", (0, 0))
    return web


def site(nom="ACME", siren="123456789", mentions=True, titre=None, contact=True, recrutement=False,
         emails=("contact@acme.fr",), racine="https://acme.fr", formulaire=False, siren_dans_mentions=True):
    """Pages d'un site d'entreprise : accueil (titre, liens réels), mentions
    légales (SIREN), contact (adresses, formulaire)."""
    liens = []
    if mentions:
        liens.append('<a href="/infos/mentions-legales">Mentions légales</a>')
    if contact:
        liens.append('<a href="/nous-joindre">Contact</a>')
    if recrutement:
        liens.append('<a href="/rejoignez-nous">Carrières</a>')
    pages = {racine: f"<html><head><title>{titre if titre is not None else nom} - accueil</title></head>"
                     f"<body><h1>Bienvenue</h1><footer>{' '.join(liens)}</footer></body></html>"}
    if mentions:
        pages[f"{racine}/infos/mentions-legales"] = (
            f"<html><body><h1>Mentions légales</h1><p>{nom} SAS au capital de 10 000 €, RCS Paris "
            f"{' '.join([siren[:3], siren[3:6], siren[6:]]) if siren_dans_mentions else '000 000 000'}</p></body></html>")
    if contact:
        corps = " ".join(f'<a href="mailto:{e}">{e}</a>' for e in emails)
        if formulaire:
            corps += '<form action="/envoyer"><input type="email" name="email"><textarea name="message"></textarea></form>'
        pages[f"{racine}/nous-joindre"] = f"<html><body><h1>Contact</h1>{corps}</body></html>"
    if recrutement:
        pages[f"{racine}/rejoignez-nous"] = ('<html><body><form><input type="file" name="cv">'
                                             '<input type="email"></form></body></html>')
    return pages
