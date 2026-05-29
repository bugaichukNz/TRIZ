"""Общий UI просмотра HTML/DOCX отчёта."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from report_builder import build_report_html


def render_report_page(*, show_back: bool = True, back_mode: str = "session") -> None:
    """Отображает HTML-отчёт и кнопки скачивания."""
    st.markdown(
        """
        <div class="triz-hero" style="margin-bottom:1rem;padding:1.25rem 1.5rem;">
            <span class="triz-badge">Экспертный отчёт</span>
            <h1 style="font-size:1.35rem;">TRIZ-аналитический отчёт</h1>
            <p style="font-size:0.9rem;">HTML с графиками и таблицами · DOCX для руководства</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.get("report_html"):
        st.info("Сначала решите задачу на главной странице — отчёт сформируется автоматически.")
        if show_back:
            if back_mode == "link":
                st.page_link("app.py", label="Перейти к решению задачи", icon="💡")
            elif st.button("Перейти к решению задачи", type="primary"):
                st.session_state.view = "home"
                st.rerun()
        return

    problem = st.session_state.get("last_problem", "")
    report_html = st.session_state.report_html

    c1, c2, c3, c4 = st.columns([2, 2, 2, 4])
    with c1:
        if show_back:
            if back_mode == "link":
                st.page_link("app.py", label="На главную", icon="💡")
            elif st.button("← На главную"):
                st.session_state.view = "home"
                st.rerun()
    with c2:
        st.download_button(
            "Скачать HTML",
            data=report_html.encode("utf-8"),
            file_name="triz_expert_report.html",
            mime="text/html",
            use_container_width=True,
        )
    with c3:
        if st.session_state.get("report_docx"):
            st.download_button(
                "Скачать DOCX",
                data=st.session_state.report_docx,
                file_name="triz_expert_report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
    with c4:
        if st.button("Обновить отчёты", use_container_width=True):
            if st.session_state.get("last_result") and problem:
                result = st.session_state.last_result
                st.session_state.report_html = build_report_html(problem, result)
                try:
                    from docx_builder import build_report_docx

                    st.session_state.report_docx = build_report_docx(problem, result)
                except Exception as exc:
                    st.error(f"DOCX: {exc}")
                st.rerun()

    if problem:
        with st.expander("Исходная задача", expanded=False):
            st.write(problem)

    components.html(report_html, height=3200, scrolling=True)
