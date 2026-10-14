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

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Reponse(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class AnalyseOffre(_Reponse):
    """Analyse d'une offre, dans tous les modes."""
    # Ni minimum ni maximum dans le schéma (Ollama les ignore) : bornes en Python
    score: int = Field(description="Note de 0 à 10")
    eligible: bool = Field(description="Faux si une condition d'inéligibilité est remplie")
    points_forts: list[str] = Field(description="3 au plus")
    points_faibles: list[str] = Field(description="2 au plus")
    domaine: str = Field(description="Catégorie métier en 2 à 4 mots")
    resume: str = Field(description="12 mots au plus")
    # Facultatif (hors de « required ») : niveau d'études que demande l'offre,
    # tel que le modèle l'a compris ; affiché par scripts/verifier_ia_locale.py
    niveau_demande: str | None = Field(None, description="Niveau d'études demandé par l'offre, ou null")

    @field_validator("score")
    @classmethod
    def _borne(cls, score):
        """Score ramené à 0..10 en Python, quoi que le modèle ait écrit."""
        return max(0, min(10, score))

    @field_validator("points_forts", "points_faibles")
    @classmethod
    def _sans_vides(cls, valeurs):
        return [v.strip() for v in valeurs if isinstance(v, str) and v.strip()]


class LettreIA(_Reponse):
    """Les deux éléments de la lettre rédigés par l'IA."""
    contact_entreprise: str = Field(description="Nom de l'entreprise puis ville, 2 à 3 lignes")
    paragraphe_entreprise: str = Field(min_length=1, description="2 à 3 phrases sur l'entreprise")


def modele_avis_emails(douteuses: list[str], trouvees: list[str]) -> type[_Reponse]:
    """Avis de l'IA sur les adresses douteuses d'une entreprise, en un appel.
    valides : sous-ensemble des douteuses ; meilleur_contact : une des adresses
    trouvées dans la page, ou null. Les deux sont des énumérations construites
    à partir des adresses réelles : le modèle ne peut pas en écrire d'autre,
    et la validation Python le vérifie encore."""
    Douteuse = Literal[tuple(douteuses)]
    Trouvee = Literal[tuple(trouvees)]

    class AvisEmails(_Reponse):
        valides: list[Douteuse] = Field(description="Adresses douteuses retenues")
        meilleur_contact: Trouvee | None = Field(description="Meilleure adresse pour candidater, ou null")

        @classmethod
        def schema_ia(cls) -> dict:
            return {"type": "object",
                    "properties": {"valides": {"type": "array", "items": {"type": "string", "enum": list(douteuses)}},
                                   "meilleur_contact": {"enum": [*trouvees, None]}},
                    "required": ["valides", "meilleur_contact"]}

    return AvisEmails
