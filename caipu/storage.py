from __future__ import annotations

from datetime import date
from typing import Any

import requests

from caipu.dates import DEFAULT_VISIBLE_DAYS
from caipu.models import LearnedDish, MEAL_SLOTS, Meal, MealSlot

API_BASE = "https://api.notion.com/v1"
API_VERSION = "2026-03-11"
DATABASE_TITLE = "七日餐单 · Caipu"
LEARNED_DISH_FLAG = "学会的菜"
LEARNED_DISH_IMAGE = "菜品照片"
MAX_DISH_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_DISH_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


class StorageError(RuntimeError):
    """A safe, user-facing Notion storage error."""


class NotionMealRepository:
    def __init__(
        self,
        token: str,
        data_source_id: str | None = None,
        parent_page_id: str | None = None,
        timeout: int = 15,
        session: requests.Session | None = None,
    ) -> None:
        if not token:
            raise ValueError("缺少 Notion Token")
        if not data_source_id and not parent_page_id:
            raise ValueError("需要 notion_data_source_id 或 notion_parent_page_id")
        self.data_source_id = _clean_id(data_source_id) if data_source_id else None
        self.parent_page_id = _clean_id(parent_page_id) if parent_page_id else None
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": API_VERSION,
            }
        )

    def ensure_ready(self) -> str:
        if self.data_source_id:
            self._request("GET", f"/data_sources/{self.data_source_id}")
            return self.data_source_id

        found = self._find_data_source()
        if found:
            self.data_source_id = found
            return found

        payload = {
            "parent": {"type": "page_id", "page_id": self.parent_page_id},
            "title": [_text(DATABASE_TITLE)],
            "description": [_text("由共享餐桌应用自动维护，请勿删除或重命名字段。")],
            "is_inline": False,
            "icon": {"type": "emoji", "emoji": "🍲"},
            "initial_data_source": {"properties": _schema()},
        }
        result = self._request("POST", "/databases", json=payload)
        sources = result.get("data_sources", [])
        if not sources:
            raise StorageError(
                "Notion 已创建数据库，但没有返回数据源 ID。请刷新后重试。"
            )
        self.data_source_id = sources[0]["id"]
        return self.data_source_id

    def load_week(self, start: date, end: date) -> dict[str, Meal]:
        source_id = self.ensure_ready()
        payload: dict[str, Any] = {
            "filter": {
                "and": [
                    {"property": "日期", "date": {"on_or_after": start.isoformat()}},
                    {"property": "日期", "date": {"on_or_before": end.isoformat()}},
                ]
            },
            "sorts": [{"property": "日期", "direction": "ascending"}],
            "page_size": 100,
        }
        pages: list[dict[str, Any]] = []
        while True:
            response = self._request(
                "POST", f"/data_sources/{source_id}/query", json=payload
            )
            pages.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            payload["start_cursor"] = response["next_cursor"]

        meals: dict[str, Meal] = {}
        for page in pages:
            meal = _page_to_meal(page)
            if meal is None:
                continue
            previous = meals.get(meal.key)
            if previous is None or (meal.last_edited_time or "") > (
                previous.last_edited_time or ""
            ):
                meals[meal.key] = meal
        return meals

    def save(self, meal: Meal, editor: str) -> Meal:
        source_id = self.ensure_ready()
        properties = _meal_properties(meal, editor)
        page_id = meal.page_id or self._find_meal_page(meal)
        if page_id:
            response = self._request(
                "PATCH", f"/pages/{page_id}", json={"properties": properties}
            )
        else:
            response = self._request(
                "POST",
                "/pages",
                json={
                    "parent": {
                        "type": "data_source_id",
                        "data_source_id": source_id,
                    },
                    "properties": properties,
                },
            )
        return meal.with_page(response["id"], response.get("last_edited_time"))

    def load_learned_dishes(self) -> list[LearnedDish]:
        source_id = self._ensure_learned_dish_schema()
        payload: dict[str, Any] = {
            "filter": {
                "property": LEARNED_DISH_FLAG,
                "checkbox": {"equals": True},
            },
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
            "page_size": 100,
        }
        pages: list[dict[str, Any]] = []
        while True:
            response = self._request(
                "POST", f"/data_sources/{source_id}/query", json=payload
            )
            pages.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            payload["start_cursor"] = response["next_cursor"]

        dishes: dict[str, LearnedDish] = {}
        for page in pages:
            dish = _page_to_learned_dish(page)
            if dish is None:
                continue
            key = dish.name.casefold()
            previous = dishes.get(key)
            if previous is None or (dish.last_edited_time or "") > (
                previous.last_edited_time or ""
            ):
                dishes[key] = dish
        return sorted(dishes.values(), key=lambda dish: dish.name.casefold())

    def save_learned_dish(
        self,
        *,
        name: str,
        ingredients: str,
        image_bytes: bytes,
        filename: str,
        content_type: str,
        editor: str,
    ) -> LearnedDish:
        name = name.strip()
        ingredients = ingredients.strip()
        content_type = content_type.lower().strip()
        if not name:
            raise ValueError("请填写菜名。")
        if not image_bytes:
            raise ValueError("请选择一张菜品照片。")
        if len(image_bytes) > MAX_DISH_IMAGE_BYTES:
            raise ValueError("照片不能超过 5 MB。")
        if content_type not in ALLOWED_DISH_IMAGE_TYPES:
            raise ValueError("照片仅支持 JPG、PNG 或 WebP。")

        source_id = self._ensure_learned_dish_schema()
        upload_id = self._upload_file(
            image_bytes=image_bytes,
            filename=filename,
            content_type=content_type,
        )
        properties = {
            "餐次": {"title": [_text(f"已学会 · {name}")]},
            "菜品": {"rich_text": _rich_text(name)},
            "食材": {"rich_text": _rich_text(ingredients)},
            LEARNED_DISH_FLAG: {"checkbox": True},
            LEARNED_DISH_IMAGE: {
                "files": [
                    {
                        "type": "file_upload",
                        "file_upload": {"id": upload_id},
                    }
                ]
            },
            "更新者": {"rich_text": [_text(editor)]},
        }
        page_id = self._find_learned_dish_page(name)
        if page_id:
            response = self._request(
                "PATCH", f"/pages/{page_id}", json={"properties": properties}
            )
        else:
            response = self._request(
                "POST",
                "/pages",
                json={
                    "parent": {
                        "type": "data_source_id",
                        "data_source_id": source_id,
                    },
                    "properties": properties,
                },
            )
        return LearnedDish(
            name=name,
            ingredients=ingredients,
            added_by=editor,
            page_id=response["id"],
            last_edited_time=response.get("last_edited_time"),
        )

    def update_learned_dish(
        self,
        dish: LearnedDish,
        *,
        name: str,
        ingredients: str,
        editor: str,
        image_bytes: bytes | None = None,
        filename: str = "",
        content_type: str = "",
    ) -> LearnedDish:
        if not dish.page_id:
            raise ValueError("这道菜缺少 Notion 页面 ID，请刷新后重试。")

        name = name.strip()
        ingredients = ingredients.strip()
        if not name:
            raise ValueError("请填写菜名。")

        if name.casefold() != dish.name.casefold():
            existing_page_id = self._find_learned_dish_page(name)
            if existing_page_id and _clean_id(existing_page_id) != _clean_id(
                dish.page_id
            ):
                raise ValueError("已经有一道同名的菜，请换一个名字。")

        properties: dict[str, Any] = {
            "餐次": {"title": [_text(f"已学会 · {name}")]},
            "菜品": {"rich_text": _rich_text(name)},
            "食材": {"rich_text": _rich_text(ingredients)},
            LEARNED_DISH_FLAG: {"checkbox": True},
            "更新者": {"rich_text": [_text(editor)]},
        }

        if image_bytes is not None:
            content_type = content_type.lower().strip()
            if not image_bytes:
                raise ValueError("新照片是空的，请重新选择。")
            if len(image_bytes) > MAX_DISH_IMAGE_BYTES:
                raise ValueError("照片不能超过 5 MB。")
            if content_type not in ALLOWED_DISH_IMAGE_TYPES:
                raise ValueError("照片仅支持 JPG、PNG 或 WebP。")
            upload_id = self._upload_file(
                image_bytes=image_bytes,
                filename=filename,
                content_type=content_type,
            )
            properties[LEARNED_DISH_IMAGE] = {
                "files": [
                    {
                        "type": "file_upload",
                        "file_upload": {"id": upload_id},
                    }
                ]
            }

        response = self._request(
            "PATCH",
            f"/pages/{dish.page_id}",
            json={"properties": properties},
        )
        return LearnedDish(
            name=name,
            ingredients=ingredients,
            image_url=dish.image_url,
            added_by=editor,
            page_id=response["id"],
            last_edited_time=response.get("last_edited_time"),
        )

    def _ensure_learned_dish_schema(self) -> str:
        source_id = self.data_source_id or self.ensure_ready()
        source = self._request("GET", f"/data_sources/{source_id}")
        properties = source.get("properties", {})
        required = {
            LEARNED_DISH_FLAG: "checkbox",
            LEARNED_DISH_IMAGE: "files",
        }
        additions: dict[str, Any] = {}
        for name, expected_type in required.items():
            existing = properties.get(name)
            if existing is None:
                additions[name] = {expected_type: {}}
            elif existing.get("type") != expected_type:
                raise StorageError(
                    f'Notion 字段“{name}”类型不正确，请将它改为 {expected_type}。'
                )
        if additions:
            self._request(
                "PATCH",
                f"/data_sources/{source_id}",
                json={"properties": additions},
            )
        return source_id

    def _upload_file(
        self, *, image_bytes: bytes, filename: str, content_type: str
    ) -> str:
        safe_filename = _safe_filename(filename, content_type)
        upload = self._request(
            "POST",
            "/file_uploads",
            json={
                "mode": "single_part",
                "filename": safe_filename,
                "content_type": content_type,
            },
        )
        upload_id = upload.get("id")
        if not upload_id:
            raise StorageError("Notion 没有返回照片上传 ID，请重试。")
        sent = self._request(
            "POST",
            f"/file_uploads/{upload_id}/send",
            files={"file": (safe_filename, image_bytes, content_type)},
        )
        if sent.get("status") not in (None, "uploaded"):
            raise StorageError("照片上传尚未完成，请重试。")
        return str(upload_id)

    def _find_meal_page(self, meal: Meal) -> str | None:
        """Avoid duplicates if another user created a meal after our refresh."""
        response = self._request(
            "POST",
            f"/data_sources/{self.data_source_id}/query",
            json={
                "filter": {
                    "and": [
                        {
                            "property": "日期",
                            "date": {"equals": meal.day.isoformat()},
                        },
                        {
                            "property": "时段",
                            "select": {"equals": meal.slot.value},
                        },
                    ]
                },
                "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
                "page_size": 1,
            },
        )
        pages = response.get("results", [])
        return pages[0]["id"] if pages else None

    def _find_learned_dish_page(self, name: str) -> str | None:
        response = self._request(
            "POST",
            f"/data_sources/{self.data_source_id}/query",
            json={
                "filter": {
                    "and": [
                        {
                            "property": LEARNED_DISH_FLAG,
                            "checkbox": {"equals": True},
                        },
                        {
                            "property": "菜品",
                            "rich_text": {"equals": name},
                        },
                    ]
                },
                "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
                "page_size": 1,
            },
        )
        pages = response.get("results", [])
        return pages[0]["id"] if pages else None

    def _find_data_source(self) -> str | None:
        response = self._request(
            "POST",
            "/search",
            json={
                "query": DATABASE_TITLE,
                "filter": {"property": "object", "value": "data_source"},
                "page_size": 20,
            },
        )
        for item in response.get("results", []):
            title = _plain_text(item.get("title", []))
            parent = item.get("database_parent", {})
            same_parent = (
                not self.parent_page_id
                or _clean_id(parent.get("page_id", "")) == self.parent_page_id
            )
            if title == DATABASE_TITLE and same_parent:
                return item["id"]
        return None

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.session.request(
                method, f"{API_BASE}{path}", timeout=self.timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise StorageError("暂时无法连接 Notion，请稍后再试。") from exc
        if response.ok:
            return response.json()

        try:
            detail = response.json().get("message", "")
        except ValueError:
            detail = ""
        if response.status_code in (401, 403):
            message = "Notion 授权失败，请检查 Token、连接权限和父页面共享设置。"
        elif response.status_code == 404:
            message = "找不到 Notion 页面或数据库，请确认 ID 正确且已共享给连接。"
        elif response.status_code == 429:
            message = "Notion 请求过于频繁，请稍等几秒再试。"
        else:
            message = "Notion 保存失败，请稍后再试。"
        if detail:
            message = f"{message}（{detail[:160]}）"
        raise StorageError(message)


def empty_week(start: date, days: int = DEFAULT_VISIBLE_DAYS) -> dict[str, Meal]:
    from datetime import timedelta

    return {
        meal.key: meal
        for offset in range(days)
        for slot in MEAL_SLOTS
        if (meal := Meal(day=start + timedelta(days=offset), slot=slot))
    }


def _schema() -> dict[str, Any]:
    return {
        "餐次": {"title": {}},
        "日期": {"date": {}},
        "时段": {
            "select": {
                "options": [
                    {"name": slot.value, "color": color}
                    for slot, color in zip(MEAL_SLOTS, ("yellow", "orange", "blue"))
                ]
            }
        },
        "菜品": {"rich_text": {}},
        "食材": {"rich_text": {}},
        "已备齐": {"checkbox": {}},
        "提议人": {
            "select": {
                "options": [
                    {"name": "Eva", "color": "pink"},
                    {"name": "Heng", "color": "blue"},
                    {"name": "强尼", "color": "green"},
                ]
            }
        },
        "备注": {"rich_text": {}},
        "更新者": {"rich_text": {}},
        LEARNED_DISH_FLAG: {"checkbox": {}},
        LEARNED_DISH_IMAGE: {"files": {}},
    }


def _meal_properties(meal: Meal, editor: str) -> dict[str, Any]:
    return {
        "餐次": {"title": [_text(meal.title)]},
        "日期": {"date": {"start": meal.day.isoformat()}},
        "时段": {"select": {"name": meal.slot.value}},
        "菜品": {"rich_text": _rich_text(meal.dish)},
        "食材": {"rich_text": _rich_text(meal.ingredients)},
        "已备齐": {"checkbox": meal.stocked},
        "提议人": {"select": {"name": meal.suggested_by or editor}},
        "备注": {"rich_text": _rich_text(meal.note)},
        "更新者": {"rich_text": [_text(editor)]},
    }


def _page_to_meal(page: dict[str, Any]) -> Meal | None:
    properties = page.get("properties", {})
    day_value = properties.get("日期", {}).get("date")
    slot_value = properties.get("时段", {}).get("select")
    if not day_value or not slot_value:
        return None
    try:
        return Meal(
            day=date.fromisoformat(day_value["start"][:10]),
            slot=MealSlot(slot_value["name"]),
            dish=_property_text(properties.get("菜品", {}), "rich_text"),
            ingredients=_property_text(properties.get("食材", {}), "rich_text"),
            stocked=bool(properties.get("已备齐", {}).get("checkbox")),
            suggested_by=(properties.get("提议人", {}).get("select") or {}).get(
                "name", ""
            ),
            note=_property_text(properties.get("备注", {}), "rich_text"),
            page_id=page.get("id"),
            last_edited_time=page.get("last_edited_time"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _page_to_learned_dish(page: dict[str, Any]) -> LearnedDish | None:
    properties = page.get("properties", {})
    if not properties.get(LEARNED_DISH_FLAG, {}).get("checkbox"):
        return None
    name = _property_text(properties.get("菜品", {}), "rich_text").strip()
    if not name:
        return None
    image_url = ""
    for file_value in properties.get(LEARNED_DISH_IMAGE, {}).get("files", []):
        file_type = file_value.get("type")
        if file_type in ("file", "external"):
            image_url = (file_value.get(file_type) or {}).get("url", "")
            if image_url:
                break
    return LearnedDish(
        name=name,
        ingredients=_property_text(properties.get("食材", {}), "rich_text"),
        image_url=image_url,
        added_by=_property_text(properties.get("更新者", {}), "rich_text"),
        page_id=page.get("id"),
        last_edited_time=page.get("last_edited_time"),
    )


def _text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": value}}


def _rich_text(value: str) -> list[dict[str, Any]]:
    return [_text(value[index : index + 1900]) for index in range(0, len(value), 1900)]


def _plain_text(items: list[dict[str, Any]]) -> str:
    return "".join(item.get("plain_text", "") for item in items)


def _property_text(prop: dict[str, Any], kind: str) -> str:
    return _plain_text(prop.get(kind, []))


def _clean_id(value: str | None) -> str:
    return (value or "").replace("-", "").strip()


def _safe_filename(filename: str, content_type: str) -> str:
    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }[content_type]
    stem = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = stem.rsplit(".", 1)[0].strip()
    stem = "".join(
        character
        for character in stem
        if character.isalnum() or character in ("-", "_", " ")
    ).strip() or "dish"
    return f"{stem[:120]}{extension}"
