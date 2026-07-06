"""Тесты per-run профиля AnalysisProfile."""



from __future__ import annotations



from typing import Any



import pytest



from backend.config import settings

from backend.llm.chain import TRIZChain

from backend.llm.models import AnalysisProfile, PhysicalEffect

from backend.llm.profile_prompts import (

    get_solution_system_prompt,

    get_solution_user_prompt,

)

from backend.llm.solution_prompt import SOLUTION_SYSTEM_PROMPT, SOLUTION_USER_PROMPT

from backend.llm.system_prompt import CORE_USER_PROMPT

from backend.llm.tools_registry import DEFAULT_TOOLS_ENABLED

from tests.test_effects_integration import (

    LEGACY_SOLUTION_USER_PROMPT,

    PROBLEM,

    SAMPLE_EFFECT,

)

from tests.test_fp_validator import _VALID_FP

from tests.test_pipeline_trace import FULL_CORE_FIXTURE, _make_chain, _stub_happy_path





class TestAnalysisProfilePromptParity:

    def test_none_profile_core_user_prompt_unchanged(self) -> None:

        profile = AnalysisProfile.resolve(None)

        assert profile.core_prompt_suffix() == ""

        assert profile.is_default()



        effective = PROBLEM + profile.core_prompt_suffix()

        rendered = CORE_USER_PROMPT.format(problem=effective)

        legacy = CORE_USER_PROMPT.format(problem=PROBLEM)

        assert rendered == legacy



    def test_none_profile_solution_prompts_are_static_objects(self) -> None:

        profile = AnalysisProfile.resolve(None)

        assert get_solution_system_prompt(profile) is SOLUTION_SYSTEM_PROMPT

        assert get_solution_user_prompt(profile) is SOLUTION_USER_PROMPT



    def test_none_profile_core_has_no_profile_prompt_helper(self) -> None:

        """Core-промпты не в profile_prompts; дефолт = пустой suffix, статические CORE_* в chain."""

        profile = AnalysisProfile.resolve(None)

        assert profile.core_prompt_suffix() == ""



    def test_none_profile_solution_user_prompt_unchanged(

        self,

        monkeypatch: pytest.MonkeyPatch,

        fake_llm,

    ) -> None:

        monkeypatch.setattr(settings, "effects_rag_enabled", False)

        chain = _make_chain(monkeypatch, fake_llm)

        profile = AnalysisProfile.resolve(None)



        solution_input = chain._build_solution_input(

            FULL_CORE_FIXTURE, PROBLEM, effects_block=""

        )

        current = SOLUTION_USER_PROMPT.format(**solution_input)

        legacy = LEGACY_SOLUTION_USER_PROMPT.format(

            **{k: v for k, v in solution_input.items() if k != "effects_block"}

        )

        assert current == legacy

        assert profile.target_solutions == 4





class TestAnalysisProfilePsaValidationSkip:

    def test_psa_fp_validation_disabled_skips_validator(

        self,

        monkeypatch: pytest.MonkeyPatch,

        fake_llm,

    ) -> None:

        chain = _make_chain(monkeypatch, fake_llm)

        _stub_happy_path(chain, monkeypatch)



        validate_called = {"n": 0}



        def _spy_validate(*_args: Any, **_kwargs: Any):

            validate_called["n"] += 1

            return FULL_CORE_FIXTURE, 1, [], True



        monkeypatch.setattr(chain, "_validate_and_fix_fp", _spy_validate)



        profile = AnalysisProfile(

            tools_enabled=dict(DEFAULT_TOOLS_ENABLED),

            effects_rag=False,

            target_solutions=4,

            psa_fp_validation=False,

        )

        payload = chain.solve(PROBLEM, profile=profile)



        assert validate_called["n"] == 0

        fp_step = next(

            s for s in payload["pipeline_trace"] if s["step_id"] == "psa_fp_validation"

        )

        assert fp_step["status"] == "warning"

        assert fp_step["validator_notes"] == ["отключено профилем"]



    def test_psa_fp_validation_disabled_still_reconciles_contradiction_type(

        self,

        monkeypatch: pytest.MonkeyPatch,

        fake_llm,

    ) -> None:

        chain = _make_chain(monkeypatch, fake_llm)

        _stub_happy_path(chain, monkeypatch)



        core_needs_reconcile = {

            **FULL_CORE_FIXTURE,

            "physical_contradiction": _VALID_FP,

            "contradiction_type": "техническое",

        }

        chain._run_core_analysis = lambda _problem, brief=None, **_: dict(core_needs_reconcile)



        profile = AnalysisProfile(

            tools_enabled=dict(DEFAULT_TOOLS_ENABLED),

            effects_rag=False,

            target_solutions=4,

            psa_fp_validation=False,

        )

        payload = chain.solve(PROBLEM, profile=profile)



        assert payload["contradiction_type"] == "физическое"

        fp_step = next(

            s for s in payload["pipeline_trace"] if s["step_id"] == "psa_fp_validation"

        )

        assert any("отключено профилем" in n for n in fp_step["validator_notes"])

        assert any("contradiction_type исправлен" in n for n in fp_step["validator_notes"])





