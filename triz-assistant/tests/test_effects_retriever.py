"""Unit-тесты EffectsRetriever и мультивекторного индекса."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pytest

from backend.config import settings
from backend.llm.effects_retriever import (
    EffectsRetriever,
    build_embedding_text,
    build_tasks_embedding_text,
    index_meta_payload,
)
from backend.llm.models import EffectsCorpus, PhysicalEffect

_SAMPLE_KW = {
    "category": "физический",
    "description": "Описание тестового эффекта для семантического поиска.",
    "input_action": "входное воздействие",
    "output_action": "выходной результат",
    "functions": ["локальный нагрев"],
    "limitations": "ограничения применения",
    "examples": ["пример применения"],
}


def _effect(
    effect_id: str,
    name: str,
    *,
    task_phrases: list[str] | None = None,
) -> PhysicalEffect:
    return PhysicalEffect(
        id=effect_id,
        name=name,
        task_phrases=task_phrases or [],
        **_SAMPLE_KW,
    )


def _write_corpus(tmp_path: Path, effects: list[PhysicalEffect], version: str = "1.1.0") -> Path:
    path = tmp_path / "effects.json"
    corpus = EffectsCorpus(effects=effects, version=version)
    path.write_text(json.dumps(corpus.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_index(
    tmp_path: Path,
    *,
    ids: list[str],
    matrix: np.ndarray,
    vector_kinds: list[str] | None = None,
    corpus_version: str = "1.1.0",
) -> tuple[Path, Path]:
    index_path = tmp_path / "effects_index.npz"
    meta_path = tmp_path / "effects_index.meta.json"

    payload: dict = {"matrix": matrix, "ids": np.array(ids, dtype=object)}
    if vector_kinds is not None:
        payload["vector_kind"] = np.array(vector_kinds, dtype=object)
    np.savez(index_path, **payload)

    meta = index_meta_payload(corpus_version, vector_count=len(ids))
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return index_path, meta_path


class TestEmbeddingText:
    def test_build_embedding_text(self) -> None:
        effect = _effect("eddy_currents", "Вихревые токи")
        text = build_embedding_text(effect)
        assert "Вихревые токи" in text
        assert "локальный нагрев" in text

    def test_build_tasks_embedding_text(self) -> None:
        effect = _effect(
            "eddy_currents",
            "Вихревые токи",
            task_phrases=[
                "бесконтактно нагреть локальную зону металла",
                "затормозить движущийся металл без контакта",
            ],
        )
        text = build_tasks_embedding_text(effect)
        assert text.startswith("Вихревые токи.")
        assert "бесконтактно нагреть" in text

    def test_build_tasks_embedding_text_empty(self) -> None:
        effect = _effect("x", "X")
        assert build_tasks_embedding_text(effect) == ""


class TestEffectsRetrieverLoad:
    def test_disabled_without_index(self, tmp_path: Path) -> None:
        effects_path = _write_corpus(tmp_path, [_effect("a", "A")])
        retriever = EffectsRetriever(
            effects_path,
            tmp_path / "missing.npz",
            tmp_path / "missing.meta.json",
        )
        assert not retriever.enabled

    def test_disabled_on_version_mismatch(self, tmp_path: Path) -> None:
        effects = [_effect("a", "A")]
        effects_path = _write_corpus(tmp_path, effects, version="9.9.9")
        matrix = np.array([[1.0, 0.0]], dtype=np.float32)
        index_path, meta_path = _write_index(
            tmp_path,
            ids=["a"],
            matrix=matrix,
            vector_kinds=["desc"],
            corpus_version="1.1.0",
        )
        retriever = EffectsRetriever(effects_path, index_path, meta_path)
        assert not retriever.enabled

    def test_legacy_index_disabled_with_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        effects = [_effect("a", "A")]
        effects_path = _write_corpus(tmp_path, effects)
        index_path = tmp_path / "effects_index.npz"
        meta_path = tmp_path / "effects_index.meta.json"
        np.savez(index_path, matrix=np.array([[1.0, 0.0]], dtype=np.float32), ids=np.array(["a"], dtype=object))
        meta_path.write_text(
            json.dumps(index_meta_payload("1.1.0", vector_count=1), ensure_ascii=False),
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING):
            retriever = EffectsRetriever(effects_path, index_path, meta_path)

        assert not retriever.enabled
        assert any("legacy index format" in record.message for record in caplog.records)


class TestEffectsRetrieverSearch:
    def test_format_for_prompt(self) -> None:
        effect = _effect("a", "Эффект A")
        block = EffectsRetriever.format_for_prompt([effect])
        assert "Эффект A" in block
        assert "ограничения" in block.lower() or "Ограничения" in block

    def test_search_with_mocked_embeddings(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        effects = [
            _effect("low", "Низкий"),
            _effect("high", "Высокий"),
        ]
        effects_path = _write_corpus(tmp_path, effects)
        matrix = np.array(
            [
                [1.0, 0.0],
                [0.0, 1.0],
            ],
            dtype=np.float32,
        )
        index_path, meta_path = _write_index(
            tmp_path,
            ids=["low", "high"],
            matrix=matrix,
            vector_kinds=["desc", "desc"],
        )
        retriever = EffectsRetriever(effects_path, index_path, meta_path)
        assert retriever.enabled

        def _fake_embed(texts: list[str]) -> np.ndarray:
            if len(texts) == 1 and "высокий" in texts[0].lower():
                return np.array([[0.0, 1.0]], dtype=np.float32)
            return np.array([[1.0, 0.0]], dtype=np.float32)

        monkeypatch.setattr("backend.llm.effects_retriever.embed_texts", _fake_embed)
        monkeypatch.setattr(settings, "effects_score_threshold", 0.1)

        results = retriever.search(["найти высокий эффект"], top_k=1)
        assert len(results) == 1
        assert results[0].id == "high"

    def test_search_filters_below_threshold(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        effects = [_effect("a", "A")]
        effects_path = _write_corpus(tmp_path, effects)
        matrix = np.array([[1.0, 0.0]], dtype=np.float32)
        index_path, meta_path = _write_index(
            tmp_path,
            ids=["a"],
            matrix=matrix,
            vector_kinds=["desc"],
        )
        retriever = EffectsRetriever(effects_path, index_path, meta_path)

        monkeypatch.setattr(
            "backend.llm.effects_retriever.embed_texts",
            lambda _t: np.array([[0.0, 1.0]], dtype=np.float32),
        )
        monkeypatch.setattr(settings, "effects_score_threshold", 0.9)

        assert retriever.search(["query"]) == []

    def test_max_aggregation_two_vectors(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        effect = _effect(
            "eddy_currents",
            "Вихревые токи",
            task_phrases=["бесконтактно нагреть металл"],
        )
        effects_path = _write_corpus(tmp_path, [effect])
        matrix = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float32,
        )
        index_path, meta_path = _write_index(
            tmp_path,
            ids=["eddy_currents", "eddy_currents"],
            matrix=matrix,
            vector_kinds=["desc", "tasks"],
        )
        retriever = EffectsRetriever(effects_path, index_path, meta_path)

        def _fake_embed(texts: list[str]) -> np.ndarray:
            return np.array([[0.0, 1.0, 0.0]], dtype=np.float32)

        monkeypatch.setattr("backend.llm.effects_retriever.embed_texts", _fake_embed)
        monkeypatch.setattr(settings, "effects_score_threshold", 0.5)

        scores = retriever.score_queries(["нагреть металл"])
        assert scores["eddy_currents"] == pytest.approx(1.0)

        results = retriever.search(["нагреть металл"], top_k=1)
        assert len(results) == 1
        assert results[0].id == "eddy_currents"


class TestCalibrateRetriever:
    def test_recall_table_output(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts.calibrate_retriever import run_calibration

        effects = [
            _effect("eddy_currents", "Вихревые токи", task_phrases=["бесконтактно нагреть металл"]),
            _effect("noise", "Шум", task_phrases=["случайный запрос"]),
        ]
        effects_path = _write_corpus(tmp_path, effects)
        matrix = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float32,
        )
        index_path, meta_path = _write_index(
            tmp_path,
            ids=["eddy_currents", "eddy_currents", "noise", "noise"],
            matrix=matrix,
            vector_kinds=["desc", "tasks", "desc", "tasks"],
        )

        def _fake_embed(texts: list[str]) -> np.ndarray:
            if any("нагреть" in text for text in texts):
                return np.array([[0.0, 1.0, 0.0]], dtype=np.float32)
            return np.array([[0.0, 0.0, 1.0]], dtype=np.float32)

        monkeypatch.setattr("backend.llm.effects_retriever.embed_texts", _fake_embed)

        cases = [
            (
                "бесконтактно нагреть локальную зону проводящего металла",
                ["eddy_currents"],
            ),
        ]
        assert run_calibration(effects_path, index_path, meta_path, cases=cases) == 0
        captured = capsys.readouterr().out
        assert "Recall@5" in captured
        assert "threshold" in captured
        assert "HIT" in captured or "hit" in captured.lower()
