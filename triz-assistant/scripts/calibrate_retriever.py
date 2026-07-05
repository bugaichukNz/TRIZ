#!/usr/bin/env python3
"""Калибровка порога семантического поиска по корпусу физэффектов."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm.effects_retriever import (  # noqa: E402
    DEFAULT_EFFECTS_PATH,
    DEFAULT_INDEX_PATH,
    DEFAULT_META_PATH,
    EffectsRetriever,
)

CalibrationCase = tuple[str, list[str]]

CALIBRATION_CASES: list[CalibrationCase] = [
    (
        "бесконтактно нагреть локальную зону проводящего металла",
        ["eddy_currents", "magnetic_hyperthermia"],
    ),
    (
        "обнаружить зарождающуюся микротрещину в конструкции под нагрузкой",
        ["acoustic_emission", "ultrasound", "acoustic_tomography"],
    ),
    (
        "снизить трение между движущимися деталями без замены материала",
        ["hydrodynamic_lubrication", "rehbinder_effect", "magnetorheological_fluid"],
    ),
    (
        "переместить объект без механического контакта",
        [
            "acoustic_levitation",
            "electromagnetic_levitation",
            "electrostatic_attraction",
            "meissner_effect",
        ],
    ),
    (
        "дозировать жидкость с точным объёмом без насоса",
        ["osmotic_pump", "capillarity"],
    ),
    (
        "ультразвуковая очистка загрязнённой поверхности в жидкости",
        ["acoustic_cavitation"],
    ),
    (
        "измерить скорость движущегося объекта по звуку",
        ["acoustic_doppler"],
    ),
    (
        "локально охладить электронный компонент без вентилятора",
        ["peltier_effect", "evaporative_cooling", "thermoelectric_effect"],
    ),
    (
        "удержать металлическую деталь на весу в магнитном поле",
        ["electromagnetic_levitation", "meissner_effect"],
    ),
    (
        "контролировать целостность сосуда давления без остановки эксплуатации",
        ["acoustic_emission", "ultrasound"],
    ),
    (
        "перекрыть поток жидкости изменением вязкости",
        ["magnetorheological_fluid", "electrorheological_fluid"],
    ),
    (
        "поднять лёгкий объект звуковым полем",
        ["acoustic_levitation"],
    ),
]

THRESHOLD_START = 0.20
THRESHOLD_END = 0.45
THRESHOLD_STEP = 0.05
TOP_K = 5


def rank_with_threshold(
    scores: dict[str, float],
    *,
    threshold: float,
    top_k: int,
) -> list[tuple[str, float]]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [(effect_id, score) for effect_id, score in ranked if score >= threshold][:top_k]


def recall_at_k(
    scores: dict[str, float],
    expected: list[str],
    *,
    threshold: float,
    top_k: int,
) -> bool:
    top_ids = {effect_id for effect_id, _ in rank_with_threshold(scores, threshold=threshold, top_k=top_k)}
    return any(effect_id in top_ids for effect_id in expected)


def print_query_results(
    retriever: EffectsRetriever,
    cases: list[CalibrationCase],
    *,
    top_k: int,
) -> None:
    print("\n=== Топ-5 по запросам (без порога) ===\n")
    for query, expected in cases:
        scores = retriever.score_queries([query])
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        expected_set = set(expected)
        print(f"Запрос: {query}")
        print(f"Ожидаемые id: {', '.join(expected)}")
        for rank, (effect_id, score) in enumerate(ranked, start=1):
            hit = "HIT" if effect_id in expected_set else "miss"
            name = retriever._effects_by_id[effect_id].name if retriever.enabled else effect_id
            print(f"  {rank}. {effect_id} ({name}) score={score:.3f} [{hit}]")
        print()


def print_recall_table(
    retriever: EffectsRetriever,
    cases: list[CalibrationCase],
    *,
    top_k: int,
) -> None:
    print("=== Recall@5 по порогам ===\n")
    print(f"{'threshold':>10}  {'recall@5':>10}  {'hits':>6}/{len(cases)}")

    threshold = THRESHOLD_START
    while threshold <= THRESHOLD_END + 1e-9:
        hits = 0
        for query, expected in cases:
            scores = retriever.score_queries([query])
            if recall_at_k(scores, expected, threshold=threshold, top_k=top_k):
                hits += 1
        recall = hits / len(cases) if cases else 0.0
        print(f"{threshold:10.2f}  {recall:10.1%}  {hits:6}/{len(cases)}")
        threshold = round(threshold + THRESHOLD_STEP, 2)


def run_calibration(
    effects_path: Path,
    index_path: Path,
    meta_path: Path,
    *,
    cases: list[CalibrationCase] | None = None,
) -> int:
    cases = cases or CALIBRATION_CASES
    retriever = EffectsRetriever(effects_path, index_path, meta_path)
    if not retriever.enabled:
        print("ОШИБКА: retriever disabled — проверьте корпус, индекс и version.", file=sys.stderr)
        return 1

    print_query_results(retriever, cases, top_k=TOP_K)
    print_recall_table(retriever, cases, top_k=TOP_K)
    print(
        f"\nТекущий порог в settings: effects_score_threshold "
        f"(см. .env EFFECTS_SCORE_THRESHOLD)"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Калибровка порога EffectsRetriever")
    parser.add_argument(
        "--effects",
        type=Path,
        default=DEFAULT_EFFECTS_PATH,
        help=f"Путь к effects.json (по умолчанию {DEFAULT_EFFECTS_PATH})",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=DEFAULT_INDEX_PATH,
        help=f"Путь к effects_index.npz (по умолчанию {DEFAULT_INDEX_PATH})",
    )
    parser.add_argument(
        "--meta",
        type=Path,
        default=DEFAULT_META_PATH,
        help=f"Путь к effects_index.meta.json (по умолчанию {DEFAULT_META_PATH})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_calibration(args.effects, args.index, args.meta)


if __name__ == "__main__":
    raise SystemExit(main())
