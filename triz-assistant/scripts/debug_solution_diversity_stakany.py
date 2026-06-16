#!/usr/bin/env python3
"""Прогон «стаканы»: финальные решения должны опираться на разные механизмы."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings  # noqa: E402
from backend.llm.chain import TRIZChain  # noqa: E402
from backend.llm.solution_validator import (  # noqa: E402
    MIN_DISTINCT_APPROACHES,
    _dominant_mechanism_clusters,
    _heuristic_diversity_check,
    _mechanism_cluster_hits,
    _principle_key,
    check_solution_diversity,
)

BRIEF_PATH = PROJECT_ROOT / "scripts" / "brief_stakany.txt"
SEP = "=" * 72


def _print_diversity_report(solutions: list[dict]) -> None:
    print("\n--- разнообразие финального набора ---")
    for sol in solutions:
        sid = sol.get("id")
        principle = _principle_key(sol)
        stems = sorted(_mechanism_cluster_hits(sol)) or ["(нет кластера)"]
        print(f"  #{sid}: принцип={principle!r}")
        print(f"       title: {sol.get('title')}")
        print(f"       stems: {', '.join(stems)}")

    principles = [_principle_key(s) for s in solutions]
    unique_principles = sorted(set(principles))
    print(f"\nуникальных принципов: {len(unique_principles)} — {unique_principles}")

    clusters = _dominant_mechanism_clusters(solutions)
    if clusters:
        print("кластеры механизмов (>=2 решений):")
        for stem, count, ids in clusters:
            print(f"  «{stem}»: {count} шт. ({', '.join(f'#{i}' for i in ids)})")
    else:
        print("кластеры механизмов (>=2 решений): нет")


def test_heuristic_rejects_silicone_variations() -> None:
    print(SEP)
    print("MOCK: эвристика отклоняет три силиконовые вариации")
    print(SEP)
    collapsed = [
        {
            "id": 1,
            "title": "Силиконовая подкладка под стакан",
            "triz_principle": "№15: Динамичность",
            "mechanism": "Силиконовый вкладыш собирает воду",
            "applicability": "Поднос САМ",
        },
        {
            "id": 2,
            "title": "Formный силиконовый вкладыш",
            "triz_principle": "№15: Динамичность",
            "mechanism": "Formный вкладыш из силикона",
            "applicability": "Поднос САМ",
        },
        {
            "id": 3,
            "title": "Прорезиненное гнездо",
            "triz_principle": "№1: Разделение",
            "mechanism": "Прорезиненное гнездо для стакана",
            "applicability": "Поднос САМ",
        },
    ]
    ok, feedback = _heuristic_diversity_check(collapsed)
    print(f"passed={ok}")
    print(f"feedback: {feedback[:300]}...")
    assert not ok, "ожидалось отклонение схлопнутого набора"
    print("OK: эвристика ловит вариации одной идеи\n")


def test_heuristic_accepts_diverse_set() -> None:
    print(SEP)
    print("MOCK: эвристика принимает разные механизмы")
    print(SEP)
    diverse = [
        {
            "id": 1,
            "title": "Текстурированное дно подноса",
            "triz_principle": "№17: Переход в другое измерение",
            "mechanism": "Микроканавки на дне подноса отводят воду",
            "applicability": "Поднос САМ",
        },
        {
            "id": 2,
            "title": "Пауза перед переносом",
            "triz_principle": "№10: Предварительное действие",
            "mechanism": "Краткая сушка на стойке перед переносом",
            "applicability": "Стойка САМА",
        },
        {
            "id": 3,
            "title": "Организация линии выдачи",
            "triz_principle": "№13: Наоборот",
            "mechanism": "Зона выдачи в надсистеме с принудительным обдувом",
            "applicability": "Зал САМ",
        },
    ]
    ok, feedback = _heuristic_diversity_check(diverse)
    print(f"passed={ok}, feedback={feedback!r}")
    assert ok, f"ожидался проход разнообразного набора: {feedback}"
    print("OK: эвристика пропускает разные механизмы\n")


def run_stakany_live() -> None:
    print(SEP)
    print("LIVE: стаканы — генерация решений с проверкой разнообразия")
    print(SEP)

    if not BRIEF_PATH.is_file():
        print(f"ОШИБКА: бриф не найден: {BRIEF_PATH}")
        sys.exit(1)

    if not settings.openai_api_key:
        print("Пропуск LIVE: OPENAI_API_KEY не задан")
        return

    brief = BRIEF_PATH.read_text(encoding="utf-8").strip()
    chain = TRIZChain()

    print("Core-анализ...")
    core = chain._run_core_analysis(brief)
    core = chain._validate_and_fix_fp(brief, core)

    print("Генерация решений (до 3 попыток)...")
    solutions, warning, attempts = chain._validate_and_generate_solutions(core, brief)

    print(f"\nпопыток: {attempts}, решений: {len(solutions)}")
    if warning:
        print(f"предупреждение: {warning}")

    _print_diversity_report(solutions)

    resources = (core.get("analysis") or {}).get("resources_analysis", "")
    div_ok, div_feedback = check_solution_diversity(solutions, resources, chain._llm)
    print(f"\ncheck_solution_diversity: passed={div_ok}")
    if div_feedback:
        print(f"feedback: {div_feedback[:400]}...")

    if len(solutions) < 2:
        print("\nПРОБЛЕМА: слишком мало решений")
        sys.exit(1)

    unique_principles = len({_principle_key(s) for s in solutions})
    required = min(MIN_DISTINCT_APPROACHES, len(solutions))
    clusters = _dominant_mechanism_clusters(solutions)
    max_cluster = max((c[1] for c in clusters), default=0)

    ok = True
    if unique_principles < required:
        print(
            f"\nПРОБЛЕМА: только {unique_principles} уникальных принципов "
            f"(нужно >= {required})"
        )
        ok = False
    if max_cluster >= 3:
        print(f"\nПРОБЛЕМА: кластер с {max_cluster} вариациями одной идеи")
        ok = False
    if not div_ok:
        print("\nПРОБЛЕМА: LLM/эвристика разнообразия не пройдена")
        ok = False

    if ok:
        print(
            f"\nOK: {len(solutions)} решений, {unique_principles} разных принципов, "
            f"макс. кластер={max_cluster}"
        )
    else:
        sys.exit(1)


def main() -> None:
    test_heuristic_rejects_silicone_variations()
    test_heuristic_accepts_diverse_set()
    run_stakany_live()


if __name__ == "__main__":
    main()
