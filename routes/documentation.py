"""
routes/documentation.py
=======================
Documentation de l'API, réservée aux utilisateurs connectés.
"""


from fastapi import Request
from fastapi.openapi.docs import get_swagger_ui_html

from routes.commun import routeur_prive

router = routeur_prive()


# ─── Documentation de l'API (connecté uniquement) ─────────────────────────────
@router.get("/openapi.json", include_in_schema=False)
def openapi_json(request: Request):
    return request.app.openapi()

@router.get("/docs", include_in_schema=False)
def docs(request: Request):
    return get_swagger_ui_html(openapi_url="/openapi.json", title=request.app.title + " : API")
