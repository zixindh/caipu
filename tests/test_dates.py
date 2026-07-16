import unittest
from datetime import date, timedelta

from caipu.dates import day_label, rolling_days
from caipu.storage import empty_week


class RollingWindowTests(unittest.TestCase):
    def test_table_day_label_is_compact_for_mobile(self):
        today = date(2026, 7, 3)

        self.assertEqual(day_label(today, today), "今天 7/3")
        self.assertEqual(day_label(date(2026, 7, 4), today), "周六 7/4")

    def test_default_window_contains_today_and_tomorrow(self):
        today = date(2026, 7, 3)
        days = rolling_days(today)

        self.assertEqual(len(days), 2)
        self.assertEqual(days[0], today)
        self.assertEqual(days[-1], today + timedelta(days=1))

    def test_window_length_can_be_adjusted(self):
        today = date(2026, 7, 3)

        days = rolling_days(today, 7)

        self.assertEqual(len(days), 7)
        self.assertEqual(days[-1], today + timedelta(days=6))

    def test_tomorrow_drops_old_day_and_adds_new_empty_day(self):
        today = date(2026, 7, 3)
        tomorrow = today + timedelta(days=1)
        old_days = rolling_days(today)
        new_days = rolling_days(tomorrow)
        meals = empty_week(tomorrow)

        self.assertNotIn(today, new_days)
        self.assertEqual(new_days[:-1], old_days[1:])
        self.assertEqual(new_days[-1], today + timedelta(days=2))
        self.assertEqual(
            {meal.slot.value for meal in meals.values() if meal.day == new_days[-1]},
            {"早餐", "午餐", "晚餐"},
        )
        self.assertTrue(
            all(meal.is_empty for meal in meals.values() if meal.day == new_days[-1])
        )


if __name__ == "__main__":
    unittest.main()
