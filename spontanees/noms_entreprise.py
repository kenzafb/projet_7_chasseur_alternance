"""
spontanees/noms_entreprise.py
=============================
Autres noms d'une entreprise pour retrouver son site (D167) : sigle,
dénominations usuelles et enseignes de Sirene. Lus à la récupération Sirene
(spontanees/recuperation.extraire_infos) ; pour une entreprise qui ne les a
pas (déjà en base, ou venue de LBA), demandés une fois à l'API publique
Recherche d'entreprises (recherche-entreprises.api.gouv.fr, données Sirene,
sans clé), puis gardés dans extra.autres_noms. Seul le SIREN est envoyé.
"""

import re

import requests

URL = "https://recherche-entreprises.api.gouv.fr/search"
DELAI_S = 10


def depuis_sirene(ul: dict, periode: dict | None) -> list[str]:
    """Autres noms d'un établissement de l'API Sirene (unité légale, période courante)."""
    periode = periode or {}
    noms = [ul.get("sigleUniteLegale"), *(ul.get(f"denominationUsuelle{i}UniteLegale") for i in (1, 2, 3)),
            *(periode.get(f"enseigne{i}Etablissement") for i in (1, 2, 3)),
            periode.get("denominationUsuelleEtablissement")]
    return list(dict.fromkeys(str(n).strip() for n in noms if n and str(n).strip()))


def depuis_annuaire(siren: str, http=None) -> list[str] | None:
    """Autres noms d'après l'API Recherche d'entreprises, None si elle ne répond pas."""
    fiche = fiche_annuaire(siren, http)
    return None if fiche is None else fiche["noms"]


def fiche_annuaire(siren: str, http=None) -> dict | None:
    """{noms, siege: {code_postal, voie}} d'après l'API Recherche d'entreprises
    (un appel), None si elle ne répond pas."""
    siren = re.sub(r"\D", "", siren or "")
    if len(siren) != 9:
        return {"noms": [], "siege": {}}
    http = http or requests
    try:
        r = http.get(URL, params={"q": siren, "page": 1, "per_page": 1}, timeout=DELAI_S)
        resultats = r.json().get("results") or [] if r.status_code == 200 else None
    except (requests.RequestException, ValueError, AttributeError):
        return None
    if resultats is None:
        return None
    e = next((x for x in resultats if x.get("siren") == siren), None)
    if not e:
        return {"noms": [], "siege": {}}
    siege = e.get("siege") or {}
    noms = [e.get("sigle"), siege.get("nom_commercial"), *(siege.get("liste_enseignes") or [])]
    # nom_complet : « RAISON SOCIALE (DÉNOMINATION USUELLE) »
    noms += re.findall(r"\(([^)]+)\)", e.get("nom_complet") or "")
    voie = " ".join(str(siege.get(k) or "") for k in ("type_voie", "libelle_voie")).strip()
    return {"noms": list(dict.fromkeys(str(n).strip() for n in noms if n and str(n).strip())),
            "siege": {"code_postal": str(siege.get("code_postal") or ""), "voie": voie}}


def completer(entreprise: dict) -> list[str]:
    """Autres noms de l'entreprise, demandés à l'annuaire s'ils manquent ;
    mis dans entreprise["autres_noms"] (sauvegardé dans extra par le scraper)."""
    deja = entreprise.get("autres_noms")
    if deja is None:
        deja = (entreprise.get("_extra") or {}).get("autres_noms")
    if deja is not None:
        entreprise["autres_noms"] = list(deja)
        return entreprise["autres_noms"]
    siren = entreprise.get("siren") or str((entreprise.get("_extra") or {}).get("siret") or "")[:9]
    fiche = fiche_annuaire(siren)
    if fiche is not None:
        entreprise["autres_noms"] = fiche["noms"]
        if fiche["siege"].get("code_postal"):
            entreprise["adresse_siege"] = fiche["siege"]      # preuve par l'adresse (D173)
    return (fiche or {}).get("noms") or []
