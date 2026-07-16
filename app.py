from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html import escape

import streamlit as st

from caipu.dates import (
    DEFAULT_VISIBLE_DAYS,
    MAX_VISIBLE_DAYS,
    day_label,
    full_day_label,
    rolling_days,
    today_in_china,
)
from caipu.groceries import grocery_items
from caipu.history import group_history
from caipu.menu_table import (
    build_menu_rows,
    changed_meals,
    ordered_meal,
    records_from_editor,
)
from caipu.models import LearnedDish, MealSlot
from caipu.storage import NotionMealRepository, StorageError, empty_week

st.set_page_config(
    page_title="我们的餐桌",
    page_icon="💗",
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
          --ink: #3b2b31;
          --muted: #806d74;
          --line: #f0dfe3;
          --paper: #fffaf9;
          --accent: #ed5a48;
          --accent-deep: #cf4436;
          --soft: #fff0ed;
        }
        .stApp { background: var(--paper); color: var(--ink); }
        [data-testid="stHeader"] { background: rgba(255,250,249,.9); }
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
        .brand-heart {
          display:inline-block; margin-right:.3rem; color:var(--accent);
          animation: heart-in .45s ease-out both;
        }
        .subtle { color: var(--muted); font-size: .92rem; }
        .login-note {
          color: var(--muted); font-size: .82rem; margin:.65rem 0 1rem;
        }
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
        div[data-testid="stDataFrame"] { font-size: .82rem; }
        .stButton > button, .stFormSubmitButton > button {
          min-height: 2.8rem; border-radius: 999px; font-weight: 650;
          border-color: var(--line); transition: transform .16s ease,
          background-color .16s ease, box-shadow .16s ease;
        }
        .stButton > button:hover { transform: translateY(-1px); }
        .stFormSubmitButton > button[kind="primary"],
        .stButton > button[kind="primary"] {
          background: var(--accent); color: white; border: 0;
        }
        .stFormSubmitButton > button[kind="primary"]:hover,
        .stButton > button[kind="primary"]:hover {
          background: var(--accent-deep); color: white;
        }
        @keyframes heart-in {
          from { opacity:0; transform:translateY(3px) scale(.8); }
          to { opacity:1; transform:translateY(0) scale(1); }
        }
        div[data-testid="stImage"] img {
          border-radius: 18px; aspect-ratio: 4 / 3; object-fit: cover;
          animation: dish-in .28s ease-out both;
        }
        .dish-preview-copy { padding:.15rem 0; }
        .dish-preview-copy strong {
          display:block; font-size:1.15rem; line-height:1.35; margin-bottom:.45rem;
        }
        .dish-preview-copy p {
          color:var(--muted); font-size:.88rem; line-height:1.5; margin:0;
          display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical;
          overflow:hidden;
        }
        .st-key-learned-dish-preview div[data-testid="stImage"] img {
          aspect-ratio:1 / 1; max-height:220px;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
          border-radius: 22px; overflow: hidden;
          transition: transform .18s ease, box-shadow .18s ease;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
          transform: translateY(-2px);
          box-shadow: 0 12px 30px rgba(96, 45, 39, .08);
        }
        @keyframes dish-in {
          from { opacity: 0; transform: translateY(5px); }
          to { opacity: 1; transform: translateY(0); }
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
          [data-testid="stMainBlockContainer"] {
            padding:3.35rem .8rem 2.5rem;
          }
          h1 { font-size:1.55rem !important; line-height:1.18 !important; }
          h2 { font-size:1.3rem !important; }
          h3 { font-size:1.08rem !important; }
          .brand { margin-bottom:.2rem; }
          .subtle { font-size:.84rem; }
          .people-legend { gap:.35rem; margin:.25rem 0 .6rem; }
          .person-badge { padding:.2rem .48rem; font-size:.74rem; }
          .stButton > button, .stFormSubmitButton > button {
            min-height:2.55rem; padding-left:.72rem; padding-right:.72rem;
          }
          .st-key-learned-dish-browser [data-testid="stVerticalBlock"] {
            gap:.65rem;
          }
          .st-key-learned-dish-preview [data-testid="stHorizontalBlock"] {
            gap:.65rem;
          }
          .st-key-learned-dish-preview [data-testid="stColumn"] {
            min-width:0;
          }
          .st-key-learned-dish-preview div[data-testid="stImage"] img {
            border-radius:14px; max-height:145px;
          }
          .dish-preview-copy strong { font-size:1rem; margin-bottom:.25rem; }
          .dish-preview-copy p {
            font-size:.8rem; line-height:1.4; -webkit-line-clamp:3;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _login() -> bool:
    if st.session_state.get("user"):
        return True

    st.markdown(
        '<div class="brand"><span class="brand-heart">♥</span>我们的餐桌</div>',
        unsafe_allow_html=True,
    )
    st.title("今天是谁来写菜单？")
    st.markdown(
        '<p class="subtle">为喜欢的人，认真安排每一顿饭。</p>'
        '<p class="login-note">点一下名字，直接进入</p>',
        unsafe_allow_html=True,
    )

    columns = st.columns(len(USERS))
    for column, user in zip(columns, USERS, strict=True):
        style = USER_STYLES[user]
        if column.button(
            f"{style['dot']} {user}",
            key=f"login-{user}",
            type="primary",
            width="stretch",
        ):
            st.session_state.user = user
            st.rerun()
    return False


def _load_meals(
    repo: NotionMealRepository,
    start,
    day_count: int = DEFAULT_VISIBLE_DAYS,
    force: bool = False,
) -> None:
    range_key = f"{start.isoformat()}:{day_count}"
    if (
        not force
        and st.session_state.get("meal_range") == range_key
        and "meals" in st.session_state
    ):
        return
    end = rolling_days(start, day_count)[-1]
    remote = repo.load_week(start, end)
    meals = empty_week(start, day_count)
    meals.update(remote)
    st.session_state.meals = meals
    st.session_state.meal_range = range_key


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


def _load_learned_dishes(
    repo: NotionMealRepository, force: bool = False
) -> list[LearnedDish]:
    loaded_at = st.session_state.get("learned_dishes_loaded_at")
    stale = not isinstance(loaded_at, datetime) or (
        datetime.now(timezone.utc) - loaded_at >= timedelta(minutes=50)
    )
    if force or stale or "learned_dishes" not in st.session_state:
        st.session_state.learned_dishes = repo.load_learned_dishes()
        st.session_state.learned_dishes_loaded_at = datetime.now(timezone.utc)
    return st.session_state.learned_dishes


@st.dialog("点这道菜")
def _order_learned_dish(
    repo: NotionMealRepository,
    user: str,
    dish: LearnedDish,
    start,
    day_count: int,
) -> None:
    if dish.image_url:
        st.image(dish.image_url, width=220)
    st.subheader(dish.name)
    if dish.ingredients:
        st.caption(f"常用食材：{dish.ingredients}")

    days = rolling_days(start, day_count)
    selected_day = st.selectbox(
        "哪天吃",
        days,
        format_func=lambda day: day_label(day, start),
    )
    slot_name = st.segmented_control(
        "安排在哪一餐",
        tuple(slot.value for slot in MealSlot),
        default=MealSlot.DINNER.value,
        selection_mode="single",
    )
    if slot_name is None:
        return
    slot = MealSlot(slot_name)
    original = st.session_state.meals[f"{selected_day.isoformat()}:{slot.value}"]
    if original.dish.strip() and original.dish.strip() != dish.name:
        st.warning(f"这里已经有“{original.dish}”，确认后会替换。")

    if st.button("确认放进餐单", type="primary", width="stretch"):
        meal = ordered_meal(original, dish, user)
        try:
            with st.spinner("正在安排…"):
                saved = repo.save(meal, user)
                st.session_state.meals[saved.key] = saved
                st.session_state.menu_table_version = (
                    st.session_state.get("menu_table_version", 0) + 1
                )
                st.session_state.pop("history_range", None)
            st.toast("已经放进餐单", icon="✅")
            st.rerun()
        except StorageError as exc:
            st.error(str(exc))


@st.dialog("编辑这道菜")
def _edit_learned_dish(
    repo: NotionMealRepository,
    user: str,
    dish: LearnedDish,
) -> None:
    if dish.image_url:
        st.image(dish.image_url, width=140)

    with st.form(f"edit-learned-dish-{dish.page_id}"):
        name = st.text_input("菜名", value=dish.name, max_chars=200)
        ingredients = st.text_input(
            "常用食材（可选）",
            value=dish.ingredients,
            max_chars=1000,
            placeholder="例如：番茄、鸡蛋、葱",
        )
        photo = st.file_uploader(
            "更换照片（可选）",
            type=("jpg", "jpeg", "png", "webp"),
            accept_multiple_files=False,
            help="不选择就保留现在的照片；最大 5 MB。",
        )
        submitted = st.form_submit_button(
            "保存修改", type="primary", width="stretch"
        )

    if not submitted:
        return

    try:
        with st.spinner("正在保存修改…"):
            repo.update_learned_dish(
                dish,
                name=name,
                ingredients=ingredients,
                editor=user,
                image_bytes=photo.getvalue() if photo is not None else None,
                filename=photo.name if photo is not None else "",
                content_type=(photo.type or "") if photo is not None else "",
            )
            _load_learned_dishes(repo, force=True)
        st.toast("菜品已更新", icon="✅")
        st.rerun()
    except (StorageError, ValueError) as exc:
        st.error(str(exc))


def _menu_view(
    repo: NotionMealRepository,
    start,
    user: str,
    learned_dishes: list[LearnedDish],
    day_count: int,
) -> None:
    control, _ = st.columns([1, 4], vertical_alignment="bottom")
    with control:
        selected_day_count = st.selectbox(
            "显示天数",
            options=tuple(range(1, MAX_VISIBLE_DAYS + 1)),
            index=day_count - 1,
            format_func=lambda value: f"{value} 天",
            key="visible-days-control",
        )
    if selected_day_count != day_count:
        st.session_state.visible_days = selected_day_count
        st.rerun()

    days = rolling_days(start, day_count)
    meals = st.session_state.meals
    legend = "".join(
        f'<span class="person-badge" style="color:{style["color"]};'
        f'background:{style["soft"]}">{style["dot"]} {name}</span>'
        for name, style in USER_STYLES.items()
    )
    st.markdown(f'<div class="people-legend">{legend}</div>', unsafe_allow_html=True)

    labels = {day: day_label(day, start) for day in days}
    person_labels = {
        name: f"{style['dot']} {name}" for name, style in USER_STYLES.items()
    }
    learned_ingredients = {
        dish.name: dish.ingredients for dish in learned_dishes
    }
    learned_names = list(learned_ingredients)
    rows = build_menu_rows(
        meals, days, labels, person_labels, learned_dish_names=learned_names
    )
    table_version = st.session_state.get("menu_table_version", 0)
    column_order = (
        "日期",
        "餐次",
        *(("已学会",) if learned_names else ()),
        "菜品",
        "食材",
        "已备齐",
        "提议",
        "备注",
    )
    column_config = {
        "日期": st.column_config.TextColumn("日期", width=None, disabled=True),
        "餐次": st.column_config.TextColumn("餐次", width=58, disabled=True),
        "菜品": st.column_config.TextColumn("想吃什么", width=110, max_chars=200),
        "食材": st.column_config.TextColumn(
            "需要的食材",
            width=160,
            help="用逗号分隔，采购清单会自动汇总。",
            max_chars=1000,
        ),
        "已备齐": st.column_config.CheckboxColumn(
            "已备齐",
            width=70,
            help="食材已购买或冰箱已有",
        ),
        "提议": st.column_config.TextColumn(
            "提议",
            width="small",
            help="根据最后修改者自动标记",
            disabled=True,
        ),
        "备注": st.column_config.TextColumn("备注", width="medium", max_chars=300),
    }
    if learned_names:
        column_config["已学会"] = st.column_config.SelectboxColumn(
            "已学会的菜",
            options=[""] + learned_names,
            width=105,
            help="从上传过照片的菜里选择",
        )
    edited = st.data_editor(
        rows,
        width="stretch",
        height="content",
        row_height=68,
        hide_index=True,
        column_order=column_order,
        column_config=column_config,
        num_rows="fixed",
        disabled=("日期", "餐次", "提议"),
        key=f"menu-table-{start.isoformat()}-{day_count}-{table_version}",
    )
    changes = changed_meals(
        records_from_editor(edited),
        meals,
        user,
        learned_ingredients=learned_ingredients,
    )
    if changes:
        saved_count = 0
        try:
            with st.spinner("正在自动保存…"):
                for meal in changes:
                    saved = repo.save(meal, user)
                    st.session_state.meals[saved.key] = saved
                    saved_count += 1
            st.session_state.menu_table_version = table_version + 1
            st.session_state.pop("history_range", None)
            st.toast("已自动保存", icon="✅")
            st.rerun()
        except StorageError as exc:
            st.error(
                f"自动保存失败。已完成 {saved_count} 处，未保存的内容仍留在表格中。"
                f"{exc}"
            )


def _learned_dishes_view(
    repo: NotionMealRepository,
    user: str,
    dishes: list[LearnedDish],
    start,
    day_count: int,
) -> None:
    st.subheader("已学会的菜")

    with st.container(key="learned-dish-browser", width=680):
        if dishes:
            dishes_by_key = {
                dish.page_id or f"legacy-dish-{index}": dish
                for index, dish in enumerate(dishes)
            }
            selected_key = st.selectbox(
                "选择菜品",
                options=tuple(dishes_by_key),
                format_func=lambda key: dishes_by_key[key].name,
                key="learned-dish-picker",
            )
            selected_dish = dishes_by_key[selected_key]
            with st.container(key="learned-dish-preview", border=True):
                photo_column, copy_column = st.columns(
                    [1, 1.45], vertical_alignment="center", gap="small"
                )
                with photo_column:
                    if selected_dish.image_url:
                        st.image(selected_dish.image_url, width=220)
                    else:
                        st.markdown("### 🍲")
                with copy_column:
                    ingredient_copy = escape(
                        selected_dish.ingredients or "还没有填写常用食材"
                    )
                    st.markdown(
                        '<div class="dish-preview-copy">'
                        f"<strong>{escape(selected_dish.name)}</strong>"
                        f"<p>{ingredient_copy}</p></div>",
                        unsafe_allow_html=True,
                    )

                order_column, edit_column = st.columns(2, gap="small")
                if order_column.button(
                    "点这道菜",
                    key=f"order-learned-dish-{selected_key}",
                    type="primary",
                    width="stretch",
                ):
                    _order_learned_dish(
                        repo, user, selected_dish, start, day_count
                    )
                if edit_column.button(
                    "编辑",
                    key=f"edit-learned-dish-{selected_key}",
                    width="stretch",
                ):
                    _edit_learned_dish(repo, user, selected_dish)

        with st.expander("＋ 添加一道菜", expanded=not dishes):
            with st.form("learned-dish-form", clear_on_submit=True):
                name = st.text_input(
                    "菜名", max_chars=200, placeholder="例如：番茄炒蛋"
                )
                ingredients = st.text_input(
                    "常用食材（可选）",
                    max_chars=1000,
                    placeholder="例如：番茄、鸡蛋、葱",
                )
                photo = st.file_uploader(
                    "菜品照片",
                    type=("jpg", "jpeg", "png", "webp"),
                    accept_multiple_files=False,
                    help="支持 JPG、PNG、WebP，最大 5 MB。",
                )
                submitted = st.form_submit_button(
                    "加入已学会的菜", type="primary", width="stretch"
                )
            if submitted:
                if photo is None:
                    st.error("请选择一张菜品照片。")
                else:
                    try:
                        with st.spinner("正在保存这道菜…"):
                            repo.save_learned_dish(
                                name=name,
                                ingredients=ingredients,
                                image_bytes=photo.getvalue(),
                                filename=photo.name,
                                content_type=photo.type or "",
                                editor=user,
                            )
                            _load_learned_dishes(repo, force=True)
                        st.toast("已加入已学会的菜", icon="✅")
                        st.rerun()
                    except (StorageError, ValueError) as exc:
                        st.error(str(exc))


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
    day_count = max(
        1,
        min(
            MAX_VISIBLE_DAYS,
            int(st.session_state.get("visible_days", DEFAULT_VISIBLE_DAYS)),
        ),
    )
    try:
        with st.spinner("正在打开共享餐单…"):
            _load_meals(repo, today, day_count)
    except (StorageError, ValueError) as exc:
        st.error(str(exc))
        st.info("请检查 NOTION_TOKEN 和 NOTION_PAGE_ID，然后重新启动应用。")
        return

    learned_dishes_error = ""
    try:
        learned_dishes = _load_learned_dishes(repo)
    except StorageError as exc:
        learned_dishes = []
        learned_dishes_error = str(exc)

    top_left, top_right = st.columns([5, 2], vertical_alignment="bottom")
    with top_left:
        st.markdown(
            '<div class="brand"><span class="brand-heart">♥</span>我们的餐桌</div>',
            unsafe_allow_html=True,
        )
        st.title("接下来几天，一起好好吃饭")
    with top_right:
        a, b = st.columns(2)
        if a.button("刷新", width="stretch", help="从 Notion 获取家人的最新修改"):
            try:
                with st.spinner("正在同步…"):
                    _load_meals(repo, today, day_count, force=True)
                    _load_learned_dishes(repo, force=True)
                    st.session_state.pop("history_range", None)
                st.toast("已获取最新餐单", icon="✅")
                st.rerun()
            except StorageError as exc:
                st.error(str(exc))
        user_dot = USER_STYLES[user]["dot"]
        if b.button(f"{user_dot} {user}", width="stretch", help="点击退出"):
            st.session_state.clear()
            st.rerun()

    section = st.segmented_control(
        "页面",
        ("餐单", "已学会的菜", "往期", "采购"),
        default="餐单",
        selection_mode="single",
        label_visibility="collapsed",
        key="main-section",
    )
    st.write("")
    if learned_dishes_error:
        st.warning(f"“已学会的菜”暂时无法读取：{learned_dishes_error}")
    if section == "餐单":
        _menu_view(repo, today, user, learned_dishes, day_count)
    elif section == "已学会的菜":
        _learned_dishes_view(repo, user, learned_dishes, today, day_count)
    elif section == "往期":
        _history_view(repo, today)
    else:
        _grocery_view()


if __name__ == "__main__":
    main()
