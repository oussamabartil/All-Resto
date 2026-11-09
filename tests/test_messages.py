import json

import pytest

from app import order as o
from app.menu import load_menu
from app.messages import (
    PROMPTS_DIR,
    describe_order,
    format_price,
    join_list,
    order_total,
    question_for_error,
    t,
)
from app.order import Order, validate_order


@pytest.fixture(scope="module")
def menu():
    return load_menu()


def test_simple_message():
    assert t("greeting").startswith("Bonjour")


def test_message_with_variables():
    assert "lait" in t("allergy_no_conflict", allergens="lait")


def test_every_error_code_has_a_french_text():
    errors = json.loads((PROMPTS_DIR / "fr" / "messages.json").read_text(encoding="utf-8"))["errors"]
    codes = {v for k, v in vars(o).items() if k.isupper() and isinstance(v, str) and k != "MAX_QUANTITY"}
    assert codes <= errors.keys()


def test_join_list():
    assert join_list(["a"]) == "a"
    assert join_list(["a", "b", "c"]) == "a, b et c"


def test_format_price():
    assert format_price(1250) == "12,50 euros"
    assert format_price(305) == "3,05 euros"


def test_describe_order_and_total(menu):
    order = Order.model_validate(
        {
            "lines": [
                {"item": "burger_bacon", "size": "large", "modifiers": ["sans_oignons", "supplement_fromage"]},
                {"item": "frites", "size": "grande", "quantity": 2},
                {"item": "eau_minerale"},
            ]
        }
    )
    assert describe_order(order, menu) == (
        "1 Burger bacon large (sans oignons et supplément fromage), 2 Frites grande et 1 Eau minérale"
    )
    assert order_total(order, menu) == 1400 + 100 + 2 * 450 + 200


def test_question_size_required_lists_options(menu):
    result = validate_order({"lines": [{"item": "coca_cola"}]}, menu)
    question = question_for_error(result.errors[0], result.order, menu)
    assert question == "Quelle taille souhaitez-vous pour Coca-Cola : 33 centilitres et 50 centilitres ?"


def test_question_modifier_not_allowed_lists_available_options_only(menu):
    result = validate_order(
        {"lines": [{"item": "pizza_margherita", "size": "grande", "modifiers": ["sans_oignons"]}]}, menu
    )
    question = question_for_error(result.errors[0], result.order, menu)
    assert "supplément fromage" in question
    assert "champignons" not in question  # indisponible


def test_question_for_every_error_code_does_not_crash(menu):
    for code in ["invalid_format", "empty_order", "unknown_allergen"]:
        assert question_for_error(o.OrderError(code=code), None, menu)
