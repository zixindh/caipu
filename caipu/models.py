from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import Enum


class MealSlot(str, Enum):
    BREAKFAST = "早餐"
    LUNCH = "午餐"
    DINNER = "晚餐"


MEAL_SLOTS = tuple(MealSlot)


@dataclass(frozen=True, slots=True)
class Meal:
    day: date
    slot: MealSlot
    dish: str = ""
    ingredients: str = ""
    stocked: bool = False
    suggested_by: str = ""
    note: str = ""
    page_id: str | None = None
    last_edited_time: str | None = None

    @property
    def key(self) -> str:
        return f"{self.day.isoformat()}:{self.slot.value}"

    @property
    def title(self) -> str:
        return f"{self.day.isoformat()} · {self.slot.value}"

    @property
    def is_empty(self) -> bool:
        return not any((self.dish.strip(), self.ingredients.strip(), self.note.strip()))

    def with_page(self, page_id: str, last_edited_time: str | None = None) -> "Meal":
        return replace(self, page_id=page_id, last_edited_time=last_edited_time)
