"""Une couleur d'accent par mode (D210) : valeurs dans modes.css seulement,
contrastes d'au moins 4,5:1, états indépendants du mode."""

import re

import pytest

from shared import config

CSS = config.STATIC_DIR / "css"
PALETTES = {"alternance": ("#0F766E", "#0B5A54", "#E3F1EF"),
            "stage": ("#534AB7", "#3C3489", "#EEEDFE"),
            "job": ("#993C1D", "#712B13", "#FAECE7")}


def _variables(mode: str) -> dict[str, str]:
    """Variables du bloc de modes.css qui vise data-mode="<mode>"."""
    css = (CSS / "modes.css").read_text(encoding="utf-8")
    bloc = re.search(r'\[data-mode="%s"\][^{]*\{([^}]*)\}' % mode, css).group(1)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-F]{6})", bloc))


def _luminance(couleur: str) -> float:
    v = [int(couleur[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in v)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a: str, b: str) -> float:
    clair, sombre = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (clair + 0.05) / (sombre + 0.05)


@pytest.mark.parametrize("mode", PALETTES)
def test_palette_et_contrastes(mode):
    v = _variables(mode)
    assert (v["accent"], v["accent-survol"], v["accent-doux"]) == PALETTES[mode]
    assert set(v) == {"accent", "accent-survol", "accent-doux", "accent-moyen", "accent-bordure"}
    for texte, fonds in (("accent", ("#FFFFFF", "#F7F8F7", "#EEF1F0", v["accent-doux"])),
                         ("accent-survol", ("#FFFFFF", v["accent-doux"], v["accent-moyen"]))):
        for fond in fonds:
            assert _contraste(v[texte], fond) >= 4.5, (mode, texte, fond)


def test_accent_jamais_ecrit_en_dur_ailleurs():
    teintes = {c for m in PALETTES for c in _variables(m).values()}
    for dossier, motif in ((CSS, "*.css"), (config.STATIC_DIR / "js", "*.js"), (config.TEMPLATES_DIR, "**/*.html")):
        for f in dossier.glob(motif):
            if f.name == "modes.css":
                continue
            texte = re.sub(r"--succes[\w-]*:\s*#\w+", "", f.read_text(encoding="utf-8"))
            assert not [c for c in teintes if c.lower() in texte.lower()], f.name
            assert not re.search(r"--accent[\w-]*:", texte), f.name


def test_etats_et_notes_independants_du_mode():
    css = (CSS / "pages.css").read_text(encoding="utf-8") + (CSS / "components.css").read_text(encoding="utf-8")
    for selecteur in (".note--bien, .verdict--bien", ".chip--vert", ".partie-lien__etat--complet",
                      ".ce-message.is-ok", ".volet__points--colle li::before", ".volet__message"):
        regle = re.search(r"^%s \{([^}]*)\}" % re.escape(selecteur), css, re.M).group(1)
        assert "--succes" in regle and "--accent" not in regle, selecteur


def test_pages_avec_et_sans_mode(client, utilisateur):
    assert "modes.css" in client.get("/login").text
    assert "data-mode=" not in client.get("/login").text
    connecte, _ = utilisateur("a@test.fr", prenom="Alice")
    choix = connecte.get("/").text
    assert "data-mode=" not in choix
    for mode in PALETTES:
        assert f'data-mode-lien="{mode}"' in choix
        page = connecte.get(f"/{mode}").text
        assert f'<html lang="fr" data-mode="{mode}"' in page
        assert page.index("css/modes.css") < page.index("css/base.css")
