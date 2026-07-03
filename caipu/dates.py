from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = "一二三四五六日"
APP_TIMEZONE = ZoneInfo("Asia/Shanghai")


def today_in_china() -> date:
    from datetime import datetime

    return datetime.now(APP_TIMEZONE).date()


def rolling_days(start: date, count: int = 7) -> list[date]:
    return [start + timedelta(days=offset) for offset in range(count)]


def day_label(day: date, today: date) -> str:
    prefix = "今天" if day == today else f"周{WEEKDAYS[day.weekday()]}"
    return f"{prefix} {day.month}/{day.day}"


def full_day_label(day: date, today: date) -> str:
    prefix = "今天" if day == today else f"星期{WEEKDAYS[day.weekday()]}"
    return f"{prefix} · {day.month}月{day.day}日"
