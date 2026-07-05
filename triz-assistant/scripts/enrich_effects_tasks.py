#!/usr/bin/env python3
"""Обогащение корпуса полем task_phrases (инженерные постановки задач) через LLM."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm.effects_corpus import CORPUS_VERSION  # noqa: E402
from backend.llm.models import (  # noqa: E402
    EffectTaskPhrasesRow,
    EffectsCorpus,
    EffectsTaskEnrichmentBatch,
    PhysicalEffect,
)

DEFAULT_INPUT = PROJECT_ROOT / "data" / "triz_corpus" / "effects.json"
DEFAULT_BATCH_SIZE = 18
ENRICHMENT_PROMPT = """Для каждого физического эффекта из списка сформулируй 4–6 типовых инженерных задач,
которые он решает, в форме «глагол + объект + условие».

Пиши языком постановки задачи, как их формулирует инженер, НЕ языком описания явления.

Пример для вихревых токов:
- бесконтактно нагреть локальную зону проводящего металла
- затормозить движущийся металлический объект без контакта
- обнаружить дефект в проводящем материале
- отсортировать металлы от неметаллов

Пример для акустической эмиссии:
- обнаружить зарождающуюся трещину в конструкции под нагрузкой
- контролировать целостность сосуда давления без остановки эксплуатации

Верни task_phrases для каждого id из входного списка.

Эффекты:
{effects_block}
"""


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def load_corpus(path: Path) -> EffectsCorpus:
    if not path.is_file():
        raise FileNotFoundError(f"Corpus not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return EffectsCorpus.model_validate(raw)


def needs_enrichment(effect: PhysicalEffect) -> bool:
    return not any(phrase.strip() for phrase in effect.task_phrases)


def format_batch_block(effects: list[PhysicalEffect]) -> str:
    lines: list[str] = []
    for effect in effects:
        functions = ", ".join(effect.functions)
        lines.append(
            f"- id={effect.id}; name={effect.name}; "
            f"description={effect.description}; "
            f"вход={effect.input_action}; выход={effect.output_action}; "
            f"функции={functions}"
        )
    return "\n".join(lines)


def apply_enrichment(
    effects: list[PhysicalEffect],
    rows: list[EffectTaskPhrasesRow],
) -> int:
    by_id = {row.id: row for row in rows}
    updated = 0
    for idx, effect in enumerate(effects):
        row = by_id.get(effect.id)
        if row is None:
            logging.warning("Батч не вернул id=%s — пропуск", effect.id)
            continue
        if not needs_enrichment(effect):
            continue
        effects[idx] = effect.model_copy(update={"task_phrases": list(row.task_phrases)})
        updated += 1
    return updated


def enrich_batch(
    llm: Any,
    batch: list[PhysicalEffect],
    *,
    retries: int = 3,
) -> list[EffectTaskPhrasesRow]:
    structured = llm.with_structured_output(EffectsTaskEnrichmentBatch)
    prompt = ENRICHMENT_PROMPT.format(effects_block=format_batch_block(batch))
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            result: EffectsTaskEnrichmentBatch = structured.invoke(prompt)
            return list(result.effects)
        except Exception as exc:
            last_error = exc
            logging.warning(
                "Батч [%s..%s]: попытка %d/%d не удалась: %s",
                batch[0].id,
                batch[-1].id,
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                time.sleep(2**attempt)
    raise RuntimeError(
        f"Батч [{batch[0].id}..{batch[-1].id}] не обогащён: {last_error}",
    ) from last_error


def run_enrichment(
    path: Path,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
    pause_sec: float = 1.0,
    llm: Any | None = None,
) -> tuple[int, int]:
    corpus = load_corpus(path)
    effects = list(corpus.effects)
    pending = [effect for effect in effects if needs_enrichment(effect)]
    already = len(effects) - len(pending)

    logging.info(
        "Корпус: %d эффектов, уже с task_phrases: %d, к обогащению: %d",
        len(effects),
        already,
        len(pending),
    )
    if not pending:
        if corpus.version != CORPUS_VERSION:
            logging.info("Обновление version → %s без изменений task_phrases", CORPUS_VERSION)
            if not dry_run:
                _save_corpus(path, effects)
        return len(effects), 0

    batches = [
        pending[start : start + batch_size]
        for start in range(0, len(pending), batch_size)
    ]
    logging.info("Запланировано батчей: %d (размер до %d)", len(batches), batch_size)

    if dry_run:
        for batch in batches:
            logging.info(
                "[dry-run] батч %d эффектов: %s .. %s",
                len(batch),
                batch[0].id,
                batch[-1].id,
            )
        return len(effects), len(pending)

    if llm is None:
        from backend.llm.openai_client import create_chat_llm

        llm = create_chat_llm(temperature=0.3)

    enriched_count = 0
    for batch_idx, batch in enumerate(batches, start=1):
        logging.info(
            "Батч %d/%d: %d эффектов (%s .. %s)",
            batch_idx,
            len(batches),
            len(batch),
            batch[0].id,
            batch[-1].id,
        )
        rows = enrich_batch(llm, batch)
        enriched_count += apply_enrichment(effects, rows)
        _save_corpus(path, effects)
        if pause_sec > 0 and batch_idx < len(batches):
            time.sleep(pause_sec)

    logging.info("Обогащено эффектов: %d", enriched_count)
    return len(effects), enriched_count


def _save_corpus(path: Path, effects: list[PhysicalEffect]) -> None:
    if path.is_file():
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)
        logging.info("Бэкап: %s", backup_path)

    corpus = EffectsCorpus(effects=effects, version=CORPUS_VERSION)
    path.write_text(
        json.dumps(corpus.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logging.info("Записано: %s (version=%s)", path, CORPUS_VERSION)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Обогащение effects.json полем task_phrases",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Путь к effects.json (по умолчанию {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Размер батча LLM (по умолчанию {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать план батчей без вызова LLM",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=1.0,
        help="Пауза между батчами в секундах",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)
    try:
        total, pending_or_enriched = run_enrichment(
            args.input,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            pause_sec=args.pause,
        )
    except KeyboardInterrupt:
        logging.warning("Прервано пользователем")
        return 130
    except Exception as exc:
        logging.error("Ошибка обогащения: %s", exc)
        return 1

    if args.dry_run:
        logging.info(
            "Dry-run завершён: %d эффектов, к обогащению %d",
            total,
            pending_or_enriched,
        )
        return 0

    logging.info("Готово: %d эффектов в корпусе", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
