#!/usr/bin/env python3
"""Валидация корпуса физических эффектов data/triz_corpus/effects.json."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm.effects_corpus import EFFECT_FUNCTIONS_SET  # noqa: E402
from backend.llm.models import EffectsCorpus, PhysicalEffect  # noqa: E402

DEFAULT_INPUT = PROJECT_ROOT / "data" / "triz_corpus" / "effects.json"
MIN_RECORDS = 196
MIN_DESCRIPTION_LEN = 100


def _check_non_empty(effect: PhysicalEffect) -> list[str]:
    issues: list[str] = []
    for field in (
        "id",
        "name",
        "category",
        "description",
        "input_action",
        "output_action",
        "limitations",
    ):
        if not getattr(effect, field, "").strip():
            issues.append(f"пустое поле {field}")
    if not effect.functions:
        issues.append("пустой список functions")
    if not effect.examples or not any(ex.strip() for ex in effect.examples):
        issues.append("пустой список examples")
    return issues


def _check_functions(effect: PhysicalEffect) -> list[str]:
    invalid = [fn for fn in effect.functions if fn not in EFFECT_FUNCTIONS_SET]
    if invalid:
        return [f"невалидные functions: {invalid}"]
    return []


def _suspicious(effect: PhysicalEffect) -> list[str]:
    flags: list[str] = []
    if len(effect.description.strip()) < MIN_DESCRIPTION_LEN:
        flags.append(f"короткое description ({len(effect.description.strip())} симв.)")
    if not effect.limitations.strip():
        flags.append("пустые limitations")
    return flags


def validate_corpus(path: Path, *, min_records: int = MIN_RECORDS) -> int:
    if not path.is_file():
        print(f"ОШИБКА: файл не найден: {path}")
        return 1

    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        corpus = EffectsCorpus.model_validate(raw)
    except Exception as exc:
        print(f"ОШИБКА схемы EffectsCorpus: {exc}")
        return 1

    effects = corpus.effects
    errors: list[str] = []
    warnings: list[str] = []

    ids = [e.id for e in effects]
    id_counts = Counter(ids)
    duplicates = [eid for eid, cnt in id_counts.items() if cnt > 1]
    if duplicates:
        errors.append(f"дубликаты id: {duplicates}")

    for effect in effects:
        field_issues = _check_non_empty(effect) + _check_functions(effect)
        if field_issues:
            errors.append(f"{effect.id}: {'; '.join(field_issues)}")
        suspicious = _suspicious(effect)
        if suspicious:
            warnings.append(f"{effect.id}: {'; '.join(suspicious)}")

    category_stats = Counter(e.category for e in effects)
    function_stats: Counter[str] = Counter()
    for effect in effects:
        function_stats.update(effect.functions)

    uncovered_functions = sorted(EFFECT_FUNCTIONS_SET - set(function_stats))
    if len(effects) < min_records:
        errors.append(f"записей {len(effects)} < минимума {min_records}")
    if uncovered_functions:
        errors.append(f"функции без покрытия ({len(uncovered_functions)}): {uncovered_functions}")

    print(f"Файл: {path}")
    print(f"Версия корпуса: {corpus.version}")
    print(f"Всего эффектов: {len(effects)}")
    print("\nПо категориям:")
    for cat, cnt in sorted(category_stats.items()):
        print(f"  {cat}: {cnt}")

    print("\nПо functions (топ-15):")
    for fn, cnt in function_stats.most_common(15):
        print(f"  {fn}: {cnt}")
    if len(function_stats) > 15:
        print(f"  … всего уникальных functions: {len(function_stats)}")

    if warnings:
        print(f"\nПодозрительные записи ({len(warnings)}):")
        for line in warnings[:30]:
            print(f"  ⚠ {line}")
        if len(warnings) > 30:
            print(f"  … и ещё {len(warnings) - 30}")

    if errors:
        print(f"\nОШИБКИ ({len(errors)}):")
        for line in errors:
            print(f"  ✗ {line}")
        return 1

    print("\n✓ Валидация пройдена успешно")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Валидация корпуса физэффектов TRIZ")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Путь к effects.json (по умолчанию {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--min-records",
        type=int,
        default=MIN_RECORDS,
        help=f"Минимальное число записей (по умолчанию {MIN_RECORDS})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sys.exit(validate_corpus(args.input, min_records=args.min_records))


if __name__ == "__main__":
    main()
