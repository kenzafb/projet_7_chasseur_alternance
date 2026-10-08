"""
scripts/verifier_mistral.py
===========================
Vérifie la configuration Mistral du .env, à lancer par l'humain (appels réels) :

    venv/bin/python scripts/verifier_mistral.py

1. Liste les modèles accessibles avec MISTRAL_API_KEY (client.models.list).
2. Pour chaque usage (analyse, lettre, extraction), affiche le modèle
   configuré (MODELE_MISTRAL_<USAGE>, sinon MODELE_MISTRAL, sinon le défaut)
   et fait un appel minimal (quelques tokens) : OK, ou l'erreur expliquée.

Chaque appel passe par le limiteur commun de shared/ia.py
(MISTRAL_INTERVALLE_MIN_S entre deux appels), comme le reste du projet.

Code de sortie 0 si chaque modèle configuré répond, 1 sinon.
ANALYSE_IA=false : aucun appel, message et code de sortie 0.
Aucune clé n'est affichée.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import config  # noqa: E402  (charge le .env)
from shared import ia  # noqa: E402
from shared.ia import ErreurIABloquante, classer, client  # noqa: E402

MESSAGE_TEST = [{"role": "user", "content": "Réponds seulement : OK"}]


def lister_modeles(sortie=print) -> set[str] | None:
    """Identifiants des modèles de la clé, ou None si la liste est inaccessible."""
    ia.limiteur.attendre()
    try:
        reponse = client.models.list()
    except Exception as err:
        erreur, _ = classer(err, "(liste des modèles)")
        sortie(f"❌ Liste des modèles inaccessible : {erreur}")
        return None
    ids = sorted({m.id for m in (reponse.data or []) if getattr(m, "id", None)})
    sortie(f"Modèles accessibles avec cette clé ({len(ids)}) :")
    for i in ids:
        sortie(f"  - {i}")
    return set(ids)


def essayer(modele: str) -> tuple[str | None, str]:
    """Appel minimal sur `modele` : (None si réussi, sinon "bloquante" ou
    "passagère" ; message)."""
    ia.limiteur.attendre()
    try:
        reponse = client.chat.complete(model=modele, messages=MESSAGE_TEST, max_tokens=5)
    except Exception as err:
        erreur, _ = classer(err, modele)
        nature = "bloquante" if isinstance(erreur, ErreurIABloquante) else "passagère"
        return nature, f"{erreur} (erreur {nature})"
    texte = (reponse.choices[0].message.content or "").strip() if reponse.choices else ""
    return None, f"réponse : {texte[:30]!r}"


def main(sortie=print) -> int:
    if not config.analyse_ia_active():
        sortie(f"ℹ️  {config.MESSAGE_IA_DESACTIVEE} Rien à vérifier.")
        return 0
    if not os.getenv("MISTRAL_API_KEY"):
        sortie("❌ MISTRAL_API_KEY absente du .env.")
        return 1
    disponibles = lister_modeles(sortie)
    sortie("")
    sortie("Modèles configurés :")
    natures = set()
    deja = {}
    for usage in config.USAGES_MISTRAL:
        modele = config.modele_mistral(usage)
        if modele not in deja:
            deja[modele] = essayer(modele)
        nature, message = deja[modele]
        ok = nature is None
        if nature:
            natures.add(nature)
        absent = (" ; absent de la liste de la clé" if disponibles is not None and modele not in disponibles
                  else "")
        sortie(f"  {'OK ' if ok else 'ÉCHEC'} {usage:<10} {modele} : {message}{absent}")
    sortie("")
    if not natures:
        sortie("Tout est prêt.")
    if "bloquante" in natures:
        sortie("À corriger dans le .env : MODELE_MISTRAL, ou MODELE_MISTRAL_ANALYSE / _LETTRE / _EXTRACTION.")
    if "passagère" in natures:
        sortie("Erreur passagère (429, 5xx) : rien à corriger dans le .env, le modèle est accessible "
               "mais la limite de débit ou le quota Mistral est atteint. Réessaie plus tard, ou "
               "vérifie le quota sur la console Mistral (https://console.mistral.ai).")
    return 0 if not natures else 1


if __name__ == "__main__":
    sys.exit(main())
