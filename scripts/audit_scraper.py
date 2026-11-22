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

C2, réseau : rejoue les fonctions de l'application sur l'échantillon (ou
--fichier) : identification du site (spontanees/site_officiel.identifier :
site LBA, sites donnés par les offres de la base en lecture seule, recherche
web ; vérification par SIREN ou nom, D160 ; le site en base, trouvé par
l'ancienne recherche, n'est pas repris), puis scraper_et_extraire sur le
site vérifié (D161), en notant chaque requête HTTP : URL, statut, durée,
taille, type, redirection, erreur, et si robots.txt l'interdit ; le temps
passé en pauses ; puis, pour chaque page HTML reçue, les signes d'une page
rendue en JavaScript, les formulaires de contact et les liens mailto.
--sans-ddg : sans recherche web. IA coupée par défaut (--ia pour la
validation des douteuses). Avec audit_exports/scraper_reference.json (ou
--reference), chaque site retenu est comparé au site officiel : juste,
faux, manqué, non tranché. Rien n'est écrit en base.

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


def sites_des_offres_lecture(base, user_id) -> dict:
    """Sites donnés par les offres (France Travail, LBA) de l'utilisateur, base en lecture seule."""
    from database.candidatures_db import sites_des_offres
    if not user_id:
        return {}
    with session_lecture(base) as db:
        return sites_des_offres(user_id, db)


def brancher_cache_recherche(S, chemin):
    """Résultats de recherche web gardés par requête dans chemin (JSON) :
    plusieurs mesures rejouent exactement les mêmes résultats, et leurs
    écarts ne viennent que du code (le moteur varie d'un passage à l'autre).
    Une requête en échec n'est pas gardée : elle sera redemandée."""
    import json
    from pathlib import Path
    chemin = Path(chemin)
    cache = json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else {}
    vrai = S._resultats_ddg
    compte = {"du_cache": 0, "demandees": 0}

    def avec_cache(requete):
        if requete in cache:
            compte["du_cache"] += 1
            return cache[requete]
        echecs = S.erreurs_ddg
        r = vrai(requete)
        compte["demandees"] += 1
        if S.erreurs_ddg == echecs:
            cache[requete] = r
            chemin.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        return r
    S._resultats_ddg = avec_cache
    return compte


