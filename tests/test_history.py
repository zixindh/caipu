import unittest
from datetime import date

from caipu.history import group_history
from caipu.models import Meal, MealSlot


class HistoryTests(unittest.TestCase):
    def test_groups_newest_day_first_and_meals_in_day_order(self):
        meals = [
            Meal(date(2026, 7, 1), MealSlot.DINNER, dish="咖喱饭"),
            Meal(date(2026, 7, 2), MealSlot.LUNCH, dish="牛肉面"),
            Meal(date(2026, 7, 2), MealSlot.BREAKFAST, dish="粥"),
        ]

        grouped = group_history(meals)

        self.assertEqual(
            [day for day, _ in grouped], [date(2026, 7, 2), date(2026, 7, 1)]
        )
        self.assertEqual(
            [meal.slot for meal in grouped[0][1]],
            [MealSlot.BREAKFAST, MealSlot.LUNCH],
        )

    def test_ignores_empty_meal_placeholders(self):
        meals = [
            Meal(date(2026, 7, 1), MealSlot.BREAKFAST),
            Meal(date(2026, 7, 1), MealSlot.LUNCH, ingredients="番茄、鸡蛋"),
        ]

        grouped = group_history(meals)

        self.assertEqual(len(grouped), 1)
        self.assertEqual(len(grouped[0][1]), 1)
        self.assertIs(grouped[0][1][0].slot, MealSlot.LUNCH)


if __name__ == "__main__":
    unittest.main()
