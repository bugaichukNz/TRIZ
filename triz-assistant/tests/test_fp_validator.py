"""Тесты детерминированной логики fp_validator."""

from __future__ import annotations

import pytest

from backend.llm.fp_validator import (
    _FPValueDesirabilityResult,
    _has_spatial_split,
    check_contradiction_type_consistency,
    fp_has_temporal_resolution,
    looks_like_fp_formulation,
    reconcile_contradiction_type,
    task_has_process_phases,
    validate_fp,
    validate_fp_resolution_axis,
)

_VALID_FP = (
    "Поднос: параметр влажность поверхности должен быть высокой, "
    "чтобы вода стекала с краёв, и должен быть низкой, "
    "чтобы этикетка оставалась сухой."
)

_TEMPORAL_FP = (
    "Катетер: параметр диаметр отверстий на фазе введения "
    "должен быть широким, чтобы снизить сопротивление, "
    "и на фазе фиксации должен быть узким, чтобы удерживать положение."
)

_SPATIAL_FP = (
    "Стакан: параметр влажность внутри должен быть высокой, "
    "чтобы напиток не вытекал, и снаружи должен быть низкой, "
    "чтобы поднос оставался сухим."
)


class TestFpFormula:
    def test_valid_formula_passes(self) -> None:
        assert looks_like_fp_formulation(_VALID_FP) is True

    def test_temporal_formula_passes(self) -> None:
        assert looks_like_fp_formulation(_TEMPORAL_FP) is True

    def test_empty_formula_fails(self) -> None:
        assert looks_like_fp_formulation("") is False

    def test_malformed_formula_fails(self) -> None:
        text = "Поднос должен быть и мокрым, и сухим одновременно."
        assert looks_like_fp_formulation(text) is False


class TestSpatialSplit:
    def test_inside_outside_rejected(self) -> None:
        spatial, feedback = _has_spatial_split(_SPATIAL_FP)
        assert spatial is True
        assert "внутри" in feedback.lower() or "пространствен" in feedback.lower()

    def test_valid_fp_no_spatial_split(self) -> None:
        spatial, feedback = _has_spatial_split(_VALID_FP)
        assert spatial is False
        assert feedback == ""

    def test_one_side_only_not_spatial(self) -> None:
        text = "Стакан: параметр температура должен быть высокой, чтобы сохранить вкус."
        spatial, _ = _has_spatial_split(text)
        assert spatial is False


class TestPhaseResolution:
    def test_temporal_fp_has_phase_resolution(self) -> None:
        assert fp_has_temporal_resolution(_TEMPORAL_FP) is True

    def test_static_fp_no_temporal_resolution(self) -> None:
        assert fp_has_temporal_resolution(_VALID_FP) is False

    def test_task_with_phases_detected(self) -> None:
        core = {"problem_description": "Сначала инкубация, потом эксперимент в узком канале."}
        assert task_has_process_phases(core) is True

    def test_phase_separation_passes_axis_check(self) -> None:
        core = {"problem_description": "На этапе загрузки и на этапе выдачи разные требования."}
        ok, feedback = validate_fp_resolution_axis(_TEMPORAL_FP, core)
        assert ok is True
        assert feedback == ""

    def test_static_fp_fails_when_task_has_phases(self) -> None:
        core = {"problem_description": "Сначала инкубация в широкой камере, потом эксперимент."}
        ok, feedback = validate_fp_resolution_axis(_VALID_FP, core)
        assert ok is False
        assert "фаз" in feedback.lower() or "время" in feedback.lower()


class TestReconcileContradictionType:
    def test_switches_type_to_physical(self) -> None:
        core = {
            "physical_contradiction": _VALID_FP,
            "contradiction_type": "техническое",
        }
        updated, note = reconcile_contradiction_type(core)
        assert updated["contradiction_type"] == "физическое"
        assert "физическое" in note

    def test_already_physical_unchanged(self) -> None:
        core = {
            "physical_contradiction": _VALID_FP,
            "contradiction_type": "физическое",
        }
        updated, note = reconcile_contradiction_type(core)
        assert updated["contradiction_type"] == "физическое"
        assert note == ""

    def test_non_formula_skips_reconcile(self) -> None:
        core = {
            "physical_contradiction": "просто текст без формулы",
            "contradiction_type": "техническое",
        }
        consistent, _ = check_contradiction_type_consistency(core)
        assert consistent is True


class TestValidateFpWithFakeLlm:
    def test_formula_passes_with_desirable_values(self, fake_llm) -> None:
        llm = fake_llm(
            {
                _FPValueDesirabilityResult: _FPValueDesirabilityResult(
                    inherently_desirable=True,
                    feedback="",
                )
            }
        )
        passed, feedback = validate_fp(_VALID_FP, "ТП: нужно и то, и другое", llm)
        assert passed is True
        assert feedback == ""

    def test_spatial_rejected_before_llm(self, fake_llm) -> None:
        llm = fake_llm()
        passed, feedback = validate_fp(_SPATIAL_FP, "", llm)
        assert passed is False
        assert feedback

    @pytest.mark.parametrize(
        "fp_text",
        [
            _VALID_FP,
            _TEMPORAL_FP,
        ],
    )
    def test_bilateral_formulas_accepted(self, fp_text: str) -> None:
        assert looks_like_fp_formulation(fp_text) is True
