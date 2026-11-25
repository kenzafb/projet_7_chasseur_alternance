"""Ce que voit l'IA (D189) : compteurs de tokens d'Ollama lus à chaque
appel, fenêtre pleine journalisée, description coupée signalée dans le
journal et le détail de l'offre."""

import httpx

import shared.ia
from offres.analyse import appliquer_analyse, coupure_description
from offres.analyse_v2 import analyser_offre_v2
from shared.marques import etiquettes, marquer_description_coupee
from tests.test_analyse_v2 import PROFIL, _extraction, _jugement


def _avec_compteurs(contenu, prompt, sortie):
    return httpx.Response(200, json={"model": "m", "message": {"role": "assistant", "content": contenu},
                                     "done": True, "prompt_eval_count": prompt, "eval_count": sortie})


def test_compteurs_et_fenetre_pleine(ia, monkeypatch):
    journal = []
    monkeypatch.setattr(shared.ia, "journaliser", journal.append)
    monkeypatch.setenv("IA_NUM_CTX", "4096")
    ia.file = [_avec_compteurs(_extraction(), 1800, 120), _avec_compteurs(_jugement(), 4050, 60)]
    analyser_offre_v2({"titre": "Stage", "description": "Stage web."}, PROFIL, "stage")
    infos = shared.ia.dernier_appel()
    assert {k: infos[k] for k in ("prompt_eval_count", "eval_count", "num_ctx", "fenetre_pleine")} == {
        "prompt_eval_count": 4050, "eval_count": 60, "num_ctx": 4096, "fenetre_pleine": True}
    assert ia.appels[0]["options"]["num_ctx"] == 4096
    assert [ligne for ligne in journal if "Fenêtre de contexte pleine" in ligne] and len(
        [ligne for ligne in journal if "Fenêtre" in ligne]) == 1             # l'extraction tenait dans la fenêtre


def test_description_coupee_journal_et_marque(ia, monkeypatch):
    import offres.analyse as A
    journal = []
    monkeypatch.setattr(A, "journaliser", journal.append)
    monkeypatch.setenv("IA_LONGUEUR_DESCRIPTION", "2000")              # plafond de sécurité abaissé pour le test
    ia.file = [_extraction(), _jugement()]
    offre = {"titre": "Stage web", "description": "mot " * 1000, "marques": ["niveau_different"]}
    r = analyser_offre_v2(offre, PROFIL, "stage")
    assert r["description_coupee"] == {"longueur": 3999, "lus": {"extraction": 2000, "jugement": 2000}}
    assert any("Plafond de sécurité atteint" in ligne and "jugement 2000" in ligne for ligne in journal)
    appliquer_analyse(offre, r, mode="stage", verbeux=False)
    assert offre["marques"] == ["niveau_different", "description_coupee:2000"]
    assert "Description longue : l'IA en a lu les 2 000 premiers caractères sur 3 999 pour la note" in \
        etiquettes(offre)
    # Nouvelle analyse avec tout lu : marque retirée
    marquer_description_coupee(offre, None)
    assert offre["marques"] == ["niveau_different"]


def test_description_courte_rien_a_signaler():
    assert coupure_description({"description": "court"}, extraction=8000, jugement=2000) is None


def test_num_ctx_jamais_trop_petit(monkeypatch):
    monkeypatch.setenv("IA_NUM_CTX", "4096")
    court = [{"role": "user", "content": "x" * 6000}]                 # ~2000 tokens + 1024 : tient dans 4096
    assert shared.ia.num_ctx_pour(court) == 4096
    long = [{"role": "user", "content": "x" * 15000}]                 # ~5000 tokens + 1024 -> 6144
    assert shared.ia.num_ctx_pour(long) == 6144
    assert shared.ia.num_ctx_pour([{"role": "user", "content": "x" * 90000}]) == 16384   # plafond
    monkeypatch.setenv("IA_NUM_CTX", "8192")
    assert shared.ia.num_ctx_pour(long) == 8192                       # IA_NUM_CTX plus grand : gardé


def test_num_ctx_unique_4096_releve_seulement_si_besoin(ia, monkeypatch):
    import offres.analyse_v2 as V
    monkeypatch.delenv("IA_LONGUEUR_DESCRIPTION", raising=False)
    from shared.config import ia_longueur_description
    assert ia_longueur_description() == 20000
    journal = []
    monkeypatch.setattr(V, "journaliser", journal.append)
    # Offre réelle la plus longue (environ 5 000 caractères) : 4 096, rien au journal
    ia.file = [_extraction(), _jugement()]
    analyser_offre_v2({"titre": "Stage", "description": "mot " * 1250}, PROFIL, "stage")
    assert [a["options"]["num_ctx"] for a in ia.appels] == [4096, 4096] and not journal
    # Description de 15 000 caractères : relevé pour les deux appels, journalisé
    ia.appels.clear()
    ia.file = [_extraction(), _jugement()]
    analyser_offre_v2({"titre": "Stage", "description": "mot " * 3750}, PROFIL, "stage")
    valeurs = [a["options"]["num_ctx"] for a in ia.appels]
    assert valeurs[0] == valeurs[1] > 4096 and valeurs[0] % 1024 == 0
    assert any("num_ctx porté de 4096" in ligne for ligne in journal)
