"""Scénarios d'appel complets, avec un faux Claude qui renvoie des extractions écrites à l'avance."""

import anthropic
import httpx2
import pytest

from app.conversation import Conversation
from app.llm import MODEL_COMPLEX, MODEL_DEFAULT, OrderExtractor
from app.menu import load_menu
from app.messages import t
from tests.fakes import FakeClaude, extraction

BURGER = {"item": "burger_bacon", "size": "large", "modifiers": ["sans_oignons"], "quantity": 1}
COCA_NO_SIZE = {"item": "coca_cola", "size": None, "modifiers": [], "quantity": 1}
COCA = dict(COCA_NO_SIZE, size="33cl")


@pytest.fixture(scope="module")
def menu():
    return load_menu()


def make_call(menu, *responses):
    fake = FakeClaude(*responses)
    call = Conversation(menu, OrderExtractor(menu, client=fake))
    call.start()
    return call, fake


def test_happy_path(menu):
    call, fake = make_call(
        menu,
        extraction(lines=[BURGER]),  # « un burger bacon large sans oignons »
        extraction(intent="no", lines=[BURGER]),  # « c'est tout »
        extraction(intent="no", lines=[BURGER]),  # « pas d'allergie »
        extraction(intent="yes", lines=[BURGER]),  # « oui c'est correct »
    )
    assert call.handle("un burger bacon large sans oignons") == t("ask_anything_else")
    assert call.handle("c'est tout") == t("ask_allergies")
    readback = call.handle("non")
    assert call.step == "readback"
    assert "1 Burger bacon large (sans oignons)" in readback
    assert "14,00 euros" in readback
    assert call.handle("oui") == t("order_confirmed")

    assert call.is_over
    assert call.ticket() == {"lines": [BURGER], "total": 1400, "staff_note": None}
    assert all(r["model"] == MODEL_DEFAULT for r in fake.requests)


def test_missing_size_triggers_clarification(menu):
    call, _ = make_call(
        menu,
        extraction(lines=[BURGER, COCA_NO_SIZE]),
        extraction(lines=[BURGER, COCA]),
    )
    assert "Quelle taille" in call.handle("un burger bacon large et un coca")
    assert call.handle("33") == t("ask_anything_else")


def test_declared_allergy_requires_confirmation_and_goes_to_ticket(menu):
    call, _ = make_call(
        menu,
        extraction(lines=[BURGER]),
        extraction(intent="no", lines=[BURGER]),
        extraction(lines=[BURGER], allergies=["lait"]),  # « oui, je suis allergique au lait »
        extraction(intent="yes", lines=[BURGER], allergies=["lait"]),  # « je garde le burger »
        extraction(intent="yes", lines=[BURGER], allergies=["lait"]),
    )
    call.handle("un burger bacon large sans oignons")
    call.handle("c'est tout")
    question = call.handle("je suis allergique au lait")
    assert call.step == "confirm_allergy"
    assert "lait" in question and "Burger bacon" in question
    call.handle("oui je le garde")
    assert call.step == "readback"
    call.handle("oui")

    note = call.ticket()["staff_note"]
    assert note["declared_allergies"] == ["lait"]
    assert note["conflicts"][0]["item"] == "burger_bacon"


def test_allergy_must_be_confirmed_again_if_order_changes(menu):
    frites_mayo = {"item": "frites", "size": "petite", "modifiers": ["sauce_mayonnaise"], "quantity": 1}
    call, _ = make_call(
        menu,
        extraction(lines=[COCA], allergies=["oeufs"]),
        extraction(intent="no", lines=[COCA], allergies=["oeufs"]),
        extraction(intent="yes", lines=[COCA], allergies=["oeufs"]),  # confirme (aucun conflit)
        extraction(lines=[COCA, frites_mayo], allergies=["oeufs"]),  # ajoute des frites mayo à la relecture
    )
    call.handle("un coca 33, je suis allergique aux œufs")
    assert call.handle("c'est tout").startswith("J'ai bien noté votre allergie")
    call.handle("oui")
    assert call.step == "readback"
    question = call.handle("ajoutez des petites frites mayo")
    assert call.step == "confirm_allergy"
    assert "Frites" in question


def test_unavailable_item_is_removed(menu):
    reine = {"item": "pizza_reine", "size": "grande", "modifiers": [], "quantity": 1}
    call, _ = make_call(menu, extraction(lines=[COCA, reine]))
    answer = call.handle("un coca et une grande reine")
    assert "Pizza Reine n'est pas disponible" in answer
    assert call.order["lines"] == [COCA]


def test_unrecognized_item(menu):
    call, _ = make_call(menu, extraction(unrecognized=["un kebab"]))
    assert "un kebab" in call.handle("un kebab")


def test_readback_refused_goes_back_to_taking_order(menu):
    call, _ = make_call(
        menu,
        extraction(lines=[COCA], allergies=[]),
        extraction(intent="no", lines=[COCA]),
        extraction(intent="no", lines=[COCA]),
        extraction(intent="no", lines=[COCA]),  # « non ce n'est pas ça »
    )
    call.handle("un coca 33")
    call.handle("c'est tout")
    call.handle("pas d'allergie")
    assert call.handle("non") == t("ask_change")
    assert call.step == "taking_order"


def test_escalates_to_sonnet_after_two_failures(menu):
    call, fake = make_call(
        menu,
        extraction(intent="unclear"),
        extraction(intent="unclear"),
        extraction(lines=[COCA]),
    )
    call.handle("euh")
    call.handle("hmm")
    call.handle("un coca 33")
    assert [r["model"] for r in fake.requests] == [MODEL_DEFAULT, MODEL_DEFAULT, MODEL_COMPLEX]


def test_transfer_after_three_unclear(menu):
    call, _ = make_call(menu, *[extraction(intent="unclear")] * 3)
    call.handle("...")
    call.handle("...")
    assert call.handle("...") == t("transfer_to_staff")
    assert call.is_over


def test_caller_asks_for_staff(menu):
    call, _ = make_call(menu, extraction(intent="staff"))
    assert call.handle("je veux parler à quelqu'un") == t("transfer_to_staff")
    assert call.step == "transfer"


def test_api_failure_transfers_to_staff(menu):
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))
    call, _ = make_call(menu, error)
    assert call.handle("un coca") == t("transfer_to_staff")


def test_saying_no_with_empty_order_cancels(menu):
    call, _ = make_call(menu, extraction(intent="no"))
    assert call.handle("non rien finalement") == t("order_cancelled")
    assert call.is_over
    assert call.ticket() is None
