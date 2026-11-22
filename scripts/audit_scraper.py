"""
scripts/audit_scraper.py
========================
Audit C (phase 15) : le scraper d'emails des candidatures spontanées
(spontanees/recherche_emails.py).

C1, sans réseau : échantillon de 40 entreprises de la base (LECTURE SEULE),
mélange de tailles et de secteurs, avec et sans email trouvé : nom, site,
URL lue, emails trouvés, douteux, écartés par l'IA, provenance, traitement.
La base ne garde pas les pages visitées ni les adresses écartées par les
règles : C2 les mesure.

    CHASSEUR_ENV_FILE=/dev/null venv/bin/python scripts/audit_scraper.py echantillon --base sqlite:///data/chasseur_v2.db

C2, réseau (à lancer par l'humain) : rejoue scraper_et_extraire, la fonction
de l'application, sur l'échantillon (ou --fichier), en notant chaque requête
HTTP : URL, statut, durée, taille, type, redirection, erreur, et si
robots.txt l'interdit ; le temps passé en pauses ; puis, pour chaque page
HTML reçue, les signes d'une page rendue en JavaScript (peu de texte, beaucoup
de scripts, racine d'application vide, <noscript>), les formulaires de
contact (textarea, champ email) et les liens mailto. Les entreprises sans
site passent par la recherche DuckDuckGo de l'application (--sans-ddg pour
l'éviter). IA coupée par défaut (--ia pour la validation des douteuses).
Rien n'est écrit en base.

    venv/bin/python scripts/audit_scraper.py mesure                      # audit_exports/scraper_echantillon.json
    venv/bin/python scripts/audit_scraper.py mesure --max 10 --sans-ddg

Sorties : audit_exports/scraper_echantillon.json (C1),
audit_exports/scraper_mesure.json (C2, détail par site et synthèse) et
audit_exports/emails_candidats.json (adresses vues, au format du banc
d'emails, « attendu_valide » à remplir). Compter 30 s à 1 min par site
(pauses de l'application comprises).
"""

import argparse
import random
import re
import time
import urllib.robotparser
from collections import Counter
from urllib.parse import urlparse

from audit_commun import Chrono, ecrire_json, lire_json, maintenant, pourcentage, session_lecture, SORTIE  # noqa: E402

TAILLE_ECHANTILLON = 40
UA_ROBOTS = "*"


