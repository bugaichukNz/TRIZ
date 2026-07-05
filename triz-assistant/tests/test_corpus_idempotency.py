"""Тесты идемпотентности сборки корпуса физэффектов."""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.llm.effects_corpus import (
    BATCH_COVERAGE_THRESHOLD,
    MAX_BATCH_GENERATION_ATTEMPTS,
    GenerationBatch,
    batch_is_complete,
    batch_missing_ids,
    canonicalize_batch_effects,
    merge_effects,
)
from backend.llm.models import EffectsBatch, PhysicalEffect
from scripts.build_effects_corpus import (
    get_batch_attempts,
    increment_batch_attempt,
    load_build_state,
    run_build,
    save_build_state,
)

_SAMPLE_EFFECT_KW: dict[str, Any] = {
    "category": "физический",
    "description": "Описание эффекта для тестов.",
    "input_action": "вход",
    "output_action": "выход",
    "functions": ["локальный нагрев"],
    "limitations": "ограничения",
    "examples": ["пример"],
}

_MAGNETOSTRICTION = "Магнитострикция"
_THERMAL_EXPANSION = "Тепловое расширение"


def _effect(
    effect_id: str,
    name: str,
    *,
    provenance: str = "planned",
) -> PhysicalEffect:
    return PhysicalEffect(id=effect_id, name=name, provenance=provenance, **_SAMPLE_EFFECT_KW)


def _test_batch() -> GenerationBatch:
    return {
        "key": "test_batch",
        "title": "Тест",
        "category_hint": "физический",
        "topics": _MAGNETOSTRICTION,
        "suggested_ids": {"magnetostriction": _MAGNETOSTRICTION},
        "target_count": 1,
    }


def _magnetostriction_llm_payload(*, effect_id: str = "wrong_slug") -> dict[str, Any]:
    return {
        "id": effect_id,
        "name": _MAGNETOSTRICTION,
        "category": "физический",
        "description": "Изменение размеров в магнитном поле.",
        "input_action": "магнитное поле",
        "output_action": "деформация",
        "functions": ["локальный нагрев"],
        "limitations": "нужен ферромагнетик",
        "examples": ["актуатор"],
    }


class TestCanonicalizeBatchEffects:
    def test_wrong_id_expected_name_gets_canonical_id(self) -> None:
        batch = _test_batch()
        wrong = _effect("wrong_slug", _MAGNETOSTRICTION)
        result = canonicalize_batch_effects(
            batch,
            [wrong],
            missing_ids=["magnetostriction"],
        )
        assert len(result) == 1
        assert result[0].id == "magnetostriction"
        assert result[0].provenance == "planned"

    def test_unmatched_effect_marked_extra(self) -> None:
        batch = _test_batch()
        extra = _effect("surprise_effect", "Совсем другой эффект")
        result = canonicalize_batch_effects(
            batch,
            [extra],
            missing_ids=["magnetostriction"],
        )
        assert result[0].provenance == "extra"


class TestMergeEffectsNameDedup:
    def test_duplicate_name_new_id_skipped(self) -> None:
        existing = [_effect("magnetostriction", _MAGNETOSTRICTION)]
        duplicate = _effect("other_id", "магнитострикция")
        merged = merge_effects(existing, [duplicate])
        assert len(merged) == 1
        assert merged[0].id == "magnetostriction"


class TestBatchCompletion:
    def test_closed_after_two_attempts_even_if_ids_missing(self) -> None:
        batch = _test_batch()
        assert batch_is_complete(
            batch,
            existing_ids=set(),
            batch_count=0,
            attempt_count=MAX_BATCH_GENERATION_ATTEMPTS,
        )

    def test_not_closed_with_zero_attempts_and_empty_corpus(self) -> None:
        batch = _test_batch()
        assert not batch_is_complete(
            batch,
            existing_ids=set(),
            batch_count=0,
            attempt_count=0,
        )

    def test_closed_at_coverage_threshold(self) -> None:
        batch: GenerationBatch = {
            "key": "multi",
            "title": "Multi",
            "category_hint": "физический",
            "topics": "a, b, c, d, e",
            "suggested_ids": {
                "id_a": "a",
                "id_b": "b",
                "id_c": "c",
                "id_d": "d",
                "id_e": "e",
            },
            "target_count": 5,
        }
        existing = {"id_a", "id_b", "id_c", "id_d"}
        assert batch_is_complete(
            batch,
            existing_ids=existing,
            batch_count=4,
            attempt_count=0,
            coverage_threshold=BATCH_COVERAGE_THRESHOLD,
        )


