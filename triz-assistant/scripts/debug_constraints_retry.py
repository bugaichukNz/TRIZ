#!/usr/bin/env python3
"""Проверка: генерация решений при жёстких constraints завершается за конечное число шагов."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings  # noqa: E402
from backend.llm.chain import TRIZChain  # noqa: E402
from backend.llm.solution_validator import (  # noqa: E402
    MAX_SOLUTION_GENERATION_ATTEMPTS,
    MIN_SOLUTIONS,
    PARTIAL_GENERATION_WARNING,
)

SEP = "=" * 72

# Почти любое инженерное решение нарушает эти ограничения.
NARROW_CONSTRAINTS = [
    "Запрещено изменять поднос, стаканы, напиток, температуру, материалы и форму объектов.",
    "Запрещено добавлять любые новые компоненты, оборудование, покрытия, пропитки и расходники.",
    "Запрещено менять процесс мытья, сушки, переноски и укладки стаканов.",
    "Допустимо только пассивное наблюдение без физического вмешательства в систему.",
]

STUB_CORE = {
    "problem_description": (
        "Мокрые стаканы на подносе оставляют лужи воды при переноске."
    ),
    "technical_contradiction": (
        "Нужно сохранить стаканы сухими на подносе, но они мокрые после мытья."
    ),
    "physical_contradiction": (
        "Стакан: параметр влажность внешней поверхности должен быть высокой, "
        "чтобы обеспечить чистоту после мытья, и должен быть низкой, "
        "чтобы не оставлять капли воды на подносе."
    ),
    "ideal_final_result": (
        "Поднос остаётся сухим при переноске; визуально нет луж на дне подноса."
    ),
    "root_cause": (
        "Капли воды с внешней поверхности стакана стекают на поднос "
        "и не успевают высохнуть до момента переноски."
    ),
    "known_solutions": "Прорезиненные подносы; силиконовые вкладыши; наклонная поверхность.",
    "why_failed": "Вкладыши не держатся; наклон неудобен; прорезиненные подносы дороги.",
    "analysis": {
        "resources_analysis": (
            "Пластиковые подносы, стеклянные стаканы, салфетки, силиконовые вкладыши."
        ),
    },
    "system_context": {
        "constraints": NARROW_CONSTRAINTS,
    },
}


def _fake_solution(solution_id: int, title: str) -> dict:
    return {
        "id": solution_id,
        "title": title,
        "triz_principle": "№1: Разделение",
        "mechanism": "Механизм",
        "applicability": "Поднос САМ выполняет функцию",
        "risks": "Риск",
        "effectiveness_score": 7,
        "complexity_score": 5,
        "cost_score": 5,
        "scalability_score": 6,
    }


def test_retry_cap_without_llm() -> None:
    """Симуляция: каждая попытка отбраковывает всё, кроме одного нового решения."""
    print(SEP)
    print("MOCK: накопление валидных + лимит попыток (без LLM)")
    print(SEP)

    call_count = 0

    def fake_generate(*_args, **_kwargs) -> list[dict]:
        nonlocal call_count
        call_count += 1
        return [
            _fake_solution(1, f"решение попытки {call_count}"),
            _fake_solution(2, "нарушитель constraints"),
        ]

    single_valid = _fake_solution(1, "единственное допустимое решение")

    def fake_validate(batch, *_args, **_kwargs):
        valid = [s for s in batch if "нарушитель" not in s.get("title", "")]
        if valid:
            return False, "все нарушают constraints", [single_valid]
        return False, "все нарушают constraints", []

    chain = TRIZChain()
    with (
        patch.object(chain, "_generate_solutions", side_effect=fake_generate),
        patch("backend.llm.chain.validate_solutions", side_effect=fake_validate),
    ):
        solutions, warning, attempts_used = chain._validate_and_generate_solutions(
            STUB_CORE, STUB_CORE["problem_description"]
        )

    print(f"попыток: {attempts_used} (макс. {MAX_SOLUTION_GENERATION_ATTEMPTS})")
    print(f"накоплено валидных: {len(solutions)}")
    print(f"предупреждение: {warning!r}")

    assert attempts_used == MAX_SOLUTION_GENERATION_ATTEMPTS, (
        f"ожидалось {MAX_SOLUTION_GENERATION_ATTEMPTS} попыток, получено {attempts_used}"
    )
    assert call_count == MAX_SOLUTION_GENERATION_ATTEMPTS
    assert len(solutions) == 1
    assert warning == PARTIAL_GENERATION_WARNING
    print("OK: mock — без зацикливания, частичный результат + предупреждение\n")


def main() -> None:
    test_retry_cap_without_llm()

    print(SEP)
    print("LIVE: жёсткие constraints, лимит попыток генерации решений")
    print(SEP)
    print(f"MAX_SOLUTION_GENERATION_ATTEMPTS = {MAX_SOLUTION_GENERATION_ATTEMPTS}")
    print(f"MIN_SOLUTIONS = {MIN_SOLUTIONS}\n")
    print("Constraints:")
    for line in NARROW_CONSTRAINTS:
        print(f"  • {line}")
    print()

    if not settings.openai_api_key:
        print("Пропуск LIVE-прогона: OPENAI_API_KEY не задан")
        return

    chain = TRIZChain()
    problem = STUB_CORE["problem_description"]

    solutions, warning, attempts_used = chain._validate_and_generate_solutions(
        STUB_CORE, problem
    )

    print(SEP)
    print("ИТОГ LIVE")
    print(SEP)
    print(f"попыток генерации: {attempts_used} (макс. {MAX_SOLUTION_GENERATION_ATTEMPTS})")
    print(f"валидных решений: {len(solutions)}")
    print(f"предупреждение: {warning or '(нет)'}")

    if solutions:
        print("\nРешения:")
        for sol in solutions:
            print(f"  #{sol.get('id')}: {sol.get('title')}")

    if attempts_used > MAX_SOLUTION_GENERATION_ATTEMPTS:
        print("\nПРОБЛЕМА: превышен лимит попыток")
        sys.exit(1)
    if attempts_used < 1:
        print("\nПРОБЛЕМА: не было ни одной попытки генерации")
        sys.exit(1)

    print(f"\nOK: LIVE — пайплайн завершился за {attempts_used} попыток, без зацикливания")


if __name__ == "__main__":
    main()
