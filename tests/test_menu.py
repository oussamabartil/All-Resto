import pytest
from pydantic import ValidationError

from app.menu import Menu, load_menu


def minimal_menu(**item_overrides) -> dict:
    item = {"id": "frites", "category": "accompagnements", "names": {"fr": "Frites"}, "price": 300}
    item.update(item_overrides)
    return {"allergens": {"gluten": {"names": {"fr": "gluten"}}}, "modifiers": {}, "items": [item]}


def test_example_menu_loads():
    menu = load_menu()
    assert len(menu.items) == 10
    assert menu.get_item("burger_bacon") is not None
    assert menu.get_item("inexistant") is None


def test_rejects_duplicate_item_ids():
    data = minimal_menu()
    data["items"].append(dict(data["items"][0]))
    with pytest.raises(ValidationError, match="en double"):
        Menu.model_validate(data)


def test_rejects_unknown_modifier_reference():
    with pytest.raises(ValidationError, match="modificateur inconnu"):
        Menu.model_validate(minimal_menu(modifiers=["sans_sel"]))


def test_rejects_unknown_allergen_reference():
    with pytest.raises(ValidationError, match="allergène inconnu"):
        Menu.model_validate(minimal_menu(allergens=["arachide"]))


def test_rejects_missing_french_name():
    with pytest.raises(ValidationError, match="nom 'fr' manquant"):
        Menu.model_validate(minimal_menu(names={"en": "Fries"}))


def test_requires_price_or_sizes():
    with pytest.raises(ValidationError, match="prix ou au moins une taille"):
        Menu.model_validate(minimal_menu(price=None))
