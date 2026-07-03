#!/usr/bin/env python3
"""E2E-тест диалогового интервью TRIZ без UI (реальные вызовы OpenAI API)."""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.chat_brief import compile_interview_brief  # noqa: E402
from backend.chat_store import ChatStore  # noqa: E402
from backend.llm.chain import TRIZChain, TRIZChainError  # noqa: E402
from backend.llm.chat_prompt import CHAT_OPENING_MESSAGE, READY_FOR_ANALYSIS_MARKER  # noqa: E402
from backend.llm.interview_state import (  # noqa: E402
    BLOCKS,
    InterviewStateManager,
    _SKIPPED_VALUE,
)

USER_ID = "e2e-test-user"

UZK_FIRST_MESSAGE = (
    "Ультразвуковой контроль (УЗК) сварных швов на магистральном трубопроводе D=1420 мм. "
    "Нежелательный эффект: датчик УЗК физически не помещается в зону контроля у фланцевых "
    "соединений — в этих зонах контроль сплошности шва невозможен. "
    "Потери от простоя участка — порядка 40 млн руб. в сутки."
)

FIELD_ANSWERS: dict[str, str] = {
    "ne_when": "При плановых остановках раз в год, давление в трубопроводе менее 10 бар",
    "cause_hypothesis": (
        "Гипотеза задачедателя: корпус датчика 60×40 мм, зазор у фланца менее 30 мм"
    ),
    "system_function": (
        "Обеспечить ультразвуковой контроль сплошности сварного шва "
        "в труднодоступных зонах трубопровода"
    ),
    "system_elements": (
        "УЗК-датчик, сканирующий механизм, трубопровод, фланцевое соединение, "
        "контактная жидкость, оператор НК"
    ),
    "system_object": "Сварной шов в зоне фланцевого узла",
    "supersystem": (
        "Газотранспортная система магистрального трубопровода "
        "с участком плановой диагностики"
    ),
    "expected_result": (
        "Контроль 100% протяжённости шва в зоне фланца, включая участки "
        "с зазором от 30 мм и менее"
    ),
    "economic_result": (
        "Снизить риск простоя с уровня 40 млн руб/сутки; "
        "окупаемость решения — до 12 месяцев"
    ),
    "constraints": (
        "Нельзя останавливать магистраль чаще одного раза в год; "
        "нельзя демонтировать фланец; контроль только при давлении ниже 10 бар"
    ),
    "resources": (
        "Бюджет проекта до 15 млн руб., срок внедрения 6 месяцев, "
        "доступ к зоне только при плановой остановке"
    ),
    "known_solutions": (
        "Пробовали миниатюрный датчик другого производителя "
        "и установку датчика с противоположной стороны фланца"
    ),
    "why_failed": (
        "Мини-датчик не обеспечил стабильный акустический контакт; "
        "с другой стороны мешает обвязка и нет места для манипулятора"
    ),
    "unrealized_ideas": (
        "Рассматривали гибкий ввод датчика и роботизированный манипулятор — "
        "не внедряли из-за требований взрывозащиты и сроков"
    ),
    "experts": "Иванов А.П., главный метролог; Петров С.В., инженер НК, отдел диагностики",
}

ALL_FIELDS: list[str] = [f for _, fields in BLOCKS for f in fields]

REQUIRED_SOLVE_FIELDS = (
    "problem_description",
    "system_context",
    "technical_contradiction",
    "physical_contradiction",
    "ideal_final_result",
    "triz_tools",
)

STEP_21_PATTERNS: tuple[tuple[str, ...], ...] = (
    ("пса", "причинно-следств", "инструмент 11"),
    ("кса", "компонентно-структурн", "инструмент 14"),
    ("постановка задачи", "инструмент 2"),
)


@dataclass
class ScenarioStats:
    name: str
    passed: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def ok(self, condition: bool, label: str) -> bool:
        if condition:
            print(f"  PASS: {label}")
            self.passed += 1
            return True
        print(f"  FAIL: {label}")
        self.failed += 1
        self.errors.append(label)
        return False


def _fields_in_order() -> list[str]:
    return list(ALL_FIELDS)


def _next_missing_field(confirmed: dict[str, str]) -> str | None:
    for fld in _fields_in_order():
        if fld not in confirmed:
            return fld
    return None


def _state_from_messages(messages: list[dict[str, str]]) -> InterviewStateManager:
    return InterviewStateManager(messages)


