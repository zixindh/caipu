from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from caipu.models import LearnedDish, MEAL_SLOTS, Meal

ROW_KEY = "_meal_key"


def build_menu_rows(
    meals: Mapping[str, Meal],
    days: Iterable[date],
    day_labels: Mapping[date, str],
    person_labels: Mapping[str, str],
    learned_dish_names: Iterable[str] = (),
) -> list[dict[str, Any]]:
    learned_names = set(learned_dish_names)
    rows: list[dict[str, Any]] = []
    for day in days:
        for slot in MEAL_SLOTS:
            meal = meals[f"{day.isoformat()}:{slot.value}"]
            rows.append(
                {
                    ROW_KEY: meal.key,
                    "日期": day_labels[day],
                    "餐次": slot.value,
                    "已学会": meal.dish if meal.dish in learned_names else "",
                    "菜品": meal.dish,
                    "食材": meal.ingredients,
                    "已备齐": meal.stocked,
                    "提议": person_labels.get(meal.suggested_by, "—"),
                    "备注": meal.note,
                }
            )
    return rows


def changed_meals(
    rows: Iterable[Mapping[str, Any]],
    originals: Mapping[str, Meal],
    editor: str,
    learned_ingredients: Mapping[str, str] | None = None,
) -> list[Meal]:
    learned_ingredients = learned_ingredients or {}
    changes: list[Meal] = []
    for row in rows:
        key = str(row.get(ROW_KEY, ""))
        original = originals.get(key)
        if original is None:
            continue
        dish = _clean_text(row.get("菜品"))
        ingredients = _clean_text(row.get("食材"))
        selected_dish = _clean_text(row.get("已学会"))
        original_selection = (
            original.dish if original.dish in learned_ingredients else ""
        )
        if selected_dish and selected_dish != original_selection:
            dish = selected_dish
            ingredients = learned_ingredients.get(selected_dish, ingredients).strip()
        stocked = bool(row.get("已备齐", False))
        note = _clean_text(row.get("备注"))
        content_changed = (
            dish != original.dish.strip()
            or ingredients != original.ingredients.strip()
            or stocked != original.stocked
            or note != original.note.strip()
        )
        if not content_changed:
            continue
        changes.append(
            Meal(
                day=original.day,
                slot=original.slot,
                dish=dish,
                ingredients=ingredients,
                stocked=stocked,
                suggested_by=editor,
                note=note,
                page_id=original.page_id,
                last_edited_time=original.last_edited_time,
            )
        )
    return changes


def records_from_editor(data: Any) -> list[dict[str, Any]]:
    if hasattr(data, "to_dict"):
        return list(data.to_dict(orient="records"))
    return [dict(row) for row in data]


def ordered_meal(original: Meal, dish: LearnedDish, editor: str) -> Meal:
    """Place a learned dish into an existing date and meal slot."""
    return Meal(
        day=original.day,
        slot=original.slot,
        dish=dish.name,
        ingredients=dish.ingredients,
        stocked=False,
        suggested_by=editor,
        page_id=original.page_id,
        last_edited_time=original.last_edited_time,
    )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
