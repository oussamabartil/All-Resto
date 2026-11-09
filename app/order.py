"""Commande structurée (produite par le LLM) et validation contre le menu.

Format attendu, par exemple :

    {
      "lines": [
        {"item": "burger_bacon", "size": "large", "modifiers": ["sans_oignons"], "quantity": 1}
      ],
      "declared_allergies": ["lait"]
    }

La validation ne renvoie que des codes d'erreur et des identifiants : les phrases
dites à l'appelant sont construites ailleurs, à partir de prompts/<langue>/.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from app.menu import Menu

MAX_QUANTITY = 20


class OrderLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: str
    size: str | None = None
    modifiers: list[str] = Field(default_factory=list)
    quantity: int = 1


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[OrderLine]
    declared_allergies: list[str] = Field(default_factory=list)


class OrderError(BaseModel):
    """Une erreur de validation. `line` vaut None pour une erreur globale."""

    code: str
    line: int | None = None
    value: str | None = None


class AllergyConflict(BaseModel):
    """Une ligne de la commande contient un allergène déclaré par le client."""

    line: int
    item: str
    allergens: list[str]


class ValidationResult(BaseModel):
    order: Order | None = None
    errors: list[OrderError] = Field(default_factory=list)
    allergy_conflicts: list[AllergyConflict] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def needs_allergy_confirmation(self) -> bool:
        """Toute allergie déclarée impose une confirmation, même sans conflit détecté."""
        return self.order is not None and bool(self.order.declared_allergies)

    @property
    def staff_note(self) -> dict | None:
        """Note structurée pour la cuisine, présente dès qu'une allergie est déclarée."""
        if not self.needs_allergy_confirmation:
            return None
        return {
            "declared_allergies": self.order.declared_allergies,
            "conflicts": [c.model_dump() for c in self.allergy_conflicts],
        }


# Codes d'erreur possibles
INVALID_FORMAT = "invalid_format"
EMPTY_ORDER = "empty_order"
UNKNOWN_ITEM = "unknown_item"
ITEM_UNAVAILABLE = "item_unavailable"
SIZE_REQUIRED = "size_required"
UNKNOWN_SIZE = "unknown_size"
SIZE_NOT_APPLICABLE = "size_not_applicable"
MODIFIER_NOT_ALLOWED = "modifier_not_allowed"
MODIFIER_UNAVAILABLE = "modifier_unavailable"
DUPLICATE_MODIFIER = "duplicate_modifier"
INVALID_QUANTITY = "invalid_quantity"
UNKNOWN_ALLERGEN = "unknown_allergen"


def validate_order(data: dict | Order, menu: Menu) -> ValidationResult:
    """Valide une commande structurée contre le menu.

    Accepte la sortie brute du LLM (dict) ou un `Order` déjà construit.
    """
    if isinstance(data, Order):
        order = data
    else:
        try:
            order = Order.model_validate(data)
        except PydanticValidationError as exc:
            return ValidationResult(errors=[OrderError(code=INVALID_FORMAT, value=str(exc))])

    errors: list[OrderError] = []
    conflicts: list[AllergyConflict] = []

    for allergen_id in order.declared_allergies:
        if allergen_id not in menu.allergens:
            errors.append(OrderError(code=UNKNOWN_ALLERGEN, value=allergen_id))

    if not order.lines:
        errors.append(OrderError(code=EMPTY_ORDER))

    for index, line in enumerate(order.lines):
        errors.extend(_validate_line(index, line, menu))

        conflict = _find_allergy_conflict(index, line, order.declared_allergies, menu)
        if conflict:
            conflicts.append(conflict)

    return ValidationResult(order=order, errors=errors, allergy_conflicts=conflicts)


def _validate_line(index: int, line: OrderLine, menu: Menu) -> list[OrderError]:
    errors: list[OrderError] = []

    def error(code: str, value: str | None = None) -> None:
        errors.append(OrderError(code=code, line=index, value=value))

    if not 1 <= line.quantity <= MAX_QUANTITY:
        error(INVALID_QUANTITY, str(line.quantity))

    item = menu.get_item(line.item)
    if item is None:
        error(UNKNOWN_ITEM, line.item)
        return errors  # impossible de vérifier taille et modificateurs
    if not item.available:
        error(ITEM_UNAVAILABLE, item.id)

    if item.sizes:
        if line.size is None:
            error(SIZE_REQUIRED, item.id)
        elif line.size not in item.sizes:
            error(UNKNOWN_SIZE, line.size)
    elif line.size is not None:
        error(SIZE_NOT_APPLICABLE, line.size)

    seen: set[str] = set()
    for mod_id in line.modifiers:
        if mod_id in seen:
            error(DUPLICATE_MODIFIER, mod_id)
            continue
        seen.add(mod_id)
        if mod_id not in item.modifiers:
            error(MODIFIER_NOT_ALLOWED, mod_id)
        elif not menu.modifiers[mod_id].available:
            error(MODIFIER_UNAVAILABLE, mod_id)

    return errors


def _find_allergy_conflict(
    index: int, line: OrderLine, declared: list[str], menu: Menu
) -> AllergyConflict | None:
    """Allergènes de l'article + ceux ajoutés par les modificateurs.

    Volontairement prudent : un retrait (ex. "sans_fromage") n'enlève pas
    l'allergène, à cause des risques de contamination croisée. Le personnel
    tranche grâce à la note.
    """
    item = menu.get_item(line.item)
    if item is None or not declared:
        return None

    contained = set(item.allergens)
    for mod_id in line.modifiers:
        modifier = menu.modifiers.get(mod_id)
        if modifier:
            contained.update(modifier.allergens)

    matching = [a for a in declared if a in contained]
    if not matching:
        return None
    return AllergyConflict(line=index, item=item.id, allergens=matching)
