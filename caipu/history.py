from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from caipu.models import MEAL_SLOTS, Meal

_SLOT_ORDER = {slot: index for index, slot in enumerate(MEAL_SLOTS)}


def group_history(meals: Iterable[Meal]) -> list[tuple[date, list[Meal]]]:
    """Return non-empty meals grouped by day, newest day first."""
    grouped: dict[date, list[Meal]] = defaultdict(list)
    for meal in meals:
        if not meal.is_empty:
            grouped[meal.day].append(meal)

    return [
        (day, sorted(day_meals, key=lambda meal: _SLOT_ORDER[meal.slot]))
        for day, day_meals in sorted(grouped.items(), reverse=True)
    ]
