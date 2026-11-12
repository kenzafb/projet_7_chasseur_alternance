"""Mon profil en cinq parties (D147) : aucun champ ne disparaît, chaque
champ est dans un bloc de son mode, et l'état des parties est servi par
/api/profil/completude."""

import re

import pytest

COMMUNS = ["prenom", "nom", "email", "telephone", "ville", "linkedin", "github", "portfolio", "lettre_type",
           "email_objet", "email_type"]
PAR_MODE = {
    "alternance": {"profil": ["formation", "niveau_etudes", "niveau_vise", "formation_apporte", "criteres_eviter",
                              "experience", "langues"],
                   "rech": ["type_contrat", "localisation", "disponibilite", "rythme"]},
    "job": {"profil": ["niveau_etudes", "experience", "langues", "duree_souhaitee", "dispo_horaires", "mobilite",
                       "types_jobs_ok", "types_jobs_eviter", "localisation_pref"],
            "rech": ["disponibilite"]},
    "stage": {"profil": ["date_debut", "date_fin", "etablissement", "formation", "niveau_etudes", "missions",
                         "experience"],
              "rech": []},
}


def _modes_du_bloc(page, i):
    modes = re.findall(r'data-mode-section="([^"]+)"', page[:i])[-1].split()
    return {"alternance", "job", "stage"} if modes == ["commun"] else set(modes)


@pytest.mark.parametrize("mode", ["alternance", "job", "stage"])
def test_aucun_champ_ne_disparait(utilisateur, mode):
    client, _ = utilisateur("a@test.fr")
    page = client.get(f"/{mode}").text
    attendus = [("profil", c) for c in COMMUNS + PAR_MODE[mode]["profil"]] + [("rech", c) for c in PAR_MODE[mode]["rech"]]
    for genre, champ in attendus:
        positions = [m.start() for m in re.finditer(rf'data-{genre}="{champ}"', page)]
        assert any(mode in _modes_du_bloc(page, i) for i in positions), f"{mode} : {genre} {champ}"
    for attribut in ('data-tags-input="competences"', "data-projet-add", "data-pj-upload", 'data-options-recherche="'
                     + mode + '"', "data-copie-ouvrir"):
        assert attribut in page, attribut
    # Cinq parties, la première affichée, chacune avec son titre
    assert len(re.findall(r'<section class="partie" data-partie="', page)) == 5
    assert page.count('data-partie-lien="') == 5 and 'aria-current="step"' in page


def test_completude_servie_par_mode(utilisateur):
    client, _ = utilisateur("a@test.fr", prenom="Ada")
    d = client.get("/api/profil/completude?mode=stage").json()
    assert [p["titre"] for p in d["parties"]] == ["Toi", "Ton stage", "Ton parcours", "Ce que tu cherches",
                                                   "Tes documents"]
    toi = d["parties"][0]
    assert toi["manque"] == "Il manque ton prénom, ton nom, ton email, ton téléphone et ta ville."
    client.post("/api/profil?mode=stage", json={"prenom": "Ada", "nom": "Lovelace", "email": "a@t.fr",
                                                  "telephone": "06", "ville": "Paris"})
    assert client.get("/api/profil/completude?mode=stage").json()["parties"][0]["complet"]
    assert client.get("/api/profil/completude?mode=job").json()["parties"][1]["titre"] == "Ton job"


def test_etiquettes_et_projets_accessibles():
    from shared import config
    js = (config.STATIC_DIR / "js" / "profil.js").read_text(encoding="utf-8")
    assert '<button type="button" class="tag__x" data-rm=' in js and 'aria-label="Retirer ${esc(v)}"' in js
    assert '<button type="button" class="lien-bouton projet__rm"' in js
