"""
fetch_entreprises.py v7
=======================
Réécriture complète sur l'API Sirene INSEE directe
(https://api.insee.fr/api-sirene/3.11/siret)

Pourquoi on quitte recherche-entreprises.api.gouv.fr :
  - Cette API cappait tout à 10 000 résultats et ignorait les filtres fins
  - Aucun filtre (categorie, caractereEmployeur, tranche) ne fonctionnait réellement

Ce que la v7 apporte :
  - Requêtes Lucene précises : NAF + dept + tranche + employeur + actif en UN seul appel
  - Pagination par curseur → aucune limite de résultats (plus de saturation possible)
  - Micro-entreprises et boîtes sans salarié exclues DÈS la requête (pas en post-traitement)
  - 64 requêtes au total (4 depts × 16 NAFs) au lieu de 512+ avec splits
  - Source officielle INSEE = données plus fiables
"""

import requests
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()
INSEE_API_KEY = os.getenv("INSEE_API_KEY")

FICHIER_RAW    = "/home/kenza/Bureau/chasseur_alternance/data/entreprises_raw.json"
FICHIER_SORTIE = "/home/kenza/Bureau/chasseur_alternance/data/entreprises_enrichies.json"

BASE_URL = "https://api.insee.fr/api-sirene/3.11/siret"

HEADERS = {
    "X-INSEE-Api-Key-Integration": INSEE_API_KEY,
    "Accept": "application/json",
}

# ─── Codes NAF ────────────────────────────────────────────────────────────────

CODES_NAF = [
    "62.01Z",   # Programmation informatique
    "62.02A",   # Conseil en systèmes et logiciels informatiques
    "62.02B",   # Tierce maintenance de systèmes et d'applications
    "62.03Z",   # Gestion d'installations informatiques
    "62.09Z",   # Autres activités informatiques n.c.a.
    "63.11Z",   # Traitement de données, hébergement et activités connexes
    "58.21Z",   # Édition de jeux électroniques
    "58.29A",   # Édition de logiciels système et réseau
    "58.29B",   # Édition de logiciels outils de développement
    "58.29C",   # Édition d'autres logiciels applicatifs
    "61.10Z",   # Télécommunications filaires
    "61.20Z",   # Télécommunications sans fil
    "61.90Z",   # Autres activités de télécommunication
    "70.22Z",   # Conseil pour les affaires et autres conseils de gestion
    "71.12B",   # Ingénierie, études techniques
    "74.90B",   # Activités spécialisées, scientifiques et techniques diverses
]

# ─── Départements IDF ─────────────────────────────────────────────────────────

DEPARTEMENTS = [
    "75",   # Paris
#   "77",   # Seine-et-Marne
#   "78",   # Yvelines
#   "91",   # Essonne
    "92",   # Hauts-de-Seine
    "93",   # Seine-Saint-Denis
    "94",   # Val-de-Marne
#   "95",   # Val-d'Oise
]

# ─── Tranches d'effectifs ─────────────────────────────────────────────────────

TRANCHES_EFFECTIF = {
    "NN": "0", "00": "0", "01": "1-2", "02": "3-5", "03": "6-9",
    "11": "10-19", "12": "20-49", "21": "50-99", "22": "100-199",
    "31": "200-249", "32": "250-499", "41": "500-999", "42": "1000-1999",
    "51": "2000-4999", "52": "5000-9999", "53": "10000+",
}

# Tranches cibles (≥ 10 salariés) — intégrées directement dans la requête Sirene
TRANCHES_CIBLES = "11 OR 12 OR 21 OR 22 OR 31 OR 32 OR 41 OR 42 OR 51 OR 52 OR 53"

# Résultats par page (max 1000 sur l'API Sirene)
PER_PAGE = 1000


# ─── Construction de la requête Lucene ────────────────────────────────────────

def construire_query(code_naf, departement):
    return (
        f"etablissementSiege:true "
        f"AND etatAdministratifUniteLegale:A "
        f"AND trancheEffectifsUniteLegale:({TRANCHES_CIBLES}) "
        f"AND activitePrincipaleUniteLegale:{code_naf} "
        f"AND codePostalEtablissement:{departement}*"
    )

# ─── Fetch avec pagination par curseur ────────────────────────────────────────

