"""
shared/extinction.py
====================
Extinction et veille du PC en fin de campagne (D213), par systemctl, jamais
par root. Droits : ceux de logind (session ouverte), sinon la règle polkit de
deploy/polkit (poweroff et suspend seulement).

Réveil : le minuteur chasseur-campagne.timer porte WakeSystem=true. systemd
--user doit avoir CAP_WAKE_ALARM (donnée par pam_systemd à l'ouverture d'une
session locale). rtcwake n'est pas employé : /dev/rtc0 demande root.
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path

MINUTEUR = "chasseur-campagne.timer"
CAP_WAKE_ALARM = 35
ETEINDRE, VEILLE = "eteindre", "veille"
_METHODES = {ETEINDRE: "CanPowerOff", VEILLE: "CanSuspend"}
PROC = Path("/proc")


class ErreurExtinction(Exception):
    """Extinction ou veille impossible, message à afficher."""


def _executer(args: list[str]) -> subprocess.CompletedProcess:
    """Seule commande du module (remplacée dans les tests)."""
    return subprocess.run(args, capture_output=True, text=True, timeout=30)


def _sortie(args: list[str]) -> str:
    try:
        r = _executer(args)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def autorise(action: str) -> bool:
    """logind répond « yes » (sans mot de passe) pour cette action."""
    return '"yes"' in _sortie(["busctl", "call", "org.freedesktop.login1", "/org/freedesktop/login1",
                               "org.freedesktop.login1.Manager", _METHODES[action]])


def prochain_lancement() -> datetime | None:
    """Prochain lancement du minuteur, None s'il n'est pas actif."""
    texte = _sortie(["systemctl", "--user", "show", MINUTEUR, "--property=NextElapseUSecRealtime", "--value",
                     "--timestamp=unix"])
    try:
        return datetime.fromtimestamp(int(texte.lstrip("@"))).astimezone()
    except ValueError:
        return None


def _gestionnaire_peut_reveiller() -> bool:
    """CAP_WAKE_ALARM dans les capacités effectives de systemd --user."""
    pid = os.getenv("MANAGERPID", "").strip() or _sortie(["pgrep", "-u", str(os.getuid()), "-o", "-f", "systemd --user"])
    try:
        for ligne in (PROC / pid / "status").read_text(encoding="ascii", errors="replace").splitlines():
            if ligne.startswith("CapEff:"):
                return bool(int(ligne.split()[1], 16) >> CAP_WAKE_ALARM & 1)
    except (OSError, ValueError):
        pass
    return False


def reveil() -> datetime:
    """Instant où le minuteur réveillera le PC. ErreurExtinction s'il ne le
    ferait pas : pas de veille sans réveil."""
    quand = prochain_lancement()
    if quand is None:
        raise ErreurExtinction(f"{MINUTEUR} n'est pas actif : le PC ne se réveillerait pas.")
    if _sortie(["systemctl", "--user", "show", MINUTEUR, "--property=WakeSystem", "--value"]) != "yes":
        raise ErreurExtinction(f"{MINUTEUR} n'a pas WakeSystem=true : le PC ne se réveillerait pas.")
    if not _gestionnaire_peut_reveiller():
        raise ErreurExtinction("systemd --user n'a pas CAP_WAKE_ALARM : le PC ne se réveillerait pas.")
    return quand


def verifier(action: str) -> datetime | None:
    """Tout ce qui se sait avant d'agir. Retourne l'instant du réveil (veille)."""
    quand = reveil() if action == VEILLE else None
    if not autorise(action):
        raise ErreurExtinction("autorisation refusée par le système : installe la règle polkit (docs/CAMPAGNE.md).")
    return quand


def agir(action: str):
    """Éteint, ou met en veille. Sans mot de passe demandé, sans passer outre
    un programme qui s'y oppose. La veille part 5 s plus tard, par une unité à
    part : la campagne doit être finie au réveil, sinon le minuteur, qui se
    déclenche à ce moment, ne relancerait pas un service encore actif."""
    commande = ["systemctl", "--no-ask-password", "poweroff" if action == ETEINDRE else "suspend"]
    if action == VEILLE:
        commande = ["systemd-run", "--user", "--collect", "--quiet", "--on-active=5s",
                    "--timer-property=AccuracySec=1s", *commande]
    try:
        r = _executer(commande)
    except (OSError, subprocess.SubprocessError) as e:
        raise ErreurExtinction(f"commande impossible ({type(e).__name__})") from None
    if r.returncode != 0:
        raise ErreurExtinction((r.stderr or "").strip()[:200] or f"refus du système (code {r.returncode})")