class TestAnalysisProfileTargetSolutions:

    def test_target_solutions_substituted_in_prompt(self) -> None:

        profile = AnalysisProfile(

            tools_enabled=dict(DEFAULT_TOOLS_ENABLED),

            effects_rag=False,

            target_solutions=6,

            psa_fp_validation=True,

        )

        prompt = get_solution_user_prompt(profile)

        assert "6" in prompt

        assert "3–5" not in prompt





class TestAnalysisProfileEffectsRag:

    def test_profile_disables_effects_despite_global_flag(

        self,

        monkeypatch: pytest.MonkeyPatch,

        fake_llm,

    ) -> None:

        monkeypatch.setattr(settings, "effects_rag_enabled", True)

        chain = _make_chain(monkeypatch, fake_llm)

        _stub_happy_path(chain, monkeypatch)



        retrieve_called = {"n": 0}

        original = chain._retrieve_effects_for_solutions



        def _spy_retrieve(core: dict, *, profile: AnalysisProfile):

            retrieve_called["n"] += 1

            return original(core, profile=profile)



        chain._retrieve_effects_for_solutions = _spy_retrieve



        profile = AnalysisProfile(

            tools_enabled=dict(DEFAULT_TOOLS_ENABLED),

            effects_rag=False,

            target_solutions=4,

            psa_fp_validation=True,

        )

        payload = chain.solve(PROBLEM, profile=profile)



        assert retrieve_called["n"] == 0

        effects_step = next(

            s for s in payload["pipeline_trace"] if s["step_id"] == "effects_retrieval"

        )

        assert effects_step["validator_notes"] == ["отключён профилем"]

        assert payload.get("effects_used") == []



    def test_profile_enables_effects_when_global_flag_off_and_retriever_disabled(

        self,

        monkeypatch: pytest.MonkeyPatch,

        fake_llm,

    ) -> None:

        monkeypatch.setattr(settings, "effects_rag_enabled", False)

        chain = _make_chain(monkeypatch, fake_llm)

        _stub_happy_path(chain, monkeypatch)



        class DisabledRetriever:

            enabled = False



        monkeypatch.setattr(

            "backend.llm.chain.get_effects_retriever",

            lambda: DisabledRetriever(),

        )



        profile = AnalysisProfile(

            tools_enabled=dict(DEFAULT_TOOLS_ENABLED),

            effects_rag=True,

            target_solutions=4,

            psa_fp_validation=True,

        )

        payload = chain.solve(PROBLEM, profile=profile)



        effects_step = next(

            s for s in payload["pipeline_trace"] if s["step_id"] == "effects_retrieval"

        )

        assert effects_step["step_id"] == "effects_retrieval"

        assert payload.get("effects_used") == []



    def test_profile_enables_effects_when_global_flag_off_and_retriever_ready(

        self,

        monkeypatch: pytest.MonkeyPatch,

        fake_llm,

    ) -> None:

        monkeypatch.setattr(settings, "effects_rag_enabled", False)

        chain = _make_chain(monkeypatch, fake_llm)

        _stub_happy_path(chain, monkeypatch)



        search_called = {"n": 0}



        class ReadyRetriever:

            enabled = True



            def search(self, queries: list[str], top_k: int = 6) -> list[PhysicalEffect]:

                search_called["n"] += 1

                assert queries == ["тест"]

                assert top_k == 6

                return [SAMPLE_EFFECT]



        monkeypatch.setattr(

            "backend.llm.chain.get_effects_retriever",

            lambda: ReadyRetriever(),

        )



        profile = AnalysisProfile(

            tools_enabled=dict(DEFAULT_TOOLS_ENABLED),

            effects_rag=True,

            target_solutions=4,

            psa_fp_validation=True,

        )

        payload = chain.solve(PROBLEM, profile=profile)



        assert search_called["n"] == 1

        assert payload.get("effects_used") == [SAMPLE_EFFECT.name]





class TestAnalysisProfilePayload:

    def test_profile_serialized_in_payload(

        self,

        monkeypatch: pytest.MonkeyPatch,

        fake_llm,

    ) -> None:

        chain = _make_chain(monkeypatch, fake_llm)

        _stub_happy_path(chain, monkeypatch)



        profile = AnalysisProfile(

            tools_enabled={

                **DEFAULT_TOOLS_ENABLED,

                "tool_11_psa": False,

            },

            effects_rag=False,

            target_solutions=5,

            psa_fp_validation=True,

        )

        payload = chain.solve(PROBLEM, profile=profile)



        assert "analysis_profile" in payload

        assert payload["analysis_profile"]["target_solutions"] == 5

        assert payload["analysis_profile"]["tools_enabled"]["tool_11_psa"] is False



        core_step = payload["pipeline_trace"][0]

        assert any("нестандартный профиль" in n for n in core_step["validator_notes"])


