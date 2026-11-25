# Références annotées versionnées

Seules les références sans donnée personnelle sont ici.

- `scraper_reference.json` : 40 entreprises (nom, SIREN, site officiel, confiance, notes), données publiques. Lu par `scripts/audit_scraper.py`, `scripts/mesurer_wikidata.py` et `scripts/mesurer_moteurs_recherche.py`.

Restent dans `audit_exports/` (ignoré par git), car elles contiennent des données personnelles :

- `banc_reference.json`, `banc_reglage.json`, `banc_test.json`, `banc_test_profils_a_jour.json` : profils complets des utilisateurs (formation, expérience, projets, lettre type, ville) et état des candidatures ;
- `banc_emails_reference.json` : une adresse nominative d'un tiers.

Pour les versionner un jour, il faudrait des profils fictifs à la place des profils réels et retirer l'état des candidatures ; les offres elles-mêmes sont publiques.
