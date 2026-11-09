"""Textes destinés à l'appelant, lus depuis prompts/<langue>/messages.json.

Aucune phrase n'est écrite ici : ce module ne fait que choisir la bonne clé
et remplir les variables avec les libellés du menu dans la bonne langue.
"""

import json
from functools import cache
from pathlib import Path

from app.menu import Menu, MenuItem
from app.order import Order, OrderError, OrderLine

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT_LANGUAGE = "fr"


@cache
def _load(lang: str) -> dict:
    with open(PROMPTS_DIR / lang / "messages.json", encoding="utf-8") as f:
        return json.load(f)


def t(key: str, lang: str = DEFAULT_LANGUAGE, **variables) -> str:
    """Renvoie le texte `key` (notation pointée : "errors.size_required")."""
    value = _load(lang)
    for part in key.split("."):
        value = value[part]
    return value.format(**variables)


def name(names: dict[str, str], lang: str) -> str:
    """Libellé dans la langue demandée, sinon en français."""
    return names.get(lang) or names[DEFAULT_LANGUAGE]


def join_list(values: list[str], lang: str = DEFAULT_LANGUAGE) -> str:
    """["a", "b", "c"] -> "a, b et c"."""
    if not values:
        return t("format.no_options", lang)
    if len(values) == 1:
        return values[0]
    head = t("format.list_separator", lang).join(values[:-1])
    return head + t("format.list_last_separator", lang) + values[-1]


def format_price(cents: int, lang: str = DEFAULT_LANGUAGE) -> str:
    return t("format.price", lang, euros=cents // 100, cents=cents % 100)


def line_price(line: OrderLine, menu: Menu) -> int:
    """Prix d'une ligne déjà validée, en centimes."""
    item = menu.get_item(line.item)
    unit = item.sizes[line.size].price if item.sizes else item.price
    unit += sum(menu.modifiers[m].price_delta for m in line.modifiers)
    return unit * line.quantity


def order_total(order: Order, menu: Menu) -> int:
    return sum(line_price(line, menu) for line in order.lines)


def describe_line(line: OrderLine, menu: Menu, lang: str = DEFAULT_LANGUAGE) -> str:
    """Ligne validée -> "2 Frites grande (sauce ketchup)"."""
    item = menu.get_item(line.item)
    item_name = name(item.names, lang)
    if line.size:
        text = t("format.line_size", lang, quantity=line.quantity, item=item_name,
                 size=name(item.sizes[line.size].names, lang))
    else:
        text = t("format.line", lang, quantity=line.quantity, item=item_name)
    if line.modifiers:
        modifiers = join_list([name(menu.modifiers[m].names, lang) for m in line.modifiers], lang)
        text = t("format.line_modifiers", lang, line=text, modifiers=modifiers)
    return text


def describe_order(order: Order, menu: Menu, lang: str = DEFAULT_LANGUAGE) -> str:
    return join_list([describe_line(line, menu, lang) for line in order.lines], lang)


def question_for_error(error: OrderError, order: Order | None, menu: Menu,
                       lang: str = DEFAULT_LANGUAGE) -> str:
    """Transforme un code d'erreur de validation en question pour le client."""
    item: MenuItem | None = None
    line: OrderLine | None = None
    if order is not None and error.line is not None:
        line = order.lines[error.line]
        item = menu.get_item(line.item)

    variables = {"value": error.value or "", "item": "", "options": "", "modifier": ""}
    if item is not None:
        variables["item"] = name(item.names, lang)
        if error.code in ("size_required", "unknown_size"):
            variables["options"] = join_list([name(s.names, lang) for s in item.sizes.values()], lang)
        elif error.code == "modifier_not_allowed":
            available = [m for m in item.modifiers if menu.modifiers[m].available]
            variables["options"] = join_list([name(menu.modifiers[m].names, lang) for m in available], lang)
    if error.value in menu.modifiers:
        variables["modifier"] = name(menu.modifiers[error.value].names, lang)

    return t(f"errors.{error.code}", lang, **variables)
