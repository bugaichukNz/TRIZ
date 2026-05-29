"""Streamlit-интерфейс TRIZ AI-ассистента."""

import html
import os
from datetime import datetime

import requests
import streamlit as st

from report_builder import build_report_html
from theme import inject_theme

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
SOLVE_ENDPOINT = "/solve"
HEALTH_ENDPOINT = "/health"
HISTORY_LIMIT = 5
MIN_PROBLEM_LENGTH = 3
MAX_PROBLEM_LENGTH = 4000

st.set_page_config(
    page_title="TRIZ AI-Ассистент",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

if "history" not in st.session_state:
    st.session_state.history = []
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

# Просмотр отчёта без st.switch_page (надёжно при Streamlit multipage v2)
if st.session_state.view == "report":
    from report_view import render_report_page

    render_report_page(show_back=True)
    st.stop()


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


def _backend_base() -> str:
    return st.session_state.get("backend_url", BACKEND_URL).rstrip("/")


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


def add_to_history(problem: str, result: dict) -> None:
    """Добавляет запрос в историю (не более HISTORY_LIMIT записей)."""
    entry = {
        "problem": problem,
        "result": result,
        "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    st.session_state.history = [entry, *st.session_state.history][:HISTORY_LIMIT]


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


# --- Sidebar ---
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-title">AI-Ассистент</div>
            <div class="sidebar-brand-sub">Настройки и история</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.session_state.backend_url = st.text_input(
        "URL backend API",
        value=st.session_state.get("backend_url", BACKEND_URL),
        help="Адрес FastAPI-сервера (по умолчанию localhost:8000)",
    )

    healthy, health_message = check_backend_health()
    render_sidebar_status(healthy, health_message)

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    col_h1, col_h2 = st.columns([5, 2], gap="small", vertical_alignment="center")
    with col_h1:
        st.markdown('<span class="sidebar-history-title">История</span>', unsafe_allow_html=True)
    with col_h2:
        if st.button("Очистить", disabled=not st.session_state.history, key="clear_history"):
            st.session_state.history = []
            st.session_state.last_result = None
            st.session_state.last_problem = ""
            st.session_state.report_html = None
            st.session_state.report_docx = None
            st.session_state.view = "home"
            st.rerun()

    if not st.session_state.history:
        st.markdown(
            '<p class="sidebar-empty">Пока нет запросов — решите первую задачу.</p>',
            unsafe_allow_html=True,
        )
    else:
        for hist_idx, item in enumerate(st.session_state.history):
            with st.expander(f"🕐 {item['time']}", expanded=False):
                st.markdown(f"**Задача:** {item['problem']}")
                res = item["result"]
                st.markdown(f"**Противоречие:** {res.get('contradiction', '—')}")
                n_principles = len(res.get("recommended_principles", []))
                n_solutions = len(res.get("solution_concepts") or res.get("solutions", []))
                st.markdown(f"**Принципов:** {n_principles} · **Решений:** {n_solutions}")
                if st.button("Показать снова", key=f"hist_show_{hist_idx}"):
                    st.session_state.last_result = res
                    st.session_state.last_problem = item["problem"]
                    build_reports(item["problem"], res)
                    st.session_state.view = "home"
                    st.rerun()

# --- Main page ---
st.markdown(
    """
    <div class="triz-hero">
        <span class="triz-badge">Теория решения изобретательских задач</span>
        <h1>TRIZ AI-Ассистент</h1>
        <p>Экспертный TRIZ-анализ: противоречия, инструменты, ранжированные решения
        и отчёт для руководства (HTML / DOCX).</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("**Опишите вашу задачу**")
problem = st.text_area(
    "Опишите вашу задачу",
    height=140,
    placeholder="Например: нужно снизить энергопотребление двигателя без потери мощности...",
    label_visibility="collapsed",
    max_chars=MAX_PROBLEM_LENGTH,
    key="problem_input",
)

char_count = len(problem)
st.caption(f"{char_count} / {MAX_PROBLEM_LENGTH} символов")

solve_clicked = st.button("Решить задачу", type="primary", use_container_width=True)

if solve_clicked:
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
                add_to_history(problem_text, result)
                st.session_state.last_result = result
                st.session_state.last_problem = problem_text
                build_reports(problem_text, result)
            except requests.ConnectionError:
                st.error(
                    "Не удалось подключиться к backend. "
                    f"Проверьте `{_backend_base()}{SOLVE_ENDPOINT}` "
                    "и что сервер запущен.",
                    icon="🔌",
                )
            except requests.Timeout:
                st.error(
                    "Backend не ответил вовремя. "
                    "Упростите формулировку или повторите позже.",
                    icon="⏱️",
                )
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response else "?"
                st.error(f"Ошибка API ({code}): {exc}", icon="⚠️")
            except requests.RequestException as exc:
                st.error(f"Ошибка запроса: {exc}", icon="⚠️")

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
