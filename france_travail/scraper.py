import requests
import json
import os
import time
import hashlib
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DEPTS_IDF = {"75", "77", "78", "91", "92", "93", "94", "95"}


def detecter_zone(lieu):
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


def _fichier_vues(mode="alternance"):
    return f"data/offres_vues_{mode}.json"


def charger_offres_vues(mode="alternance"):
    fichier = _fichier_vues(mode)
    if os.path.exists(fichier):
        with open(fichier, "r") as f:
            return set(json.load(f))
    return set()


def sauvegarder_offres_vues(vues, mode="alternance"):
    fichier = _fichier_vues(mode)
    os.makedirs(os.path.dirname(fichier), exist_ok=True)
    with open(fichier, "w") as f:
        json.dump(list(vues), f)


def generer_id(texte):
    return hashlib.md5(texte.encode()).hexdigest()


_token_cache = {"token": None, "expire": 0}


def get_token():
    if time.time() < _token_cache["expire"]:
        return _token_cache["token"]
    r = requests.post(
        "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire",
        data={
            "grant_type":    "client_credentials",
            "client_id":     os.getenv("FT_CLIENT_ID"),
            "client_secret": os.getenv("FT_CLIENT_SECRET"),
            "scope":         "api_offresdemploiv2 o2dsoffre",
        },
    )
    if r.status_code == 200:
        data = r.json()
        _token_cache["token"]  = data["access_token"]
        _token_cache["expire"] = time.time() + data["expires_in"] - 60
        return _token_cache["token"]
    print(f"Erreur token France Travail : {r.status_code} – {r.text}")
    return None


def _paginer(params_base: dict) -> list:
    offres = []
    token = get_token()
    if not token:
        return offres

    url     = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
    headers = {"Authorization": f"Bearer {token}"}
    debut   = 0
    taille  = 100
    total_attendu = None

    while True:
        fin    = debut + taille - 1
        params = {**params_base, "range": f"{debut}-{fin}"}

        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)

            if r.status_code == 204:
                break

            if r.status_code not in [200, 206]:
                print(f"  FT {r.status_code} (range {debut}-{fin}) : {r.text[:200]}")
                break

            content_range = r.headers.get("Content-Range", "")
            if content_range and total_attendu is None:
                try:
                    total_attendu = int(content_range.split("/")[-1])
                    print(f"  {total_attendu} offres disponibles côté France Travail")
                except Exception:
                    pass

            resultats = r.json().get("resultats", [])
            if not resultats:
                break

            offres.extend(resultats)
            debut += taille

            if total_attendu and debut >= min(total_attendu, 3000):
                break
            if len(resultats) < taille:
                break

            time.sleep(0.4)

        except Exception as e:
            print(f"  Erreur range {debut}-{fin} : {e}")
            break

    return offres


