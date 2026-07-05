#!/usr/bin/env python3
"""A/B-сравнение качества TRIZ-решений: effects RAG off vs on.

Для каждого эталонного брифа из scripts/eval_cases/*.txt прогоняет chain.solve
дважды, сохраняет payload и формирует сравнительную таблицу метрик + summary.md.

Пример:
    python scripts/ab_effects_eval.py
    python scripts/ab_effects_eval.py --judge
    python scripts/ab_effects_eval.py --cases example_stakany --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# JWT_SECRET обязателен при импорте backend.config (как в pytest conftest).
os.environ.setdefault("JWT_SECRET", "ab-effects-eval-local-not-for-production")

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from backend.config import settings  # noqa: E402
from backend.llm.chain import TRIZChain, TRIZChainError  # noqa: E402
from backend.llm.openai_client import create_chat_llm  # noqa: E402
from backend.llm.solution_validator import (  # noqa: E402
    _SolutionChecklistResult,
    _llm_checklist,
    _principle_key,
)

SCRIPTS_DIR = Path(__file__).resolve().parent
EVAL_CASES_DIR = SCRIPTS_DIR / "eval_cases"
EVAL_OUT_DIR = SCRIPTS_DIR / "eval_out"

logger = logging.getLogger(__name__)

JudgeWinner = Literal["off", "on", "tie"]


class JudgeVerdict(BaseModel):
    winner: JudgeWinner
    reasoning: str = Field(description="Краткое обоснование на русском")


_JUDGE_SYSTEM = """Ты — независимый эксперт ТРИЗ. Сравни два набора концепций решений одной задачи.

Критерии (в порядке важности):
1. Насколько набор разрешает физическое/техническое противоречие задачи.
2. Реализуемость в рамках ограничений брифа.
3. Разнообразие подходов (разные принципы и механизмы, не вариации одной идеи).

Верни winner:
- "off" — сильнее набор при EFFECTS_RAG=off;
- "on" — сильнее набор при EFFECTS_RAG=on;
- "tie" — паритет или нельзя уверенно выбрать.

Все формулировки reasoning — на русском, 3–6 предложений."""

_JUDGE_USER = """Задача (фрагмент брифа):
{problem_excerpt}

Физическое противоречие:
{physical_contradiction}

ИКР:
{ideal_final_result}

{solution_sections}

