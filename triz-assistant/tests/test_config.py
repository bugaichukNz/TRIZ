"""Тесты конфигурации по умолчанию."""

from __future__ import annotations

from backend.config import Settings


def test_effects_rag_enabled_default_true() -> None:
    assert Settings.model_fields["effects_rag_enabled"].default is True
