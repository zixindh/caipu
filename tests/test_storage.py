import unittest
from datetime import date

from caipu.models import MealSlot
from caipu.storage import _page_to_meal, empty_week


class StorageTests(unittest.TestCase):
    def test_empty_week_contains_three_meals_per_day(self):
        meals = empty_week(date(2026, 7, 3))
        self.assertEqual(len(meals), 21)
        self.assertIn("2026-07-03:早餐", meals)
        self.assertIn("2026-07-09:晚餐", meals)

    def test_page_to_meal_reads_notion_properties(self):
        page = {
            "id": "page-id",
            "last_edited_time": "2026-07-03T12:00:00Z",
            "properties": {
                "日期": {"date": {"start": "2026-07-04"}},
                "时段": {"select": {"name": "午餐"}},
                "菜品": {"rich_text": [{"plain_text": "番茄炒蛋"}]},
                "食材": {"rich_text": [{"plain_text": "番茄、鸡蛋"}]},
                "已备齐": {"checkbox": True},
                "提议人": {"select": {"name": "Heng"}},
                "备注": {"rich_text": [{"plain_text": "少盐"}]},
            },
        }
        meal = _page_to_meal(page)
        self.assertIsNotNone(meal)
        self.assertIs(meal.slot, MealSlot.LUNCH)
        self.assertEqual(meal.dish, "番茄炒蛋")
        self.assertTrue(meal.stocked)
        self.assertEqual(meal.suggested_by, "Heng")


if __name__ == "__main__":
    unittest.main()
