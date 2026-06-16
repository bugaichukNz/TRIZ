#!/usr/bin/env python3
"""Быстрый прогон CORE + валидация ФП (attempt 1 / retry) на трёх брифах."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings  # noqa: E402
from backend.llm.chain import TRIZChain  # noqa: E402
from backend.llm.fp_validator import validate_fp  # noqa: E402

BRIEFS = {
    "оптоволокно": PROJECT_ROOT / "scripts" / "brief_optovolokno.txt",
    "тромбоз": PROJECT_ROOT / "scripts" / "brief_tromboz.txt",
    "стаканы": PROJECT_ROOT / "scripts" / "brief_stakany.txt",
}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print(f"Модель: {settings.llm_model}")
    chain = TRIZChain()
    results: list[tuple[str, bool, bool, bool]] = []

    for name, path in BRIEFS.items():
        problem = path.read_text(encoding="utf-8").strip()
        print(f"\n{'=' * 60}\n{name}\n{'=' * 60}")
        core = chain._run_core_analysis(problem)
        fp = core.get("physical_contradiction", "")
        print(f"CORE ФП: {fp}")

        passed, feedback = validate_fp(
            fp,
            core.get("technical_contradiction", ""),
            chain._llm,
            root_cause=core.get("root_cause", ""),
        )
        retry_used = False
        attempt2_passed = passed

        if passed:
            print("attempt 1: PASSED")
        else:
            print(f"attempt 1: FAILED — {feedback}")
            repaired = chain._regenerate_contradictions(problem, core, feedback)
            fp2 = repaired["physical_contradiction"]
            attempt2_passed, feedback2 = validate_fp(
                fp2,
                repaired["technical_contradiction"],
                chain._llm,
                root_cause=core.get("root_cause", ""),
            )
            retry_used = True
            print(f"RETRY ФП: {fp2}")
            status = "PASSED" if attempt2_passed else f"FAILED — {feedback2}"
            print(f"attempt 2: {status}")

        results.append((name, passed, attempt2_passed, retry_used))

    print(f"\n{'=' * 60}\nSUMMARY\n{'=' * 60}")
    for name, a1, a2, retry in results:
        print(
            f"{name}: attempt1={'PASS' if a1 else 'FAIL'}, "
            f"attempt2={'PASS' if a2 else 'FAIL'}, retry_used={retry}"
        )


if __name__ == "__main__":
    main()
