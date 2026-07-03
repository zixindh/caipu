from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from caipu.models import Meal

_SEPARATOR = re.compile(r"[\n,，、;；]+")


def split_ingredients(value: str) -> list[str]:
    return [item.strip() for item in _SEPARATOR.split(value) if item.strip()]


def grocery_items(meals: Iterable[Meal]) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    display_names: dict[str, str] = {}
    for meal in meals:
        if meal.stocked:
            continue
        for item in split_ingredients(meal.ingredients):
            normalized = item.casefold()
            display_names.setdefault(normalized, item)
            counts[normalized] += 1
    return sorted(
        ((display_names[key], count) for key, count in counts.items()),
        key=lambda item: (-item[1], item[0]),
    )
