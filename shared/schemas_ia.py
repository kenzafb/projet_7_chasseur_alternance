"""
shared/schemas_ia.py
====================
Réponses attendues de l'IA, en modèles Pydantic. Leur schéma JSON est
imposé au serveur (shared.ia.appeler_structure) et chaque réponse est
validée avec eux : un champ manquant ou du mauvais type, et la réponse est
redemandée une fois puis abandonnée. Rien n'est complété par défaut.

Champs tous obligatoires et types simples : un petit modèle suit mieux un
schéma court, et la grammaire de sortie d'Ollama n'en prend que l'essentiel.
Les longueurs (trois points forts...) sont ramenées après validation.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Reponse(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class AnalyseOffre(_Reponse):
    """Analyse d'une offre, dans tous les modes."""
    score: int = Field(ge=1, le=10, description="Note de 1 à 10")
    eligible: bool = Field(description="Faux si une condition d'inéligibilité est remplie")
    points_forts: list[str] = Field(description="3 au plus")
    points_faibles: list[str] = Field(description="2 au plus")
    domaine: str = Field(description="Catégorie métier en 2 à 4 mots")
    resume: str = Field(description="12 mots au plus")

    @field_validator("points_forts", "points_faibles")
    @classmethod
    def _sans_vides(cls, valeurs):
        return [v.strip() for v in valeurs if isinstance(v, str) and v.strip()]


class LettreIA(_Reponse):
    """Les deux éléments de la lettre rédigés par l'IA."""
    contact_entreprise: str = Field(description="Nom de l'entreprise puis ville, 2 à 3 lignes")
    paragraphe_entreprise: str = Field(min_length=1, description="2 à 3 phrases sur l'entreprise")


class ValidationEmail(_Reponse):
    """Avis de l'IA sur une adresse douteuse trouvée par le scraper."""
    valide: bool = Field(description="Vrai si l'adresse permet de candidater auprès de cette entreprise")
