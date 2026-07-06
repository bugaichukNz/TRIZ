"""Тесты трассировки pipeline_trace в TRIZChain.solve."""

from __future__ import annotations

from typing import Any

import pytest

from backend.config import settings
from backend.llm import chain as chain_module
from backend.llm.chain import TRIZChain
from backend.llm.models import EffectQueries, SolutionSet
from backend.llm.solution_prompt import SOLUTION_USER_PROMPT
from tests.test_effects_integration import (
    CORE_FIXTURE,
    LEGACY_SOLUTION_USER_PROMPT,
    PROBLEM,
    SAMPLE_SOLUTIONS,
)

EXPECTED_STEP_IDS = [
    "core_analysis",
    "psa_fp_validation",
    "effects_retrieval",
    "solution_generation",
    "assembly",
]

FULL_CORE_FIXTURE: dict[str, Any] = {
    **CORE_FIXTURE,
    "contradiction_type": "физическое",
    "assumptions": [],
    "triz_tools": [
        {
            "tool": "Инструмент 2: Постановка задачи",
            "why_applied": "Формализация НЭ",
            "insight": "Задача о стекании воды",
            "practical_value": "База для анализа",
        },
        {
            "tool": "Инструмент 11 (ПСА)",
            "why_applied": "Поиск корневой причины",
            "insight": "Гравитация создаёт конфликт",
            "practical_value": "root_cause",
        },
        {
            "tool": "Инструмент 14 (КСА)",
            "why_applied": "Структура системы",
            "insight": "Поднос — носитель",
            "practical_value": "Контекст",
        },
    ],
}


def _pass_validation(*_args: Any, **_kwargs: Any) -> tuple[bool, str, list[dict]]:
    batch = [s.model_dump() for s in SAMPLE_SOLUTIONS.solution_concepts]
    return True, "", batch


def _make_chain(monkeypatch: pytest.MonkeyPatch, fake_llm) -> TRIZChain:
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    llm = fake_llm(
        {
            EffectQueries: {"queries": ["тест"]},
            SolutionSet: SAMPLE_SOLUTIONS,
        }
    )
    monkeypatch.setattr("backend.llm.chain.create_chat_llm", lambda **_kw: llm)
    return TRIZChain()


def _stub_happy_path(chain: TRIZChain, monkeypatch: pytest.MonkeyPatch) -> None:
    chain._run_core_analysis = lambda _problem, brief=None: dict(FULL_CORE_FIXTURE)
    monkeypatch.setattr("backend.llm.chain.validate_psa_and_fp_alignment", lambda _c: (True, ""))
    monkeypatch.setattr(
        "backend.llm.chain.validate_fp",
        lambda *_a, **_k: (True, ""),
    )
    monkeypatch.setattr("backend.llm.chain.validate_solutions", _pass_validation)
    monkeypatch.setattr(
        "backend.llm.chain.check_solution_diversity",
        lambda *_a, **_k: (True, ""),
    )


class TestPipelineTraceStructure:
    def test_solve_returns_five_steps_in_order(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)

        payload = chain.solve(PROBLEM)
        trace = payload.get("pipeline_trace") or []

        assert len(trace) == 5
        assert [step["step_id"] for step in trace] == EXPECTED_STEP_IDS
        assert trace[0]["tools_used"] == [row["tool"] for row in FULL_CORE_FIXTURE["triz_tools"]]
        assert trace[3]["tools_used"] == [
            s.triz_principle for s in SAMPLE_SOLUTIONS.solution_concepts
        ]


class TestPipelineTraceFpRetry:
    def test_fp_retry_reflected_in_trace(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        chain = _make_chain(monkeypatch, fake_llm)
        chain._run_core_analysis = lambda _problem, brief=None: dict(FULL_CORE_FIXTURE)

        fp_calls = {"n": 0}

        def _validate_fp(*_args: Any, **_kwargs: Any) -> tuple[bool, str]:
            fp_calls["n"] += 1
            if fp_calls["n"] == 1:
                return False, "ФП не соответствует формуле: параметр не один"
            return True, ""

        monkeypatch.setattr("backend.llm.chain.validate_psa_and_fp_alignment", lambda _c: (True, ""))
        monkeypatch.setattr("backend.llm.chain.validate_fp", _validate_fp)
        monkeypatch.setattr("backend.llm.chain.validate_solutions", _pass_validation)
        monkeypatch.setattr(
            "backend.llm.chain.check_solution_diversity",
            lambda *_a, **_k: (True, ""),
        )

        repaired = {
            "root_cause": FULL_CORE_FIXTURE["root_cause"],
            "causal_chains": FULL_CORE_FIXTURE["analysis"]["causal_chains"],
            "technical_contradiction": FULL_CORE_FIXTURE["technical_contradiction"],
            "physical_contradiction": FULL_CORE_FIXTURE["physical_contradiction"],
        }
        chain._regenerate_contradictions = lambda *_a, **_k: dict(repaired)

        payload = chain.solve(PROBLEM)
        fp_step = next(s for s in payload["pipeline_trace"] if s["step_id"] == "psa_fp_validation")

        assert fp_step["attempts"] == 2
        assert fp_step["status"] == "ok_with_retries"
        assert any("формул" in n.lower() for n in fp_step["validator_notes"])


class TestPipelineTraceEffectsDisabled:
    def test_disabled_effects_step_present_with_note(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        monkeypatch.setattr(settings, "effects_rag_enabled", False)
        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)

        payload = chain.solve(PROBLEM)
        effects_step = next(
            s for s in payload["pipeline_trace"] if s["step_id"] == "effects_retrieval"
        )

        assert effects_step["status"] == "ok"
        assert effects_step["tools_used"] == []
        assert effects_step["validator_notes"] == ["отключён"]


class TestPipelineTraceResilience:
    def test_trace_exception_does_not_break_solve(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)

        real_trace = chain_module.PipelineStepTrace

        class _SelectiveFailingTrace(real_trace):
            def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
                if self.step_id == "psa_fp_validation":
                    raise RuntimeError("simulated trace failure")
                return super().model_dump(*args, **kwargs)

        monkeypatch.setattr(chain_module, "PipelineStepTrace", _SelectiveFailingTrace)

        payload = chain.solve(PROBLEM)

        assert len(payload.get("solution_concepts", [])) == 3
        trace = payload.get("pipeline_trace") or []
        assert len(trace) == 4
        assert [s["step_id"] for s in trace] == [
            "core_analysis",
            "effects_retrieval",
            "solution_generation",
            "assembly",
        ]


class TestPipelineTracePromptParity:
    def test_trace_does_not_change_solution_prompt(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        """Trace не меняет тексты промптов, уходящих в LLM."""
        monkeypatch.setattr(settings, "effects_rag_enabled", False)
        chain = _make_chain(monkeypatch, fake_llm)

        solution_input = chain._build_solution_input(
            FULL_CORE_FIXTURE, PROBLEM, effects_block=""
        )
        current = SOLUTION_USER_PROMPT.format(**solution_input)
        legacy = LEGACY_SOLUTION_USER_PROMPT.format(
            **{k: v for k, v in solution_input.items() if k != "effects_block"}
        )
        assert current == legacy
