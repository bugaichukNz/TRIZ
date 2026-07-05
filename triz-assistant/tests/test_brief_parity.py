"""Паритет InterviewBrief.to_prompt_text() и compile_interview_brief."""

from __future__ import annotations

import json

from backend.chat_brief import compile_interview_brief
from backend.llm.interview_state import FIELD_LABELS, InterviewStateManager, _SKIPPED_VALUE


def _messages_with_confirmed(
    confirmed: dict[str, str],
    *,
    dialog: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    state = json.dumps(
        {
            "confirmed": confirmed,
            "pending_field": None,
            "asked": list(confirmed.keys()),
            "attempts": {},
        },
        ensure_ascii=False,
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": f"__interview_state__:{state}"}]
    if dialog:
        messages.extend(dialog)
    return messages


def _assert_brief_parity(messages: list[dict[str, str]]) -> None:
    brief = InterviewStateManager(messages).export_brief()
    expected = compile_interview_brief(messages)
    assert brief.to_prompt_text(messages) == expected


class TestBriefParity:
    def test_all_fields_confirmed(self) -> None:
        confirmed = {
            field: f"  значение для {label}  "
            for field, label in FIELD_LABELS.items()
        }
        messages = _messages_with_confirmed(confirmed)
        _assert_brief_parity(messages)

    def test_some_fields_skipped(self) -> None:
        confirmed = {
            "ne_fact": "трещины на шве",
            "ne_where": "линия розлива, цех №3",
            "ne_when": _SKIPPED_VALUE,
            "consequences": "брак партии",
            "cause_hypothesis": _SKIPPED_VALUE,
            "system_function": "герметизация ёмкости",
            "system_elements": "крышка, уплотнитель, корпус",
            "system_object": "стакан",
            "supersystem": "линия розлива",
            "expected_result": "брак < 0.5%",
            "economic_result": _SKIPPED_VALUE,
            "constraints": "без остановки линии",
            "resources": "сжатый воздух, оператор",
            "known_solutions": "замена уплотнителя",
            "why_failed": _SKIPPED_VALUE,
            "unrealized_ideas": "датчик давления",
            "experts": _SKIPPED_VALUE,
        }
        messages = _messages_with_confirmed(confirmed)
        _assert_brief_parity(messages)

    def test_some_fields_untouched(self) -> None:
        confirmed = {
            "ne_fact": "  трещины на шве  ",
            "ne_where": "линия розлива",
            "ne_when": _SKIPPED_VALUE,
            "consequences": "брак партии",
            "system_function": "герметизация",
        }
        messages = _messages_with_confirmed(
            confirmed,
            dialog=[
                {"role": "assistant", "content": "Опишите нежелательный эффект."},
                {"role": "user", "content": "Трещины на шве при розливе."},
            ],
        )
        _assert_brief_parity(messages)

    def test_skipped_uses_gap_message_not_dash(self) -> None:
        confirmed = {"ne_fact": "факт НЭ", "ne_where": _SKIPPED_VALUE}
        messages = _messages_with_confirmed(confirmed)
        text = InterviewStateManager(messages).export_brief().to_prompt_text(messages)
        assert "данные не получены (пропущено в интервью)" in text
        assert "• НЭ — где: —" not in text

    def test_untouched_fields_absent(self) -> None:
        confirmed = {"ne_fact": "факт НЭ"}
        messages = _messages_with_confirmed(confirmed)
        text = InterviewStateManager(messages).export_brief().to_prompt_text(messages)
        for field, label in FIELD_LABELS.items():
            if field == "ne_fact":
                continue
            assert f"• {label}:" not in text
