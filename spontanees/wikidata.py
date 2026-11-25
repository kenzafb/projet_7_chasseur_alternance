"""
spontanees/wikidata.py
======================
Site officiel d'une entreprise d'après Wikidata (D188) : l'élément qui
porte son SIREN (propriété P1616) et son site officiel (P856). Interrogé
avant toute recherche web ; un site trouvé ainsi compte comme vérifié
(spontanees/site_officiel.identifier), son accueil devant seulement se
lire. Service public et gratuit (query.wikidata.org), sans clé ; seuls
les SIREN sont envoyés, par lots. Une panne ne bloque rien : la suite des
sources (LBA, offres, domaines devinés, recherche web) prend le relais.
"""

import re

import requests

URL = "https://query.wikidata.org/sparql"
# Politique de Wikidata : un User-Agent qui nomme le client (sans contact personnel)
ENTETES = {"User-Agent": "Chasseur/1.0 (outil personnel de recherche d'emploi; python-requests)",
           "Accept": "application/sparql-results+json"}
DELAI_S = 20
TAILLE_LOT = 100

_cache: dict[str, list[str]] = {}     # SIREN -> sites (liste vide : aucun), pour le processus


def _requete(sirens: list[str]) -> str:
    valeurs = " ".join(f'"{s}"' for s in sirens)
    return ("SELECT ?siren ?site WHERE { VALUES ?siren { " + valeurs + " } "
            "?item wdt:P1616 ?siren . ?item wdt:P856 ?site . }")


def _interroger(sirens: list[str]) -> dict[str, list[str]] | None:
    """{SIREN: [sites]} pour un lot, None si Wikidata ne répond pas."""
    try:
        r = requests.get(URL, params={"query": _requete(sirens), "format": "json"}, headers=ENTETES,
                         timeout=DELAI_S)
        if r.status_code != 200:
            return None
        lignes = r.json()["results"]["bindings"]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None
    out: dict[str, list[str]] = {}
    for b in lignes:
        siren, site = b.get("siren", {}).get("value", ""), b.get("site", {}).get("value", "")
        if siren and site.startswith(("http://", "https://")) and site not in out.get(siren, []):
            out.setdefault(siren, []).append(site)
    return out


def _propre(siren) -> str:
    s = re.sub(r"\D", "", str(siren or ""))
    return s if len(s) == 9 else ""


def precharger(sirens) -> int:
    """Demande par lots les SIREN pas encore connus ; retourne le nombre de
    SIREN qui ont un site. Un lot sans réponse n'est pas mis en cache."""
    a_demander = list(dict.fromkeys(s for s in map(_propre, sirens) if s and s not in _cache))
    for i in range(0, len(a_demander), TAILLE_LOT):
        lot = a_demander[i:i + TAILLE_LOT]
        res = _interroger(lot)
        if res is None:
            continue
        for s in lot:
            _cache[s] = res.get(s, [])
    return sum(1 for s in set(map(_propre, sirens)) if _cache.get(s))


def sites_wikidata(entreprise: dict) -> list[str]:
    """Sites officiels déclarés dans Wikidata pour le SIREN de l'entreprise."""
    siren = _propre(entreprise.get("siren") or str((entreprise.get("_extra") or {}).get("siret") or "")[:9])
    if not siren:
        return []
    if siren not in _cache:
        precharger([siren])
    return list(_cache.get(siren, []))