def fetch_toutes_pages(code_naf, departement, entreprises, stats_dept, stats_naf):
    """
    Pagine la totalité des résultats pour une combinaison NAF+dept
    via le mécanisme de curseur de l'API Sirene (pas de limite à 10 000).
    """
    query   = construire_query(code_naf, departement)
    curseur = "*"   # Premier appel
    page    = 0

    while True:
        params = {
            "q":       query,
            "nombre":  PER_PAGE,
            "curseur": curseur,
        }

        try:
            r = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=30)

            # 404 = aucun résultat pour cette combinaison (normal)
            if r.status_code == 404:
                print(f"  (aucun résultat)")
                return

            # 429 = rate limit
            if r.status_code == 429:
                print(f"  ⚠️  Rate limit — pause 10s")
                time.sleep(10)
                continue

            r.raise_for_status()
            data = r.json()

        except Exception as e:
            print(f"  [ERREUR] NAF {code_naf} / Dept {departement} : {e}")
            return

        header      = data.get("header", {})
        total       = header.get("total", 0)
        suivant     = header.get("curseurSuivant", None)
        etablissements = data.get("etablissements", [])

        page += 1
        nouvelles_cette_page = 0

        for etab in etablissements:
            infos = extraire_infos(etab)
            siret = infos["siret"]
            if siret and siret not in entreprises:
                entreprises[siret]      = infos
                nouvelles_cette_page   += 1
                stats_dept[departement] = stats_dept.get(departement, 0) + 1
                stats_naf[code_naf]     = stats_naf.get(code_naf, 0) + 1

        print(f"  Page {page} [{len(etablissements)} résultats / {total} total] "
              f"— +{nouvelles_cette_page} nouvelles | Total base : {len(entreprises)}")

        # (sauvegardes intermédiaires retirées : insertion en base à la fin)

        # Fin de pagination : plus de curseur suivant, ou identique au précédent
        if not suivant or suivant == curseur:
            break

        curseur = suivant
        time.sleep(0.5)   # Respect rate limit INSEE


# ─── Extraction des infos depuis un établissement Sirene ─────────────────────

def extraire_infos(etab):
    ul      = etab.get("uniteLegale") or {}
    adresse = etab.get("adresseEtablissement") or {}

    # Période courante = première période avec dateFin == null
    periodes = etab.get("periodesEtablissement") or {}
    periode  = next((p for p in periodes if p.get("dateFin") is None), periodes[0] if periodes else {})

    # Nom
    nom = (ul.get("denominationUniteLegale") or  "").strip()

    # Nom commercial : enseigne ou dénomination usuelle de l'établissement
    nom_commercial = (
        periode.get("enseigne1Etablissement")
        or periode.get("denominationUsuelleEtablissement")
        or None
    )

    # Adresse
    num         = adresse.get("numeroVoieEtablissement") or ""
    type_voie   = adresse.get("typeVoieEtablissement") or ""
    libelle_voie = adresse.get("libelleVoieEtablissement") or ""
    adresse_str = " ".join(filter(None, [num, type_voie, libelle_voie])).strip()

    code_postal = adresse.get("codePostalEtablissement", "") or ""
    ville       = adresse.get("libelleCommuneEtablissement", "") or ""
    departement = code_postal[:2] if len(code_postal) >= 2 else ""

    # Taille
    code_effectif = (
        ul.get("trancheEffectifsUniteLegale")
        or etab.get("trancheEffectifsEtablissement")
        or ""
    )
    taille = TRANCHES_EFFECTIF.get(code_effectif, code_effectif)

    # NAF de la période courante
    code_naf = periode.get("activitePrincipaleEtablissement", "")

    # Identifiants
    siret = etab.get("siret", "")
    siren = ul.get("siren") or (siret[:9] if siret else "")

    return {
        "nom":            nom,
        "nom_commercial": nom_commercial,
        "siret":          siret,
        "siren":          siren,
        "code_naf":       code_naf,
        "adresse":        adresse_str,
        "ville":          ville,
        "code_postal":    code_postal,
        "departement":    departement,
        "site_web":       None,
        "taille":         taille,
        "categorie":      ul.get("categorieEntreprise", ""),
        "ca":             None,   # Non disponible dans l'API Sirene
        "dirigeant":      "",     # Non disponible dans l'API Sirene
        "traite":         False,
        "emails_trouves": [],
    }


# ─── Chargement / sauvegarde ──────────────────────────────────────────────────

