import unittest
from datetime import date

from caipu.groceries import grocery_items, split_ingredients
from caipu.models import Meal, MealSlot


class GroceryTests(unittest.TestCase):
    def test_split_ingredients_accepts_chinese_and_newline_separators(self):
        self.assertEqual(
            split_ingredients("番茄 2个、鸡蛋 3个\n葱，盐"),
            ["番茄 2个", "鸡蛋 3个", "葱", "盐"],
        )

    def test_grocery_items_skip_stocked_meals_and_merge_duplicates(self):
        meals = [
            Meal(date(2026, 7, 3), MealSlot.BREAKFAST, ingredients="鸡蛋、牛奶"),
            Meal(date(2026, 7, 3), MealSlot.LUNCH, ingredients="鸡蛋，番茄"),
            Meal(
                date(2026, 7, 3),
                MealSlot.DINNER,
                ingredients="大米",
                stocked=True,
            ),
        ]
        self.assertEqual(grocery_items(meals), [("鸡蛋", 2), ("牛奶", 1), ("番茄", 1)])


if __name__ == "__main__":
    unittest.main()
