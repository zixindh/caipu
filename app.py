from __future__ import annotations

import os
from datetime import datetime, timedelta
from hashlib import sha256
from html import escape

import streamlit as st

from caipu.dates import APP_TIMEZONE, full_day_label, rolling_days, today_in_china
from caipu.groceries import grocery_items
from caipu.history import group_history
from caipu.menu_table import build_menu_rows, changed_meals, records_from_editor
from caipu.models import MEAL_SLOTS
from caipu.storage import NotionMealRepository, StorageError, empty_week

st.set_page_config(
    page_title="七日食谱",
    page_icon="🍲",
    layout="wide",
    initial_sidebar_state="collapsed",
)

USERS = ("Eva", "Heng", "强尼")
USER_STYLES = {
    "Eva": {"dot": "🟣", "color": "#8B5CF6", "soft": "#F3EEFF"},
    "Heng": {"dot": "🔵", "color": "#2F6FED", "soft": "#EDF3FF"},
    "强尼": {"dot": "🟠", "color": "#D97706", "soft": "#FFF3E5"},
}


def _secret_section(name: str) -> dict:
    try:
        section = st.secrets.get(name, {})
        return dict(section)
    except FileNotFoundError:
        return {}


def _repository() -> NotionMealRepository | None:
    notion = _secret_section("notion")
    token = (
        os.getenv("NOTION_TOKEN")
        or os.getenv("NOTION_API_KEY")
        or str(notion.get("token", ""))
    ).strip()
    data_source_id = (
        os.getenv("NOTION_DATA_SOURCE_ID") or str(notion.get("data_source_id", ""))
    ).strip() or None
    parent_page_id = (
        os.getenv("NOTION_PAGE_ID") or str(notion.get("parent_page_id", ""))
    ).strip() or None
    if not token or not (data_source_id or parent_page_id):
        return None
    token_fingerprint = sha256(token.encode("utf-8")).hexdigest()
    config_key = (token_fingerprint, data_source_id, parent_page_id)
    if st.session_state.get("_repository_config") != config_key:
        st.session_state._repository = NotionMealRepository(
            token, data_source_id, parent_page_id
        )
        st.session_state._repository_config = config_key
    return st.session_state._repository


