"""Schéma du menu et chargement depuis data/menu.json.

Chaque article, taille, modificateur et allergène a un identifiant stable
(snake_case, sans accents). Les libellés affichés ou prononcés sont dans
`names`, indexés par code de langue ("fr", "en", ...).

Les prix sont en centimes pour éviter les erreurs d'arrondi.
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

DEFAULT_MENU_PATH = Path(__file__).resolve().parent.parent / "data" / "menu.json"
REQUIRED_LANGUAGE = "fr"

# Traductions : {"fr": "Frites", "en": "Fries"}
Names = dict[str, str]


class Allergen(BaseModel):
    names: Names


class Modifier(BaseModel):
    """Option applicable à un article : retrait, supplément, sauce..."""

    names: Names
    price_delta: int = 0
    allergens: list[str] = Field(default_factory=list)  # allergènes ajoutés par le modificateur
    available: bool = True


class SizeOption(BaseModel):
    names: Names
    price: int  # prix total de l'article dans cette taille


class MenuItem(BaseModel):
    id: str
    category: str
    names: Names
    descriptions: Names = Field(default_factory=dict)
    price: int | None = None  # prix si l'article n'a pas de tailles
    sizes: dict[str, SizeOption] = Field(default_factory=dict)
    modifiers: list[str] = Field(default_factory=list)  # identifiants autorisés pour cet article
    allergens: list[str] = Field(default_factory=list)
    available: bool = True

    @model_validator(mode="after")
    def _check_price(self) -> "MenuItem":
        if not self.sizes and self.price is None:
            raise ValueError(f"{self.id}: un prix ou au moins une taille est requis")
        if self.sizes and self.price is not None:
            raise ValueError(f"{self.id}: utiliser soit `price`, soit `sizes`, pas les deux")
        return self


class Menu(BaseModel):
    allergens: dict[str, Allergen]
    modifiers: dict[str, Modifier]
    items: list[MenuItem]

    @model_validator(mode="after")
    def _check_references(self) -> "Menu":
        """Vérifie la cohérence interne du menu au chargement."""
        seen: set[str] = set()
        for item in self.items:
            if item.id in seen:
                raise ValueError(f"identifiant d'article en double : {item.id}")
            seen.add(item.id)

            if REQUIRED_LANGUAGE not in item.names:
                raise ValueError(f"{item.id}: nom '{REQUIRED_LANGUAGE}' manquant")
            for size_id, size in item.sizes.items():
                if REQUIRED_LANGUAGE not in size.names:
                    raise ValueError(f"{item.id}/{size_id}: nom '{REQUIRED_LANGUAGE}' manquant")
            for mod_id in item.modifiers:
                if mod_id not in self.modifiers:
                    raise ValueError(f"{item.id}: modificateur inconnu {mod_id}")
            for allergen_id in item.allergens:
                if allergen_id not in self.allergens:
                    raise ValueError(f"{item.id}: allergène inconnu {allergen_id}")

        for mod_id, mod in self.modifiers.items():
            if REQUIRED_LANGUAGE not in mod.names:
                raise ValueError(f"modificateur {mod_id}: nom '{REQUIRED_LANGUAGE}' manquant")
            for allergen_id in mod.allergens:
                if allergen_id not in self.allergens:
                    raise ValueError(f"modificateur {mod_id}: allergène inconnu {allergen_id}")
        return self

    def get_item(self, item_id: str) -> MenuItem | None:
        return next((item for item in self.items if item.id == item_id), None)


def load_menu(path: Path = DEFAULT_MENU_PATH) -> Menu:
    with open(path, encoding="utf-8") as f:
        return Menu.model_validate(json.load(f))
