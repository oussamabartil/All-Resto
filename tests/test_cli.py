from app import cli
from app.llm import OrderExtractor
from tests.fakes import FakeClaude, extraction

COCA = {"item": "coca_cola", "size": "33cl", "modifiers": [], "quantity": 1}


def test_cli_full_call(monkeypatch, capsys):
    fake = FakeClaude(
        extraction(lines=[COCA]),
        extraction(intent="no", lines=[COCA]),
        extraction(intent="no", lines=[COCA]),
        extraction(intent="yes", lines=[COCA]),
    )
    monkeypatch.setattr(cli, "OrderExtractor", lambda menu: OrderExtractor(menu, client=fake))
    answers = iter(["un coca 33", "c'est tout", "non", "oui"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    cli.main()

    out = capsys.readouterr().out
    assert out.startswith("Agent : Bonjour")
    assert "Ticket cuisine" in out
    assert '"total": 300' in out
