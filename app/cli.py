"""Démo en terminal : simule un appel au clavier.

    python -m app.cli

Nécessite des identifiants Claude (ANTHROPIC_API_KEY dans .env ou `ant auth login`).
"""

import json

from dotenv import load_dotenv

load_dotenv()  # avant l'import de app.llm, qui lit les modèles dans l'environnement

from app.conversation import Conversation  # noqa: E402
from app.llm import OrderExtractor  # noqa: E402
from app.menu import load_menu  # noqa: E402


def main() -> None:
    menu = load_menu()
    call = Conversation(menu, OrderExtractor(menu))
    print(f"Agent : {call.start()}")

    while not call.is_over:
        try:
            utterance = input("Vous  : ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if utterance:
            print(f"Agent : {call.handle(utterance)}")

    ticket = call.ticket()
    if ticket:
        print("\n--- Ticket cuisine ---")
        print(json.dumps(ticket, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
