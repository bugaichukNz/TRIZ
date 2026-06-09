"""Streamlit-интерфейс TRIZ AI-ассистента."""

import html
import os
from datetime import datetime

import requests
import streamlit as st

from chat_client import (
    CHAT_OPENING_MESSAGE,
    analyze_chat_session,
    complete_chat_session,
    create_chat_session,
    delete_all_chat_sessions,
    delete_chat_session,
    get_chat_session,
    list_chat_sessions,
    send_chat_message,
)
from history_client import clear_history_api, fetch_history, fetch_history_entry
from state_client import fetch_active_chat, save_active_chat
from report_builder import build_report_html
from theme import inject_theme

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
SOLVE_ENDPOINT = "/solve"
HEALTH_ENDPOINT = "/health"
HISTORY_LIMIT = int(os.getenv("HISTORY_MAX_ENTRIES", "20"))
CHAT_LIST_LIMIT = int(os.getenv("CHAT_SESSIONS_MAX", "50"))
MIN_PROBLEM_LENGTH = 3
MAX_PROBLEM_LENGTH = 4000

st.set_page_config(
    page_title="TRIZ AI-Ассистент",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get help": None,
        "Report a bug": None,
        "About": None,
    },
)

inject_theme()

if "history" not in st.session_state:
    st.session_state.history = []
if "db_menu_error" not in st.session_state:
    st.session_state.db_menu_error = None
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_problem" not in st.session_state:
    st.session_state.last_problem = ""
if "report_html" not in st.session_state:
    st.session_state.report_html = None
if "report_docx" not in st.session_state:
    st.session_state.report_docx = None
if "view" not in st.session_state:
    st.session_state.view = "home"
if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "chat_status" not in st.session_state:
    st.session_state.chat_status = None
if "chat_sessions" not in st.session_state:
    st.session_state.chat_sessions = []
if "active_chat_restored" not in st.session_state:
    st.session_state.active_chat_restored = False
if "menu_loaded" not in st.session_state:
    st.session_state.menu_loaded = False


def _backend_base() -> str:
    return st.session_state.get("backend_url", BACKEND_URL).rstrip("/")


def reload_menu_from_db() -> bool:
    """Загружает диалоги и отчёты из SQLite (через API)."""
    base = _backend_base()
    try:
        st.session_state.chat_sessions = list_chat_sessions(
            base, limit=CHAT_LIST_LIMIT
        )
        st.session_state.history = fetch_history(base, limit=HISTORY_LIMIT)
        st.session_state.db_menu_error = None
        st.session_state.menu_loaded = True
        return True
    except requests.RequestException as exc:
        st.session_state.db_menu_error = (
            f"Не удалось загрузить меню из БД: {exc}"
        )
        return False


def ensure_menu_loaded() -> None:
    """Загружает меню один раз за сессию (не на каждый rerun)."""
    if not st.session_state.menu_loaded:
        reload_menu_from_db()


def _history_entry_with_result(item: dict) -> dict:
    """Подгружает полный отчёт, если в меню только краткая запись."""
    if item.get("result"):
        return item
    return fetch_history_entry(_backend_base(), item["id"])


def build_reports(problem: str, result: dict) -> None:
    """Генерирует HTML и DOCX отчёты в session_state."""
    st.session_state.report_html = build_report_html(problem, result)
    try:
        from docx_builder import build_report_docx

        st.session_state.report_docx = build_report_docx(problem, result)
    except ImportError as exc:
        st.session_state.report_docx = None
        st.warning(f"DOCX недоступен: {exc}")
    except Exception as exc:
        st.session_state.report_docx = None
        st.warning(f"DOCX не сформирован: {exc}")