class TestBuildState:
    def test_increment_persists(self, tmp_path) -> None:
        path = tmp_path / ".build_state.json"
        state = load_build_state(path)
        assert get_batch_attempts(state, "test_batch") == 0
        assert increment_batch_attempt(state, "test_batch") == 1
        save_build_state(path, state)
        reloaded = load_build_state(path)
        assert get_batch_attempts(reloaded, "test_batch") == 1


class TestRunBuildIdempotency:
    @pytest.fixture
    def mock_llm(self, fake_llm):
        return fake_llm(
            {EffectsBatch: {"effects": [_magnetostriction_llm_payload()]}}
        )

    @pytest.fixture
    def single_batch(self, monkeypatch: pytest.MonkeyPatch) -> GenerationBatch:
        batch = _test_batch()
        monkeypatch.setattr(
            "scripts.build_effects_corpus.GENERATION_BATCHES",
            [batch],
        )
        monkeypatch.setattr(
            "scripts.build_effects_corpus.MIN_TARGET",
            1,
        )
        return batch

    def test_double_run_same_corpus_size(
        self,
        tmp_path,
        mock_llm,
        single_batch: GenerationBatch,
    ) -> None:
        output = tmp_path / "effects.json"
        state_path = tmp_path / ".build_state.json"

        run_build(
            output,
            build_state_path=state_path,
            llm=mock_llm,
            pause_sec=0,
        )
        after_first = json.loads(output.read_text(encoding="utf-8"))
        assert len(after_first["effects"]) == 1
        assert after_first["effects"][0]["id"] == "magnetostriction"

        run_build(
            output,
            build_state_path=state_path,
            llm=mock_llm,
            pause_sec=0,
        )
        after_second = json.loads(output.read_text(encoding="utf-8"))
        assert after_second == after_first
        assert get_batch_attempts(load_build_state(state_path), single_batch["key"]) == 1

    def test_second_run_skips_generation(
        self,
        tmp_path,
        mock_llm,
        single_batch: GenerationBatch,
    ) -> None:
        output = tmp_path / "effects.json"
        state_path = tmp_path / ".build_state.json"

        run_build(output, build_state_path=state_path, llm=mock_llm, pause_sec=0)
        state_after = load_build_state(state_path)
        attempts_after_first = get_batch_attempts(state_after, single_batch["key"])

        run_build(output, build_state_path=state_path, llm=mock_llm, pause_sec=0)
        state_after_second = load_build_state(state_path)
        assert get_batch_attempts(state_after_second, single_batch["key"]) == attempts_after_first

    def test_batch_closed_after_two_attempts_without_full_coverage(
        self,
        tmp_path,
        fake_llm,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        batch: GenerationBatch = {
            "key": "stub_batch",
            "title": "Stub",
            "category_hint": "физический",
            "topics": f"{_MAGNETOSTRICTION}, {_THERMAL_EXPANSION}",
            "suggested_ids": {
                "magnetostriction": _MAGNETOSTRICTION,
                "thermal_expansion": _THERMAL_EXPANSION,
            },
            "target_count": 2,
        }
        monkeypatch.setattr("scripts.build_effects_corpus.GENERATION_BATCHES", [batch])
        monkeypatch.setattr("scripts.build_effects_corpus.MIN_TARGET", 1)

        llm = fake_llm({EffectsBatch: {"effects": [_magnetostriction_llm_payload()]}})

        output = tmp_path / "effects.json"
        state_path = tmp_path / ".build_state.json"

        run_build(output, build_state_path=state_path, llm=llm, pause_sec=0)
        assert batch_missing_ids(batch, {"magnetostriction"}) == ["thermal_expansion"]

        run_build(output, build_state_path=state_path, llm=llm, pause_sec=0)
        assert get_batch_attempts(load_build_state(state_path), "stub_batch") == 2
        assert batch_is_complete(
            batch,
            {e["id"] for e in json.loads(output.read_text(encoding="utf-8"))["effects"]},
            batch_count=1,
            attempt_count=2,
        )

        run_build(output, build_state_path=state_path, llm=llm, pause_sec=0)
        assert get_batch_attempts(load_build_state(state_path), "stub_batch") == 2
