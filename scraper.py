import requests
import json
import os
import time
import hashlib
from datetime import datetime
from dotenv import load_dotenv
from profil import PROFIL

load_dotenv()

FICHIER_VUES = "offres_vues.json"

def charger_offres_vues():
    if os.path.exists(FICHIER_VUES):
        with open(FICHIER_VUES, "r") as f:
            return set(json.load(f))
    return set()

def sauvegarder_offres_vues(vues):
    with open(FICHIER_VUES, "w") as f:
        json.dump(list(vues), f)

def generer_id(texte):
    return hashlib.md5(texte.encode()).hexdigest()

# ─────────────────────────────────────────────
# AUTHENTIFICATION FRANCE TRAVAIL
# Le token expire après 25 minutes.
# On le régénère automatiquement si besoin.
# ─────────────────────────────────────────────
_token_cache = {"token": None, "expire": 0}

def get_token():
    if time.time() < _token_cache["expire"]:
        return _token_cache["token"]

    r = requests.post(
        "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire",
        data={
            "grant_type": "client_credentials",
            "client_id": os.getenv("FT_CLIENT_ID"),
            "client_secret": os.getenv("FT_CLIENT_SECRET"),
            "scope": "api_offresdemploiv2 o2dsoffre"
        }
    )

    if r.status_code == 200:
        data = r.json()
        _token_cache["token"] = data["access_token"]
        _token_cache["expire"] = time.time() + data["expires_in"] - 60
        return _token_cache["token"]
    else:
        print(f"Erreur token France Travail : {r.status_code}")
        return None


# ─────────────────────────────────────────────
# SCRAPER FRANCE TRAVAIL
# ─────────────────────────────────────────────
def scraper_france_travail(query):
    offres = []
    token = get_token()
    if not token:
        return offres

    url = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
    params = {
        "motsCles": query + " alternance",
	"region": "11",
        "range": "0-14",
        "sort": "1",
    }
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code in [200, 206]:
            data = r.json()
            for offre in data.get("resultats", []):
                lien = offre.get("origineOffre", {}).get("urlOrigine", "")
                if not lien:
                    lien = f"https://candidat.francetravail.fr/offres/recherche/detail/{offre.get('id', '')}"
                offres.append({
                    "id": generer_id(offre.get("id", lien)),
                    "titre": offre.get("intitule", "Sans titre"),
                    "entreprise": offre.get("entreprise", {}).get("nom", "Inconnue"),
                    "lieu": offre.get("lieuTravail", {}).get("libelle", "Paris"),
                    "lien": lien,
                    "source": "France Travail",
                    "description": offre.get("description", "")[:800],
                    "date_trouvee": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "score": 0,
                    "lettre": "",
                    "statut": "nouveau"
                })
        else:
            print(f"  France Travail {r.status_code} pour '{query}'")
    except Exception as e:
        print(f"  Erreur France Travail ({query}) : {e}")

    return offres


# ─────────────────────────────────────────────
# FONCTION PRINCIPALE
# ─────────────────────────────────────────────
def chercher_offres():
    print("Recherche des offres en cours...\n")

    offres_vues = charger_offres_vues()
    toutes_offres = []
    ids_session = set()

    queries = PROFIL["recherche"]["titre_poste"]

    for query in queries:
        print(f"  -> '{query}'")
        nouvelles = scraper_france_travail(query)

        for offre in nouvelles:
            if offre["id"] not in offres_vues and offre["id"] not in ids_session:
                if offre["titre"] and offre["titre"] != "Sans titre":
                    toutes_offres.append(offre)
                    ids_session.add(offre["id"])

        time.sleep(0.3)

    print(f"\n{len(toutes_offres)} nouvelles offres trouvees !\n")
    return toutes_offres, offres_vues


if __name__ == "__main__":
    offres, _ = chercher_offres()
    print(f"\n-- Apercu des 5 premieres --")
    for o in offres[:5]:
        print(f"\n[{o['source']}] {o['titre']}")
        print(f"  Entreprise : {o['entreprise']}")
        print(f"  Lieu       : {o['lieu']}")
        print(f"  Lien       : {o['lien']}")
