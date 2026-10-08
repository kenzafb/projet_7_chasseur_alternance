"""
scripts/verifier_mistral.py
===========================
Vérifie la configuration Mistral du .env, à lancer par l'humain (appels réels) :

    venv/bin/python scripts/verifier_mistral.py

1. Liste les modèles accessibles avec MISTRAL_API_KEY (client.models.list).
2. Pour chaque usage (analyse, lettre, extraction), affiche le modèle
   configuré (MODELE_MISTRAL_<USAGE>, sinon MODELE_MISTRAL, sinon le défaut)
   et fait un appel minimal (quelques tokens) : OK, ou l'erreur expliquée.

Code de sortie 0 si chaque modèle configuré répond, 1 sinon.
Aucune clé n'est affichée.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import config  # noqa: E402  (charge le .env)
from shared.ia import ErreurIABloquante, classer, client  # noqa: E402

MESSAGE_TEST = [{"role": "user", "content": "Réponds seulement : OK"}]


def lister_modeles(sortie=print) -> set[str] | None:
    """Identifiants des modèles de la clé, ou None si la liste est inaccessible."""
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


def essayer(modele: str) -> tuple[bool, str]:
    """Appel minimal sur `modele` : (réussi, message)."""
    try:
        reponse = client.chat.complete(model=modele, messages=MESSAGE_TEST, max_tokens=5)
    except Exception as err:
        erreur, _ = classer(err, modele)
        nature = "bloquante" if isinstance(erreur, ErreurIABloquante) else "passagère"
        return False, f"{erreur} (erreur {nature})"
    texte = (reponse.choices[0].message.content or "").strip() if reponse.choices else ""
    return True, f"réponse : {texte[:30]!r}"


def main(sortie=print) -> int:
    if not os.getenv("MISTRAL_API_KEY"):
        sortie("❌ MISTRAL_API_KEY absente du .env.")
        return 1
    disponibles = lister_modeles(sortie)
    sortie("")
    sortie("Modèles configurés :")
    tous_ok = True
    deja = {}
    for usage in config.USAGES_MISTRAL:
        modele = config.modele_mistral(usage)
        if modele not in deja:
            deja[modele] = essayer(modele)
        ok, message = deja[modele]
        tous_ok &= ok
        absent = (" ; absent de la liste de la clé" if disponibles is not None and modele not in disponibles
                  else "")
        sortie(f"  {'OK ' if ok else 'ÉCHEC'} {usage:<10} {modele} : {message}{absent}")
    sortie("")
    sortie("Tout est prêt." if tous_ok else
           "À corriger dans le .env : MODELE_MISTRAL, ou MODELE_MISTRAL_ANALYSE / _LETTRE / _EXTRACTION.")
    return 0 if tous_ok else 1


if __name__ == "__main__":
    sys.exit(main())