def _inject_style() -> None:
    st.markdown(
        """
        <style>
        :root {
          --ink: #17201b;
          --muted: #677169;
          --line: #e6e9e5;
          --paper: #fbfcfa;
          --accent: #176b45;
          --soft: #edf5f0;
        }
        .stApp { background: var(--paper); color: var(--ink); }
        [data-testid="stHeader"] { background: rgba(251,252,250,.88); }
        [data-testid="stMainBlockContainer"] {
          max-width: 1280px;
          padding-top: 4.75rem;
          padding-bottom: 5rem;
        }
        #MainMenu, footer { visibility: hidden; }
        h1, h2, h3, p, label, button, input, textarea {
          font-family: -apple-system, BlinkMacSystemFont, "PingFang SC",
            "Microsoft YaHei", "Noto Sans CJK SC", sans-serif !important;
        }
        h1 { letter-spacing: -.04em; font-weight: 720 !important; }
        .brand {
          font-size: .82rem; letter-spacing: .12em; color: var(--accent);
          font-weight: 750; margin-bottom: .45rem;
        }
        .subtle { color: var(--muted); font-size: .92rem; }
        .people-legend {
          display:flex; gap:.55rem; flex-wrap:wrap; margin:.5rem 0 1rem;
        }
        .person-badge {
          display:inline-flex; align-items:center; gap:.38rem;
          padding:.28rem .62rem; border-radius:999px;
          font-size:.8rem; font-weight:650;
        }
        div[data-testid="stForm"] {
          border: 0; padding: 0 0 1.1rem 0; background: transparent;
        }
        div[data-baseweb="segmented-control"] {
          background: #f0f2ef; border-radius: 14px; padding: 4px;
        }
        .stButton > button, .stFormSubmitButton > button {
          min-height: 2.8rem; border-radius: 999px; font-weight: 650;
          border-color: var(--line);
        }
        .stFormSubmitButton > button[kind="primary"],
        .stButton > button[kind="primary"] {
          background: var(--accent); color: white; border: 0;
        }
        .grocery-row {
          display:flex; justify-content:space-between; align-items:center;
          padding: .85rem .1rem; border-bottom: 1px solid var(--line);
        }
        .grocery-row b { font-weight: 620; }
        .grocery-row span { color: var(--muted); font-size: .86rem; }
        .history-meal {
          padding: .85rem .1rem; border-bottom: 1px solid var(--line);
        }
        .history-meal:last-child { border-bottom: 0; }
        .history-meal strong { font-size: 1rem; font-weight: 650; }
        .history-meal p {
          margin: .28rem 0 0; color: var(--muted); font-size: .88rem;
          line-height: 1.55;
        }
        @media (max-width: 640px) {
          [data-testid="stMainBlockContainer"] { padding-top: 4.25rem; }
          h1 { font-size: 2rem !important; }
          .stButton > button { padding-left: .85rem; padding-right: .85rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _login() -> bool:
    if st.session_state.get("user"):
        return True

    st.markdown('<div class="brand">CAIPU · 七日食谱</div>', unsafe_allow_html=True)
    st.title("一起决定，这周吃什么")
    st.markdown(
        '<p class="subtle">选择你的名字，进入共享餐单。</p>',
        unsafe_allow_html=True,
    )

    with st.form("login", border=False):
        selected = st.segmented_control(
            "你是谁？",
            USERS,
            default=USERS[0],
            selection_mode="single",
        )
        submitted = st.form_submit_button("进入餐单", type="primary", width="stretch")
    if submitted:
        st.session_state.user = selected
        st.rerun()
    return False


def _load_meals(repo: NotionMealRepository, start, force: bool = False) -> None:
    if (
        not force
        and st.session_state.get("week_start") == start.isoformat()
        and "meals" in st.session_state
    ):
        return
    end = rolling_days(start)[-1]
    remote = repo.load_week(start, end)
    meals = empty_week(start)
    meals.update(remote)
    st.session_state.meals = meals
    st.session_state.week_start = start.isoformat()
    st.session_state.loaded_at = datetime.now(APP_TIMEZONE).strftime("%H:%M")


def _load_history(
    repo: NotionMealRepository, today, days: int, force: bool = False
) -> None:
    range_key = f"{today.isoformat()}:{days}"
    if (
        not force
        and st.session_state.get("history_range") == range_key
        and "history_meals" in st.session_state
    ):
        return
    start = today - timedelta(days=days)
    end = today - timedelta(days=1)
    st.session_state.history_meals = repo.load_week(start, end)
    st.session_state.history_range = range_key


def _menu_view(repo: NotionMealRepository, start, user: str) -> None:
    days = rolling_days(start)
    meals = st.session_state.meals
    planned = sum(
        not meals[f"{day.isoformat()}:{slot.value}"].is_empty
        for day in days
        for slot in MEAL_SLOTS
    )
    st.markdown(
        f'<p class="subtle">未来 7 天已安排 {planned}/21 餐 · '
        f"上次同步 {st.session_state.get('loaded_at', '刚刚')}</p>",
        unsafe_allow_html=True,
    )
    st.caption("直接填写菜品和食材，勾选备齐。修改会自动记在当前登录者名下。")
    legend = "".join(
        f'<span class="person-badge" style="color:{style["color"]};'
        f'background:{style["soft"]}">{style["dot"]} {name}</span>'
        for name, style in USER_STYLES.items()
    )
    st.markdown(f'<div class="people-legend">{legend}</div>', unsafe_allow_html=True)

    labels = {day: full_day_label(day, start) for day in days}
    person_labels = {
        name: f"{style['dot']} {name}" for name, style in USER_STYLES.items()
    }
    rows = build_menu_rows(meals, days, labels, person_labels)
    table_version = st.session_state.get("menu_table_version", 0)
    edited = st.data_editor(
        rows,
        width="stretch",
        height="content",
        hide_index=True,
        column_order=("日期", "餐次", "菜品", "食材", "已备齐", "提议", "备注"),
        column_config={
            "日期": st.column_config.TextColumn("日期", width=180, disabled=True),
            "餐次": st.column_config.TextColumn("餐次", width="small", disabled=True),
            "菜品": st.column_config.TextColumn(
                "想吃什么", width="medium", max_chars=200
            ),
            "食材": st.column_config.TextColumn(
                "需要的食材",
                width="large",
                help="用逗号分隔，采购清单会自动汇总。",
                max_chars=1000,
            ),
            "已备齐": st.column_config.CheckboxColumn(
                "已备齐",
                width="small",
                help="食材已购买或冰箱已有",
            ),
            "提议": st.column_config.TextColumn(
                "提议",
                width="small",
                help="根据最后修改者自动标记",
                disabled=True,
            ),
            "备注": st.column_config.TextColumn("备注", width="medium", max_chars=300),
        },
        num_rows="fixed",
        disabled=("日期", "餐次", "提议"),
        key=f"menu-table-{start.isoformat()}-{table_version}",
    )
    changes = changed_meals(records_from_editor(edited), meals, user)
    button_label = f"保存 {len(changes)} 处修改" if changes else "没有需要保存的修改"
    if st.button(
        button_label,
        type="primary",
        width="stretch",
        disabled=not changes,
        key="save-menu-table",
    ):
        saved_count = 0
        try:
            with st.spinner("正在保存修改…"):
                for meal in changes:
                    saved = repo.save(meal, user)
                    st.session_state.meals[saved.key] = saved
                    saved_count += 1
            st.session_state.menu_table_version = table_version + 1
            st.session_state.pop("history_range", None)
            st.toast(f"已保存 {saved_count} 处修改", icon="✓")
            st.rerun()
        except StorageError as exc:
            st.error(f"已保存 {saved_count} 处；其余修改未保存。{exc}")


def _grocery_view() -> None:
    meals = list(st.session_state.meals.values())
    items = grocery_items(meals)
    pending_meals = sum(
        bool(meal.ingredients.strip()) and not meal.stocked for meal in meals
    )
    st.subheader("采购清单")
    st.markdown(
        f'<p class="subtle">来自 {pending_meals} 个尚未备齐的餐次。'
        "完成采购后，请回到对应餐次打开“已备齐”。</p>",
        unsafe_allow_html=True,
    )
    if not items:
        st.success("需要采购的食材都处理好了。")
        return
    for item, count in items:
        source = f"{count} 个餐次需要" if count > 1 else "1 个餐次需要"
        st.markdown(
            f'<div class="grocery-row"><b>{escape(item)}</b>'
            f"<span>{source}</span></div>",
            unsafe_allow_html=True,
        )


def _history_view(repo: NotionMealRepository, today) -> None:
    days = st.session_state.get("history_days", 30)
    st.subheader("往期灵感")
    st.markdown(
        f'<p class="subtle">最近 {days} 天 · 只显示填写过的餐次，旧菜单不会被修改。</p>',
        unsafe_allow_html=True,
    )

    try:
        with st.spinner("正在翻找往期菜单…"):
            _load_history(repo, today, days)
    except StorageError as exc:
        st.error(str(exc))
        return

    grouped = group_history(st.session_state.history_meals.values())
    if not grouped:
        st.info("还没有往期菜单。使用几天后，这里会自动积累灵感。")
    else:
        for index, (day, meals) in enumerate(grouped):
            label = f"{full_day_label(day, today)} · {len(meals)} 餐"
            with st.expander(label, expanded=index == 0):
                for meal in meals:
                    dish = escape(meal.dish or "未命名菜品")
                    details = []
                    if meal.ingredients:
                        ingredients = escape(meal.ingredients).replace("\n", "、")
                        details.append(f"食材：{ingredients}")
                    if meal.suggested_by:
                        person = USER_STYLES.get(meal.suggested_by, {})
                        dot = person.get("dot", "●")
                        details.append(f"提议：{dot} {escape(meal.suggested_by)}")
                    if meal.note:
                        details.append(f"备注：{escape(meal.note)}")
                    detail_html = " · ".join(details) or "没有补充信息"
                    st.markdown(
                        f'<div class="history-meal"><strong>'
                        f"{meal.slot.value} · {dish}</strong>"
                        f"<p>{detail_html}</p></div>",
                        unsafe_allow_html=True,
                    )

    if st.button("再看前 30 天", width="stretch"):
        st.session_state.history_days = days + 30
        st.rerun()


def main() -> None:
    _inject_style()
    if not _login():
        return

    repo = _repository()
    if repo is None:
        st.error("应用尚未连接 Notion。请设置 NOTION_TOKEN 和 NOTION_PAGE_ID。")
        return

    user = st.session_state.user
    today = today_in_china()
    try:
        with st.spinner("正在打开共享餐单…"):
            _load_meals(repo, today)
    except (StorageError, ValueError) as exc:
        st.error(str(exc))
        st.info("请检查 NOTION_TOKEN 和 NOTION_PAGE_ID，然后重新启动应用。")
        return

    top_left, top_right = st.columns([5, 2], vertical_alignment="bottom")
    with top_left:
        st.markdown('<div class="brand">CAIPU · 七日食谱</div>', unsafe_allow_html=True)
        st.title("未来七天，吃得明白")
    with top_right:
        a, b = st.columns(2)
        if a.button("刷新", width="stretch", help="从 Notion 获取家人的最新修改"):
            try:
                with st.spinner("正在同步…"):
                    _load_meals(repo, today, force=True)
                    st.session_state.pop("history_range", None)
                st.toast("已获取最新餐单", icon="✓")
                st.rerun()
            except StorageError as exc:
                st.error(str(exc))
        user_dot = USER_STYLES[user]["dot"]
        if b.button(f"{user_dot} {user}", width="stretch", help="点击退出"):
            st.session_state.clear()
            st.rerun()

    section = st.segmented_control(
        "页面",
        ("本周餐单", "往期灵感", "采购清单"),
        default="本周餐单",
        selection_mode="single",
        label_visibility="collapsed",
        key="main-section",
    )
    st.write("")
    if section == "本周餐单":
        _menu_view(repo, today, user)
    elif section == "往期灵感":
        _history_view(repo, today)
    else:
        _grocery_view()


if __name__ == "__main__":
    main()
