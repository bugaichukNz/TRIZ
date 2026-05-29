"""Страница просмотра HTML/DOCX отчёта (sidebar Streamlit)."""

import sys
from pathlib import Path

# Импорты из каталога frontend/
_FRONTEND_DIR = Path(__file__).resolve().parent.parent
if str(_FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(_FRONTEND_DIR))

import streamlit as st

from report_view import render_report_page
from theme import inject_theme

st.set_page_config(
    page_title="TRIZ · Отчёт",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_theme()

if "report_html" not in st.session_state:
    st.session_state.report_html = None
if "report_docx" not in st.session_state:
    st.session_state.report_docx = None
if "view" not in st.session_state:
    st.session_state.view = "home"

render_report_page(show_back=True, back_mode="link")
