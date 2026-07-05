"""Тесты InterviewStateManager и вспомогательных функций."""

from __future__ import annotations

import json

import pytest

from backend.llm.interview_state import (
    BLOCKS,
    FIELD_LABELS,
    InterviewStateManager,
    _MAX_FIELD_ATTEMPTS,
    _SKIPPED_VALUE,
    _is_skip_answer,
)


def _empty_messages() -> list[dict[str, str]]:
    state = json.dumps(
        {
            "confirmed": {},
            "pending_field": None,
            "asked": [],
            "attempts": {},
        },
        ensure_ascii=False,
    )
    return [{"role": "system", "content": f"__interview_state__:{state}"}]


class TestIsSkipAnswer:
    @pytest.mark.parametrize(
        "text",
        [
            "не знаю",
            "Не знаю.",
            "пропустить",
            "Пропусти этот вопрос",
            "затрудняюсь ответить",
            "нет данных",
        ],
    )
    def test_skip_markers_recognized(self, text: str) -> None:
        assert _is_skip_answer(text) is True

    def test_normal_answer_not_skip(self) -> None:
        text = "НЭ проявляется при температуре 80°C на линии розлива в цехе №3."
        assert _is_skip_answer(text) is False

    def test_long_text_with_marker_not_skip(self) -> None:
        text = "не знаю " + "подробностей " * 10
        assert _is_skip_answer(text) is False


class TestMaxFieldAttempts:
    def test_field_marked_dash_after_max_attempts(self) -> None:
        mgr = InterviewStateManager(_empty_messages())
        field = "ne_when"
        for prior in ("ne_fact", "ne_where"):
            mgr.confirm_manual(prior, "значение")
        mgr.set_pending_field(field)
        mgr.mark_asked(field)

        for _ in range(_MAX_FIELD_ATTEMPTS):
            mgr.confirm_pending_answer("", messages=[])
            mgr.prepare_next_pending()

        assert mgr.confirmed.get(field) == _SKIPPED_VALUE

    def test_user_skip_sets_dash_immediately(self) -> None:
        mgr = InterviewStateManager(_empty_messages())
        mgr.set_pending_field("constraints")
        mgr.mark_asked("constraints")
        skipped = mgr.confirm_pending_answer("не знаю", messages=[])
        assert skipped is True
        assert mgr.confirmed["constraints"] == _SKIPPED_VALUE


class TestBlocksOrder:
    def test_get_status_follows_blocks_order(self) -> None:
        mgr = InterviewStateManager(_empty_messages())
        status = mgr.get_status()
        block_names = [item["block"] for item in status]
        expected = [name for name, _ in BLOCKS]
        assert block_names == expected

    def test_next_field_follows_block_sequence(self) -> None:
        mgr = InterviewStateManager(_empty_messages())
        first = mgr.next_field_to_ask()
        assert first is not None
        field_key, _label = first
        assert field_key == BLOCKS[0][1][0]

        mgr.confirm_manual(field_key, "значение")
        second = mgr.next_field_to_ask()
        assert second is not None
        assert second[0] == BLOCKS[0][1][1]

    def test_first_open_block_is_first_incomplete(self) -> None:
        mgr = InterviewStateManager(_empty_messages())
        block = mgr.first_open_block()
        assert block is not None
        assert block["block"] == BLOCKS[0][0]

    def test_all_block_fields_in_field_labels(self) -> None:
        for _block_name, fields in BLOCKS:
            for field in fields:
                assert field in FIELD_LABELS

    def test_is_complete_false_until_all_non_expert_blocks_closed(self) -> None:
        mgr = InterviewStateManager(_empty_messages())
        assert mgr.is_complete() is False

        for _block_name, fields in BLOCKS[:-1]:
            for field in fields:
                mgr.confirm_manual(field, "ok")

        assert mgr.is_complete() is True
