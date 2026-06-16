#!/usr/bin/env python3
"""Проверка: детерминированный шаблон ФП не должен пропускать семантически пустые формулировки."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm.fp_validator import (  # noqa: E402
    _matches_fp_formula,
    _has_bilateralism,
    validate_fp,
)

ROOT_CAUSE = (
    "Капли воды с внешней поверхности стакана стекают на поднос "
    "и не успевают высохнуть до момента переноски."
)

GARBAGE_FPS = [
    (
        "нерелевантный параметр (вязкость)",
        "Стакан: параметр вязкость должен быть высокой, чтобы замедлить вытекание, "
        "и должен быть низкой, чтобы напиток легко пилось.",
    ),
    (
        "нерелевантный параметр (цвет подноса)",
        "Поднос: параметр цвет должен быть ярким, чтобы привлекать внимание гостей, "
        "и должен быть тусклым, чтобы не отвлекать официанта.",
    ),
    (
        "абсурдная половина (высокие оптические потери)",
        "Оптический тракт: параметр оптические потери должен быть высокими, "
        "чтобы избежать линзовой системы, и должен быть низкими, "
        "чтобы обеспечить яркое изображение на экране.",
    ),
]

GOOD_FP = (
    "релевантный параметр (влажность поверхности)",
    "Стакан: параметр влажность внешней поверхности должен быть высокой, "
    "чтобы обеспечить чистоту после мытья, и должен быть низкой, "
    "чтобы не оставлять капли воды на подносе.",
)

SEP = "-" * 72


def main() -> None:
    print(SEP)
    print("ДЕТЕРМИНИРОВАННАЯ ПРОВЕРКА (без LLM)")
    print(SEP)
    print(f"root_cause: {ROOT_CAUSE}\n")

    for label, fp in [*GARBAGE_FPS, [GOOD_FP[0], GOOD_FP[1]]]:
        formula = _matches_fp_formula(fp)
        bilateral, _ = _has_bilateralism(fp)
        print(f"[{label}]")
        print(f"  formula={formula}, bilateral={bilateral}")
        print(f"  FP: {fp}\n")

    try:
        from backend.config import settings  # noqa: WPS433
        from backend.llm.chain import TRIZChain  # noqa: WPS433
    except ImportError as exc:
        print(f"Пропуск LLM-прогона: {exc}")
        return

    if not settings.openai_api_key:
        print("\nПропуск LLM-прогона: OPENAI_API_KEY не задан")
        return

    chain = TRIZChain()
    tp = "Необходимо сохранить стаканы сухими на подносе, но при этом они должны быть мокрыми снаружи после мытья."

    print(SEP)
    print("ПОЛНАЯ validate_fp (форма + релевантность)")
    print(SEP)

    ok = True
    for label, fp in [*GARBAGE_FPS, [GOOD_FP[0], GOOD_FP[1]]]:
        passed, feedback = validate_fp(fp, tp, chain._llm, root_cause=ROOT_CAUSE)
        expect = label.startswith("релевантный")
        status = "OK" if passed == expect else "ПРОБЛЕМА"
        if passed != expect:
            ok = False
        print(f"[{status}] {label}: passed={passed}")
        if feedback:
            print(f"  feedback: {feedback}")
        print()

    if ok:
        print("OK: мусор отклонён, релевантный ФП принят")
    else:
        print("ПРОБЛЕМА: валидатор ведёт себя не так, как ожидалось")
        sys.exit(1)


if __name__ == "__main__":
    main()
