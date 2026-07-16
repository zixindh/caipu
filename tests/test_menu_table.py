import unittest
from datetime import date, timedelta

from caipu.menu_table import build_menu_rows, changed_meals, ordered_meal
from caipu.models import LearnedDish, MEAL_SLOTS, Meal
from caipu.storage import empty_week


class MenuTableTests(unittest.TestCase):
    def setUp(self):
        self.start = date(2026, 7, 3)
        self.days = [self.start + timedelta(days=offset) for offset in range(7)]
        self.meals = empty_week(self.start, days=7)
        self.labels = {day: day.isoformat() for day in self.days}
        self.people = {
            "Eva": "🟣 Eva",
            "Heng": "🔵 Heng",
            "强尼": "🟠 强尼",
        }

    def test_builds_one_table_with_all_seven_days_and_three_meals(self):
        rows = build_menu_rows(self.meals, self.days, self.labels, self.people)

        self.assertEqual(len(rows), 21)
        self.assertEqual({row["日期"] for row in rows}, set(self.labels.values()))
        self.assertEqual(
            [row["餐次"] for row in rows[:3]],
            [slot.value for slot in MEAL_SLOTS],
        )
        self.assertTrue(all(row["提议"] == "—" for row in rows))

    def test_changed_row_is_automatically_assigned_to_logged_in_user(self):
        rows = build_menu_rows(self.meals, self.days, self.labels, self.people)
        rows[0]["菜品"] = "豆浆油条"
        rows[0]["食材"] = "豆浆、油条"
        rows[0]["已备齐"] = True

        changes = changed_meals(rows, self.meals, "Heng")

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].dish, "豆浆油条")
        self.assertEqual(changes[0].ingredients, "豆浆、油条")
        self.assertTrue(changes[0].stocked)
        self.assertEqual(changes[0].suggested_by, "Heng")

    def test_existing_attribution_does_not_trigger_a_change(self):
        first = next(iter(self.meals.values()))
        self.meals[first.key] = Meal(
            day=first.day,
            slot=first.slot,
            dish="粥",
            suggested_by="Eva",
        )
        rows = build_menu_rows(self.meals, self.days, self.labels, self.people)

        self.assertEqual(changed_meals(rows, self.meals, "强尼"), [])

    def test_picking_a_learned_dish_fills_name_and_saved_ingredients(self):
        learned = {"番茄炒蛋": "番茄、鸡蛋、葱"}
        rows = build_menu_rows(
            self.meals,
            self.days,
            self.labels,
            self.people,
            learned_dish_names=learned,
        )
        rows[0]["已学会"] = "番茄炒蛋"

        changes = changed_meals(
            rows,
            self.meals,
            "Eva",
            learned_ingredients=learned,
        )

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].dish, "番茄炒蛋")
        self.assertEqual(changes[0].ingredients, "番茄、鸡蛋、葱")
        self.assertEqual(changes[0].suggested_by, "Eva")

    def test_ordering_a_learned_dish_replaces_the_slot_and_preserves_page(self):
        original = Meal(
            day=self.start,
            slot=MEAL_SLOTS[2],
            dish="旧菜",
            ingredients="旧食材",
            stocked=True,
            note="旧备注",
            page_id="meal-page-id",
        )
        dish = LearnedDish(name="红烧肉", ingredients="五花肉、冰糖")

        result = ordered_meal(original, dish, "Heng")

        self.assertEqual(result.dish, "红烧肉")
        self.assertEqual(result.ingredients, "五花肉、冰糖")
        self.assertEqual(result.suggested_by, "Heng")
        self.assertFalse(result.stocked)
        self.assertEqual(result.note, "")
        self.assertEqual(result.page_id, "meal-page-id")


if __name__ == "__main__":
    unittest.main()
