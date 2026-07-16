import unittest
from datetime import date
from unittest.mock import Mock

from caipu.models import MealSlot
from caipu.storage import (
    LEARNED_DISH_FLAG,
    LEARNED_DISH_IMAGE,
    NotionMealRepository,
    _page_to_learned_dish,
    _page_to_meal,
    empty_week,
)


class StorageTests(unittest.TestCase):
    def test_empty_week_defaults_to_two_days(self):
        meals = empty_week(date(2026, 7, 3))
        self.assertEqual(len(meals), 6)
        self.assertIn("2026-07-03:早餐", meals)
        self.assertIn("2026-07-04:晚餐", meals)

    def test_empty_week_can_be_adjusted_to_seven_days(self):
        meals = empty_week(date(2026, 7, 3), days=7)

        self.assertEqual(len(meals), 21)
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

    def test_page_to_learned_dish_reads_photo_and_details(self):
        page = {
            "id": "dish-page-id",
            "last_edited_time": "2026-07-16T12:00:00Z",
            "properties": {
                "学会的菜": {"checkbox": True},
                "菜品": {"rich_text": [{"plain_text": "番茄炒蛋"}]},
                "食材": {"rich_text": [{"plain_text": "番茄、鸡蛋"}]},
                "菜品照片": {
                    "files": [
                        {
                            "type": "file",
                            "file": {"url": "https://example.com/dish.jpg"},
                        }
                    ]
                },
                "更新者": {"rich_text": [{"plain_text": "Eva"}]},
            },
        }

        dish = _page_to_learned_dish(page)

        self.assertIsNotNone(dish)
        self.assertEqual(dish.name, "番茄炒蛋")
        self.assertEqual(dish.ingredients, "番茄、鸡蛋")
        self.assertEqual(dish.image_url, "https://example.com/dish.jpg")
        self.assertEqual(dish.added_by, "Eva")

    def test_save_learned_dish_attaches_uploaded_file_to_catalog_row(self):
        repo = NotionMealRepository("token", data_source_id="source-id")
        repo._ensure_learned_dish_schema = Mock(return_value="source-id")
        repo._upload_file = Mock(return_value="upload-id")
        repo._find_learned_dish_page = Mock(return_value=None)
        repo._request = Mock(
            return_value={
                "id": "dish-page-id",
                "last_edited_time": "2026-07-16T12:00:00Z",
            }
        )

        dish = repo.save_learned_dish(
            name="红烧肉",
            ingredients="五花肉、冰糖",
            image_bytes=b"image-bytes",
            filename="pork.jpg",
            content_type="image/jpeg",
            editor="Heng",
        )

        self.assertEqual(dish.name, "红烧肉")
        request_json = repo._request.call_args.kwargs["json"]
        self.assertEqual(
            request_json["properties"]["菜品照片"]["files"][0],
            {"type": "file_upload", "file_upload": {"id": "upload-id"}},
        )

    def test_update_learned_dish_keeps_existing_photo_when_no_new_photo(self):
        repo = NotionMealRepository("token", data_source_id="source-id")
        repo._upload_file = Mock()
        repo._request = Mock(
            return_value={
                "id": "dish-page-id",
                "last_edited_time": "2026-07-16T13:00:00Z",
            }
        )
        original = _page_to_learned_dish(
            {
                "id": "dish-page-id",
                "properties": {
                    "学会的菜": {"checkbox": True},
                    "菜品": {"rich_text": [{"plain_text": "番茄炒蛋"}]},
                    "食材": {"rich_text": [{"plain_text": "番茄、鸡蛋"}]},
                    "菜品照片": {
                        "files": [
                            {
                                "type": "file",
                                "file": {"url": "https://example.com/old.jpg"},
                            }
                        ]
                    },
                },
            }
        )

        updated = repo.update_learned_dish(
            original,
            name="番茄炒蛋",
            ingredients="番茄、鸡蛋、葱",
            editor="Eva",
        )

        method, path = repo._request.call_args.args
        properties = repo._request.call_args.kwargs["json"]["properties"]
        self.assertEqual((method, path), ("PATCH", "/pages/dish-page-id"))
        self.assertNotIn(LEARNED_DISH_IMAGE, properties)
        self.assertEqual(updated.image_url, "https://example.com/old.jpg")
        repo._upload_file.assert_not_called()

    def test_update_learned_dish_replaces_photo_only_when_selected(self):
        repo = NotionMealRepository("token", data_source_id="source-id")
        repo._upload_file = Mock(return_value="replacement-upload-id")
        repo._request = Mock(
            return_value={
                "id": "dish-page-id",
                "last_edited_time": "2026-07-16T13:00:00Z",
            }
        )
        dish = _page_to_learned_dish(
            {
                "id": "dish-page-id",
                "properties": {
                    "学会的菜": {"checkbox": True},
                    "菜品": {"rich_text": [{"plain_text": "红烧肉"}]},
                },
            }
        )

        repo.update_learned_dish(
            dish,
            name="红烧肉",
            ingredients="五花肉、冰糖",
            editor="Heng",
            image_bytes=b"new-image",
            filename="new.jpg",
            content_type="image/jpeg",
        )

        properties = repo._request.call_args.kwargs["json"]["properties"]
        self.assertEqual(
            properties[LEARNED_DISH_IMAGE]["files"][0],
            {
                "type": "file_upload",
                "file_upload": {"id": "replacement-upload-id"},
            },
        )

    def test_learned_dish_schema_adds_only_missing_catalog_fields(self):
        repo = NotionMealRepository("token", data_source_id="source-id")
        repo._request = Mock(
            side_effect=[
                {
                    "properties": {
                        LEARNED_DISH_FLAG: {
                            "type": "checkbox",
                            "checkbox": {},
                        }
                    }
                },
                {"id": "source-id"},
            ]
        )

        source_id = repo._ensure_learned_dish_schema()

        self.assertEqual(source_id, "sourceid")
        patch_call = repo._request.call_args_list[1]
        self.assertEqual(patch_call.args[:2], ("PATCH", "/data_sources/sourceid"))
        self.assertEqual(
            patch_call.kwargs["json"],
            {"properties": {LEARNED_DISH_IMAGE: {"files": {}}}},
        )


if __name__ == "__main__":
    unittest.main()
