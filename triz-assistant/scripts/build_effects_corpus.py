#!/usr/bin/env python3
"""Генерация корпуса физических эффектов data/triz_corpus/effects.json через LLM."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm.effects_corpus import (  # noqa: E402
    BATCH_COVERAGE_THRESHOLD,
    CORPUS_VERSION,
    GENERATION_BATCHES,
    MAX_BATCH_GENERATION_ATTEMPTS,
    batch_is_complete,
    batch_missing_ids,
    build_batch_prompt,
    canonicalize_batch_effects,
    merge_effects,
    sanitize_effect_functions,
    total_target_count,
)
from backend.llm.models import EffectsBatch, EffectsCorpus, PhysicalEffect  # noqa: E402

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "triz_corpus" / "effects.json"
DEFAULT_BUILD_STATE = PROJECT_ROOT / "data" / "triz_corpus" / ".build_state.json"
MAX_BATCH_SIZE = 20
MIN_TARGET = 200


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def load_existing(path: Path) -> list[PhysicalEffect]:
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    corpus = EffectsCorpus.model_validate(raw)
    return list(corpus.effects)


def save_corpus(path: Path, effects: list[PhysicalEffect]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    corpus = EffectsCorpus(effects=effects, version=CORPUS_VERSION)
    path.write_text(
        json.dumps(corpus.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_build_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"batch_attempts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logging.warning("Повреждён %s — сброс состояния сборки", path)
        return {"batch_attempts": {}}
    if not isinstance(data.get("batch_attempts"), dict):
        data["batch_attempts"] = {}
    return data


def save_build_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_batch_attempts(state: dict[str, Any], batch_key: str) -> int:
    attempts = state.get("batch_attempts") or {}
    return int(attempts.get(batch_key, 0))


def increment_batch_attempt(state: dict[str, Any], batch_key: str) -> int:
    attempts = dict(state.get("batch_attempts") or {})
    attempts[batch_key] = attempts.get(batch_key, 0) + 1
    state["batch_attempts"] = attempts
    return attempts[batch_key]


def count_batch_effects(batch_key: str, effects: list[PhysicalEffect], batch) -> int:
    """Считает эффекты батча по пересечению id с suggested_ids."""
    suggested = set(batch["suggested_ids"])
    if suggested:
        return sum(1 for e in effects if e.id in suggested)
    return 0


def resolve_batch_count(
    batch,
    missing_ids: list[str],
    existing_count: int,
    *,
    min_total: int = MIN_TARGET,
) -> int:
    """Сколько эффектов запросить у LLM для данного батча."""
    if batch["key"] == "gap_fill":
        need = max(min_total - existing_count, 0)
        if need == 0:
            return 0
        return min(need, MAX_BATCH_SIZE)
    if missing_ids:
        return min(len(missing_ids), MAX_BATCH_SIZE)
    if batch["suggested_ids"]:
        return min(batch["target_count"], MAX_BATCH_SIZE)
    remaining = batch["target_count"]
    return min(max(remaining, 1), MAX_BATCH_SIZE)


def generate_batch(
    llm,
    batch,
    *,
    missing_ids: list[str],
    existing_ids: set[str],
    count: int,
    retries: int = 3,
) -> list[PhysicalEffect]:
    structured = llm.with_structured_output(EffectsBatch)
    prompt = build_batch_prompt(
        batch,
        missing_ids=missing_ids,
        existing_ids=existing_ids,
        count=count,
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            result: EffectsBatch = structured.invoke(prompt)
            sanitized = [sanitize_effect_functions(e) for e in result.effects]
            return [e for e in sanitized if e.functions]
        except Exception as exc:
            last_error = exc
            logging.warning(
                "Батч %s: попытка %d/%d не удалась: %s",
                batch["key"],
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"Батч {batch['key']} не сгенерирован: {last_error}") from last_error


def log_unclosed_suggested_ids(
    batch,
    existing_ids: set[str],
    *,
    attempt_count: int,
) -> None:
    missing = batch_missing_ids(batch, existing_ids)
    if missing and attempt_count >= MAX_BATCH_GENERATION_ATTEMPTS:
        logging.warning(
            "Батч %s: после %d попыток остаются непокрытые suggested_ids (%d): %s",
            batch["key"],
            attempt_count,
            len(missing),
            ", ".join(missing),
        )


def run_build(
    output: Path,
    *,
    force_all: bool = False,
    dry_run: bool = False,
    pause_sec: float = 1.0,
    build_state_path: Path = DEFAULT_BUILD_STATE,
    llm: Any | None = None,
) -> int:
    effects = [] if force_all else load_existing(output)
    existing_ids = {e.id for e in effects}
    build_state = {} if force_all else load_build_state(build_state_path)
    logging.info(
        "Загружено %d эффектов; целевой объём по батчам: %d (минимум %d)",
        len(effects),
        total_target_count(),
        MIN_TARGET,
    )

    batches_run = 0
    batches_skipped = 0

    for batch in GENERATION_BATCHES:
        batch_key = batch["key"]
        attempt_count = get_batch_attempts(build_state, batch_key)
        missing_ids = batch_missing_ids(batch, existing_ids)
        batch_count = count_batch_effects(batch_key, effects, batch)

        if not force_all and batch_is_complete(
            batch,
            existing_ids,
            batch_count,
            attempt_count=attempt_count,
            total_count=len(effects),
            min_total=MIN_TARGET,
        ):
            logging.info(
                "Пропуск батча %s (%s): уже покрыт (попыток=%d)",
                batch_key,
                batch["title"],
                attempt_count,
            )
            batches_skipped += 1
            continue

        count = resolve_batch_count(
            batch,
            missing_ids,
            len(effects),
            min_total=MIN_TARGET,
        )
        if count <= 0:
            batches_skipped += 1
            continue

        logging.info(
            "Батч %s: запрос %d эффектов (missing_ids=%d, попытка=%d)",
            batch_key,
            count,
            len(missing_ids),
            attempt_count + 1,
        )

        if dry_run:
            batches_run += 1
            continue

        if llm is None:
            from backend.llm.openai_client import create_chat_llm

            llm = create_chat_llm(temperature=0.3)

        raw_effects = generate_batch(
            llm,
            batch,
            missing_ids=missing_ids,
            existing_ids=existing_ids,
            count=count,
        )
        new_effects = canonicalize_batch_effects(
            batch,
            raw_effects,
            missing_ids=missing_ids,
        )
        attempt_count = increment_batch_attempt(build_state, batch_key)
        save_build_state(build_state_path, build_state)

        before = len(effects)
        effects = merge_effects(effects, new_effects)
        added = len(effects) - before
        existing_ids = {e.id for e in effects}
        logging.info(
            "Батч %s: добавлено %d новых эффектов (всего %d)",
            batch_key,
            added,
            len(effects),
        )
        save_corpus(output, effects)
        batches_run += 1

        if batch_is_complete(
            batch,
            existing_ids,
            count_batch_effects(batch_key, effects, batch),
            attempt_count=attempt_count,
            total_count=len(effects),
            min_total=MIN_TARGET,
        ):
            log_unclosed_suggested_ids(
                batch,
                existing_ids,
                attempt_count=attempt_count,
            )

        if pause_sec > 0:
            time.sleep(pause_sec)

    if not dry_run:
        save_corpus(output, effects)
        if not force_all:
            save_build_state(build_state_path, build_state)

    logging.info(
        "Готово: %d эффектов в %s (батчей запущено: %d, пропущено: %d; порог покрытия=%.0f%%)",
        len(effects),
        output,
        batches_run,
        batches_skipped,
        BATCH_COVERAGE_THRESHOLD * 100,
    )
    return len(effects)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Генерация корпуса физэффектов TRIZ")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Путь к effects.json (по умолчанию {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--build-state",
        type=Path,
        default=DEFAULT_BUILD_STATE,
        help=f"Путь к .build_state.json (по умолчанию {DEFAULT_BUILD_STATE})",
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Игнорировать существующий корпус и перегенерировать все батчи",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать план батчей без вызова LLM",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Подробный лог",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=1.0,
        help="Пауза между батчами в секундах",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)
    try:
        total = run_build(
            args.output,
            force_all=args.force_all,
            dry_run=args.dry_run,
            pause_sec=args.pause,
            build_state_path=args.build_state,
        )
    except KeyboardInterrupt:
        logging.warning("Прервано пользователем")
        sys.exit(130)
    except Exception as exc:
        logging.error("Ошибка генерации: %s", exc)
        sys.exit(1)

    if args.dry_run:
        sys.exit(0)
    if total < MIN_TARGET:
        logging.warning(
            "Корпус содержит %d записей — меньше целевых %d. Запустите скрипт повторно.",
            total,
            MIN_TARGET,
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