# ─── C1 : échantillon ─────────────────────────────────────────────────────────
def echantillon(base, user=None, taille=TAILLE_ECHANTILLON, graine=15) -> dict:
    from database.models import Entreprise, EntrepriseMode
    lignes = []
    with session_lecture(base) as db:
        q = db.query(Entreprise)
        if user:
            q = q.filter(Entreprise.user_id == user)
        for e in q:
            extra = e.extra or {}
            lignes.append({
                "id": e.id, "user_id": e.user_id, "nom": e.nom_commercial or extra.get("nom") or "",
                "raison_sociale": extra.get("nom", ""), "siren": e.siren, "ville": e.ville, "code_postal": e.code_postal,
                "taille": extra.get("taille", ""), "categorie": extra.get("categorie", ""), "naf": e.naf_rev2,
                "secteur": e.secteur, "sources": e.sources or [],
                "modes": [m.mode for m in db.query(EntrepriseMode).filter_by(entreprise_id=e.id)],
                "site_web": e.site_web or "", "url_scrapee": extra.get("url_scrapee", ""),
                "source_site": extra.get("source_recherche", ""), "tentatives_site": extra.get("tentatives_site", 0),
                "traite": bool(e.traite), "emails_trouves": e.emails_trouves or [],
                "emails_douteux": extra.get("emails_douteux"), "emails_ecartes_ia": extra.get("emails_ecartes_ia", []),
                "validation": extra.get("validation_emails", {}), "meilleur_contact": extra.get("meilleur_contact"),
                "pages_visitees": "non enregistré par l'application (voir la mesure C2)",
                "emails_ecartes_par_les_regles": "non enregistré par l'application (voir la mesure C2)"})
    hasard = random.Random(graine)
    avec = [x for x in lignes if x["emails_trouves"]]
    traites_sans = [x for x in lignes if x["traite"] and not x["emails_trouves"]]
    reste = [x for x in lignes if not x["traite"]]
    choix = avec + traites_sans
    # Le reste : réparti par taille puis par division NAF, pour mélanger
    par_strate = {}
    for x in reste:
        par_strate.setdefault((x["taille"] or "?", (x["naf"] or "?")[:2]), []).append(x)
    strates = list(par_strate.values())
    for s in strates:
        hasard.shuffle(s)
    while len(choix) < taille and any(strates):
        for s in strates:
            if s and len(choix) < taille:
                choix.append(s.pop())
    choix = choix[:taille]
    return {"le": maintenant(), "base_entreprises": len(lignes),
            "base_avec_email": len(avec), "base_traitees": sum(1 for x in lignes if x["traite"]),
            "repartition_echantillon": {"avec_email": sum(1 for x in choix if x["emails_trouves"]),
                                        "traitees_sans_email": sum(1 for x in choix if x["traite"] and not x["emails_trouves"]),
                                        "pas_encore_traitees": sum(1 for x in choix if not x["traite"]),
                                        "tailles": Counter(x["taille"] or "?" for x in choix),
                                        "divisions_naf": Counter((x["naf"] or "?")[:2] for x in choix)},
            "entreprises": choix}


