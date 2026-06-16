#!/usr/bin/env python3
"""Диагностика: почему validate_solutions не даёт passed=True за 3 попытки."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings  # noqa: E402
from backend.llm.chain import TRIZChain  # noqa: E402
from backend.llm.fp_validator import validate_fp  # noqa: E402
from backend.llm.solution_validator import (  # noqa: E402
    MAX_SOLUTION_GENERATION_ATTEMPTS,
    MIN_SOLUTIONS,
    _build_feedback_from_items,
    _check_constraint_violations,
    _heuristic_constraint_violation,
    _heuristic_diversity_check,
    _heuristic_precheck,
    _llm_checklist,
    _llm_constraint_check,
    check_solution_diversity,
    merge_valid_solutions,
    select_diverse_solutions,
    validate_solutions,
)

BRIEFS = {
    "оптоволокно": PROJECT_ROOT / "scripts" / "brief_optovolokno.txt",
    "тромбоз": PROJECT_ROOT / "scripts" / "brief_tromboz.txt",
    "стаканы": PROJECT_ROOT / "scripts" / "brief_stakany.txt",
}


def _analyze_batch(
    chain: TRIZChain,
    core: dict,
    problem: str,
    batch: list[dict],
) -> dict[str, Any]:
    """Пошаговая разбивка валидации одного батча."""
    constraints = chain._get_constraints(core)
    analysis = core.get("analysis") or {}
    resources = analysis.get("resources_analysis", "")
    known, why_failed, _ = chain._get_attempt_history(core, problem)
    ifr = core.get("ideal_final_result", "")

    report: dict[str, Any] = {
        "generated_count": len(batch),
        "titles": [s.get("title") for s in batch],
    }

    # --- constraints по каждому решению ---
    constraint_items: list[dict] = []
    for sol in batch:
        sid = sol.get("id")
        h_viol, h_text, h_reason = _heuristic_constraint_violation(
            sol, "\n".join(f"• {c}" for c in constraints)
        )
        constraint_items.append(
            {
                "id": sid,
                "title": sol.get("title"),
                "heuristic_violation": h_viol,
                "heuristic_reason": h_reason or None,
            }
        )
    report["constraints_per_solution"] = constraint_items

    valid_after_c, rejected, constraint_feedback = _check_constraint_violations(
        batch, constraints, chain._llm
    )
    report["constraints"] = {
        "rejected_count": len(rejected),
        "rejected_titles": [s.get("title") for s in rejected],
        "valid_after_filter": len(valid_after_c),
        "has_feedback": bool(constraint_feedback),
        "feedback_preview": (constraint_feedback or "")[:400],
    }

    # --- precheck ---
    ok_pre, pre_feedback = _heuristic_precheck(valid_after_c)
    report["precheck"] = {"ok": ok_pre, "feedback": pre_feedback or None}

    # --- quality checklist ---
    quality: dict[str, Any] = {"skipped": True}
    if ok_pre and valid_after_c:
        try:
            result = _llm_checklist(
                valid_after_c, known, why_failed, resources, ifr, chain._llm
            )
            items = []
            for item in result.items:
                items.append(
                    {
                        "id": item.solution_id,
                        "not_dead_end_duplicate": item.not_dead_end_duplicate,
                        "uses_specific_resource": item.uses_specific_resource,
                        "advances_ifr": item.advances_ifr,
                        "failed": not (
                            item.not_dead_end_duplicate
                            and item.uses_specific_resource
                            and item.advances_ifr
                        ),
                    }
                )
            quality = {
                "skipped": False,
                "passed": result.passed,
                "items": items,
                "failed_items": [i for i in items if i["failed"]],
                "feedback": result.feedback or _build_feedback_from_items(
                    valid_after_c, result.items
                ),
            }
        except Exception as exc:
            quality = {"skipped": False, "error": str(exc)}

    report["quality"] = quality

    # --- diversity на отфильтрованном батче ---
    div_batch: dict[str, Any] = {"skipped": True}
    if valid_after_c:
        h_ok, h_fb = _heuristic_diversity_check(valid_after_c)
        llm_ok, llm_fb = check_solution_diversity(
            valid_after_c, resources, chain._llm
        )
        div_batch = {
            "skipped": False,
            "heuristic_ok": h_ok,
            "heuristic_feedback": h_fb or None,
            "llm_ok": llm_ok,
            "llm_feedback": (llm_fb or "")[:400] or None,
        }
    report["diversity_on_batch"] = div_batch

    # --- итог validate_solutions ---
    passed, feedback, valid_out = validate_solutions(
        batch, known, why_failed, resources, ifr, chain._llm, constraints
    )
    report["validate_solutions"] = {
        "passed": passed,
        "valid_count": len(valid_out),
        "feedback_preview": (feedback or "")[:500],
    }

    # --- почему passed=False (декомпозиция) ---
    blockers: list[str] = []
    if constraint_feedback:
        blockers.append(
            f"constraints: отсечено {len(rejected)} "
            f"(осталось {len(valid_after_c)}; блокирует только если < {MIN_SOLUTIONS})"
        )
    if not ok_pre:
        blockers.append(f"precheck: {pre_feedback}")
    elif not quality.get("skipped") and not quality.get("passed"):
        failed = quality.get("failed_items", [])
        blockers.append(
            f"quality: {len(failed)} решений не прошли чек-лист"
        )
    elif not div_batch.get("skipped") and not div_batch.get("llm_ok"):
        blockers.append("diversity_on_batch: не прошёл")

    report["blockers"] = blockers
    return report


def run_case(chain: TRIZChain, name: str, problem: str) -> dict[str, Any]:
    print(f"\n{'=' * 72}\nКЕЙС: {name}\n{'=' * 72}")

    core = chain._run_core_analysis(problem)
    passed_fp, fb_fp = validate_fp(
        core.get("physical_contradiction", ""),
        core.get("technical_contradiction", ""),
        chain._llm,
        root_cause=core.get("root_cause", ""),
    )
    if not passed_fp:
        repaired = chain._regenerate_contradictions(problem, core, fb_fp)
        core["technical_contradiction"] = repaired["technical_contradiction"]
        core["physical_contradiction"] = repaired["physical_contradiction"]

    case_report: dict[str, Any] = {"brief": name, "attempts": []}
    known, why_failed, _ = chain._get_attempt_history(core, problem)
    case_report["attempt_history"] = {
        "known_solutions": known[:200],
        "why_failed": why_failed[:200],
    }
    feedback = ""
    batches: list[list[dict]] = []
    any_passed = False

    for attempt in range(1, MAX_SOLUTION_GENERATION_ATTEMPTS + 1):
        print(f"  попытка {attempt}...", flush=True)
        if attempt == 1:
            batch = chain._generate_solutions(core, problem)
        else:
            batch = chain._generate_solutions(
                core, problem, validator_feedback=feedback
            )

        attempt_report = _analyze_batch(chain, core, problem, batch)
        attempt_report["attempt"] = attempt

        passed, feedback, valid_batch = validate_solutions(
            batch,
            known,
            why_failed,
            (core.get("analysis") or {}).get("resources_analysis", ""),
            core.get("ideal_final_result", ""),
            chain._llm,
            chain._get_constraints(core),
        )
        batches.append(valid_batch)
        accumulated = select_diverse_solutions(
            merge_valid_solutions(*batches), limit=5
        )

        attempt_report["chain_passed"] = passed
        attempt_report["accumulated_count"] = len(accumulated)
        if passed:
            div_ok, div_fb = check_solution_diversity(
                accumulated,
                (core.get("analysis") or {}).get("resources_analysis", ""),
                chain._llm,
            )
            attempt_report["accumulated_diversity_ok"] = div_ok
            attempt_report["accumulated_diversity_feedback"] = (
                (div_fb or "")[:300] or None
            )
            if div_ok:
                any_passed = True

        case_report["attempts"].append(attempt_report)

        print(f"    passed={passed}, blockers={attempt_report['blockers']}")
        if attempt_report["quality"].get("failed_items"):
            for fi in attempt_report["quality"]["failed_items"]:
                fails = []
                if not fi["not_dead_end_duplicate"]:
                    fails.append("dead_end_dup")
                if not fi["uses_specific_resource"]:
                    fails.append("no_resource")
                if not fi["advances_ifr"]:
                    fails.append("no_ifr")
                print(f"    quality fail #{fi['id']}: {fails}")

    case_report["any_attempt_full_pass"] = any_passed
    return case_report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not settings.openai_api_key:
        print("OPENAI_API_KEY не задан")
        sys.exit(1)

    chain = TRIZChain()
    all_reports: list[dict] = []

    for name, path in BRIEFS.items():
        problem = path.read_text(encoding="utf-8").strip()
        all_reports.append(run_case(chain, name, problem))

    out_path = PROJECT_ROOT / "scripts" / "debug_solution_pass_output.json"
    out_path.write_text(
        json.dumps(all_reports, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n{'=' * 72}\nСВОДКА\n{'=' * 72}")
    blocker_counts: dict[str, int] = {}
    for case in all_reports:
        print(f"\n{case['brief']}: any_full_pass={case['any_attempt_full_pass']}")
        for att in case["attempts"]:
            for b in att["blockers"]:
                key = b.split(":")[0]
                blocker_counts[key] = blocker_counts.get(key, 0) + 1
            print(
                f"  attempt {att['attempt']}: passed={att['chain_passed']}, "
                f"blockers={att['blockers']}"
            )

    print("\nЧастота блокеров (по попыткам):")
    for k, v in sorted(blocker_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    print(f"\nПолный отчёт: {out_path}")


if __name__ == "__main__":
    main()
