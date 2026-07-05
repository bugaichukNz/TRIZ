#!/usr/bin/env python3
"""Сборка мультивекторного семантического индекса data/triz_corpus/effects_index.npz."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm.effects_retriever import (  # noqa: E402
    DEFAULT_EFFECTS_PATH,
    DEFAULT_INDEX_PATH,
    DEFAULT_META_PATH,
    EMBED_BATCH_SIZE,
    build_embedding_text,
    build_tasks_embedding_text,
    embed_texts,
    index_meta_payload,
)
from backend.llm.models import EffectsCorpus, PhysicalEffect  # noqa: E402


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


def collect_index_rows(effects: list[PhysicalEffect]) -> tuple[list[str], list[str], list[str]]:
    """Строки для эмбеддинга, id и kind (desc/tasks) для каждого вектора."""
    texts: list[str] = []
    ids: list[str] = []
    kinds: list[str] = []

    for effect in effects:
        texts.append(build_embedding_text(effect))
        ids.append(effect.id)
        kinds.append("desc")

        tasks_text = build_tasks_embedding_text(effect)
        if tasks_text:
            texts.append(tasks_text)
            ids.append(effect.id)
            kinds.append("tasks")

    return texts, ids, kinds


def build_index(
    effects_path: Path,
    index_path: Path,
    meta_path: Path,
    *,
    batch_size: int = EMBED_BATCH_SIZE,
) -> tuple[int, int]:
    corpus = load_corpus(effects_path)
    effects = corpus.effects
    if not effects:
        raise ValueError("Corpus is empty")

    texts, ids, kinds = collect_index_rows(effects)
    if len(texts) != len(ids) or len(texts) != len(kinds):
        raise RuntimeError("Internal error: texts/ids/kinds length mismatch")

    chunks: list[np.ndarray] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        logging.info("Embedding batch %d–%d / %d", start + 1, start + len(batch), len(texts))
        chunks.append(embed_texts(batch))

    matrix = np.vstack(chunks).astype(np.float32, copy=False)
    if matrix.shape[0] != len(ids):
        raise RuntimeError(f"Matrix rows {matrix.shape[0]} != ids {len(ids)}")

    index_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        index_path,
        matrix=matrix,
        ids=np.array(ids, dtype=object),
        vector_kind=np.array(kinds, dtype=object),
    )

    meta = index_meta_payload(corpus.version, vector_count=len(ids))
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logging.info(
        "Saved index: %s (%d vectors for %d effects, dim=%d)",
        index_path,
        matrix.shape[0],
        len(effects),
        matrix.shape[1],
    )
    logging.info("Saved meta: %s", meta_path)
    return len(effects), len(ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build semantic index for effects corpus")
    parser.add_argument(
        "--effects",
        type=Path,
        default=DEFAULT_EFFECTS_PATH,
        help=f"Path to effects.json (default: {DEFAULT_EFFECTS_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_INDEX_PATH,
        help=f"Output .npz path (default: {DEFAULT_INDEX_PATH})",
    )
    parser.add_argument(
        "--meta",
        type=Path,
        default=DEFAULT_META_PATH,
        help=f"Output meta JSON path (default: {DEFAULT_META_PATH})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=EMBED_BATCH_SIZE,
        help=f"Embedding batch size (default: {EMBED_BATCH_SIZE})",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    try:
        effect_count, vector_count = build_index(
            args.effects,
            args.output,
            args.meta,
            batch_size=args.batch_size,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        logging.error("%s", exc)
        return 1

    logging.info("Done: indexed %d effects (%d vectors)", effect_count, vector_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