def _make_store() -> tuple[ChatStore, Path]:
    tmpdir = Path(tempfile.mkdtemp(prefix="triz_e2e_"))
    db_path = tmpdir / "chat.db"
    return ChatStore(db_path=db_path, max_sessions=20), tmpdir


def _run_turn(
    store: ChatStore,
    chain: TRIZChain,
    session_id: str,
    user_content: str,
) -> tuple[str, list[dict[str, str]]]:
    session = store.append_user_message(session_id, user_content)
    reply, updated_messages = chain.chat(session["messages"])
    store.save_messages_raw(session_id, updated_messages)
    store.append_assistant_message(session_id, reply)
    return reply, updated_messages


def _seed_session(
    store: ChatStore,
    *,
    confirmed: dict[str, str],
    pending_field: str,
    asked: list[str] | None = None,
    attempts: dict[str, int] | None = None,
    extra_messages: list[dict[str, str]] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    session = store.create_session(USER_ID)
    session_id = session["id"]
    messages: list[dict[str, str]] = [
        {"role": "assistant", "content": CHAT_OPENING_MESSAGE},
    ]
    if extra_messages:
        messages.extend(extra_messages)
    state = {
        "confirmed": confirmed,
        "pending_field": pending_field,
        "asked": asked or list(confirmed.keys()) + [pending_field],
        "attempts": attempts or {},
    }
    messages.append(
        {"role": "system", "content": "__interview_state__:" + json.dumps(state, ensure_ascii=False)}
    )
    if not extra_messages:
        messages.append(
            {
                "role": "assistant",
                "content": f"Уточните, пожалуйста: {pending_field}?",
            }
        )
    store.save_messages_raw(session_id, messages)
    return session_id, messages


def scenario_full_interview(chain: TRIZChain, store: ChatStore) -> tuple[ScenarioStats, list[dict[str, str]] | None]:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ 1 — Полный цикл интервью")
    print("=" * 72)
    stats = ScenarioStats("Сценарий 1")
    messages: list[dict[str, str]] | None = None

    try:
        session = store.create_session(USER_ID)
        session_id = session["id"]

        print("\n--- Ход 0: полное описание задачи УЗК ---")
        reply, messages = _run_turn(store, chain, session_id, UZK_FIRST_MESSAGE)
        mgr = _state_from_messages(messages)
        print(f"  pending_field={mgr.pending_field!r}")
        print(f"  confirmed={list(mgr.confirmed.keys())}")

        stats.ok(len(mgr.confirmed) > 0, "после первого сообщения есть подтверждённые поля")
        stats.ok(
            mgr.pending_field is not None or mgr.is_complete(),
            "после первого сообщения интервью продвигается (pending или завершение блоков)",
        )

        for field_key in _fields_in_order():
            mgr = _state_from_messages(messages)
            if field_key in mgr.confirmed:
                continue
            if mgr.is_complete() and mgr.pending_field is None:
                break

            stats.ok(
                mgr.pending_field == field_key,
                f"перед ответом pending_field={field_key!r} (факт: {mgr.pending_field!r})",
            )

            answer = FIELD_ANSWERS.get(field_key, f"Тестовое значение для {field_key}")
            print(f"\n--- Ход: ответ на {field_key} ---")
            reply, messages = _run_turn(store, chain, session_id, answer)
            mgr = _state_from_messages(messages)
            print(f"  pending_field={mgr.pending_field!r}")
            print(f"  confirmed[{field_key}]={mgr.confirmed.get(field_key, '—')!r}")

            stats.ok(field_key in mgr.confirmed, f"поле {field_key!r} появилось в confirmed")
            expected_next = _next_missing_field(mgr.confirmed)
            if expected_next is not None:
                stats.ok(
                    mgr.pending_field == expected_next,
                    f"pending_field={expected_next!r} после подтверждения {field_key!r}",
                )

        print("\n--- Финальный ход: подтверждение резюме ---")
        reply, messages = _run_turn(store, chain, session_id, "Всё верно, можно к анализу")
        stats.ok(
            READY_FOR_ANALYSIS_MARKER in reply,
            f"ответ агента содержит маркер {READY_FOR_ANALYSIS_MARKER!r}",
        )
        print(f"  reply (фрагмент): {reply[:200]}...")

    except TRIZChainError as exc:
        print(f"  ERROR (TRIZChain): {exc}")
        stats.failed += 1
        stats.errors.append(str(exc))
        messages = None
    except Exception as exc:
        print(f"  ERROR: {exc}")
        traceback.print_exc()
        stats.failed += 1
        stats.errors.append(str(exc))
        messages = None

    return stats, messages


def scenario_tautology_ne_when(chain: TRIZChain, store: ChatStore) -> ScenarioStats:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ 2 — Тавтология ne_when")
    print("=" * 72)
    stats = ScenarioStats("Сценарий 2")

    try:
        session_id, _ = _seed_session(
            store,
            confirmed={
                "ne_fact": "Датчик УЗК не помещается в зону контроля у фланца",
                "ne_where": "Фланцевые соединения трубопровода D=1420 мм",
            },
            pending_field="ne_when",
            asked=["ne_fact", "ne_where", "ne_when"],
        )

        reply, messages = _run_turn(store, chain, session_id, "при проведении контроля")
        mgr = _state_from_messages(messages)
        print(f"  reply (фрагмент): {reply[:160]}...")
        print(f"  pending_field={mgr.pending_field!r}")
        print(f"  ne_when in confirmed={'ne_when' in mgr.confirmed}")

        stats.ok("ne_when" not in mgr.confirmed, "ne_when НЕ появился в confirmed")
        stats.ok(mgr.pending_field == "ne_when", "pending_field остался ne_when (переспрос)")

    except TRIZChainError as exc:
        print(f"  ERROR (TRIZChain): {exc}")
        stats.failed += 1
        stats.errors.append(str(exc))
    except Exception as exc:
        print(f"  ERROR: {exc}")
        traceback.print_exc()
        stats.failed += 1
        stats.errors.append(str(exc))

    return stats


def scenario_unknown_cause(chain: TRIZChain, store: ChatStore) -> ScenarioStats:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ 3 — Ответ «не знаю» на cause_hypothesis")
    print("=" * 72)
    stats = ScenarioStats("Сценарий 3")

    try:
        session_id, _ = _seed_session(
            store,
            confirmed={
                "ne_fact": "Датчик УЗК не помещается в зону контроля у фланца",
                "ne_where": "Фланцевые соединения трубопровода",
                "ne_when": "При плановых остановках, давление ниже 10 бар",
                "consequences": "Невозможен контроль шва, риск простоя 40 млн руб/сутки",
            },
            pending_field="cause_hypothesis",
            asked=["ne_fact", "ne_where", "ne_when", "consequences", "cause_hypothesis"],
        )

        reply, messages = _run_turn(store, chain, session_id, "не знаю")
        mgr = _state_from_messages(messages)
        cause_value = mgr.confirmed.get("cause_hypothesis")
        print(f"  reply (фрагмент): {reply[:160]}...")
        print(f"  pending_field={mgr.pending_field!r}")
        print(f"  cause_hypothesis={cause_value!r}")

        stats.ok(
            cause_value == _SKIPPED_VALUE,
            f"cause_hypothesis помечено как пропущенное ({_SKIPPED_VALUE!r})",
        )
        stats.ok(
            mgr.pending_field == "system_function",
            f"pending_field переключился на system_function (факт: {mgr.pending_field!r})",
        )

    except TRIZChainError as exc:
        print(f"  ERROR (TRIZChain): {exc}")
        stats.failed += 1
        stats.errors.append(str(exc))
    except Exception as exc:
        print(f"  ERROR: {exc}")
        traceback.print_exc()
        stats.failed += 1
        stats.errors.append(str(exc))

    return stats


def scenario_brief(messages: list[dict[str, str]]) -> tuple[ScenarioStats, str | None]:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ 4 — Бриф")
    print("=" * 72)
    stats = ScenarioStats("Сценарий 4")
    brief: str | None = None

    try:
        brief = compile_interview_brief(messages)
        print("\n--- полный бриф ---\n")
        print(brief)
        print("\n--- конец брифа ---\n")

        stats.ok(
            "## Подтверждённые данные (с привязкой к входам инструментов ТРИЗ)" in brief,
            "бриф содержит заголовок подтверждённых данных с привязкой к инструментам",
        )

        confirmed_part = brief.split("[ПРОБЕЛЫ В ДАННЫХ")[0]
        mgr = _state_from_messages(messages)
        lines = confirmed_part.splitlines()
        for field_key, value in mgr.confirmed.items():
            if value == _SKIPPED_VALUE:
                continue
            value_line_idx = next(
                (i for i, line in enumerate(lines) if value.strip()[:40] in line),
                None,
            )
            has_tool_line = (
                value_line_idx is not None
                and value_line_idx + 1 < len(lines)
                and lines[value_line_idx + 1].strip().startswith("→ ")
                and "Инструмент" in lines[value_line_idx + 1]
            )
            stats.ok(
                has_tool_line,
                f"поле {field_key!r} имеет строку «→ Инструмент» в брифе",
            )

        stats.ok("__interview_state__" not in brief, "бриф не содержит __interview_state__")
        stats.ok("[КОНТЕКСТ:" not in brief, "бриф не содержит [КОНТЕКСТ:")

    except Exception as exc:
        print(f"  ERROR: {exc}")
        traceback.print_exc()
        stats.failed += 1
        stats.errors.append(str(exc))
        brief = None

    return stats, brief


def scenario_analysis(chain: TRIZChain, brief: str) -> ScenarioStats:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ 5 — Анализ (chain.solve)")
    print("=" * 72)
    stats = ScenarioStats("Сценарий 5")

    try:
        print("  Запуск solve() — может занять несколько минут...")
        result = chain.solve(brief)

        for key in REQUIRED_SOLVE_FIELDS:
            value = result.get(key)
            if key == "triz_tools":
                stats.ok(isinstance(value, list) and len(value) > 0, f"поле {key!r} непустое")
            else:
                stats.ok(bool(str(value or "").strip()), f"поле {key!r} присутствует и непустое")

        tools = result.get("triz_tools") or []
        tool_lines = []
        tools_blob_parts: list[str] = []
        for row in tools:
            if isinstance(row, dict):
                name = str(row.get("tool", ""))
                why = str(row.get("why_applied", ""))[:80]
            else:
                name = str(getattr(row, "tool", row))
                why = str(getattr(row, "why_applied", ""))[:80]
            tool_lines.append(f"  • {name} — {why}")
            tools_blob_parts.append(name.lower())

        print("\n--- triz_tools ---")
        for line in tool_lines:
            print(line)

        blob = " ".join(tools_blob_parts)
        for patterns in STEP_21_PATTERNS:
            found = any(p in blob for p in patterns)
            stats.ok(
                found,
                f"маршрут ШАГ 2.1: найден один из {patterns!r} в triz_tools",
            )

    except TRIZChainError as exc:
        print(f"  ERROR (TRIZChain): {exc}")
        stats.failed += 1
        stats.errors.append(str(exc))
    except Exception as exc:
        print(f"  ERROR: {exc}")
        traceback.print_exc()
        stats.failed += 1
        stats.errors.append(str(exc))

    return stats


def main() -> int:
    print("E2E-тест интервью TRIZ (реальные вызовы OpenAI API)")
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")

    all_stats: list[ScenarioStats] = []
    scenario1_messages: list[dict[str, str]] | None = None
    brief: str | None = None

    store, tmpdir = _make_store()
    print(f"Временная БД: {tmpdir}")

    try:
        chain = TRIZChain()
    except TRIZChainError as exc:
        print(f"Не удалось инициализировать TRIZChain: {exc}")
        return 1

    stats1, scenario1_messages = scenario_full_interview(chain, store)
    all_stats.append(stats1)

    stats2 = scenario_tautology_ne_when(chain, store)
    all_stats.append(stats2)

    stats3 = scenario_unknown_cause(chain, store)
    all_stats.append(stats3)

    if scenario1_messages:
        stats4, brief = scenario_brief(scenario1_messages)
        all_stats.append(stats4)
    else:
        print("\nСЦЕНАРИЙ 4 пропущен: нет сообщений из сценария 1")

    if brief:
        stats5 = scenario_analysis(chain, brief)
        all_stats.append(stats5)
    else:
        print("\nСЦЕНАРИЙ 5 пропущен: нет брифа из сценария 4")

    total_passed = sum(s.passed for s in all_stats)
    total_failed = sum(s.failed for s in all_stats)

    print("\n" + "=" * 72)
    print("СВОДКА")
    print("=" * 72)
    for s in all_stats:
        status = "OK" if s.failed == 0 else "FAIL"
        print(f"  [{status}] {s.name}: PASS={s.passed}, FAIL={s.failed}")
        for err in s.errors:
            print(f"         - {err}")
    print(f"\nИтого: PASS={total_passed}, FAIL={total_failed}")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
