from __future__ import annotations

from datetime import date
from typing import Any

import requests

from caipu.models import MEAL_SLOTS, Meal, MealSlot

API_BASE = "https://api.notion.com/v1"
API_VERSION = "2026-03-11"
DATABASE_TITLE = "七日餐单 · Caipu"


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
                "Content-Type": "application/json",
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
            "description": [_text("由七日食谱应用自动维护，请勿删除或重命名字段。")],
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

    def _find_meal_page(self, meal: Meal) -> str | None:
        """Avoid duplicate rows when another user created this meal after our refresh."""
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


def empty_week(start: date, days: int = 7) -> dict[str, Meal]:
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