def _normaliser(bruts: list) -> list:
    offres   = []
    hors_idf = 0

    for offre in bruts:
        lien = offre.get("origineOffre", {}).get("urlOrigine", "")
        if not lien:
            lien = f"https://candidat.francetravail.fr/offres/recherche/detail/{offre.get('id', '')}"

        lieu = offre.get("lieuTravail", {}).get("libelle", "")
        zone = detecter_zone(lieu)
        if zone is None:
            hors_idf += 1
            continue

        # --- Enrichissement description ---
        desc = offre.get("description", "")

        # Description entreprise
        desc_entreprise = offre.get("entreprise", {}).get("description", "")
        if desc_entreprise:
            desc += f"\n\nEntreprise : {desc_entreprise}"

        # Infos contrat
        exp     = offre.get("experienceLibelle", "")
        duree   = offre.get("dureeTravailLibelleConverti", "")
        salaire = offre.get("salaire", {}).get("libelle", "")
        qualif  = offre.get("qualificationLibelle", "")
        secteur = offre.get("secteurActiviteLibelle", "")

        if exp:     desc += f"\nExpérience : {exp}"
        if duree:   desc += f"\nDurée : {duree}"
        if salaire: desc += f"\nSalaire : {salaire}"
        if qualif:  desc += f"\nQualification : {qualif}"
        if secteur: desc += f"\nSecteur : {secteur}"

        # Formations (~10% des offres mais critique pour détecter Bac+5)
        for f in offre.get("formations", []):
            niv       = f.get("niveauLibelle", "")
            domaine_f = f.get("domaineLibelle", "")
            exige     = "indispensable" if f.get("exigence") == "E" else "souhaitée"
            label     = " - ".join(filter(None, [domaine_f, niv]))
            if label: desc += f"\nFormation : {label} ({exige})"

        # Compétences (~10% des offres)
        for c in offre.get("competences", []):
            lib   = c.get("libelle", "")
            exige = "indispensable" if c.get("exigence") == "E" else "souhaitée"
            if lib: desc += f"\nCompétence : {lib} ({exige})"

        # Langues (rare mais utile)
        for l in offre.get("langues", []):
            lib   = l.get("libelle", "")
            exige = "indispensable" if l.get("exigence") == "E" else "souhaitée"
            if lib: desc += f"\nLangue : {lib} ({exige})"

        offres.append({
            "id":           generer_id(offre.get("id", lien)),
            "titre":        offre.get("intitule", "Sans titre"),
            "entreprise":   offre.get("entreprise", {}).get("nom", "Inconnue"),
            "lieu":         lieu,
            "zone":         zone,
            "domaine":      "Non analysé",
            "lien":         lien,
            "source":       "France Travail",
            "description":  desc[:10000],
            "date_trouvee": (offre.get("dateCreation") or "")[:10] or datetime.now().strftime("%Y-%m-%d"),
            "score":        0,
            "lettre":       "",
            "statut":       "nouveau",
            "_alternance":  bool(offre.get("alternance", False)),
        })

    if hors_idf:
        print(f"  {hors_idf} offres hors IDF écartées")
    return offres


def chercher_offres(grands_domaines=None, ft_params=None, filtrer_domaines=True,
                    mode="alternance", limite_lot=None) -> tuple[list, set]:
    # ft_params : paramètres FT spécifiques au mode (E2 pour alternance, CDD pour job)
    if ft_params is None:
        ft_params = {"natureContrat": "E2"}   # défaut alternance (rétrocompat)
    offres_vues = charger_offres_vues(mode)

    bruts = []
    base_params = {"region": "11", "sort": "1", **ft_params}

    if filtrer_domaines:
        # Mode alternance : on filtre par grand domaine (1 requête par domaine)
        if not grands_domaines:
            grands_domaines = ["M18"]
        print(f"Recherche FT (IDF, domaines: {', '.join(grands_domaines)}, params: {ft_params})...\n")
        for gd in grands_domaines:
            bruts += _paginer({**base_params, "grandDomaine": gd})
    else:
        # Mode job : recherche large, pas de filtre domaine
        print(f"Recherche FT (IDF, tous domaines, params: {ft_params})...\n")
        bruts += _paginer(base_params)

    candidates   = _normaliser(bruts)
    toutes_offres = [
        o for o in candidates
        if o["id"] not in offres_vues and o["titre"] != "Sans titre"
    ]

    # Mode job (pas de filtre domaine) : exclure les offres d'alternance/apprentissage
    if not filtrer_domaines:
        avant = len(toutes_offres)
        toutes_offres = [o for o in toutes_offres if not o.get("_alternance")]
        exclues = avant - len(toutes_offres)
        if exclues:
            print(f"  {exclues} offres d'alternance écartées (mode job)")

    # Mode job : on traite par LOTS (ex. 100/run) pour ne pas tout analyser d'un coup
    if limite_lot:
        toutes_offres = toutes_offres[:limite_lot]
        ids_a_marquer = {o["id"] for o in toutes_offres}
        sauvegarder_offres_vues(offres_vues | ids_a_marquer, mode)
    else:
        nouveaux_ids = {o["id"] for o in candidates}
        sauvegarder_offres_vues(offres_vues | nouveaux_ids, mode)

    print(f"\n{len(toutes_offres)} nouvelles offres FT trouvées (hors déjà vues) !\n")
    return toutes_offres, offres_vues


if __name__ == "__main__":
    offres, _ = chercher_offres()
    print(f"\n-- Aperçu des 5 premières --")
    for o in offres[:5]:
        print(f"\n[{o['source']}] {o['titre']}")
        print(f"  Zone : {o['zone']} | {o['lieu']}")
        print(f"  Lien : {o['lien']}")
