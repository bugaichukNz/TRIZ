"""Тесты детерминированной логики psa_validator."""

from __future__ import annotations

from backend.llm.psa_validator import (
    extract_rejected_component_stems,
    validate_fp_not_rejected_component,
    validate_psa_and_fp_alignment,
    validate_root_cause_not_crutch,
)

_VALID_FP = (
    "Торец волокон: параметр угол сведения должен быть малым, "
    "чтобы минимизировать потери, и должен быть большим, "
    "чтобы обеспечить связь."
)


class TestExtractRejectedStems:
    def test_rejects_lenses_from_constraints(self) -> None:
        core = {
            "ideal_final_result": "Система без линз сводит свет в точку",
            "system_context": {"constraints": ["Отказ от линзовой оптики"]},
        }
        stems = extract_rejected_component_stems(core)
        assert "линз" in stems

    def test_empty_core_no_stems(self) -> None:
        assert extract_rejected_component_stems({}) == []

    def test_rejects_tray_from_without_phrase(self) -> None:
        core = {
            "known_solutions": "Решение без подноса на каждый стакан",
        }
        stems = extract_rejected_component_stems(core)
        assert "поднос" in stems


class TestRootCauseNotCrutch:
    def test_root_cause_with_rejected_lens_fails(self) -> None:
        core = {
            "ideal_final_result": "Без линз",
            "root_cause": "Аберрация линзовой системы вызывает расфокусировку",
        }
        ok, feedback = validate_root_cause_not_crutch(core)
        assert ok is False
        assert "линз" in feedback.lower()

    def test_root_cause_without_rejected_component_passes(self) -> None:
        core = {
            "ideal_final_result": "Без линз",
            "root_cause": "Пространственное разнесение источников света",
            "analysis": {"causal_chains": "источники → зона сведения → корень: геометрия"},
        }
        ok, feedback = validate_root_cause_not_crutch(core)
        assert ok is True
        assert feedback == ""

    def test_causal_chain_tail_with_crutch_fails(self) -> None:
        core = {
            "ideal_final_result": "Отказ от клея",
            "root_cause": "Недостаточная жёсткость конструкции",
            "analysis": {
                "causal_chains": "нагрузка → деформация → слабая адгезия клея → корень: клей"
            },
        }
        ok, feedback = validate_root_cause_not_crutch(core)
        assert ok is False
        assert "кле" in feedback.lower() or "костыл" in feedback.lower()


class TestFpNotRejectedComponent:
    def test_fp_with_rejected_lens_fails(self) -> None:
        core = {
            "ideal_final_result": "Система без линз",
            "physical_contradiction": (
                "Линза: параметр фокусное расстояние должен быть коротким, "
                "чтобы компактность, и должен быть длинным, чтобы точность."
            ),
        }
        ok, feedback = validate_fp_not_rejected_component(
            core["physical_contradiction"],
            core,
        )
        assert ok is False
        assert "линз" in feedback.lower()

    def test_fp_without_rejected_component_passes(self) -> None:
        core = {
            "ideal_final_result": "Без линз",
            "physical_contradiction": _VALID_FP,
        }
        ok, feedback = validate_fp_not_rejected_component(_VALID_FP, core)
        assert ok is True
        assert feedback == ""


class TestPsaAlignment:
    def test_combined_validation_collects_errors(self) -> None:
        core = {
            "ideal_final_result": "Без линз",
            "root_cause": "Дефект линзовой системы",
            "physical_contradiction": (
                "Линза: параметр преломление должен быть сильным, "
                "чтобы фокус, и должен быть слабым, чтобы широкий угол."
            ),
        }
        ok, feedback = validate_psa_and_fp_alignment(core)
        assert ok is False
        assert "root_cause" in feedback.lower() or "линз" in feedback.lower()

    def test_aligned_psa_and_fp_pass(self) -> None:
        core = {
            "ideal_final_result": "Без линз",
            "root_cause": "Геометрия сведения волокон не обеспечивает плотность пучка",
            "physical_contradiction": _VALID_FP,
            "analysis": {"causal_chains": "волокна → зона сведения → корень: угол"},
        }
        ok, feedback = validate_psa_and_fp_alignment(core)
        assert ok is True
        assert feedback == ""
