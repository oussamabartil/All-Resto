import pytest

from app import order as o
from app.menu import load_menu
from app.order import Order, validate_order


@pytest.fixture(scope="module")
def menu():
    return load_menu()


def codes(result):
    return [e.code for e in result.errors]


def one_line(**line):
    return {"lines": [line]}


# --- Commandes valides ---------------------------------------------------


def test_valid_order(menu):
    result = validate_order(
        {
            "lines": [
                {"item": "burger_bacon", "size": "large", "modifiers": ["sans_oignons"]},
                {"item": "frites", "size": "grande", "modifiers": ["sauce_ketchup"], "quantity": 2},
                {"item": "eau_minerale"},
            ]
        },
        menu,
    )
    assert result.is_valid, result.errors
    assert result.order.lines[2].quantity == 1
    assert not result.needs_allergy_confirmation
    assert result.staff_note is None


def test_accepts_order_object(menu):
    order = Order.model_validate(one_line(item="eau_minerale"))
    assert validate_order(order, menu).is_valid


# --- Format ----------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        {},  # pas de "lines"
        {"lines": [{"size": "large"}]},  # pas de "item"
        {"lines": [{"item": "frites", "size": "grande", "note": "bien cuites"}]},  # champ libre interdit
        {"lines": [{"item": "frites", "quantity": "deux"}]},
    ],
)
def test_invalid_format(menu, data):
    result = validate_order(data, menu)
    assert codes(result) == [o.INVALID_FORMAT]
    assert result.order is None


def test_empty_order(menu):
    assert codes(validate_order({"lines": []}, menu)) == [o.EMPTY_ORDER]


# --- Articles --------------------------------------------------------------


def test_unknown_item(menu):
    result = validate_order(one_line(item="burger_licorne", size="large"), menu)
    assert codes(result) == [o.UNKNOWN_ITEM]
    assert result.errors[0].line == 0
    assert result.errors[0].value == "burger_licorne"


def test_unavailable_item(menu):
    result = validate_order(one_line(item="pizza_reine", size="grande"), menu)
    assert codes(result) == [o.ITEM_UNAVAILABLE]


# --- Tailles ---------------------------------------------------------------


def test_size_required(menu):
    assert codes(validate_order(one_line(item="coca_cola"), menu)) == [o.SIZE_REQUIRED]


def test_unknown_size(menu):
    # "large" existe pour les burgers mais pas pour les pizzas
    result = validate_order(one_line(item="pizza_margherita", size="large"), menu)
    assert codes(result) == [o.UNKNOWN_SIZE]


def test_size_not_applicable(menu):
    result = validate_order(one_line(item="salade_cesar", size="grande"), menu)
    assert codes(result) == [o.SIZE_NOT_APPLICABLE]


# --- Modificateurs ---------------------------------------------------------


def test_modifier_not_allowed_for_item(menu):
    # "sans_glacons" existe mais ne s'applique pas à un burger
    result = validate_order(one_line(item="burger_classique", size="normal", modifiers=["sans_glacons"]), menu)
    assert codes(result) == [o.MODIFIER_NOT_ALLOWED]


def test_unknown_modifier(menu):
    result = validate_order(one_line(item="burger_classique", size="normal", modifiers=["sans_sel"]), menu)
    assert codes(result) == [o.MODIFIER_NOT_ALLOWED]


def test_modifier_unavailable(menu):
    result = validate_order(
        one_line(item="pizza_margherita", size="grande", modifiers=["supplement_champignons"]), menu
    )
    assert codes(result) == [o.MODIFIER_UNAVAILABLE]


def test_duplicate_modifier(menu):
    result = validate_order(
        one_line(item="burger_classique", size="normal", modifiers=["sans_oignons", "sans_oignons"]), menu
    )
    assert codes(result) == [o.DUPLICATE_MODIFIER]


# --- Quantité --------------------------------------------------------------


@pytest.mark.parametrize("quantity", [0, -1, o.MAX_QUANTITY + 1])
def test_invalid_quantity(menu, quantity):
    result = validate_order(one_line(item="eau_minerale", quantity=quantity), menu)
    assert codes(result) == [o.INVALID_QUANTITY]


# --- Plusieurs erreurs -----------------------------------------------------


def test_reports_all_errors_with_line_index(menu):
    result = validate_order(
        {
            "lines": [
                {"item": "eau_minerale"},
                {"item": "coca_cola", "modifiers": ["sans_oignons"]},
                {"item": "inconnu"},
            ]
        },
        menu,
    )
    assert [(e.code, e.line) for e in result.errors] == [
        (o.SIZE_REQUIRED, 1),
        (o.MODIFIER_NOT_ALLOWED, 1),
        (o.UNKNOWN_ITEM, 2),
    ]


# --- Allergies -------------------------------------------------------------


def test_allergy_conflict_requires_confirmation_and_staff_note(menu):
    result = validate_order(
        {
            "lines": [
                {"item": "burger_classique", "size": "normal"},
                {"item": "coca_cola", "size": "33cl"},
            ],
            "declared_allergies": ["lait"],
        },
        menu,
    )
    assert result.is_valid  # une allergie n'est pas une erreur, mais doit être confirmée
    assert result.needs_allergy_confirmation
    assert [c.model_dump() for c in result.allergy_conflicts] == [
        {"line": 0, "item": "burger_classique", "allergens": ["lait"]}
    ]
    assert result.staff_note == {
        "declared_allergies": ["lait"],
        "conflicts": [{"line": 0, "item": "burger_classique", "allergens": ["lait"]}],
    }


def test_allergy_without_conflict_still_requires_confirmation(menu):
    result = validate_order(
        {"lines": [{"item": "eau_minerale"}], "declared_allergies": ["fruits_a_coque"]}, menu
    )
    assert result.is_valid
    assert result.allergy_conflicts == []
    assert result.needs_allergy_confirmation
    assert result.staff_note == {"declared_allergies": ["fruits_a_coque"], "conflicts": []}


def test_allergen_added_by_modifier(menu):
    # Les frites ne contiennent rien, mais la mayonnaise contient des œufs
    result = validate_order(
        {"lines": [{"item": "frites", "size": "petite", "modifiers": ["sauce_mayonnaise"]}],
         "declared_allergies": ["oeufs"]},
        menu,
    )
    assert [c.allergens for c in result.allergy_conflicts] == [["oeufs"]]


def test_removal_modifier_does_not_clear_allergen(menu):
    # Prudence : "sans_fromage" n'efface pas le lait (contamination croisée)
    result = validate_order(
        {"lines": [{"item": "burger_classique", "size": "normal", "modifiers": ["sans_fromage"]}],
         "declared_allergies": ["lait"]},
        menu,
    )
    assert len(result.allergy_conflicts) == 1


def test_unknown_declared_allergen(menu):
    result = validate_order({"lines": [{"item": "eau_minerale"}], "declared_allergies": ["arachide"]}, menu)
    assert codes(result) == [o.UNKNOWN_ALLERGEN]
    assert result.needs_allergy_confirmation
