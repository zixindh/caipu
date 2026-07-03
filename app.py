from __future__ import annotations

import os
from datetime import datetime
from html import escape

import streamlit as st

from caipu.dates import day_label, full_day_label, rolling_days, today_in_china
from caipu.groceries import grocery_items
from caipu.models import MEAL_SLOTS, Meal
from caipu.storage import NotionMealRepository, StorageError, empty_week

st.set_page_config(
    page_title="七日食谱",
    page_icon="🍲",
    layout="wide",
    initial_sidebar_state="collapsed",
)

USERS = ("Eva", "Heng", "强尼")


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
    config_key = (token, data_source_id, parent_page_id)
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
          max-width: 1080px;
          padding-top: 2rem;
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
        .meal-heading {
          display:flex; align-items:center; justify-content:space-between;
          border-top: 1px solid var(--line); padding-top: 1.5rem;
          margin-top: .5rem;
        }
        .meal-heading strong { font-size: 1.18rem; }
        .meal-heading span { color: var(--muted); font-size: .84rem; }
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
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea {
          border-radius: 12px; border-color: var(--line); background: white;
        }
        .status-ready { color: var(--accent); font-weight: 650; }
        .grocery-row {
          display:flex; justify-content:space-between; align-items:center;
          padding: .85rem .1rem; border-bottom: 1px solid var(--line);
        }
        .grocery-row b { font-weight: 620; }
        .grocery-row span { color: var(--muted); font-size: .86rem; }
        @media (max-width: 640px) {
          [data-testid="stMainBlockContainer"] { padding-top: 1.1rem; }
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
    st.session_state.loaded_at = datetime.now().strftime("%H:%M")


def _meal_editor(repo: NotionMealRepository, meal: Meal, user: str) -> None:
    status = "已备齐" if meal.stocked else "待准备"
    status_class = "status-ready" if meal.stocked else ""
    st.markdown(
        f'<div class="meal-heading"><strong>{meal.slot.value}</strong>'
        f'<span class="{status_class}">{status}</span></div>',
        unsafe_allow_html=True,
    )
    with st.form(f"meal-{meal.key}", border=False):
        dish = st.text_input(
            "想吃什么",
            value=meal.dish,
            placeholder="例如：番茄炒蛋",
            key=f"dish-{meal.key}",
        )
        ingredients = st.text_area(
            "需要的食材",
            value=meal.ingredients,
            placeholder="番茄 2个、鸡蛋 3个、葱",
            height=88,
            key=f"ingredients-{meal.key}",
            help="用逗号或换行分隔，采购清单会自动汇总。",
        )
        left, right = st.columns([1, 1])
        with left:
            suggested_by = st.selectbox(
                "谁的主意",
                USERS,
                index=USERS.index(meal.suggested_by)
                if meal.suggested_by in USERS
                else USERS.index(user),
                key=f"suggested-{meal.key}",
            )
        with right:
            stocked = st.toggle(
                "食材已购买或冰箱已有",
                value=meal.stocked,
                key=f"stocked-{meal.key}",
            )
        note = st.text_input(
            "备注（可选）",
            value=meal.note,
            placeholder="例如：少辣、提前解冻",
            key=f"note-{meal.key}",
        )
        saved = st.form_submit_button("保存这一餐", type="primary")
    if saved:
        updated = Meal(
            day=meal.day,
            slot=meal.slot,
            dish=dish.strip(),
            ingredients=ingredients.strip(),
            stocked=stocked,
            suggested_by=suggested_by,
            note=note.strip(),
            page_id=meal.page_id,
            last_edited_time=meal.last_edited_time,
        )
        try:
            with st.spinner("正在保存…"):
                updated = repo.save(updated, user)
            st.session_state.meals[updated.key] = updated
            st.toast(f"{meal.slot.value}已保存", icon="✓")
            st.rerun()
        except StorageError as exc:
            st.error(str(exc))


def _menu_view(repo: NotionMealRepository, start, user: str) -> None:
    days = rolling_days(start)
    labels = {day_label(day, start): day for day in days}
    selected_label = st.segmented_control(
        "选择日期",
        list(labels),
        default=list(labels)[0],
        selection_mode="single",
        label_visibility="collapsed",
        # A date-specific key resets the selector to the new "today" after midnight.
        key=f"selected-day-label-{start.isoformat()}",
    )
    selected_day = labels[selected_label]
    st.subheader(full_day_label(selected_day, start))

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
    for slot in MEAL_SLOTS:
        _meal_editor(repo, meals[f"{selected_day.isoformat()}:{slot.value}"], user)


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
                st.toast("已获取最新餐单", icon="✓")
                st.rerun()
            except StorageError as exc:
                st.error(str(exc))
        if b.button(user, width="stretch", help="点击退出"):
            st.session_state.clear()
            st.rerun()

    section = st.segmented_control(
        "页面",
        ("餐单", "采购清单"),
        default="餐单",
        selection_mode="single",
        label_visibility="collapsed",
        key="main-section",
    )
    st.write("")
    if section == "餐单":
        _menu_view(repo, today, user)
    else:
        _grocery_view()


if __name__ == "__main__":
    main()