def mesurer(entreprises: list[dict], ddg=True, ia=False, base=None, reference=None, sites_export=None,
            cache_recherche=None) -> dict:
    """Phase 15 (D160, D161) : identification du site (sources, vérification
    par SIREN ou nom), puis lecture du site vérifié, chaque requête notée."""
    from spontanees import lecture_site as L
    from spontanees import recherche_emails as S
    from spontanees import site_officiel as O
    compte_cache = brancher_cache_recherche(S, cache_recherche) if cache_recherche else None
    journal = Journal(L.requests, S.time.sleep)
    L.requests = journal
    S.time.sleep = journal.pause            # time est partagé : pauses DDG et entre pages comprises
    sites, candidats = [], []
    offres = {}
    try:
        for i, e in enumerate(entreprises, 1):
            journal.requetes, journal.html, journal.pauses = [], {}, 0.0
            chrono = Chrono()
            ligne = {"id": e["id"], "nom": e["nom"], "taille": e.get("taille"), "naf": e.get("naf"),
                     "site_en_base": e.get("site_web"), "emails_en_base": e.get("emails_trouves")}
            if e.get("user_id") not in offres:
                offres[e.get("user_id")] = sites_des_offres_lecture(base, e.get("user_id"))
            # Le site en base vient de l'ancienne recherche : il n'est pas repris (seulement LBA, offres, recherche)
            ent = {"nom_commercial": e["nom"], "nom": e.get("raison_sociale"), "ville": e.get("ville"),
                   "code_postal": e.get("code_postal"), "siren": e.get("siren"),
                   "_extra": {"lba": {"site_web": e.get("site_lba") or ""}}}
            from spontanees.noms_entreprise import completer
            completer(ent)                      # sigle, dénominations usuelles, enseignes (D167)
            ligne["autres_noms"] = ent.get("autres_noms")
            verification, essais = O.identifier(ent, offres[e.get("user_id")], S.urls_recherche if ddg else None,
                                                sites_export=sites_export)
            ligne.update(site_verifie=verification.resume() if verification else None, essais_site=essais,
                         secondes_identification=chrono.s, requetes_identification=len(journal.requetes))
            if reference is not None:
                ligne["reference"] = comparer_a_la_reference(verification, reference.get(e["id"]))
            if not verification:
                ligne["resultat"] = "site non vérifié"
                ligne.update(secondes=chrono.s, secondes_en_pause=round(journal.pauses, 1),
                             requetes=len(journal.requetes), requetes_detail=journal.requetes)
                sites.append(ligne)
                print(f"[{i}/{len(entreprises)}] {e['nom'][:40]} : site non vérifié ({len(essais)} essayés)"
                      + (f" [{ligne['reference']['verdict']}]" if reference is not None else ""))
                continue
            url = verification.url
            try:
                r = S.scraper_et_extraire(verification, e["nom"], ia=ia)
            except Exception as err:  # noqa: BLE001
                r = {"emails": [], "erreur": f"{type(err).__name__}: {err}"}
            pages = {u: analyser_html(h) for u, h in journal.html.items()}
            statuts = Counter(str(x.get("statut") or x.get("erreur")) for x in journal.requetes)
            ligne.update({
                "site": url, "formulaires": r.get("formulaires"), "robots": r.get("robots"),
                "secondes": chrono.s, "secondes_en_pause": round(journal.pauses, 1),
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
                                  "site_verifie": verification.domaine,
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
            print(f"[{i}/{len(entreprises)}] {e['nom'][:40]} : {url} ({verification.detail})"
                  + (f" [{ligne['reference']['verdict']}]" if reference is not None else "")
                  + f", {ligne['requetes']} requêtes, {ligne['secondes']} s "
                  f"(pauses {ligne['secondes_en_pause']} s), emails {len(r.get('emails') or [])}, JS "
                  f"{len(ligne['pages_js_probables'])}, formulaires {len(ligne['pages_avec_formulaire'])}, robots "
                  f"{len(ligne['interdites_par_robots'])}")
    finally:
        L.requests, S.time.sleep = journal.requests, journal.sleep_reel
    lus = [s for s in sites if s.get("site_verifie")]
    synthese = {
        "entreprises": len(sites), "sites_verifies_et_lus": len(lus),
        "sites_non_verifies": sum(1 for s in sites if not s.get("site_verifie")),
        "preuves": dict(Counter(s["site_verifie"]["preuve"] for s in lus)),
        "sources": dict(Counter(s["site_verifie"]["source"] for s in lus)),
        "requetes_par_entreprise_moyen": round(sum(s["requetes"] for s in sites) / len(sites), 1) if sites else None,
        "secondes_par_entreprise_moyen": round(sum(s["secondes"] for s in sites) / len(sites), 1) if sites else None,
        "sites_avec_formulaire": sum(1 for s in lus if s.get("formulaires")),
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
    if reference is not None:
        synthese["identification_contre_la_reference"] = bilan_reference(sites)
    if compte_cache is not None:
        synthese["recherches_du_cache"] = compte_cache
    return {"le": maintenant(), "ia": ia, "ddg": ddg, "synthese": synthese, "sites": sites}, candidats


def _parent(domaine: str) -> str:
    d = (domaine or "").lower().removeprefix("www.")
    return ".".join(d.split(".")[-2:])


def comparer_a_la_reference(verification, ref: dict | None) -> dict:
    """juste, faux (autre site retenu), manqué (site officiel connu, rien
    retenu), ou non tranché (référence à vérifier)."""
    if not ref:
        return {"verdict": "hors référence"}
    officiel = ref.get("site_officiel")
    retenu = verification.domaine if verification else None
    tranche = ref.get("confiance") in ("haute", "moyenne")
    if not tranche:
        verdict = "non tranché"
    elif officiel and retenu:
        officiels = officiel if isinstance(officiel, list) else [officiel]   # plusieurs sites acceptés
        verdict = "juste" if _parent(retenu) in {_parent(o) for o in officiels} else "faux"
    elif officiel:
        verdict = "manqué"
    else:
        verdict = "faux" if retenu else "juste"
    return {"verdict": verdict, "officiel": officiel, "retenu": retenu, "confiance": ref.get("confiance")}


def bilan_reference(sites) -> dict:
    verdicts = Counter(s["reference"]["verdict"] for s in sites if "reference" in s)
    tranches = sum(n for v, n in verdicts.items() if v in ("juste", "faux", "manqué"))
    return {"tranches": tranches, "justes": verdicts["juste"], "faux": verdicts["faux"],
            "manques": verdicts["manqué"], "non_tranches": verdicts["non tranché"],
            "faux_detail": [(s["nom"], s["reference"]["retenu"], s["reference"]["officiel"]) for s in sites
                            if s.get("reference", {}).get("verdict") == "faux"],
            "manques_detail": [(s["nom"], s["reference"]["officiel"]) for s in sites
                               if s.get("reference", {}).get("verdict") == "manqué"]}


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
    m.add_argument("--debut", type=int, default=1, help="commencer à la N-ième entreprise de l'échantillon")
    m.add_argument("--suffixe", default="", help="ajouté au nom des fichiers de sortie")
    m.add_argument("--sans-ddg", action="store_true")
    m.add_argument("--ia", action="store_true")
    m.add_argument("--base", help="URL SQLite (lecture seule) pour les sites donnés par les offres")
    m.add_argument("--sites-export", help="JSON {SIREN: site} tiré de l'export LBA (défaut : celui de l'application)")
    m.add_argument("--cache-recherche", help="JSON des résultats de recherche par requête, partagé entre mesures")
    m.add_argument("--reference", default=str(SORTIE / "scraper_reference.json"),
                   help="sites officiels de référence (absent : pas de comparaison)")
    args = ap.parse_args(argv)
    if args.action == "echantillon":
        res = echantillon(args.base, args.user, args.taille)
        print(res["repartition_echantillon"], "->", ecrire_json("scraper_echantillon", res))
        return 0
    entreprises = lire_json(args.fichier)["entreprises"][args.debut - 1:][:args.max]
    from pathlib import Path
    reference = ({x["id"]: x for x in lire_json(args.reference)["entreprises"]} if Path(args.reference).exists()
                 else None)
    sites_export = lire_json(args.sites_export) if args.sites_export else None
    res, candidats = mesurer(entreprises, ddg=not args.sans_ddg, ia=args.ia, base=args.base, reference=reference,
                             sites_export=sites_export, cache_recherche=args.cache_recherche)
    print(res["synthese"])
    from spontanees import recherche_emails as S
    res["synthese"]["recherche_web_en_echec"] = S.erreurs_ddg
    print("->", ecrire_json("scraper_mesure" + args.suffixe, res))
    print("->", ecrire_json("emails_candidats" + args.suffixe, {"version": 1, "exporte_le": maintenant(),
                                                                "emails": candidats}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