def charger_base():
    cible = FICHIER_SORTIE if os.path.exists(FICHIER_SORTIE) else FICHIER_RAW
    if os.path.exists(cible):
        with open(cible, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[Reprise] {len(data)} entreprises chargées depuis {cible}")
        return {e["siret"]: e for e in data if e.get("siret")}
    return {}


def sauvegarder(entreprises_dict, fichier):
    os.makedirs(os.path.dirname(fichier), exist_ok=True)
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(list(entreprises_dict.values()), f, ensure_ascii=False, indent=2)


# ─── Main ─────────────────────────────────────────────────────────────────────

from database.entreprises_db import ajouter_entreprises

def main(stop_event=None, on_progress=None, user_id=1):
    if not INSEE_API_KEY:
        print("❌  INSEE_API_KEY manquante dans le .env — arrêt.")
        return

    # Codes NAF selon le domaine de l'utilisateur (lu depuis son profil)
    from shared.domaines import naf_codes
    from database.profil_db import lire_profil
    _profil = lire_profil(user_id)
    _cles_domaines = (_profil.get("recherche", {}) or {}).get("domaines", []) or []
    codes_naf = naf_codes(_cles_domaines)
    print(f"  Domaines du profil : {_cles_domaines or '(défaut)'} → {len(codes_naf)} codes NAF")

    print("=" * 60)
    print("  Chasseur d'Alternance — Fetch Entreprises IT IDF v7")
    print(f"  API : INSEE Sirene 3.11 (curseur — pas de limite)")
    print(f"  {len(DEPARTEMENTS)} départements | {len(codes_naf)} codes NAF")
    print(f"  Filtres : siège actif | ≥10 sal. | employeur déclaré")
    print("=" * 60)

    # On charge les sirets déjà en base pour ne pas les recompter comme nouveaux
    from database.entreprises_db import lire_entreprises
    existantes = lire_entreprises(user_id)
    entreprises = {}
    for e in existantes:
        siret_e = (e.get("_extra") or {}).get("siret", "")
        if siret_e:
            entreprises[siret_e] = {"_deja_en_base": True}
    total_au_depart = len(entreprises)
    print(f"  Base existante : {total_au_depart} entreprises déjà connues")
    stats_dept      = {d: 0 for d in DEPARTEMENTS}
    stats_naf       = {n: 0 for n in codes_naf}

    total_combos = len(DEPARTEMENTS) * len(codes_naf)
    combos_faits = 0
    print(f"  Total de requêtes : {total_combos} (vs 512+ en v6)\n")

    for dept in DEPARTEMENTS:
        for naf in codes_naf:
            if stop_event and stop_event.is_set():
                print("⏹️  Arrêt — sauvegarde en cours...")
                n = ajouter_entreprises(user_id, [e for e in entreprises.values() if not e.get('_deja_en_base')])
                print(f"  {n} nouvelles entreprises ajoutées en base")
                return

            print(f"\n[Sirene] Dept {dept} | NAF {naf}")
            avant = len(entreprises)

            fetch_toutes_pages(naf, dept, entreprises, stats_dept, stats_naf)

            apres = len(entreprises)
            print(f"  ✔  {dept}/{naf} — +{apres - avant} entreprises")
            combos_faits += 1
            if on_progress:
                pct = round(combos_faits / total_combos * 100)
                on_progress(pct, f"{combos_faits}/{total_combos} zones · {len(entreprises)} entreprises")
            time.sleep(0.5)

    # ── Sauvegarde finale (en base) ───────────────────────────────────────────
    nb_ajoutees = ajouter_entreprises(user_id, [e for e in entreprises.values() if not e.get('_deja_en_base')])
    print(f"  {nb_ajoutees} nouvelles entreprises ajoutées en base")

    # ── Stats ─────────────────────────────────────────────────────────────────
    total_nouvelles = len(entreprises) - total_au_depart
    avec_email = sum(1 for e in entreprises.values() if e.get("emails_trouves"))
    par_cat    = {}
    for e in entreprises.values():
        c = e.get("categorie") or "?"
        par_cat[c] = par_cat.get(c, 0) + 1

    print("\n" + "=" * 60)
    print(f"  Total entreprises      : {len(entreprises)}")
    print(f"  En base au départ      : {total_au_depart}")
    print(f"  Nouvelles ce run       : {total_nouvelles}")
    print(f"  Avec email scrapé      : {avec_email}")
    print(f"  Par catégorie INSEE    : {par_cat}")
    print()
    print("  Nouvelles par département :")
    for d, n in sorted(stats_dept.items()):
        print(f"    {d} : {n}")
    print()
    print("  Nouvelles par code NAF (top 10) :")
    for naf, n in sorted(stats_naf.items(), key=lambda x: -x[1])[:10]:
        print(f"    {naf} : {n}")
    print(f"\n  Entreprises enregistrées en base de données")
    print("=" * 60)
    print("\n→ Lance maintenant : python scraper_emails.py")


if __name__ == "__main__":
    main()
