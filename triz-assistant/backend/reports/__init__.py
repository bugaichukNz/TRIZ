"""Генерация HTML и DOCX отчётов на бэкенде."""

from backend.reports.html_builder import build_report_html

__all__ = ["build_report_html", "build_report_docx"]


def build_report_docx(*args, **kwargs):
    from backend.reports.docx_builder import build_report_docx as _build

    return _build(*args, **kwargs)
