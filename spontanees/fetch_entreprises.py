"""
fetch_entreprises.py
====================
Récupère les entreprises IT (codes NAF 62.*) de Paris et petite couronne
via l'API Recherche d'Entreprises (gratuite, officielle, sans clé API).

Départements ciblés : 75 (Paris), 92 (Hauts-de-Seine), 93 (Seine-Saint-Denis), 94 (Val-de-Marne)
Résultat : entreprises_raw.json

Note : l'API ne fournit PAS de site web. Les sites seront trouvés par scraper_emails.py.
"""

import requests
import json
import time
import os

FICHIER_SORTIE = "data/entreprises_raw.json"

# Codes NAF informatique / ESN — format avec POINT (ex: 62.01Z)
CODES_NAF = [
    "62.01Z",  # Programmation informatique
    "62.02A",  # Conseil en systèmes et logiciels informatiques
    "62.02B",  # Tierce maintenance de systèmes
    "62.03Z",  # Gestion d'installations informatiques
    "62.09Z",  # Autres activités informatiques
    "63.11Z",  # Traitement de données, hébergement
]

# Paris + petite couronne
DEPARTEMENTS = ["75", "92", "93", "94"]

BASE_URL = "https://recherche-entreprises.api.gouv.fr/search"

# Correspondance code effectif → libellé lisible
TRANCHES_EFFECTIF = {
    "NN": "0", "00": "0", "01": "1-2", "02": "3-5", "03": "6-9",
    "11": "10-19", "12": "20-49", "21": "50-99", "22": "100-199",
    "31": "200-249", "32": "250-499", "41": "500-999", "42": "1000-1999",
    "51": "2000-4999", "52": "5000-9999", "53": "10000+",
}


def fetch_page(code_naf, departement, page=1, per_page=25):
    params = {
        "q": "informatique",
        "code_naf": code_naf,
        "departement": departement,
        "page": page,
        "per_page": per_page,
    }
    try:
        r = requests.get(BASE_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"    [ERREUR] NAF {code_naf} / Dept {departement} / page {page} : {e}")
        return None


def extraire_infos(unite):
    siege = unite.get("siege", {})
    matching = unite.get("matching_etablissements", [{}])
    etab = matching[0] if matching else {}

    # Nom commercial = souvent plus court, plus proche du domaine web
    nom_commercial = siege.get("nom_commercial") or etab.get("nom_commercial") or None

    # Taille lisible
    code_effectif = unite.get("tranche_effectif_salarie", "")
    taille = TRANCHES_EFFECTIF.get(code_effectif, code_effectif)

    # Chiffre d'affaires le plus récent
    finances = unite.get("finances") or {}
    ca = None
    if finances:
        annee_max = max(finances.keys())
        ca = finances[annee_max].get("ca")

    # Dirigeant principal (première personne physique)
    dirigeant = ""
    for d in (unite.get("dirigeants") or []):
        if d.get("type_dirigeant") == "personne physique":
            dirigeant = f"{d.get('prenoms', '')} {d.get('nom', '')}".strip()
            break

    return {
        "nom": unite.get("nom_complet", "").strip(),
        "nom_commercial": nom_commercial,
        "siret": siege.get("siret", ""),
        "siren": unite.get("siren", ""),
        "code_naf": unite.get("activite_principale", ""),
        "adresse": siege.get("adresse", ""),
        "ville": siege.get("libelle_commune", ""),
        "code_postal": siege.get("code_postal", ""),
        "departement": siege.get("departement", ""),
        "site_web": None,
        "taille": taille,
        "categorie": unite.get("categorie_entreprise", ""),
        "ca": ca,
        "dirigeant": dirigeant,
        "traite": False,
    }


def charger_existants():
    if os.path.exists(FICHIER_SORTIE):
        with open(FICHIER_SORTIE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {e["siret"]: e for e in data if e.get("siret")}
    return {}


def sauvegarder(entreprises_dict):
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(list(entreprises_dict.values()), f, ensure_ascii=False, indent=2)


def main():
    print("=" * 55)
    print("  Chasseur d'Alternance — Fetch Entreprises IT IDF")
    print("=" * 55)

    entreprises = charger_existants()
    if entreprises:
        print(f"[Reprise] {len(entreprises)} entreprises déjà en base.\n")

    total_nouvelles = 0
    pages_vides_consecutives = 0

    for dept in DEPARTEMENTS:
        for naf in CODES_NAF:
            print(f"\n[API] Dept {dept} | NAF {naf}")
            page = 1
            pages_vides_consecutives = 0

            while True:
                data = fetch_page(naf, dept, page=page)
                if not data:
                    break

                resultats = data.get("results", [])
                total_pages = data.get("total_pages", 1)

                if not resultats:
                    print(f"  Aucun résultat.")
                    break

                nouvelles_cette_page = 0
                for unite in resultats:
                    infos = extraire_infos(unite)
                    siret = infos["siret"]
                    if siret and siret not in entreprises:
                        entreprises[siret] = infos
                        total_nouvelles += 1
                        nouvelles_cette_page += 1

                print(f"  Page {page}/{total_pages} — +{nouvelles_cette_page} nouvelles | Total : {len(entreprises)}")

                if page >= total_pages:
                    break

                # Arrêt anticipé si 3 pages sans nouvelles
                if nouvelles_cette_page == 0:
                    pages_vides_consecutives += 1
                    if pages_vides_consecutives >= 3:
                        print(f"  → 3 pages sans nouvelles, passage au suivant.")
                        break
                else:
                    pages_vides_consecutives = 0

                # Sauvegarde toutes les 10 pages
                if page % 10 == 0:
                    sauvegarder(entreprises)

                page += 1
                time.sleep(0.3)

    sauvegarder(entreprises)

    # Résumé avec stats utiles
    avec_ca      = sum(1 for e in entreprises.values() if e.get("ca"))
    avec_dir     = sum(1 for e in entreprises.values() if e.get("dirigeant"))
    avec_nom_com = sum(1 for e in entreprises.values() if e.get("nom_commercial"))
    par_cat      = {}
    for e in entreprises.values():
        c = e.get("categorie") or "?"
        par_cat[c] = par_cat.get(c, 0) + 1

    print("\n" + "=" * 55)
    print(f"  Total entreprises     : {len(entreprises)}")
    print(f"  Nouvelles ce run      : {total_nouvelles}")
    print(f"  Avec nom commercial   : {avec_nom_com}")
    print(f"  Avec dirigeant        : {avec_dir}")
    print(f"  Avec CA               : {avec_ca}")
    print(f"  Par catégorie         : {par_cat}")
    print(f"  Fichier               : {FICHIER_SORTIE}")
    print("=" * 55)
    print("\n→ Lance maintenant : python -m spontanees.scraper_emails.py")


if __name__ == "__main__":
    main()