# ─── C2 : mesure instrumentée ─────────────────────────────────────────────────
class Journal:
    """Remplace requests.get et time.sleep dans le module du scraper."""

    def __init__(self, vrai_requests, vrai_sleep):
        self.requests, self.sleep_reel = vrai_requests, vrai_sleep
        self.requetes, self.pauses, self.html = [], 0.0, {}
        self.robots = {}

    def robots_de(self, url):
        hote = urlparse(url).scheme + "://" + urlparse(url).netloc
        if hote not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.requests.get(hote + "/robots.txt", timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
                etat = r.status_code
            except Exception as e:  # noqa: BLE001
                rp.parse([])
                etat = type(e).__name__
            self.robots[hote] = {"parser": rp, "statut": etat, "crawl_delay": rp.crawl_delay(UA_ROBOTS)}
        return self.robots[hote]

    def get(self, url, **kw):
        ligne = {"url": url}
        robots = self.robots_de(url)
        ligne["interdit_par_robots"] = not robots["parser"].can_fetch(UA_ROBOTS, url)
        debut = time.monotonic()
        try:
            r = self.requests.get(url, **kw)
        except Exception as e:  # noqa: BLE001
            ligne.update(erreur=type(e).__name__, secondes=round(time.monotonic() - debut, 2))
            self.requetes.append(ligne)
            raise
        ligne.update(statut=r.status_code, secondes=round(time.monotonic() - debut, 2), octets=len(r.content or b""),
                     type=r.headers.get("content-type", ""), url_finale=r.url if r.url != url else "")
        if "html" in ligne["type"] and r.status_code < 400:
            self.html[url] = r.text
        self.requetes.append(ligne)
        return r

    def pause(self, s):
        self.pauses += s
        self.sleep_reel(s)

    def __getattr__(self, nom):   # requests.RequestException, etc.
        return getattr(self.requests, nom)


def analyser_html(html: str) -> dict:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script")
    for t in soup(["script", "style", "noscript", "template"]):
        t.extract()
    texte = " ".join(soup.get_text(" ", strip=True).split())
    racine = soup.find(id=re.compile(r"^(root|app|__next|__nuxt|svelte)$"))
    formulaires = [f for f in soup.find_all("form")
                   if f.find("textarea") or f.find("input", attrs={"type": "email"})]
    js = (len(texte) < 300 and len(scripts) >= 3) or (racine is not None and len(racine.get_text(strip=True)) < 50)
    return {"caracteres_texte": len(texte), "scripts": len(scripts), "racine_application_vide": bool(
        racine is not None and len(racine.get_text(strip=True)) < 50),
        "probablement_rendue_en_js": bool(js), "formulaires_contact": len(formulaires),
        "mailto": len(re.findall(r"mailto:", html, re.I)),
        "emails_visibles_regex": len(set(re.findall(r"[\w.%+-]+@[\w.-]+\.[a-z]{2,}", html, re.I)))}


def mesurer(entreprises: list[dict], ddg=True, ia=False) -> dict:
    from spontanees import recherche_emails as S
    journal = Journal(S.requests, S.time.sleep)
    S.requests = journal
    S.time.sleep = journal.pause            # time est partagé : pauses DDG comprises
    sites, candidats = [], []
    try:
        for i, e in enumerate(entreprises, 1):
            journal.requetes, journal.html, journal.pauses = [], {}, 0.0
            chrono = Chrono()
            ligne = {"id": e["id"], "nom": e["nom"], "taille": e.get("taille"), "naf": e.get("naf"),
                     "site_en_base": e.get("site_web"), "emails_en_base": e.get("emails_trouves")}
            url = e.get("site_web")
            if not url and ddg:
                ent = {"nom_commercial": e["nom"], "nom": e.get("raison_sociale"), "ville": e.get("ville"),
                       "code_postal": e.get("code_postal"), "siren": e.get("siren")}
                url, _ = S.chercher_site(ent)
                ligne["site_trouve_ddg"] = url
                ligne["secondes_recherche_site"] = chrono.s
            if not url:
                ligne["resultat"] = "site introuvable" if ddg else "pas de site (DDG non lancé)"
                sites.append(ligne)
                print(f"[{i}/{len(entreprises)}] {e['nom'][:40]} : {ligne['resultat']}")
                continue
            try:
                r = S.scraper_et_extraire(url, e["nom"], ia=ia)
            except Exception as err:  # noqa: BLE001
                r = {"emails": [], "erreur": f"{type(err).__name__}: {err}"}
            pages = {u: analyser_html(h) for u, h in journal.html.items()}
            statuts = Counter(str(x.get("statut") or x.get("erreur")) for x in journal.requetes)
            ligne.update({
                "site": url, "secondes": chrono.s, "secondes_en_pause": round(journal.pauses, 1),
                "requetes": len(journal.requetes), "statuts": dict(statuts),
                "pages_html_lues": len(journal.html),
                "interdites_par_robots": [x["url"] for x in journal.requetes if x.get("interdit_par_robots")],
                "robots_txt": {h: {"statut": v["statut"], "crawl_delay": v["crawl_delay"]} for h, v in journal.robots.items()
                               if h in {urlparse(x["url"]).scheme + "://" + urlparse(x["url"]).netloc for x in journal.requetes}},
                "pages_js_probables": [u for u, p in pages.items() if p["probablement_rendue_en_js"]],
                "pages_avec_formulaire": [u for u, p in pages.items() if p["formulaires_contact"]],
                "non_html_ignorees": [x["url"] for x in journal.requetes
                                      if x.get("statut", 999) < 400 and "html" not in x.get("type", "")],
                "requetes_detail": journal.requetes, "pages_detail": pages,
                "emails": r.get("emails"), "douteux": r.get("douteux"), "ecartes": r.get("ecartes"),
                "url_finale": r.get("url_finale"), "erreur": r.get("erreur")})
            for a in r.get("emails") or []:
                candidats.append({"entreprise_id": e["id"], "entreprise": e["nom"], "site_web": url,
                                  "url_scrapee": r.get("url_finale") or url, "email": a,
                                  "etat_app": "douteuse" if a in (r.get("douteux") or []) else "validee_regle",
                                  "contexte": (r.get("contextes") or {}).get(a, ""), "attendu_valide": None,
                                  "commentaire": ""})
            for a, raison in r.get("ecartes") or []:
                candidats.append({"entreprise_id": e["id"], "entreprise": e["nom"], "site_web": url,
                                  "url_scrapee": r.get("url_finale") or url, "email": a,
                                  "etat_app": f"ecartee ({raison})", "contexte": "", "attendu_valide": None,
                                  "commentaire": ""})
            sites.append(ligne)
            print(f"[{i}/{len(entreprises)}] {e['nom'][:40]} : {ligne['requetes']} requêtes, {ligne['secondes']} s "
                  f"(pauses {ligne['secondes_en_pause']} s), emails {len(r.get('emails') or [])}, JS "
                  f"{len(ligne['pages_js_probables'])}, formulaires {len(ligne['pages_avec_formulaire'])}, robots "
                  f"{len(ligne['interdites_par_robots'])}")
    finally:
        S.requests, S.time.sleep = journal.requests, journal.sleep_reel
    lus = [s for s in sites if "requetes" in s]
    synthese = {
        "entreprises": len(sites), "sites_lus": len(lus),
        "sites_introuvables": sum(1 for s in sites if "requetes" not in s),
        "avec_au_moins_un_email": pourcentage(sum(1 for s in lus if s["emails"]), len(lus)),
        "requetes_par_site_moyen": round(sum(s["requetes"] for s in lus) / len(lus), 1) if lus else None,
        "secondes_par_site_moyen": round(sum(s["secondes"] for s in lus) / len(lus), 1) if lus else None,
        "part_du_temps_en_pause": round(sum(s["secondes_en_pause"] for s in lus) / max(1, sum(s["secondes"] for s in lus)), 2),
        "statuts": dict(sum((Counter(s["statuts"]) for s in lus), Counter())),
        "sites_avec_page_interdite_par_robots": sum(1 for s in lus if s["interdites_par_robots"]),
        "requetes_interdites_par_robots": sum(len(s["interdites_par_robots"]) for s in lus),
        "sites_avec_page_js_probable": sum(1 for s in lus if s["pages_js_probables"]),
        "sites_sans_email_mais_formulaire": sum(1 for s in lus if not s["emails"] and s["pages_avec_formulaire"]),
        "sites_sans_email_et_js": sum(1 for s in lus if not s["emails"] and s["pages_js_probables"]),
        "sites_sans_aucune_page_html": sum(1 for s in lus if not s["pages_html_lues"]),
    }
    return {"le": maintenant(), "ia": ia, "ddg": ddg, "synthese": synthese, "sites": sites}, candidats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sous = ap.add_subparsers(dest="action", required=True)
    e = sous.add_parser("echantillon")
    e.add_argument("--base")
    e.add_argument("--user", type=int)
    e.add_argument("--taille", type=int, default=TAILLE_ECHANTILLON)
    m = sous.add_parser("mesure")
    m.add_argument("--fichier", default=str(SORTIE / "scraper_echantillon.json"))
    m.add_argument("--max", type=int)
    m.add_argument("--sans-ddg", action="store_true")
    m.add_argument("--ia", action="store_true")
    args = ap.parse_args(argv)
    if args.action == "echantillon":
        res = echantillon(args.base, args.user, args.taille)
        print(res["repartition_echantillon"], "->", ecrire_json("scraper_echantillon", res))
        return 0
    entreprises = lire_json(args.fichier)["entreprises"][:args.max]
    res, candidats = mesurer(entreprises, ddg=not args.sans_ddg, ia=args.ia)
    print(res["synthese"])
    print("->", ecrire_json("scraper_mesure", res))
    print("->", ecrire_json("emails_candidats", {"version": 1, "exporte_le": maintenant(), "emails": candidats}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
