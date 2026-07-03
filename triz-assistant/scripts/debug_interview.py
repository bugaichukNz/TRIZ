#!/usr/bin/env python3
"""Отладка InterviewStateManager без UI и без LLM."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import importlib.util
import inspect


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось загрузить модуль: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_interview_state = _load_module(
    "interview_state",
    PROJECT_ROOT / "backend" / "llm" / "interview_state.py",
)
InterviewStateManager = _interview_state.InterviewStateManager
FIELD_LABELS = _interview_state.FIELD_LABELS
_SKIPPED_VALUE = _interview_state._SKIPPED_VALUE


def _load_chat_brief():
    import types

    backend = types.ModuleType("backend")
    backend_llm = types.ModuleType("backend.llm")
    sys.modules.setdefault("backend", backend)
    sys.modules.setdefault("backend.llm", backend_llm)
    sys.modules["backend.llm.interview_state"] = _interview_state
    return _load_module("chat_brief", PROJECT_ROOT / "backend" / "chat_brief.py")


_chat_brief = _load_chat_brief()
compile_interview_brief = _chat_brief.compile_interview_brief
_GAPS_HEADER = _chat_brief._GAPS_HEADER


def _load_chat_preprocessor():
    import types

    lc = types.ModuleType("langchain_core")
    lc_messages = types.ModuleType("langchain_core.messages")

    class _Msg:
        def __init__(self, content: str = "") -> None:
            self.content = content

    lc_messages.HumanMessage = _Msg
    lc_messages.SystemMessage = _Msg
    sys.modules.setdefault("langchain_core", lc)
    sys.modules["langchain_core.messages"] = lc_messages
    return _load_module(
        "chat_preprocessor",
        PROJECT_ROOT / "backend" / "llm" / "chat_preprocessor.py",
    )


_chat_preprocessor = _load_chat_preprocessor()
_ne_when_heuristic = _chat_preprocessor._ne_when_heuristic

CHAT_OPENING_MESSAGE = (
    "Добрый день. Прежде чем мы перейдём к анализу, мне нужно собрать исходные "
    "данные о задаче. Буду задавать вопросы по одному.\n"
    "Начнём с идентификации. Как кратко называется задача, которую нужно решить?"
)

SEP = "-" * 72


def _print_state(mgr: InterviewStateManager, *, step: str) -> None:
    state = mgr._state  # noqa: SLF001 — отладочный скрипт
    nxt = mgr.next_field_to_ask()
    nxt_label = FIELD_LABELS.get(nxt[0], nxt[0]) if nxt else None
    print(f"\n{SEP}")
    print(f"ХОД: {step}")
    print(f"pending_field: {state.get('pending_field')!r}")
    print(f"asked: {state.get('asked')}")
    print(f"attempts: {state.get('attempts', {})}")
    print("confirmed:")
    for key, value in state.get("confirmed", {}).items():
        print(f"  {key}: {value!r}")
    if not state.get("confirmed"):
        print("  (пусто)")
    print(f"следующий вопрос: {nxt[0] if nxt else None!r} — {nxt_label!r}")


def simulate_turn(
    messages: list[dict[str, str]],
    user_reply: str,
    *,
    step: str,
    reject_field: Callable[[str, str], bool] | None = None,
    fake_assistant: str | None = None,
) -> tuple[list[dict[str, str]], InterviewStateManager]:
    messages = list(messages)
    messages.append({"role": "user", "content": user_reply})
    mgr = InterviewStateManager(messages)
    last_user = InterviewStateManager.last_user_message(messages)
    print(f"\n>>> raw last_user_message: {last_user!r}")
    confirm_kwargs: dict = {}
    if "messages" in inspect.signature(mgr.confirm_pending_answer).parameters:
        confirm_kwargs["messages"] = messages
    mgr.confirm_pending_answer(last_user, reject_field=reject_field, **confirm_kwargs)
    _print_state(mgr, step=f"{step} — после confirm_pending_answer")
    mgr.prepare_next_pending()
    _print_state(mgr, step=f"{step} — после prepare_next_pending")
    messages = mgr.inject_state(messages)
    if fake_assistant:
        messages.append({"role": "assistant", "content": fake_assistant})
    return messages, mgr


def scenario_clean() -> None:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ A: чистые ответы")
    print("=" * 72)
    messages: list[dict[str, str]] = [
        {"role": "assistant", "content": CHAT_OPENING_MESSAGE},
    ]
    replies = [
        "Контроль сварных швов на трубопроводе",
        "Трещины в зоне термического влияния",
        "Участок сварного соединения КС-2",
        "При температуре сварки выше 200 °C",
    ]
    questions = [
        "Какой конкретный нежелательный эффект вы наблюдаете?",
        "Где именно проявляется НЭ?",
        "При каких условиях проявляется НЭ?",
    ]
    for i, reply in enumerate(replies):
        q = questions[i - 1] if i > 0 else None
        messages, _ = simulate_turn(
            messages,
            reply,
            step=f"ответ {i + 1}",
            fake_assistant=q,
        )


def scenario_garbage() -> None:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ B: мусор в content (таймстемп + текст вопроса)")
    print("=" * 72)
    assistant_q = (
        "Опишите конкретный физический факт: что именно происходит не так?"
    )
    messages: list[dict[str, str]] = [
        {"role": "assistant", "content": CHAT_OPENING_MESSAGE},
    ]
    messages, _ = simulate_turn(
        messages,
        "Контроль сварных швов",
        step="подготовка pending=ne_fact",
        fake_assistant=assistant_q,
    )
    garbage_reply = (
        "15:37\n\n"
        f"{assistant_q}\n\n"
        "Трещины в сварном шве длиной до 3 мм"
    )
    messages, mgr = simulate_turn(
        messages,
        garbage_reply,
        step="мусорный ответ на ne_fact",
        fake_assistant="Где проявляется НЭ?",
    )
    ne_fact = mgr._state["confirmed"].get("ne_fact", "")  # noqa: SLF001
    print(f"\nИТОГ ne_fact: {ne_fact!r}")
    if "15:37" in ne_fact or assistant_q in ne_fact:
        print("ПРОБЛЕМА: в confirmed попал мусор")
    else:
        print("OK: confirmed без мусора")


def scenario_repeat_reject() -> None:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ C: тавтология ne_when — переспрос, затем пропуск")
    print("=" * 72)

    def reject_ne_when(field: str, value: str) -> bool:
        return field == "ne_when"

    clarify_q = (
        "Вы назвали процесс, а нужны конкретные условия: "
        "температура, режим, тип шва"
    )
    messages: list[dict[str, str]] = [
        {"role": "assistant", "content": CHAT_OPENING_MESSAGE},
    ]
    messages.append(
        {
            "role": "system",
            "content": "__interview_state__:"
            + json.dumps(
                {
                    "confirmed": {
                        "ne_fact": "Трещины",
                        "ne_where": "КС-2",
                    },
                    "pending_field": "ne_when",
                    "asked": ["ne_fact", "ne_where", "ne_when"],
                    "attempts": {},
                },
                ensure_ascii=False,
            ),
        }
    )
    messages.append(
        {
            "role": "assistant",
            "content": "При каких условиях проявляется НЭ?",
        }
    )

    tautology = "При проведении контроля швов"
    messages, mgr = simulate_turn(
        messages,
        tautology,
        step="1-й ответ (тавтология)",
        reject_field=reject_ne_when,
        fake_assistant=clarify_q,
    )
    attempts = mgr._state.get("attempts", {})  # noqa: SLF001
    pending = mgr._state.get("pending_field")  # noqa: SLF001
    confirmed = mgr._state.get("confirmed", {})  # noqa: SLF001
    ctx = mgr.build_context_message()
    print(f"\n--- контекст после 1-го отклонения ---\n{ctx}\n")
    print(
        f"ПРОМЕЖУТОК: pending={pending!r}, attempts={attempts!r}, "
        f"ne_when confirmed={confirmed.get('ne_when')!r}"
    )
    if pending == "ne_when" and attempts.get("ne_when") == 1 and "ne_when" not in confirmed:
        print("OK: 1-я тавтология — переспрос ne_when (не пропуск)")
    else:
        print("ПРОБЛЕМА: после 1-й тавтологии ожидался переспрос ne_when")

    messages, mgr = simulate_turn(
        messages,
        tautology,
        step="2-й ответ (тавтология)",
        reject_field=reject_ne_when,
    )
    pending = mgr._state.get("pending_field")  # noqa: SLF001
    confirmed = mgr._state.get("confirmed", {})  # noqa: SLF001
    print(
        f"\nИТОГ: pending={pending!r}, ne_when confirmed={confirmed.get('ne_when')!r}"
    )
    if confirmed.get("ne_when") == _interview_state._SKIPPED_VALUE and pending != "ne_when":
        print("OK: после 2-й тавтологии ne_when пропущено, интервью движется дальше")
    elif pending == "ne_when" and "ne_when" not in confirmed:
        print("ПРОБЛЕМА: зацикливание на ne_when")
    elif "ne_when" in confirmed and confirmed["ne_when"] != _interview_state._SKIPPED_VALUE:
        print("OK: ne_when закрыто ответом")


def scenario_echo_question_phrase() -> None:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ D: ответ повторяет формулировку вопроса, затем суть")
    print("=" * 72)
    assistant_q = "В чём проявляется нежелательный эффект?"
    user_reply = "Нежелательный эффект проявляется так: трещины в шве до 3 мм"

    messages: list[dict[str, str]] = [
        {"role": "assistant", "content": CHAT_OPENING_MESSAGE},
    ]
    messages, _ = simulate_turn(
        messages,
        "Контроль сварных швов",
        step="подготовка pending=ne_fact",
        fake_assistant=assistant_q,
    )

    # Показываем сырой content и результат sanitize до confirm
    probe_messages = list(messages)
    probe_messages.append({"role": "user", "content": user_reply})
    sanitized = InterviewStateManager.sanitize_user_answer(user_reply, probe_messages)
    print(f"\n>>> raw content: {user_reply!r}")
    print(f">>> sanitize_user_answer: {sanitized!r}")

    messages, mgr = simulate_turn(
        messages,
        user_reply,
        step="ответ с эхо-формулировкой вопроса",
        fake_assistant="Где проявляется НЭ?",
    )
    ne_fact = mgr._state["confirmed"].get("ne_fact", "")  # noqa: SLF001
    print(f"\nИТОГ ne_fact: {ne_fact!r}")
    if not ne_fact or "трещин" not in ne_fact.lower():
        print("ПРОБЛЕМА: sanitize вырезала содержательную часть ответа")
    elif assistant_q in ne_fact:
        print("ПРОБЛЕМА: в confirmed попал текст вопроса ассистента")
    else:
        print("OK: содержательная часть сохранена")


def scenario_numeric_ratios() -> None:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ E: числа, похожие на время, внутри содержательного ответа")
    print("=" * 72)

    replies = [
        ("constraints", "соотношение ПДМС 9:1", "9:1"),
        ("expected_result", "давление 12:1 бар", "12:1"),
        ("economic_result", "потери < 0.05", "0.05"),
    ]

    messages: list[dict[str, str]] = [
        {"role": "assistant", "content": CHAT_OPENING_MESSAGE},
    ]

    ok = True
    for field, reply, needle in replies:
        probe = list(messages)
        probe.append({"role": "user", "content": reply})
        sanitized = InterviewStateManager.sanitize_user_answer(reply, probe)
        print(f"\n>>> {field}: raw={reply!r}")
        print(f">>> sanitize_user_answer: {sanitized!r}")
        if sanitized != reply or needle not in sanitized:
            print(f"ПРОБЛЕМА: sanitize изменила ответ для {field}")
            ok = False

    # Контроль: отдельная строка-таймстемп по-прежнему режется
    ts_cases = [
        ("15:37", ""),
        ("01.06.2026 15:37", ""),
        ("15:37\nсоотношение ПДМС 9:1", "соотношение ПДМС 9:1"),
    ]
    for raw, expected in ts_cases:
        got = InterviewStateManager.sanitize_user_answer(raw, [])
        print(f"\n>>> timestamp probe raw={raw!r} -> {got!r}")
        if got != expected:
            print("ПРОБЛЕМА: неверная обработка таймстемпа")
            ok = False

    if ok:
        print("\nOK: содержательные ответы и таймстемпы обработаны корректно")


def scenario_compile_brief() -> None:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ F: compile_interview_brief с пропущенным полем")
    print("=" * 72)

    ne_fact = "Трещины в сварном шве"
    ne_where = "Участок сварного соединения КС-2"
    ne_when_label = FIELD_LABELS["ne_when"]
    context_ephemeral = (
        "[КОНТЕКСТ: данные, подтверждённые задачедателем]\n"
        "• НЭ (факт): Трещины\n"
        "• НЭ — где: КС-2"
    )

    messages: list[dict[str, str]] = [
        {"role": "assistant", "content": CHAT_OPENING_MESSAGE},
        {"role": "user", "content": "Контроль сварных швов на трубопроводе"},
        {"role": "assistant", "content": "Опишите конкретный физический факт НЭ."},
        {"role": "assistant", "content": context_ephemeral},
        {"role": "user", "content": ne_fact},
        {"role": "assistant", "content": "Где проявляется НЭ?"},
        {"role": "user", "content": ne_where},
        {"role": "assistant", "content": "При каких условиях проявляется НЭ?"},
        {"role": "user", "content": "При проведении контроля швов"},
        {"role": "assistant", "content": "Какие последствия, если не устранить?"},
    ]

    mgr = InterviewStateManager(messages)
    mgr._state.update(  # noqa: SLF001
        {
            "confirmed": {
                "ne_fact": ne_fact,
                "ne_where": ne_where,
                "ne_when": _SKIPPED_VALUE,
            },
            "pending_field": "consequences",
            "asked": ["ne_fact", "ne_where", "ne_when"],
            "attempts": {"ne_when": 2},
        }
    )
    messages = mgr.inject_state(messages)

    brief = compile_interview_brief(messages)

    print("\n--- итоговый бриф ---\n")
    print(brief)
    print("\n--- конец брифа ---\n")

    try:
        assert (
            f": {_SKIPPED_VALUE}" not in brief
        ), f'пропуск "{_SKIPPED_VALUE}" попал в бриф как значение поля'

        confirmed_part = brief.split(_GAPS_HEADER)[0]
        assert "## Подтверждённые данные (с привязкой к входам инструментов ТРИЗ)" in confirmed_part
        assert ne_fact in confirmed_part, "ne_fact отсутствует в подтверждённых данных"
        assert ne_where in confirmed_part, "ne_where отсутствует в подтверждённых данных"
        assert ne_when_label not in confirmed_part, "пропущенное поле попало в подтверждённые данные"

        gaps_part = brief.split(_GAPS_HEADER, 1)[1]
        assert ne_when_label in gaps_part, "ne_when отсутствует в блоке пробелов"
        assert "данные не получены" in gaps_part, "нет пометки «данные не получены»"

        gaps_pos = brief.find(_GAPS_HEADER)
        dialog_pos = brief.find("## Диалог (справочно)")
        assert gaps_pos != -1, "блок ПРОБЕЛОВ не найден"
        assert dialog_pos != -1, "секция диалога не найдена"
        assert gaps_pos < dialog_pos, "блок ПРОБЕЛОВ должен идти до диалога"

        assert "__interview_state__" not in brief, "служебное состояние попало в бриф"
        assert "[КОНТЕКСТ:" not in brief, "эфемерный контекст попал в бриф"
    except AssertionError as exc:
        print(f"ПРОБЛЕМА: {exc}")
    else:
        print("OK: все проверки compile_interview_brief пройдены")


def scenario_household_ne_when() -> None:
    print("\n" + "=" * 72)
    print("СЦЕНАРИЙ G: ne_when — бытовая задача (стаканы)")
    print("=" * 72)

    household = "когда наливают холодный напиток в тёплом помещении"
    industrial_tautology = "при проведении контроля швов"

    h_house = _ne_when_heuristic(household)
    h_taut = _ne_when_heuristic(industrial_tautology)
    print(f"\n>>> heuristic({household!r}) = {h_house!r}")
    print(f">>> heuristic({industrial_tautology!r}) = {h_taut!r}")

    ok = True
    if h_house is not False:
        print("ПРОБЛЕМА: бытовой ответ ne_when ошибочно классифицирован как тавтология")
        ok = False
    if h_taut is not True:
        print("ПРОБЛЕМА: промышленная тавтология ne_when должна отсекаться эвристикой")
        ok = False

    def reject_ne_when(field: str, value: str) -> bool:
        if field != "ne_when":
            return False
        verdict = _ne_when_heuristic(value)
        return True if verdict is True else False

    messages: list[dict[str, str]] = [
        {"role": "assistant", "content": CHAT_OPENING_MESSAGE},
    ]
    messages.append(
        {
            "role": "system",
            "content": "__interview_state__:"
            + json.dumps(
                {
                    "confirmed": {
                        "ne_fact": "Мокрые стаканы оставляют лужи на подносе",
                        "ne_where": "Дно подноса под стаканами",
                    },
                    "pending_field": "ne_when",
                    "asked": ["ne_fact", "ne_where", "ne_when"],
                    "attempts": {},
                },
                ensure_ascii=False,
            ),
        }
    )
    messages.append(
        {"role": "assistant", "content": "При каких условиях проявляется НЭ?"},
    )

    messages, mgr = simulate_turn(
        messages,
        household,
        step="бытовой ответ ne_when",
        reject_field=reject_ne_when,
        fake_assistant="Какие последствия, если не устранить?",
    )
    confirmed = mgr._state.get("confirmed", {})  # noqa: SLF001
    print(f"\nИТОГ ne_when: {confirmed.get('ne_when')!r}")
    if confirmed.get("ne_when") == household:
        print("OK: бытовой ne_when подтверждён в интервью")
    else:
        print("ПРОБЛЕМА: бытовой ne_when не попал в confirmed")
        ok = False

    if ok:
        print("\nOK: валидатор ne_when принимает бытовую конкретику")


def main() -> None:
    scenario_clean()
    scenario_garbage()
    scenario_repeat_reject()
    scenario_echo_question_phrase()
    scenario_numeric_ratios()
    scenario_compile_brief()
    scenario_household_ne_when()


if __name__ == "__main__":
    main()