Какой набор сильнее по критериям (EFFECTS_RAG=off vs on)?"""


@dataclass
class VariantMetrics:
    label: str
    solution_count: int
    distinct_approaches: int
    avg_description_len: int
    effects_used: list[str]
    dead_end_duplicates: list[str] = field(default_factory=list)

    def as_row(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "solution_count": self.solution_count,
            "distinct_approaches": self.distinct_approaches,
            "avg_description_len": self.avg_description_len,
            "effects_used": self.effects_used,
            "dead_end_duplicates": self.dead_end_duplicates,
        }


@dataclass
class CaseComparison:
    case_name: str
    off: VariantMetrics
    on: VariantMetrics
    judge_winner: JudgeWinner | None = None
    judge_reasoning: str | None = None


def load_cases(cases_dir: Path, *, only: list[str] | None = None) -> list[tuple[str, str]]:
    if not cases_dir.is_dir():
        raise FileNotFoundError(f"Папка с кейсами не найдена: {cases_dir}")

    paths = sorted(cases_dir.glob("*.txt"))
    if not paths:
        raise FileNotFoundError(f"Нет .txt кейсов в {cases_dir}")

    loaded: list[tuple[str, str]] = []
    for path in paths:
        name = path.stem
        if only and name not in only:
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            logger.warning("Пропуск пустого кейса: %s", path.name)
            continue
        loaded.append((name, text))

    if only and not loaded:
        missing = ", ".join(only)
        raise FileNotFoundError(f"Запрошенные кейсы не найдены: {missing}")

    return loaded


def _solution_description_length(solution: dict) -> int:
    parts = (
        solution.get("title") or "",
        solution.get("mechanism") or "",
        solution.get("applicability") or "",
    )
    return sum(len(part.strip()) for part in parts)


def _format_solutions_block(payload: dict) -> str:
    lines: list[str] = []
    for sol in payload.get("solution_concepts") or []:
        lines.append(
            f"#{sol.get('id')}: {sol.get('title')} | {sol.get('triz_principle')}\n"
            f"  mechanism: {sol.get('mechanism')}\n"
            f"  applicability: {sol.get('applicability')}"
        )
    return "\n".join(lines) if lines else "—"


def _format_effects_block(effects_used: list[str]) -> str:
    if not effects_used:
        return "Подставленные физэффекты: —"
    return "Подставленные физэффекты: " + ", ".join(effects_used)


def detect_dead_end_duplicates(payload: dict, llm: Any) -> list[str]:
    """Повторы тупиков из брифа — через _llm_checklist из solution_validator."""
    solutions = payload.get("solution_concepts") or []
    if not solutions:
        return []

    known = str(payload.get("known_solutions") or "").strip() or "—"
    why_failed = str(payload.get("why_failed") or "").strip() or "—"
    analysis = payload.get("analysis") or {}
    resources = str(analysis.get("resources_analysis") or "").strip() or "—"
    ifr = str(payload.get("ideal_final_result") or "").strip() or "—"

    try:
        result = _llm_checklist(solutions, known, why_failed, resources, ifr, llm)
        if isinstance(result, dict):
            result = _SolutionChecklistResult.model_validate(result)
    except Exception as exc:
        logger.warning("Проверка тупиков не удалась: %s", exc)
        return [f"(проверка не удалась: {exc})"]

    by_id = {int(s.get("id")): s for s in solutions if s.get("id") is not None}
    duplicates: list[str] = []
    for item in result.items:
        if item.not_dead_end_duplicate:
            continue
        sol = by_id.get(int(item.solution_id), {})
        title = str(sol.get("title") or f"id={item.solution_id}")
        duplicates.append(title)
    return duplicates


def compute_metrics(payload: dict, *, label: str, llm: Any | None) -> VariantMetrics:
    solutions = payload.get("solution_concepts") or []
    principles = {_principle_key(sol) for sol in solutions}
    lengths = [_solution_description_length(sol) for sol in solutions]
    avg_len = round(sum(lengths) / len(lengths)) if lengths else 0

    dead_ends: list[str] = []
    if llm is not None:
        dead_ends = detect_dead_end_duplicates(payload, llm)

    return VariantMetrics(
        label=label,
        solution_count=len(solutions),
        distinct_approaches=len(principles),
        avg_description_len=avg_len,
        effects_used=list(payload.get("effects_used") or []),
        dead_end_duplicates=dead_ends,
    )


def save_payload(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_solve(chain: TRIZChain, problem: str, *, effects_enabled: bool) -> dict:
    settings.effects_rag_enabled = effects_enabled
    mode = "on" if effects_enabled else "off"
    logger.info("solve(%s): effects_rag_enabled=%s", mode, effects_enabled)
    return chain.solve(problem)


def _judge_section(label: Literal["off", "on"], payload: dict) -> str:
    return (
        f"=== Набор решений при EFFECTS_RAG={label} ===\n"
        f"{_format_effects_block(payload.get('effects_used') or [])}\n"
        f"{_format_solutions_block(payload)}"
    )


def run_judge(
    llm: Any,
    *,
    problem: str,
    off_payload: dict,
    on_payload: dict,
    swapped: bool,
) -> JudgeVerdict:
    order: list[Literal["off", "on"]] = ["on", "off"] if swapped else ["off", "on"]
    payloads = {"off": off_payload, "on": on_payload}
    sections = "\n\n".join(_judge_section(label, payloads[label]) for label in order)

    prompt = _JUDGE_USER.format(
        problem_excerpt=problem[:1200],
        physical_contradiction=off_payload.get("physical_contradiction") or "—",
        ideal_final_result=off_payload.get("ideal_final_result") or "—",
        solution_sections=sections,
    )

    structured = llm.with_structured_output(JudgeVerdict)
    result = structured.invoke(
        [
            SystemMessage(content=_JUDGE_SYSTEM),
            HumanMessage(content=prompt),
        ]
    )
    if isinstance(result, JudgeVerdict):
        return result
    return JudgeVerdict.model_validate(result)


def consolidate_judge_verdicts(v1: JudgeWinner, v2: JudgeWinner) -> JudgeWinner:
    if v1 == v2:
        return v1
    return "tie"


def judge_pair(
    llm: Any,
    *,
    problem: str,
    off_payload: dict,
    on_payload: dict,
) -> tuple[JudgeWinner, str]:
    v1 = run_judge(llm, problem=problem, off_payload=off_payload, on_payload=on_payload, swapped=False)
    v2 = run_judge(llm, problem=problem, off_payload=off_payload, on_payload=on_payload, swapped=True)
    winner = consolidate_judge_verdicts(v1.winner, v2.winner)
    reasoning = (
        f"Прогон 1 (off→on): {v1.winner} — {v1.reasoning}\n\n"
        f"Прогон 2 (on→off): {v2.winner} — {v2.reasoning}\n\n"
        f"Итог (совпадение двух прогонов): {winner}."
    )
    return winner, reasoning


def _fmt_list(items: list[str]) -> str:
    return ", ".join(items) if items else "—"


def print_comparison_table(comparisons: list[CaseComparison]) -> None:
    header = (
        f"{'Кейс':<24} {'Режим':<6} {'Реш.':<5} {'Кат.':<5} "
        f"{'Ср.дл.':<7} {'Эффекты':<8} {'Тупики'}"
    )
    print("\n" + header)
    print("-" * len(header.encode("utf-8", errors="replace")))

    for cmp in comparisons:
        for metrics in (cmp.off, cmp.on):
            effects_n = len(metrics.effects_used)
            dead = _fmt_list(metrics.dead_end_duplicates)
            print(
                f"{cmp.case_name:<24} {metrics.label:<6} "
                f"{metrics.solution_count:<5} {metrics.distinct_approaches:<5} "
                f"{metrics.avg_description_len:<7} {effects_n:<8} {dead}"
            )
        if cmp.judge_winner is not None:
            print(f"  → LLM-судья: {cmp.judge_winner}")
        print()


def render_summary_md(comparisons: list[CaseComparison], *, generated_at: str) -> str:
    lines = [
        "# A/B: effects RAG off vs on",
        "",
        f"Сгенерировано: {generated_at}",
        "",
        "## Сводная таблица",
        "",
        "| Кейс | Режим | Решений | Категорий | Ср. длина | effects_used | Повтор тупиков |",
        "|------|-------|---------|-----------|-----------|--------------|----------------|",
    ]

    for cmp in comparisons:
        for m in (cmp.off, cmp.on):
            lines.append(
                f"| {cmp.case_name} | {m.label} | {m.solution_count} | {m.distinct_approaches} | "
                f"{m.avg_description_len} | {_fmt_list(m.effects_used)} | "
                f"{_fmt_list(m.dead_end_duplicates)} |"
            )

    lines.extend(["", "## LLM-судья", ""])
    judged = [c for c in comparisons if c.judge_winner is not None]
    if not judged:
        lines.append("_Не запускался (--judge)._")
    else:
        for cmp in judged:
            lines.append(f"### {cmp.case_name}")
            lines.append("")
            lines.append(f"**Вердикт:** `{cmp.judge_winner}`")
            lines.append("")
            lines.append(cmp.judge_reasoning or "")
            lines.append("")

    lines.extend(
        [
            "## Файлы payload",
            "",
            "Для каждого кейса: `scripts/eval_out/{case}_off.json`, `{case}_on.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate_case(
    chain: TRIZChain,
    *,
    case_name: str,
    problem: str,
    out_dir: Path,
    reuse: bool,
    run_judge: bool,
    judge_llm: Any | None,
) -> CaseComparison:
    off_path = out_dir / f"{case_name}_off.json"
    on_path = out_dir / f"{case_name}_on.json"

    if reuse and off_path.is_file() and on_path.is_file():
        logger.info("Переиспользование сохранённых payload: %s", case_name)
        off_payload = load_payload(off_path)
        on_payload = load_payload(on_path)
    else:
        print(f"\n>>> Кейс: {case_name}")
        print("    Прогон EFFECTS_RAG=off …")
        off_payload = run_solve(chain, problem, effects_enabled=False)
        save_payload(off_path, off_payload)
        print(f"    Сохранено: {off_path.relative_to(PROJECT_ROOT)}")

        print("    Прогон EFFECTS_RAG=on …")
        on_payload = run_solve(chain, problem, effects_enabled=True)
        save_payload(on_path, on_payload)
        print(f"    Сохранено: {on_path.relative_to(PROJECT_ROOT)}")

    off_metrics = compute_metrics(off_payload, label="off", llm=chain._llm)
    on_metrics = compute_metrics(on_payload, label="on", llm=chain._llm)

    judge_winner: JudgeWinner | None = None
    judge_reasoning: str | None = None
    if run_judge:
        if judge_llm is None:
            raise RuntimeError("judge_llm не инициализирован")
        print(f"    LLM-судья для {case_name} …")
        judge_winner, judge_reasoning = judge_pair(
            judge_llm,
            problem=problem,
            off_payload=off_payload,
            on_payload=on_payload,
        )

    return CaseComparison(
        case_name=case_name,
        off=off_metrics,
        on=on_metrics,
        judge_winner=judge_winner,
        judge_reasoning=judge_reasoning,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A/B сравнение TRIZ solve с effects RAG off vs on."
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        metavar="NAME",
        help="Имена кейсов без .txt (по умолчанию — все из eval_cases/)",
    )
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=EVAL_CASES_DIR,
        help=f"Папка с брифами (default: {EVAL_CASES_DIR.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=EVAL_OUT_DIR,
        help=f"Папка для JSON и summary (default: {EVAL_OUT_DIR.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Запустить LLM-судью (два прогона с перестановкой блоков)",
    )
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="Не вызывать solve, если {case}_off/on.json уже существуют",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только проверить кейсы и вывести план прогона (без API)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Логи INFO",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        cases = load_cases(args.cases_dir, only=args.cases)
    except FileNotFoundError as exc:
        print(f"ОШИБКА: {exc}")
        return 1

    print(f"Кейсов: {len(cases)}")
    for name, text in cases:
        print(f"  • {name} ({len(text)} симв.)")

    if args.dry_run:
        print("\n[dry-run] solve и судья не вызываются.")
        for name, _ in cases:
            print(f"  → {args.out_dir / f'{name}_off.json'}")
            print(f"  → {args.out_dir / f'{name}_on.json'}")
        print(f"  → {args.out_dir / 'summary.md'}")
        return 0

    if not settings.openai_api_key:
        print("ОШИБКА: OPENAI_API_KEY не задан в .env")
        return 1

    settings.effects_rag_enabled = False

    try:
        chain = TRIZChain()
    except TRIZChainError as exc:
        print(f"ОШИБКА инициализации TRIZChain: {exc}")
        return 1

    judge_llm = create_chat_llm(temperature=0.0) if args.judge else None

    comparisons: list[CaseComparison] = []
    for name, problem in cases:
        try:
            comparisons.append(
                evaluate_case(
                    chain,
                    case_name=name,
                    problem=problem,
                    out_dir=args.out_dir,
                    reuse=args.reuse,
                    run_judge=args.judge,
                    judge_llm=judge_llm,
                )
            )
        except TRIZChainError as exc:
            logger.exception("Кейс %s не удался", name)
            print(f"ОШИБКА кейса {name}: {exc}")
            return 1
        except Exception as exc:
            logger.exception("Кейс %s: неожиданная ошибка", name)
            print(f"ОШИБКА кейса {name}: {exc}")
            return 1
        finally:
            settings.effects_rag_enabled = False

    print_comparison_table(comparisons)

    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    summary_path = args.out_dir / "summary.md"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        render_summary_md(comparisons, generated_at=generated_at),
        encoding="utf-8",
    )
    print(f"\nSummary: {summary_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
