"""API de La Bonne Alternance simulée, sans réseau : offres et entreprises à
fort potentiel placées sur une carte, filtrées par codes métiers, distance,
niveau de diplôme et partenaire, avec un plafond par source.

Le comportement des points encore à vérifier (SPEC_SOURCES section 7) est
réglable : nom du paramètre de niveau, codes par requête, rayon maximal,
recherche sans code, exclusion des partenaires ignorée ou non.
"""

import json
import math


class Reponse:
    def __init__(self, statut=200, corps=None):
        self.status_code = statut
        self._corps = corps
        self.headers = {}
        self.text = json.dumps(corps) if corps is not None else ""

    def json(self):
        if self._corps is None:
            raise ValueError("pas de JSON")
        return self._corps


def distance_km(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return 6371 * math.hypot(x, y)


def offre(n, rome="M1805", lieu=(48.8566, 2.3522), cp="75012", niveau=6, partenaire="La bonne alternance",
          titre=None):
    """Offre au format de l'API ; niveau None : sans niveau indiqué."""
    o = {
        "identifier": {"id": f"job{n}", "partner_label": partenaire, "partner_job_id": f"p{n}"},
        "workplace": {"name": f"Employeur {n}", "siret": f"{n:014d}",
                      "location": {"address": f"{n} RUE TEST {cp} VILLE"}},
        "apply": {"url": f"https://lba.example/emploi/{n}"},
        "offer": {"title": titre or f"Alternance {n}", "description": "desc",
                  "rome_codes": [rome], "target_diploma": {"european": str(niveau)},
                  "publication": {"creation": "2026-10-01T10:00:00.000Z"}},
        "_rome": rome, "_lieu": lieu, "_niveau": niveau,
    }
    if niveau is None:
        del o["offer"]["target_diploma"]
    return o


def siret_lba(n):
    """SIRET d'entreprise simulée : SIREN distinct pour chaque n (9 puis n sur 8 chiffres)."""
    return f"9{n:08d}00011"


def entreprise(n, rome="M1805", lieu=(48.8566, 2.3522), cp="75012", siret=None, email=None, taille="20-49"):
    e = {
        "identifier": {"id": f"rec{n}"},
        "workplace": {"siret": siret or siret_lba(n), "name": f"Société {n}", "brand": None,
                      "legal_name": f"SOCIETE {n} SAS", "website": None, "size": taille,
                      "location": {"address": f"{n} AVENUE TEST {cp} VILLE"},
                      "domain": {"naf": {"code": "6201Z", "label": "Programmation informatique"}}},
        "apply": {"url": f"https://lba.example/recruteur/{n}", "phone": "0102030405",
                  "recipient_id": f"recruteurs_lba_{n}"},
        "_rome": rome, "_lieu": lieu,
    }
    if email:
        e["apply"]["email"] = email
    return e


class FausseLBA:
    """Remplace requests.get (ou une session) pour La Bonne Alternance."""

    def __init__(self, offres=(), entreprises=(), param_niveau="target_diploma_level", codes_max=20,
                 rayon_max=200, sans_codes=False, exclusion_ignoree=False, plafond=150,
                 parametres_inconnus_refuses=False):
        self.offres = list(offres)
        self.entreprises = list(entreprises)
        self.param_niveau = param_niveau
        self.codes_max = codes_max
        self.rayon_max = rayon_max
        self.sans_codes = sans_codes
        self.exclusion_ignoree = exclusion_ignoree
        self.plafond = plafond
        # Paramètre inconnu : 400 (validation stricte) plutôt qu'ignoré
        self.parametres_inconnus_refuses = parametres_inconnus_refuses
        self.recherches = []

    def get(self, url, params=None, headers=None, timeout=None, **_):
        params = dict(params or {})
        self.recherches.append(params)
        if not (headers or {}).get("Authorization", "").startswith("Bearer ") or \
                headers["Authorization"] == "Bearer ":
            return Reponse(401, {"error": "Unauthorized"})
        connus = {"romes", "latitude", "longitude", "radius", "partners_to_exclude", self.param_niveau}
        inconnus = set(params) - connus
        if inconnus and self.parametres_inconnus_refuses:
            return Reponse(400, {"message": f"paramètres inconnus : {sorted(inconnus)}"})
        romes = [r for r in str(params.get("romes", "")).split(",") if r]
        if not romes and not self.sans_codes:
            return Reponse(400, {"message": "romes ou rncp requis"})
        if len(romes) > self.codes_max:
            return Reponse(400, {"message": f"romes : {self.codes_max} au plus"})
        rayon = float(params.get("radius", 30))
        if rayon > self.rayon_max:
            return Reponse(400, {"message": f"radius : {self.rayon_max} au plus"})
        niveau = params.get(self.param_niveau)
        if niveau is not None and niveau not in {"3", "4", "5", "6", "7"}:
            return Reponse(400, {"message": "niveau : 3, 4, 5, 6 ou 7"})
        centre = None
        if "latitude" in params:
            centre = (float(params["latitude"]), float(params["longitude"]))

        def garde(x):
            return ((not romes or x["_rome"] in romes)
                    and (centre is None or distance_km(centre, x["_lieu"]) <= rayon))

        offres = [o for o in self.offres if garde(o) and (niveau is None or str(o["_niveau"]) == niveau)]
        exclus = str(params.get("partners_to_exclude", "")).split(",")
        if not self.exclusion_ignoree:
            offres = [o for o in offres if o["identifier"]["partner_label"] not in exclus]
        par_source = {}
        for o in offres:
            par_source.setdefault(o["identifier"]["partner_label"], []).append(o)
        offres = [o for groupe in par_source.values() for o in groupe[:self.plafond]]
        entreprises = [e for e in self.entreprises if garde(e)][:self.plafond]
        return Reponse(200, {"jobs": offres, "recruiters": entreprises, "warnings": []})
