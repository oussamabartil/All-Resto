import anthropic
import httpx2
import pytest

from app.llm import MODEL_COMPLEX, MODEL_DEFAULT, LLMError, OrderExtractor, build_output_schema
from app.menu import load_menu
from tests.fakes import FakeClaude, extraction, reply


@pytest.fixture(scope="module")
def menu():
    return load_menu()


def test_schema_restricts_ids_to_menu(menu):
    schema = build_output_schema(menu)
    line = schema["properties"]["lines"]["items"]["properties"]
    assert set(line["item"]["enum"]) == {item.id for item in menu.items}
    assert "sans_oignons" in line["modifiers"]["items"]["enum"]
    assert "large" in line["size"]["anyOf"][0]["enum"]
    assert schema["additionalProperties"] is False


def test_extract_returns_structured_order(menu):
    line = {"item": "burger_bacon", "size": "large", "modifiers": ["sans_oignons"], "quantity": 1}
    fake = FakeClaude(extraction(lines=[line], allergies=["lait"]))
    result = OrderExtractor(menu, client=fake).extract("un burger bacon large sans oignons", {"lines": []}, "")

    assert result.intent == "update"
    assert result.order == {"lines": [line], "declared_allergies": ["lait"]}

    request = fake.requests[0]
    assert request["model"] == MODEL_DEFAULT
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert "burger_bacon" in request["system"][0]["text"]
    assert "un burger bacon large sans oignons" in request["messages"][0]["content"]
    assert "fallbacks" not in request


def test_complex_model_uses_server_side_fallback(menu):
    fake = FakeClaude(extraction(intent="yes"))
    OrderExtractor(menu, client=fake).extract("oui", {"lines": []}, "", model=MODEL_COMPLEX)
    assert fake.requests[0]["model"] == MODEL_COMPLEX
    assert fake.requests[0]["fallbacks"] == "default"


@pytest.mark.parametrize("response", [reply("pas du json"), reply({}, stop_reason="refusal"),
                                      reply("{\"intent\":", stop_reason="max_tokens")])
def test_bad_responses_become_unclear_and_keep_order(menu, response):
    current = {"lines": [{"item": "frites", "size": "petite", "modifiers": [], "quantity": 1}]}
    result = OrderExtractor(menu, client=FakeClaude(response)).extract("...", current, "")
    assert result.intent == "unclear"
    assert result.order == current


def test_api_error_raises_llm_error(menu):
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))
    with pytest.raises(LLMError):
        OrderExtractor(menu, client=FakeClaude(error)).extract("bonjour", {"lines": []}, "")
