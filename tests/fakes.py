"""Faux client Claude pour les tests (aucun appel réseau)."""

import json
from types import SimpleNamespace


class FakeClaude:
    """Renvoie les réponses fournies, dans l'ordre, et garde les requêtes reçues."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params):
        self.requests.append(params)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, SimpleNamespace):
            return response
        return reply(response)


def reply(data: dict | str, stop_reason: str = "end_turn") -> SimpleNamespace:
    text = data if isinstance(data, str) else json.dumps(data)
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])


def extraction(intent="update", lines=None, allergies=None, unrecognized=None) -> dict:
    return {
        "intent": intent,
        "lines": lines or [],
        "declared_allergies": allergies or [],
        "unrecognized_items": unrecognized or [],
    }
