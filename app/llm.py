"""Extraction structurée de la commande avec Claude.

Claude ne parle jamais au client : il transforme la phrase du client en données
structurées (identifiants du menu). Le schéma de sortie est construit à partir
du menu, avec des listes fermées (enum), donc Claude ne peut pas inventer
d'article, de taille ou de modificateur.

Haiku 5.5 est utilisé par défaut ; Sonnet 5.5 pour les cas difficiles
(le choix est fait par la conversation, voir app/conversation.py).
"""

import json
import os
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from app.menu import Menu

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "llm" / "extraction.md"

MODEL_DEFAULT = os.getenv("LLM_MODEL_DEFAULT", "claude-haiku-5-5")
MODEL_COMPLEX = os.getenv("LLM_MODEL_COMPLEX", "claude-sonnet-5-5")

Intent = Literal["update", "yes", "no", "staff", "unclear"]
INTENTS = ["update", "yes", "no", "staff", "unclear"]


class LLMError(Exception):
    """Claude n'a pas pu répondre (réseau, quota, erreur serveur...)."""


class Extraction(BaseModel):
    intent: Intent
    order: dict  # {"lines": [...], "declared_allergies": [...]} -> validé par app.order.validate_order
    unrecognized_items: list[str] = Field(default_factory=list)


def build_output_schema(menu: Menu) -> dict:
    sizes = sorted({size_id for item in menu.items for size_id in item.sizes})
    line = {
        "type": "object",
        "properties": {
            "item": {"type": "string", "enum": [item.id for item in menu.items]},
            "size": {"anyOf": [{"type": "string", "enum": sizes}, {"type": "null"}]},
            "modifiers": {"type": "array", "items": {"type": "string", "enum": list(menu.modifiers)}},
            "quantity": {"type": "integer"},
        },
        "required": ["item", "size", "modifiers", "quantity"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": INTENTS},
            "lines": {"type": "array", "items": line},
            "declared_allergies": {"type": "array", "items": {"type": "string", "enum": list(menu.allergens)}},
            "unrecognized_items": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["intent", "lines", "declared_allergies", "unrecognized_items"],
        "additionalProperties": False,
    }


def describe_menu_for_llm(menu: Menu, lang: str = "fr") -> str:
    """Menu compact, toujours dans le même ordre (favorise le cache de prompt)."""
    rows = []
    for item in menu.items:
        row = {
            "id": item.id,
            "name": item.names.get(lang, item.names["fr"]),
            "available": item.available,
            "sizes": {sid: s.names.get(lang, s.names["fr"]) for sid, s in item.sizes.items()},
            "modifiers": item.modifiers,
            "allergens": item.allergens,
        }
        rows.append(json.dumps(row, ensure_ascii=False))
    modifiers = {mid: m.names.get(lang, m.names["fr"]) for mid, m in menu.modifiers.items()}
    allergens = {aid: a.names.get(lang, a.names["fr"]) for aid, a in menu.allergens.items()}
    return (
        "<menu_items>\n" + "\n".join(rows) + "\n</menu_items>\n"
        f"<modifiers>{json.dumps(modifiers, ensure_ascii=False)}</modifiers>\n"
        f"<allergens>{json.dumps(allergens, ensure_ascii=False)}</allergens>"
    )


class OrderExtractor:
    def __init__(self, menu: Menu, client: anthropic.Anthropic | None = None, lang: str = "fr"):
        self.menu = menu
        self.client = client or anthropic.Anthropic()
        self.schema = build_output_schema(menu)
        self.system = PROMPT_PATH.read_text(encoding="utf-8") + "\n\n" + describe_menu_for_llm(menu, lang)

    def extract(self, utterance: str, current_order: dict, last_question: str,
                model: str = MODEL_DEFAULT) -> Extraction:
        user_content = (
            f"<current_order>{json.dumps(current_order, ensure_ascii=False)}</current_order>\n"
            f"<last_agent_question>{last_question}</last_agent_question>\n"
            f"<caller_said>{utterance}</caller_said>"
        )
        params = dict(
            model=model,
            max_tokens=4000,
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_content}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": self.schema}},
        )
        if model.startswith("claude-sonnet-5-5"):
            # Si Sonnet refuse (filtre de sécurité), l'API relance sur un autre modèle.
            params.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")

        try:
            response = self.client.beta.messages.create(**params)
        except anthropic.APIError as exc:
            raise LLMError(str(exc)) from exc

        if response.stop_reason in ("refusal", "max_tokens"):
            return Extraction(intent="unclear", order=current_order)

        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return Extraction(intent="unclear", order=current_order)

        return Extraction(
            intent=data["intent"],
            order={"lines": data["lines"], "declared_allergies": data["declared_allergies"]},
            unrecognized_items=data["unrecognized_items"],
        )
