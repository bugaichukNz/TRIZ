#!/usr/bin/env python3
"""Пошаговый прогон solve()-пайплайна: печать каждой стадии для отладки качества."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings  # noqa: E402
from backend.llm.chain import TRIZChain, TRIZChainError  # noqa: E402
from backend.llm.fp_validator import validate_fp  # noqa: E402
from backend.llm.models import enrich_legacy_fields  # noqa: E402
from backend.llm.solution_validator import MAX_SOLUTION_GENERATION_ATTEMPTS  # noqa: E402

SCRIPTS_DIR = Path(__file__).resolve().parent

# Пути к брифам; если файлов нет — кейс пропускается с предупреждением.
DEFAULT_BRIEFS: dict[str, Path] = {
    "оптоволокно": SCRIPTS_DIR / "brief_optovolokno.txt",
    "тромбоз": SCRIPTS_DIR / "brief_tromboz.txt",
    "стаканы": SCRIPTS_DIR / "brief_stakany.txt",
}

SEP = "=" * 72


def section(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")


def dump(label: str, data: Any) -> None:
    print(f"\n--- {label} ---")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(data)


def load_brief(path: Path) -> str | None:
    if not path.is_file():
        print(f"[WARN] Бриф не найден: {path}")
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        print(f"[WARN] Бриф пуст: {path}")
        return None
    return text


def debug_fp_stage(chain: TRIZChain, problem: str, core: dict) -> dict:
    """Валидация ФП с печатью попыток и retry (как в solve())."""
    stage: dict[str, Any] = {"attempts": []}

    passed, feedback = validate_fp(
        core.get("physical_contradiction", ""),
        core.get("technical_contradiction", ""),
        chain._llm,
        root_cause=core.get("root_cause", ""),
        core=core,
        problem=problem,
    )
    stage["attempts"].append(
        {
            "attempt": 1,
            "passed": passed,
            "feedback": feedback or None,
            "technical_contradiction": core.get("technical_contradiction"),
            "physical_contradiction": core.get("physical_contradiction"),
        }
    )

    if passed:
        dump("ФП-валидатор", stage)
        return core

    try:
        repaired = chain._regenerate_contradictions(problem, core, feedback)
        core["technical_contradiction"] = repaired["technical_contradiction"]
        core["physical_contradiction"] = repaired["physical_contradiction"]
        passed2, feedback2 = validate_fp(
            core["physical_contradiction"],
            core["technical_contradiction"],
            chain._llm,
            root_cause=core.get("root_cause", ""),
            core=core,
            problem=problem,
        )
        stage["retry"] = {
            "technical_contradiction": repaired["technical_contradiction"],
            "physical_contradiction": repaired["physical_contradiction"],
        }
        stage["attempts"].append(
            {
                "attempt": 2,
                "passed": passed2,
                "feedback": feedback2 or None,
                "technical_contradiction": core.get("technical_contradiction"),
                "physical_contradiction": core.get("physical_contradiction"),
            }
        )
    except Exception as exc:
        stage["retry_error"] = str(exc)

    dump("ФП-валидатор (+ retry)", stage)
    return core


def debug_solutions_stage(chain: TRIZChain, problem: str, core: dict) -> list[dict]:
    """Генерация решений + критик с печатью попыток."""
    try:
        solutions, warning, attempts_used = chain._validate_and_generate_solutions(
            core, problem
        )
    except Exception as exc:
        dump("Решения (+ критик)", {"generation_error": str(exc)})
        return []

    dump(
        "Решения (+ критик)",
        {
            "attempts_used": attempts_used,
            "max_attempts": MAX_SOLUTION_GENERATION_ATTEMPTS,
            "solution_count": len(solutions),
            "generation_warning": warning or None,
            "solution_titles": [s.get("title") for s in solutions],
            "solution_concepts": solutions,
        },
    )
    return solutions


def run_pipeline_debug(chain: TRIZChain, problem: str, label: str) -> dict:
    """Полный пайплайн с печатью каждой стадии."""
    section(f"БРИФ: {label} | символов: {len(problem)}")

    section("1. CORE-АНАЛИЗ (TRIZAnalysisCore)")
    core = chain._run_core_analysis(problem)
    dump(
        "core (кратко)",
        {
            "problem_description": core.get("problem_description"),
            "root_cause": core.get("root_cause"),
            "technical_contradiction": core.get("technical_contradiction"),
            "physical_contradiction": core.get("physical_contradiction"),
            "contradiction_type": core.get("contradiction_type"),
            "ideal_final_result": core.get("ideal_final_result"),
            "analysis": core.get("analysis"),
            "triz_tools_count": len(core.get("triz_tools") or []),
        },
    )
    dump("core (полный JSON)", core)

    section("2. ПСА + ФП-ВАЛИДАТОР (validate_and_fix_fp)")
    core_before = {
        "root_cause": core.get("root_cause"),
        "physical_contradiction": core.get("physical_contradiction"),
        "causal_chains": (core.get("analysis") or {}).get("causal_chains"),
    }
    core = chain._validate_and_fix_fp(problem, core)
    dump(
        "ПСА/ФП до → после",
        {
            "before": core_before,
            "after": {
                "root_cause": core.get("root_cause"),
                "physical_contradiction": core.get("physical_contradiction"),
                "causal_chains": (core.get("analysis") or {}).get("causal_chains"),
            },
        },
    )

    section("3. РЕШЕНИЯ + КРИТИК")
    solutions = debug_solutions_stage(chain, problem, core)

    section("4. РЕКОМЕНДАЦИИ + ФИНАЛЬНЫЙ PAYLOAD")
    payload = chain._assemble_payload(core, solutions)
    payload = enrich_legacy_fields(payload)
    dump(
        "payload (кратко)",
        {
            "contradiction_type": payload.get("contradiction_type"),
            "root_cause": payload.get("root_cause"),
            "technical_contradiction": payload.get("technical_contradiction"),
            "physical_contradiction": payload.get("physical_contradiction"),
            "solution_count": len(payload.get("solution_concepts") or []),
            "solution_titles": [
                f"#{s.get('id')}: {s.get('title')}"
                for s in (payload.get("solution_concepts") or [])
            ],
            "priority_solution_id": (payload.get("recommendations") or {}).get(
                "priority_solution_id"
            ),
            "executive_summary": payload.get("executive_summary"),
        },
    )
    dump("payload (полный JSON)", payload)

    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Пошаговая отладка TRIZ solve()-пайплайна на брифах из файлов."
    )
    parser.add_argument(
        "--brief",
        type=Path,
        help="Один бриф (путь к .txt); иначе — оптоволокно и тромбоз из scripts/",
    )
    parser.add_argument(
        "--name",
        default="custom",
        help="Метка брифа при --brief",
    )
    parser.add_argument(
        "--only",
        choices=list(DEFAULT_BRIEFS.keys()),
        help="Запустить только один из стандартных брифов",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Включить логи backend (INFO)",
    )
    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not settings.openai_api_key:
        print("ОШИБКА: OPENAI_API_KEY не задан в .env")
        sys.exit(1)

    print(f"Модель: {settings.llm_model}")
    print(f"Стандартные пути брифов:")
    for name, path in DEFAULT_BRIEFS.items():
        exists = "OK" if path.is_file() else "нет файла"
        print(f"  {name}: {path} [{exists}]")

    try:
        chain = TRIZChain()
    except TRIZChainError as exc:
        print(f"ОШИБКА инициализации TRIZChain: {exc}")
        sys.exit(1)

    jobs: list[tuple[str, str]] = []

    if args.brief:
        text = load_brief(args.brief)
        if text:
            jobs.append((args.name, text))
    else:
        briefs = DEFAULT_BRIEFS
        if args.only:
            briefs = {args.only: DEFAULT_BRIEFS[args.only]}
        for name, path in briefs.items():
            text = load_brief(path)
            if text:
                jobs.append((name, text))

    if not jobs:
        print(
            "\nНет брифов для прогона. Положите файлы:\n"
            f"  {DEFAULT_BRIEFS['оптоволокно']}\n"
            f"  {DEFAULT_BRIEFS['тромбоз']}\n"
            "или укажите --brief path/to/brief.txt"
        )
        sys.exit(1)

    for label, problem in jobs:
        try:
            run_pipeline_debug(chain, problem, label)
        except TRIZChainError as exc:
            print(f"\n[ОШИБКА пайплайна «{label}»]: {exc}")
            sys.exit(1)

    print(f"\n{SEP}\nГотово: прогон {len(jobs)} бриф(ов).\n{SEP}")


if __name__ == "__main__":
    main()
