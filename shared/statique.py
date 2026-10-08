"""
shared/statique.py
==================
Version des fichiers statiques dans leurs URL, pour que le navigateur ne
garde jamais un ancien JS ou CSS en cache : /static/js/app.js?v=<empreinte>.

L'empreinte est tirée du contenu du fichier : elle change à chaque
modification, même sans redémarrer le serveur (relue quand la date ou la
taille du fichier change).

Les modules JS s'importent entre eux (import "./api.js") : leurs URL
versionnées sont données au navigateur par une import map (importmap()),
placée dans la page avant le premier module.
"""

import hashlib
import json
import threading

from shared.config import STATIC_DIR

_verrou = threading.Lock()
_empreintes = {}   # chemin relatif -> (date de modification, taille, empreinte)


def version(relatif: str) -> str:
    """Empreinte courte du contenu de static/<relatif>."""
    chemin = STATIC_DIR / relatif
    infos = chemin.stat()
    with _verrou:
        connue = _empreintes.get(relatif)
        if connue and connue[:2] == (infos.st_mtime_ns, infos.st_size):
            return connue[2]
    empreinte = hashlib.sha256(chemin.read_bytes()).hexdigest()[:12]
    with _verrou:
        _empreintes[relatif] = (infos.st_mtime_ns, infos.st_size, empreinte)
    return empreinte


def url_statique(relatif: str) -> str:
    """URL versionnée d'un fichier de static/ : url_statique("css/base.css")."""
    return f"/static/{relatif}?v={version(relatif)}"


def importmap() -> str:
    """Import map (JSON) : chaque module de static/js vers son URL versionnée."""
    modules = sorted(p.relative_to(STATIC_DIR).as_posix() for p in (STATIC_DIR / "js").glob("*.js"))
    carte = {"imports": {f"/static/{m}": url_statique(m) for m in modules}}
    # "</" ne doit pas apparaître dans un <script> en ligne
    return json.dumps(carte, indent=2).replace("</", "<\\/")
