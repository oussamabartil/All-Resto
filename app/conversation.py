"""Déroulé d'un appel : prise de commande -> allergies -> relecture -> confirmation.

Une `Conversation` reçoit les phrases du client une par une (`handle`) et
renvoie la phrase à dire. Elle ne dépend ni de la voix ni du téléphone : le
même objet sert pour la démo en terminal et, plus tard, pour l'agent LiveKit.

Étapes (`step`) :
    taking_order     on prend la commande et on pose les questions de clarification
    ask_allergies    « Avez-vous des allergies ? »
    confirm_allergy  confirmation obligatoire dès qu'une allergie est déclarée
    readback         relecture complète de la commande
    done | cancelled | transfer
                     fin d'appel (commande validée / annulée / passage à un humain)
"""

from app.llm import MODEL_COMPLEX, MODEL_DEFAULT, LLMError, OrderExtractor
from app.menu import Menu
from app.messages import describe_order, format_price, join_list, name, order_total, question_for_error, t
from app.order import ITEM_UNAVAILABLE, MODIFIER_UNAVAILABLE, OrderError, ValidationResult, validate_order

ESCALATE_AFTER_FAILURES = 2  # passe à Sonnet après 2 tours ratés d'affilée
TRANSFER_AFTER_UNCLEAR = 3  # passe à un humain après 3 incompréhensions d'affilée


class Conversation:
    def __init__(self, menu: Menu, extractor: OrderExtractor, lang: str = "fr"):
        self.menu = menu
        self.extractor = extractor
        self.lang = lang

        self.step = "taking_order"
        self.order: dict = {"lines": [], "declared_allergies": []}
        self.finished_ordering = False  # le client a dit « c'est tout »
        self.allergies_asked = False
        self.confirmed_allergy_note: dict | None = None  # note confirmée par le client
        self.failures = 0
        self.unclear_count = 0
        self.last_question = ""

    # --- API publique -------------------------------------------------------

    def start(self) -> str:
        return self._say(t("greeting", self.lang))

    @property
    def is_over(self) -> bool:
        return self.step in ("done", "cancelled", "transfer")

    def ticket(self) -> dict | None:
        """Commande finale pour la cuisine, disponible une fois l'appel validé."""
        if self.step != "done":
            return None
        result = self._validate()
        return {
            "lines": [line.model_dump() for line in result.order.lines],
            "total": order_total(result.order, self.menu),
            "staff_note": result.staff_note,
        }

    def handle(self, utterance: str) -> str:
        model = MODEL_COMPLEX if self.failures >= ESCALATE_AFTER_FAILURES else MODEL_DEFAULT
        try:
            extraction = self.extractor.extract(utterance, self.order, self.last_question, model=model)
        except LLMError:
            return self._transfer()

        if extraction.intent == "staff":
            return self._transfer()

        if extraction.intent == "unclear":
            self.failures += 1
            self.unclear_count += 1
            if self.unclear_count >= TRANSFER_AFTER_UNCLEAR:
                return self._transfer()
            return self._say(t("not_understood", self.lang))
        self.unclear_count = 0

        if extraction.intent == "update":
            self.order = extraction.order
            if self.step == "ask_allergies":
                self.allergies_asked = True
            if extraction.unrecognized_items:
                self.failures += 1
                self.step = "taking_order"
                error = OrderError(code="unknown_item", value=extraction.unrecognized_items[0])
                return self._say(question_for_error(error, None, self.menu, self.lang))
            unavailable_message = self._drop_unavailable()
            if unavailable_message:
                return unavailable_message
            return self._next_step()

        return self._handle_yes_no(extraction.intent == "yes")

    # --- Logique interne ----------------------------------------------------

    def _handle_yes_no(self, yes: bool) -> str:
        if self.step == "taking_order" and self.last_question == t("ask_anything_else", self.lang):
            if yes:
                return self._say(t("ask_what_else", self.lang))
            self.finished_ordering = True

        elif self.step == "ask_allergies":
            if yes:  # « oui » sans dire laquelle
                return self._say(t("errors.unknown_allergen", self.lang))
            self.allergies_asked = True

        elif self.step == "confirm_allergy":
            if yes:
                self.confirmed_allergy_note = self._validate().staff_note
            else:
                return self._ask_change()

        elif self.step == "readback":
            if yes:
                self.step = "done"
                return self._say(t("order_confirmed", self.lang))
            return self._ask_change()

        elif self.step == "taking_order" and not self.order["lines"] and not yes:
            # « non » alors que rien n'a été commandé
            self.step = "cancelled"
            return self._say(t("order_cancelled", self.lang))

        return self._next_step()

    def _next_step(self) -> str:
        """Choisit la prochaine question d'après l'état de la commande."""
        result = self._validate()
        if result.errors:
            self.failures += 1
            self.step = "taking_order"
            return self._say(question_for_error(result.errors[0], result.order, self.menu, self.lang))
        self.failures = 0

        if not self.finished_ordering:
            self.step = "taking_order"
            return self._say(t("ask_anything_else", self.lang))

        if not self.allergies_asked and not result.order.declared_allergies:
            self.step = "ask_allergies"
            return self._say(t("ask_allergies", self.lang))

        if result.needs_allergy_confirmation and result.staff_note != self.confirmed_allergy_note:
            self.step = "confirm_allergy"
            return self._say(self._allergy_question(result))

        self.step = "readback"
        return self._say(t("order_readback", self.lang,
                           summary=describe_order(result.order, self.menu, self.lang),
                           total=format_price(order_total(result.order, self.menu), self.lang)))

    def _validate(self) -> ValidationResult:
        return validate_order(self.order, self.menu)

    def _drop_unavailable(self) -> str | None:
        """Retire les articles / options indisponibles et prévient le client."""
        result = self._validate()
        if result.order is None:
            return None
        unavailable = [e for e in result.errors if e.code in (ITEM_UNAVAILABLE, MODIFIER_UNAVAILABLE)]
        if not unavailable:
            return None

        message = question_for_error(unavailable[0], result.order, self.menu, self.lang)
        bad_lines = {e.line for e in unavailable if e.code == ITEM_UNAVAILABLE}
        bad_modifiers = {(e.line, e.value) for e in unavailable if e.code == MODIFIER_UNAVAILABLE}
        lines = []
        for index, line in enumerate(self.order["lines"]):
            if index in bad_lines:
                continue
            line = dict(line, modifiers=[m for m in line.get("modifiers", []) if (index, m) not in bad_modifiers])
            lines.append(line)
        self.order = dict(self.order, lines=lines)
        self.step = "taking_order"
        self.finished_ordering = False
        return self._say(message)

    def _allergy_question(self, result: ValidationResult) -> str:
        allergens = join_list([name(self.menu.allergens[a].names, self.lang)
                               for a in result.order.declared_allergies], self.lang)
        if not result.allergy_conflicts:
            return t("allergy_no_conflict", self.lang, allergens=allergens)
        items = join_list([name(self.menu.get_item(c.item).names, self.lang)
                           for c in result.allergy_conflicts], self.lang)
        return t("allergy_conflict", self.lang, allergens=allergens, items=items)

    def _ask_change(self) -> str:
        self.step = "taking_order"
        self.finished_ordering = False
        return self._say(t("ask_change", self.lang))

    def _transfer(self) -> str:
        self.step = "transfer"
        return self._say(t("transfer_to_staff", self.lang))

    def _say(self, text: str) -> str:
        self.last_question = text
        return text
