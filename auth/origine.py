"""
auth/origine.py
===============
Requêtes qui modifient des données (POST, PUT, PATCH, DELETE) venues d'une
autre page : refusées (D134). Le cookie de session est en SameSite=Lax,
mais pour localhost tous les ports sont « le même site » : une autre
application ouverte sur localhost:3000 pourrait poster vers le Chasseur
avec la session de l'utilisateur (formulaire, téléversement multipart).

Règle : si l'en-tête Origin est présent (les navigateurs l'envoient sur
tout POST), son hôte doit être celui de la requête (en-tête Host) ; sinon
le Referer, s'il est présent. Sans l'un ni l'autre (curl, client de
test, scripts), la requête passe : ce n'est pas un navigateur piloté par
une autre page.
"""

from urllib.parse import urlsplit

from starlette.responses import JSONResponse, PlainTextResponse

METHODES_SURES = {"GET", "HEAD", "OPTIONS"}
MESSAGE = "Requête refusée : elle vient d'une autre page que le Chasseur."


def meme_origine(source: str | None, hote: str) -> bool:
    """source (Origin ou Referer) désigne-t-elle l'hôte de la requête ?"""
    if not source or source == "null":
        return False
    return urlsplit(source).netloc.lower() == (hote or "").lower()


class ControleOrigine:
    """Middleware ASGI : refuse en 403 une requête non sûre d'une autre origine."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in METHODES_SURES:
            return await self.app(scope, receive, send)
        entetes = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        hote = entetes.get("host", "")
        source = entetes.get("origin") or entetes.get("referer")
        if source is not None and not meme_origine(source, hote):
            if scope["path"].startswith("/api/"):
                reponse = JSONResponse({"erreur": MESSAGE}, status_code=403)
            else:
                reponse = PlainTextResponse(MESSAGE, status_code=403)
            return await reponse(scope, receive, send)
        return await self.app(scope, receive, send)