def check_backend_health() -> tuple[bool, str]:
    """Проверяет доступность backend. Возвращает (успех, сообщение)."""
    try:
        response = requests.get(
            f"{_backend_base()}{HEALTH_ENDPOINT}",
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        status = data.get("status", "unknown")
        model = data.get("llm_model", "—")
        proxy = "прокси" if data.get("proxy_enabled") else "прямое"
        if status == "ok":
            return True, f"Сервис доступен · {model} · {proxy}"
        return False, (
            f"Статус «{status}». {data.get('message') or ''}"
        )
    except requests.ConnectionError:
        return False, (
            "Backend недоступен. Запустите: "
            "`uvicorn backend.main:app --reload`"
        )
    except requests.Timeout:
        return False, "Превышено время ожидания ответа."
    except requests.RequestException as exc:
        return False, f"Ошибка: {exc}"


def call_solve_api(problem: str) -> dict:
    """Отправляет задачу на POST /solve и возвращает JSON-ответ."""
    response = requests.post(
        f"{_backend_base()}{SOLVE_ENDPOINT}",
        json={"problem": problem},
        timeout=180,
    )
    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass
        raise requests.HTTPError(detail, response=response)
    return response.json()


def clear_history() -> None:
    """Очищает отчёты в SQLite."""
    clear_history_api(_backend_base())
    st.session_state.history = []


def render_sidebar_status(ok: bool, message: str) -> None:
    """Статус backend с нейтральной палитрой сайдбара."""
    status_class = "sidebar-status--ok" if ok else "sidebar-status--warn"
    icon = "" if ok else ""
    st.markdown(
        f'<div class="sidebar-status {status_class}">'
        f'<span class="sidebar-status-icon">{icon}</span>'
        f'<span class="sidebar-status-text">{html.escape(message)}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _card(label: str, body: str) -> str:
    return (
        f'<div class="triz-card">'
        f'<div class="triz-card-label">{html.escape(label)}</div>'
        f'<div class="triz-card-body">{html.escape(body)}</div>'
        f"</div>"
    )


def render_result(result: dict) -> None:
    """Отображает экспертный TRIZ-отчёт (краткий обзор + детали)."""
    concepts = result.get("solution_concepts") or []
    tools = result.get("triz_tools") or []
    principles = result.get("recommended_principles", [])
    conclusion = result.get("final_conclusion") or {}

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Решений", len(concepts))
    with m2:
        st.metric("Инструментов ТРИЗ", len(tools))
    with m3:
        st.metric("Принципов TRIZ", len(principles))
    with m4:
        st.metric("Тип", result.get("contradiction_type", "—"))

    st.markdown(
        '<p class="triz-section">Резюме для руководства</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        _card("Executive summary", result.get("executive_summary", "—")),
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p class="triz-section">Итоговый вывод</p>',
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(_card("Рекомендация", conclusion.get("recommended_solution", "—")), unsafe_allow_html=True)
    with c2:
        st.markdown(_card("Ключевой риск", conclusion.get("key_risk", "—")), unsafe_allow_html=True)
    with c3:
        st.markdown(_card("Следующий шаг", conclusion.get("next_step", "—")), unsafe_allow_html=True)

    with st.expander("Противоречия и ИКР", expanded=True):
        st.markdown(f"**ТП:** {result.get('technical_contradiction', '—')}")
        st.markdown(f"**ФП:** {result.get('physical_contradiction', '—')}")
        st.markdown(f"**ИКР:** {result.get('ideal_final_result', '—')}")

    concepts = result.get("solution_concepts") or []
    if concepts:
        st.markdown('<p class="triz-section">Концепции решений</p>', unsafe_allow_html=True)
        for sol in concepts:
            title = sol.get("title", f"Решение {sol.get('id')}")
            with st.expander(title, expanded=sol.get("id") == 1):
                st.markdown(f"**Принцип:** {sol.get('triz_principle', '—')}")
                st.markdown(f"**Механизм:** {sol.get('mechanism', '—')}")
                st.markdown(f"**Применимость:** {sol.get('applicability', '—')}")
                st.markdown(f"**Риски:** {sol.get('risks', '—')}")
                st.caption(
                    f"Эффективность {sol.get('effectiveness_score')}/10 · "
                    f"Сложность {sol.get('complexity_score')}/10 · "
                    f"Стоимость {sol.get('cost_score')}/10 · "
                    f"Масштабируемость {sol.get('scalability_score')}/10"
                )

    with st.expander("Система, анализ, инструменты ТРИЗ", expanded=False):
        ctx = result.get("system_context") or {}
        st.markdown(f"**Система:** {ctx.get('system', '—')}")
        st.markdown(f"**Надсистема:** {ctx.get('supersystem', '—')}")
        analysis = result.get("analysis") or {}
        st.markdown(f"**Причинные цепочки:** {analysis.get('causal_chains', '—')}")
        if tools:
            st.dataframe(
                [
                    {
                        "Инструмент": t.get("tool"),
                        "Почему": t.get("why_applied"),
                        "Инсайт": t.get("insight"),
                    }
                    for t in tools
                ],
                use_container_width=True,
                hide_index=True,
            )

    if principles:
        with st.expander("Применённые принципы TRIZ", expanded=False):
            for p in principles:
                st.markdown(f"- {p}")


def _chat_has_user_messages(sess: dict) -> bool:
    return any(
        m.get("role") == "user" and (m.get("content") or "").strip()
        for m in sess.get("messages") or []
    )


def _discard_empty_chat_session(session_id: str | None) -> bool:
    """Удаляет из БД диалог, в который пользователь ничего не написал."""
    if not session_id:
        return False
    try:
        sess = get_chat_session(_backend_base(), session_id)
        if not _chat_has_user_messages(sess):
            delete_chat_session(_backend_base(), session_id)
            return True
    except requests.RequestException:
        pass
    return False


def reset_chat_session() -> None:
    if _discard_empty_chat_session(st.session_state.get("chat_session_id")):
        reload_menu_from_db()
    st.session_state.chat_session_id = None
    st.session_state.chat_messages = []
    st.session_state.chat_status = None
    try:
        save_active_chat(_backend_base(), None)
    except requests.RequestException:
        pass


def apply_chat_session(sess: dict, *, persist_active: bool = True) -> None:
    st.session_state.chat_session_id = sess["id"]
    st.session_state.chat_messages = sess.get("messages") or []
    st.session_state.chat_status = sess.get("status", "interview")
    if persist_active:
        try:
            save_active_chat(_backend_base(), sess["id"])
        except requests.RequestException:
            pass


def _format_db_time(iso_value: str | None, fallback: str = "") -> str:
    if not iso_value:
        return fallback
    try:
        dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return (iso_value or fallback)[:16].replace("T", " ")


def open_chat_from_db(chat_id: str) -> None:
    sess = get_chat_session(_backend_base(), chat_id)
    apply_chat_session(sess)
    if sess.get("status") == "analyzed" and sess.get("brief"):
        st.session_state.last_problem = sess["brief"]
        for hist in st.session_state.history:
            if hist.get("chat_session_id") == sess["id"]:
                full = _history_entry_with_result(hist)
                st.session_state.last_result = full["result"]
                build_reports(sess["brief"], full["result"])
                break


def open_report_from_db(item: dict) -> None:
    full = _history_entry_with_result(item)
    res = full["result"]
    st.session_state.last_result = res
    st.session_state.last_problem = full["problem"]
    build_reports(full["problem"], res)
    st.session_state.view = "home"
    chat_id = item.get("chat_session_id")
    if chat_id:
        try:
            sess = get_chat_session(_backend_base(), chat_id)
            apply_chat_session(sess)
        except requests.RequestException:
            pass


def restore_active_chat() -> None:
    """Восстанавливает активный диалог из SQLite после перезагрузки страницы."""
    if st.session_state.active_chat_restored or st.session_state.chat_session_id:
        st.session_state.active_chat_restored = True
        return
    try:
        session_id = fetch_active_chat(_backend_base())
    except requests.RequestException:
        st.session_state.active_chat_restored = True
        return
    if not session_id:
        st.session_state.active_chat_restored = True
        return
    try:
        sess = get_chat_session(_backend_base(), session_id)
        if not _chat_has_user_messages(sess):
            delete_chat_session(_backend_base(), session_id)
            try:
                save_active_chat(_backend_base(), None)
            except requests.RequestException:
                pass
        else:
            apply_chat_session(sess, persist_active=False)
    except requests.RequestException:
        try:
            save_active_chat(_backend_base(), None)
        except requests.RequestException:
            pass
    st.session_state.active_chat_restored = True


def bootstrap_from_db() -> None:
    if reload_menu_from_db():
        restore_active_chat()


def _on_chats_deleted(deleted_ids: list[str]) -> None:
    """Сбрасывает UI после успешного удаления на backend."""
    active = st.session_state.chat_session_id
    if active and active in deleted_ids:
        reset_chat_session()
        st.session_state.last_result = None
        st.session_state.last_problem = ""
        st.session_state.report_html = None
        st.session_state.report_docx = None
    reload_menu_from_db()


def _delete_one_chat(chat_id: str) -> None:
    delete_chat_session(_backend_base(), chat_id)
    _on_chats_deleted([chat_id])


def render_sidebar_menu() -> None:
    """Левое меню: диалоги и отчёты из базы данных."""
    ensure_menu_loaded()

    chat_status_labels = {
        "interview": "сбор",
        "ready": "готов",
        "analyzed": "отчёт",
    }

    col_d1, col_d2, col_d3 = st.columns(
        [5, 1, 1], gap="small", vertical_alignment="center"
    )
    with col_d1:
        st.markdown(
            '<span class="sidebar-history-title">Диалоги</span>',
            unsafe_allow_html=True,
        )
    with col_d2:
        if st.button("↻", help="Обновить меню", key="refresh_menu"):
            reload_menu_from_db()
            st.rerun()
    with col_d3:
        with st.popover("⋮", help="Действия с диалогами"):
            if st.session_state.chat_sessions:
                st.checkbox(
                    "Подтвердить удаление всех",
                    key="confirm_delete_all_chats_pop",
                )
                if st.button(
                    "Удалить все диалоги",
                    key="menu_delete_all_chats",
                    disabled=not st.session_state.get(
                        "confirm_delete_all_chats_pop"
                    ),
                    use_container_width=True,
                ):
                    try:
                        all_ids = [
                            c["id"] for c in st.session_state.chat_sessions
                        ]
                        delete_all_chat_sessions(_backend_base())
                        _on_chats_deleted(all_ids)
                        st.rerun()
                    except requests.RequestException as exc:
                        st.error(f"Ошибка: {exc}")
            else:
                st.caption("Нет сохранённых диалогов")
    if not st.session_state.chat_sessions:
        st.markdown(
            '<p class="sidebar-empty">Нет диалогов в базе.</p>',
            unsafe_allow_html=True,
        )
    else:
        for chat_idx, chat_item in enumerate(st.session_state.chat_sessions):
            chat_id = chat_item["id"]
            title = (chat_item.get("title") or "Диалог")[:48]
            status = chat_status_labels.get(
                chat_item.get("status", ""),
                chat_item.get("status", ""),
            )
            updated = _format_db_time(chat_item.get("updated_at"))
            is_active = st.session_state.chat_session_id == chat_id
            btn_label = f"{'▸ ' if is_active else ''}💬 {title}"
            row_col, menu_col = st.columns(
                [8, 1], gap="small", vertical_alignment="center"
            )
            with row_col:
                if st.button(
                    btn_label,
                    key=f"menu_chat_{chat_idx}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    try:
                        open_chat_from_db(chat_id)
                        st.rerun()
                    except requests.RequestException as exc:
                        st.error(f"Не удалось открыть: {exc}")
            with menu_col:
                if is_active:
                    with st.popover(
                        "⋮",
                        key=f"chat_row_menu_{chat_id}",
                        help="Меню диалога",
                    ):
                        if st.button(
                            "Удалить диалог",
                            key=f"chat_row_delete_{chat_id}",
                            use_container_width=True,
                        ):
                            try:
                                _delete_one_chat(chat_id)
                                st.rerun()
                            except requests.RequestException as exc:
                                st.error(f"Ошибка: {exc}")
            st.caption(f"{status} · {updated}")

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    col_h1, col_h2 = st.columns([5, 2], gap="small", vertical_alignment="center")
    with col_h1:
        st.markdown(
            '<span class="sidebar-history-title">Отчёты TRIZ</span>',
            unsafe_allow_html=True,
        )
    with col_h2:
        if st.button("Очистить", disabled=not st.session_state.history, key="clear_history"):
            try:
                clear_history()
                st.session_state.last_result = None
                st.session_state.last_problem = ""
                st.session_state.report_html = None
                st.session_state.report_docx = None
                st.session_state.view = "home"
                reload_menu_from_db()
                st.rerun()
            except requests.RequestException as exc:
                st.error(f"Ошибка: {exc}")

    if not st.session_state.history:
        st.markdown(
            '<p class="sidebar-empty">Нет отчётов в базе.</p>',
            unsafe_allow_html=True,
        )
    else:
        for hist_idx, item in enumerate(st.session_state.history):
            problem_preview = (item.get("problem") or "Отчёт")[:48]
            time_label = item.get("time") or _format_db_time(item.get("created_at"))
            source = " · диалог" if item.get("chat_session_id") else ""
            if st.button(
                f"📊 {problem_preview}",
                key=f"menu_report_{hist_idx}",
                use_container_width=True,
            ):
                try:
                    open_report_from_db(item)
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"Не удалось открыть: {exc}")
            st.caption(f"{time_label}{source}")


def ensure_chat_session() -> bool:
    """Показывает приветствие; в БД сессия создаётся после первого ответа пользователя."""
    if st.session_state.chat_session_id:
        return True
    if not st.session_state.chat_messages:
        st.session_state.chat_messages = [
            {"role": "assistant", "content": CHAT_OPENING_MESSAGE},
        ]
        st.session_state.chat_status = "interview"
    return True


def ensure_chat_session_in_db() -> bool:
    """Создаёт запись в БД перед отправкой первого сообщения."""
    if st.session_state.chat_session_id:
        return True
    try:
        sess = create_chat_session(_backend_base())
        apply_chat_session(sess)
        return True
    except requests.RequestException as exc:
        st.error(f"Не удалось сохранить диалог: {exc}")
        return False


def render_chat_tab() -> None:
    """Диалоговое интервью TRIZ."""
    if not ensure_chat_session():
        return

    status = st.session_state.chat_status or "interview"
    status_labels = {
        "interview": "Сбор данных",
        "ready": "Готово к анализу",
        "analyzed": "Анализ выполнен",
    }
    st.caption(f"Этап: **{status_labels.get(status, status)}**")

    for msg in st.session_state.chat_messages:
        role = msg.get("role", "assistant")
        with st.chat_message("user" if role == "user" else "assistant"):
            st.markdown(msg.get("content", ""))

    if status == "ready":
        st.success(
            "Интервью завершено. Запустите экспертный TRIZ-анализ — формирование отчёта "
            "займёт 1–3 минуты."
        )
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(
                "Запустить TRIZ-анализ",
                type="primary",
                use_container_width=True,
                key="chat_analyze",
            ):
                with st.spinner("Выполняю экспертный TRIZ-анализ…"):
                    try:
                        payload = analyze_chat_session(
                            _backend_base(),
                            st.session_state.chat_session_id,
                        )
                        result = payload.get("result") or payload
                        brief = payload.get("brief", "")
                        st.session_state.last_result = result
                        st.session_state.last_problem = brief
                        st.session_state.chat_status = "analyzed"
                        build_reports(brief, result)
                        reload_menu_from_db()
                        st.rerun()
                    except requests.Timeout:
                        st.error("Превышено время ожидания анализа.")
                    except requests.HTTPError as exc:
                        st.error(f"Ошибка анализа: {exc}")
                    except requests.RequestException as exc:
                        st.error(f"Ошибка запроса: {exc}")
        with col_b:
            if st.button(
                "Новый диалог",
                use_container_width=True,
                key="chat_new_after_ready",
            ):
                reset_chat_session()
                st.rerun()
        return

    if status == "analyzed":
        st.info("По этой сессии анализ уже выполнен. Отчёт ниже или начните новый диалог.")
        return

    action_col1, action_col2 = st.columns(2)
    with action_col2:
        if st.button(
            "Завершить интервью вручную",
            help="Если все блоки пройдены, но кнопка анализа не появилась",
            key="chat_complete_manual",
            disabled=not st.session_state.chat_session_id,
        ):
            try:
                sess = complete_chat_session(
                    _backend_base(),
                    st.session_state.chat_session_id,
                )
                apply_chat_session(sess)
                reload_menu_from_db()
                st.rerun()
            except requests.RequestException as exc:
                st.error(f"Ошибка: {exc}")

    prompt = st.chat_input("Ваш ответ…")
    if prompt:
        with st.spinner("Аналитик формулирует следующий вопрос…"):
            try:
                if not ensure_chat_session_in_db():
                    return
                sess = send_chat_message(
                    _backend_base(),
                    st.session_state.chat_session_id,
                    prompt.strip(),
                )
                apply_chat_session(sess)
                reload_menu_from_db()
                st.rerun()
            except requests.Timeout:
                st.error("Превышено время ожидания ответа модели.")
            except requests.HTTPError as exc:
                st.error(f"Ошибка: {exc}")
            except requests.RequestException as exc:
                st.error(f"Ошибка запроса: {exc}")


def render_quick_solve_tab() -> None:
    """Одноразовый анализ без интервью (бриф целиком)."""
    st.markdown("**Опишите задачу целиком** (шаблон или сводка)")
    problem = st.text_area(
        "Опишите вашу задачу",
        height=140,
        placeholder="Например: нужно снизить энергопотребление двигателя без потери мощности...",
        label_visibility="collapsed",
        max_chars=MAX_PROBLEM_LENGTH,
        key="problem_input",
    )
    st.caption(f"{len(problem)} / {MAX_PROBLEM_LENGTH} символов")

    if st.button("Решить задачу", type="primary", use_container_width=True, key="quick_solve"):
        problem_text = problem.strip()
        if not problem_text:
            st.warning("Введите описание задачи.", icon="✏️")
        elif len(problem_text) < MIN_PROBLEM_LENGTH:
            st.warning(
                f"Задача слишком короткая — минимум {MIN_PROBLEM_LENGTH} символа.",
                icon="✏️",
            )
        else:
            with st.spinner("Выполняю экспертный TRIZ-анализ и формирую отчёт…"):
                try:
                    result = call_solve_api(problem_text)
                    reload_menu_from_db()
                    st.session_state.last_result = result
                    st.session_state.last_problem = problem_text
                    build_reports(problem_text, result)
                    st.rerun()
                except requests.ConnectionError:
                    st.error(
                        "Не удалось подключиться к backend. "
                        f"Проверьте `{_backend_base()}{SOLVE_ENDPOINT}`.",
                        icon="🔌",
                    )
                except requests.Timeout:
                    st.error("Backend не ответил вовремя.", icon="⏱️")
                except requests.HTTPError as exc:
                    code = exc.response.status_code if exc.response else "?"
                    st.error(f"Ошибка API ({code}): {exc}", icon="⚠️")
                except requests.RequestException as exc:
                    st.error(f"Ошибка запроса: {exc}", icon="⚠️")


bootstrap_from_db()

# --- Sidebar ---
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-title">AI-Ассистент</div>
            <div class="sidebar-brand-sub">Меню из базы данных</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.session_state.backend_url = st.text_input(
        "URL backend API",
        value=st.session_state.get("backend_url", BACKEND_URL),
        help="Адрес FastAPI-сервера (по умолчанию localhost:8000)",
    )

    if st.session_state.get("db_menu_error"):
        st.caption(st.session_state.db_menu_error)

    healthy, health_message = check_backend_health()
    render_sidebar_status(healthy, health_message)

    if st.button("Новый диалог", use_container_width=True, key="sidebar_new_chat"):
        reset_chat_session()
        st.session_state.last_result = None
        st.session_state.last_problem = ""
        st.session_state.report_html = None
        st.session_state.report_docx = None
        reload_menu_from_db()
        st.rerun()

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)
    render_sidebar_menu()

# Просмотр отчёта (сайдбар остаётся доступным)
if st.session_state.view == "report":
    from report_view import render_report_page

    render_report_page(show_back=True)
    st.stop()

# --- Main page ---
st.markdown(
    """
    <div class="triz-hero">
        <span class="triz-badge">Теория решения изобретательских задач</span>
        <h1>TRIZ AI-Ассистент</h1>
        <p>Диалоговый сбор исходных данных, затем экспертный TRIZ-анализ
        и отчёт для руководства (HTML / DOCX).</p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_dialog, tab_quick = st.tabs(["Диалог с аналитиком", "Быстрый анализ"])

with tab_dialog:
    render_chat_tab()

with tab_quick:
    render_quick_solve_tab()

if st.session_state.last_result:
    st.divider()
    header_col, report_col, docx_col = st.columns([4, 2, 2])
    with header_col:
        st.markdown("### Экспертный TRIZ-отчёт")
    with report_col:
        if st.session_state.report_html and st.button(
            "📊 HTML-отчёт",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.view = "report"
            st.rerun()
    with docx_col:
        if st.session_state.report_docx:
            st.download_button(
                "📄 Скачать DOCX",
                data=st.session_state.report_docx,
                file_name="triz_expert_report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
    if st.session_state.last_problem:
        with st.expander("Исходная задача", expanded=False):
            st.write(st.session_state.last_problem)
    render_result(st.session_state.last_result)
    if st.session_state.report_html:
        st.caption(
            "Полный HTML-отчёт — кнопка «HTML-отчёт»; DOCX — кнопка выше. "
            "Также доступно в sidebar: «report»."
        )
