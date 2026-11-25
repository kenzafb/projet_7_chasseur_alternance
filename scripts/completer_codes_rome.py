"""
scripts/completer_codes_rome.py
===============================
Code métier ROME des offres France Travail déjà en base qui n'en ont pas
(récupérées avant D203) : redemandé à l'API, une requête par offre, d'après
son identifiant. Seule la colonne candidatures.code_rome est écrite ; une
offre qui n'existe plus garde un code vide, et rien d'autre n'est touché.

L'identifiant est lu dans le lien de l'offre et vérifié (son empreinte est
ref_offre) ; une offre dont le lien est celui d'un site partenaire n'a pas
d'identifiant lisible : elle est comptée et laissée.

Par défaut, lecture seule (base ouverte en mode=ro, l'API est interrogée) :
combien seraient remplies, combien n'existent plus. --appliquer refuse de
tourner si l'application est lancée, et écrit en une transaction à la fin
(un Ctrl+C avant n'écrit rien). Migration 0018 nécessaire
(venv/bin/alembic upgrade head). Identifiants FT_CLIENT_ID et
FT_CLIENT_SECRET du .env.

    venv/bin/python scripts/completer_codes_rome.py
    venv/bin/python scripts/completer_codes_rome.py --appliquer

Codes de sortie : 0 fait (ou lecture seule), 1 refus, 130 interruption.
"""

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests
from sqlalchemy import update
from sqlalchemy.exc import OperationalError

from audit_commun import session_lecture
from database.models import Candidature
from offres import france_travail as ft
from remettre_a_zero import Refus, application_lancee, fichier_base
from shared import config
from shared.offres import generer_id

URL_DETAIL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/"
DISPARUE = (204, 404, 410)
LIEN = re.compile(r"^https://candidat\.francetravail\.fr/offres/recherche/detail/([0-9A-Za-z]{4,20})/?$")


def identifiant(lien: str, ref_offre: str) -> str | None:
    """Identifiant France Travail lu dans le lien, seulement s'il est bien celui de l'offre."""
    m = LIEN.match((lien or "").strip())
    return m.group(1) if m and generer_id(m.group(1)) == ref_offre else None


def lire_code(ident: str, token: str) -> tuple[str, str]:
    """(état, code) : rempli, sans_code, disparue ou erreur. Refus si les
    identifiants sont refusés."""
    for essai in (1, 2):
        try:
            r = requests.get(URL_DETAIL + ident, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        except requests.RequestException as e:
            return "erreur", type(e).__name__
        if r.status_code == 429 and essai == 1:
            time.sleep(float(r.headers.get("Retry-After") or ft.ATTENTE_429_S))
            continue
        break
    if r.status_code in (401, 403):
        raise Refus(f"France Travail refuse l'accès ({r.status_code}), rien n'est écrit.")
    if r.status_code in DISPARUE:
        return "disparue", ""
    if r.status_code != 200:
        return "erreur", str(r.status_code)
    try:
        offre = r.json()
    except ValueError:
        return "erreur", "réponse illisible"
    if not isinstance(offre, dict) or offre.get("id") != ident:
        return "erreur", "autre offre"
    code = ft.code_rome(offre)
    return ("rempli", code) if code else ("sans_code", "")


def a_completer(base=None) -> list[tuple[int, str | None, str]]:
    """[(id, identifiant ou None, titre)] des offres France Travail sans code."""
    try:
        with session_lecture(base) as db:
            return [(c.id, identifiant(c.lien, c.ref_offre), c.titre or "")
                    for c in db.query(Candidature.id, Candidature.lien, Candidature.ref_offre, Candidature.titre)
                    .filter(Candidature.source == "France Travail", Candidature.code_rome == "")
                    .order_by(Candidature.id)]
    except OperationalError as e:
        if "code_rome" in str(e):
            raise Refus("La migration 0018 manque : lance d'abord venv/bin/alembic upgrade head.") from None
        raise


def refuser_si_lancee():
    lances = application_lancee(fichier_base(config.DATABASE_URL))
    if lances:
        raise Refus("L'application est lancée ou la base est ouverte, rien n'est écrit :\n  " + "\n  ".join(lances))


def ecrire(codes: dict[int, str]) -> int:
    """Écrit les codes en une transaction, dans les lignes encore vides."""
    from database.connexion import SessionLocal
    n = 0
    with SessionLocal() as db:
        for ident, code in codes.items():
            n += db.execute(update(Candidature).where(Candidature.id == ident, Candidature.code_rome == "")
                            .values(code_rome=code)).rowcount
        db.commit()
    return n


def completer(appliquer: bool, pause: float, afficher) -> int:
    if appliquer:
        refuser_si_lancee()
    offres = a_completer()
    afficher(f"{len(offres)} offre(s) France Travail sans code métier")
    if not offres:
        return 0
    token = ft.get_token(afficher)
    if not token:
        raise Refus("Jeton France Travail non obtenu.")
    codes, bilan, vus = {}, {"rempli": 0, "sans_code": 0, "disparue": 0, "erreur": 0, "sans_identifiant": 0}, {}
    for ligne, ident, titre in offres:
        if ident is None:
            bilan["sans_identifiant"] += 1
            continue
        if ident not in vus:               # même offre dans deux modes : une requête
            if vus:
                time.sleep(pause)
            vus[ident] = lire_code(ident, token)
        etat, code = vus[ident]
        bilan[etat] += 1
        if etat == "rempli":
            codes[ligne] = code
        afficher(f"  {code if etat == 'rempli' else etat.replace('_', ' ')}"
                 + (f" ({code})" if etat == "erreur" else "") + f" : {titre[:60]}")
    afficher(f"{bilan['rempli']} {'à remplir' if not appliquer else 'trouvée(s)'}, {bilan['disparue']} qui n'existent "
             f"plus, {bilan['sans_code']} sans code dans l'API, {bilan['sans_identifiant']} sans identifiant lisible, "
             f"{bilan['erreur']} en erreur (à relancer)")
    if not appliquer:
        afficher("Lecture seule : rien n'est écrit (ajouter --appliquer).")
        return 0
    refuser_si_lancee()                    # lancée pendant les requêtes ?
    afficher(f"{ecrire(codes)} code(s) écrit(s) en une transaction.")
    return 0


def main(argv=None, afficher=print) -> int:
    ap = argparse.ArgumentParser(description="Remplit le code métier des offres France Travail qui n'en ont pas.")
    ap.add_argument("--appliquer", action="store_true", help="écrire en base (sinon : lecture seule)")
    ap.add_argument("--pause", type=float, default=ft.PAUSE_S, help="secondes entre deux requêtes")
    args = ap.parse_args(argv)
    try:
        return completer(args.appliquer, args.pause, afficher)
    except Refus as e:
        afficher(f"Refusé : {e}")
        return 1
    except KeyboardInterrupt:
        afficher("Interrompu : rien n'a été écrit en base.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
