import requests
import os
import time
import hashlib
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

LBA_URL    = "https://api.apprentissage.beta.gouv.fr/api/job/v1/search"
IDF_LAT    = 48.8566
IDF_LNG    = 2.3522
IDF_RADIUS = 60

ALL_CODES_ROME_IT = [
    "M1801","M1802","M1803","M1804","M1805","M1806","M1807","M1808","M1809","M1810",
]

DEPTS_IDF = {"75","77","78","91","92","93","94","95"}


def generer_id(texte: str) -> str:
    return hashlib.md5(texte.encode()).hexdigest()


def detecter_zone(lieu: str) -> str | None:
    if not lieu:
        return None
    dept = lieu.split(" - ")[0].strip().lstrip("0")
    if dept not in DEPTS_IDF:
        return None
    if dept == "75" or "paris" in lieu.lower():
        return "Paris"
    if dept in {"92", "93", "94"}:
        return "Petite couronne"
    return "Grande couronne"


def _get_headers() -> dict:
    token = os.getenv("LBA_API_KEY")
    if not token:
        raise ValueError("LBA_API_KEY manquant dans .env")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _batches(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _normaliser_offre_lba(offre: dict) -> dict | None:
    # --- Lieu ---
    workplace    = offre.get("workplace", {}) or {}
    location     = workplace.get("location", {}) or {}
    address_str  = location.get("address", "") or ""

    # Extrait le code postal depuis la string "8 RUE DE LA VEGA 75012 PARIS"
    cp_match    = re.search(r'\b(\d{5})\b', address_str)
    code_postal = cp_match.group(1) if cp_match else ""

    if code_postal:
        dept = code_postal[:2]
        if dept not in DEPTS_IDF:
            return None
        zone = "Paris" if dept == "75" else ("Petite couronne" if dept in {"92","93","94"} else "Grande couronne")
    else:
        zone = detecter_zone(address_str)
        if zone is None:
            return None

    lieu_label = address_str

    # --- Titre ---
    offer = offre.get("offer", {}) or {}
    titre = offer.get("title", "") or ""
    if not titre or titre == "Sans titre":
        return None

    # --- ID ---
    identifier = offre.get("identifier", {}) or {}
    partner_id = identifier.get("partner_job_id", "") or identifier.get("id", "") or (titre + lieu_label)
    offre_id   = generer_id(f"lba_{partner_id}")

    # --- Lien ---
    apply = offre.get("apply", {}) or {}
    lien  = apply.get("url", "") or f"https://labonnealternance.apprentissage.beta.gouv.fr/emploi/{identifier.get('id', '')}"

    # --- Entreprise ---
    entreprise = workplace.get("name") or workplace.get("legal_name") or "Inconnue"

    # --- Description ---
    description = offer.get("description", "") or ""

    # --- Date ---
    publication = offer.get("publication", {}) or {}
    date_str    = (publication.get("creation", "") or "")[:10]
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    return {
        "id":           offre_id,
        "titre":        titre,
        "entreprise":   entreprise,
        "lieu":         lieu_label,
        "zone":         zone,
        "domaine":      "Non analysé",
        "lien":         lien,
        "source":       "La Bonne Alternance",
        "description":  description[:5000],
        "date_trouvee": date_str,
        "score":        0,
        "lettre":       "",
        "statut":       "nouveau",
    }


def chercher_offres_lba(codes_rome=None) -> list:
    # Par défaut les codes IT (rétrocompat)
    if not codes_rome:
        codes_rome = ALL_CODES_ROME_IT
    print(f"Recherche LBA (La Bonne Alternance) — {len(codes_rome)} codes ROME...")

    try:
        headers = _get_headers()
    except ValueError as e:
        print(f"  Erreur LBA : {e}")
        return []

    toutes   = []
    ids_vus  = set()
    hors_idf = 0
    erreurs  = 0

    for batch in _batches(codes_rome, 20):
        params = {
            "romes":     ",".join(batch),
            "latitude":  IDF_LAT,
            "longitude": IDF_LNG,
            "radius":    IDF_RADIUS,
            "partners_to_exclude": "France Travail",
        }

        try:
            r = requests.get(LBA_URL, params=params, headers=headers, timeout=20)

            if r.status_code == 401:
                print("  LBA 401 : token invalide, vérifier LBA_API_KEY dans .env")
                return toutes

            if r.status_code != 200:
                print(f"  LBA {r.status_code} : {r.text[:200]}")
                erreurs += 1
                time.sleep(1)
                continue

            data = r.json()

            # Nouvelle structure : data["jobs"] est une liste directe
            for offre in data.get("jobs", []):
                norm = _normaliser_offre_lba(offre)
                if norm is None:
                    hors_idf += 1
                    continue
                if norm["id"] not in ids_vus:
                    ids_vus.add(norm["id"])
                    toutes.append(norm)

        except Exception as e:
            print(f"  Erreur LBA batch {batch[:3]}... : {e}")
            erreurs += 1

        time.sleep(0.5)

    print(f"  {len(toutes)} offres LBA récupérées ({hors_idf} hors IDF écartées, {erreurs} erreurs)")
    return toutes


if __name__ == "__main__":
    offres = chercher_offres_lba()
    print(f"\n-- Aperçu des 5 premières --")
    for o in offres[:5]:
        print(f"\n[{o['source']}] {o['titre']}")
        print(f"  Entreprise : {o['entreprise']}")
        print(f"  Zone       : {o['zone']} | {o['lieu']}")
        print(f"  Lien       : {o['lien']}")
