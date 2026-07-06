"""Тесты TRIZChain.resume и POST /solve/entries/{entry_id}/rerun."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.auth import create_access_token, get_current_user
from backend.config import settings
from backend.llm.chain import TRIZChain, TRIZChainError, _RESTORED_TRACE_NOTE, validate_psa_fp_override
from backend.llm.models import AnalysisProfile, EffectQueries, SolutionSet
from backend.llm.solution_prompt import SOLUTION_USER_PROMPT
from backend.main import (
    app,
    get_artifacts_store,
    get_chain,
    get_sessions_store,
)
from backend.sessions_store import SessionsStore
from backend.artifacts_store import ArtifactsStore
from backend.stage_artifact_hooks import make_artifact_buffer, persist_buffered_artifacts
from tests.test_effects_integration import PROBLEM, SAMPLE_SOLUTIONS
from tests.test_pipeline_trace import FULL_CORE_FIXTURE, _make_chain, _stub_happy_path

NEW_FP = (
    "Поднос: параметр шероховатость поверхности должна быть высокой, "
    "чтобы удерживать стаканы, и должна быть низкой, "
    "чтобы вода стекала без задержки."
)


def _pass_validation(*_args: Any, **_kwargs: Any) -> tuple[bool, str, list[dict]]:
    batch = [s.model_dump() for s in SAMPLE_SOLUTIONS.solution_concepts]
    return True, "", batch


def _full_artifacts(
    *,
    psa_override: dict[str, Any] | None = None,
) -> dict[str, dict]:
    psa = {
        "root_cause": FULL_CORE_FIXTURE["root_cause"],
        "causal_chains": FULL_CORE_FIXTURE["analysis"]["causal_chains"],
        "technical_contradiction": FULL_CORE_FIXTURE["technical_contradiction"],
        "physical_contradiction": FULL_CORE_FIXTURE["physical_contradiction"],
        "contradiction_type": FULL_CORE_FIXTURE["contradiction_type"],
    }
    if psa_override:
        psa.update(psa_override)

    solutions = [s.model_dump() for s in SAMPLE_SOLUTIONS.solution_concepts]
    return {
        "core_analysis": dict(FULL_CORE_FIXTURE),
        "psa_fp_validation": psa,
        "effects_retrieval": {
            "effects_block": "",
            "effects_used": [],
            "queries": [],
        },
        "solution_generation": {
            "solutions": solutions,
            "generation_warning": "",
        },
    }


@pytest.fixture
def isolated_stores(tmp_path):
    db_path = tmp_path / "rerun.db"
    sessions = SessionsStore(db_path=db_path, max_entries=10)
    artifacts = ArtifactsStore(db_path=db_path)
    return sessions, artifacts


class TestResumeChain:
    def test_resume_solution_generation_uses_overridden_fp_in_prompt(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)

        captured_inputs: list[dict] = []
        original_generate = chain._generate_solutions

        def _capture_generate(core, problem, **kwargs):
            captured_inputs.append(
                chain._build_solution_input(
                    core,
                    problem,
                    validator_feedback=kwargs.get("validator_feedback", ""),
                    brief=kwargs.get("brief"),
                    effects_block=kwargs.get("effects_block", ""),
                )
            )
            return original_generate(core, problem, **kwargs)

        chain._generate_solutions = _capture_generate  # type: ignore[method-assign]

        artifacts = _full_artifacts(
            psa_override={"physical_contradiction": NEW_FP},
        )
        chain.resume(
            PROBLEM,
            from_step="solution_generation",
            artifacts=artifacts,
        )

        assert captured_inputs
        prompt_text = SOLUTION_USER_PROMPT.format(**captured_inputs[0])
        assert NEW_FP in prompt_text
        assert FULL_CORE_FIXTURE["physical_contradiction"] not in prompt_text

    def test_resume_missing_artifact_raises_triz_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)

        artifacts = _full_artifacts()
        del artifacts["psa_fp_validation"]

        with pytest.raises(Exception) as exc_info:
            chain.resume(
                PROBLEM,
                from_step="effects_retrieval",
                artifacts=artifacts,
            )

        message = str(exc_info.value)
        assert "psa_fp_validation" in message
        assert "не хватает артефактов" in message

    def test_resume_trace_marks_restored_steps(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)

        payload = chain.resume(
            PROBLEM,
            from_step="solution_generation",
            artifacts=_full_artifacts(),
        )
        trace = payload["pipeline_trace"]

        restored = [s for s in trace if _RESTORED_TRACE_NOTE in s["validator_notes"]]
        executed = [s for s in trace if _RESTORED_TRACE_NOTE not in s["validator_notes"]]

        assert [s["step_id"] for s in restored] == [
            "core_analysis",
            "psa_fp_validation",
            "effects_retrieval",
        ]
        assert [s["step_id"] for s in executed] == ["solution_generation", "assembly"]
        for step in restored:
            assert step["status"] == "ok"
            assert step["attempts"] == 0
            assert step["duration_ms"] == 0


class TestRerunEndpoint:
    def _setup_parent_entry(
        self,
        sessions: SessionsStore,
        artifacts: ArtifactsStore,
        *,
        profile: AnalysisProfile | None = None,
        parent_profile_hash: str = "parent-profile-hash",
    ) -> dict[str, Any]:
        chain = TRIZChain.__new__(TRIZChain)
        on_stage_complete, buffer, _profile_hash = make_artifact_buffer(profile)
        artifact_dict = _full_artifacts()
        for step_id, payload in artifact_dict.items():
            buffer.append((step_id, payload))

        resolved = AnalysisProfile.resolve(profile)
        result = {
            "problem_description": PROBLEM,
            "technical_contradiction": FULL_CORE_FIXTURE["technical_contradiction"],
            "physical_contradiction": FULL_CORE_FIXTURE["physical_contradiction"],
            "contradiction_type": FULL_CORE_FIXTURE["contradiction_type"],
            "ideal_final_result": FULL_CORE_FIXTURE["ideal_final_result"],
            "root_cause": FULL_CORE_FIXTURE["root_cause"],
            "analysis": FULL_CORE_FIXTURE["analysis"],
            "system_context": FULL_CORE_FIXTURE["system_context"],
            "triz_tools": FULL_CORE_FIXTURE["triz_tools"],
            "solution_concepts": artifact_dict["solution_generation"]["solutions"],
            "effects_used": [],
            "analysis_profile": resolved.model_dump(),
            "assumptions": [],
            "recommendations": {"ranked": [], "summary": ""},
            "final_conclusion": {"text": ""},
            "recommended_principles": [],
            "executive_summary": "test",
            "contradiction": FULL_CORE_FIXTURE["technical_contradiction"],
            "solutions": [],
            "reasoning": "",
        }
        entry = sessions.add_entry(PROBLEM, result, user_id="owner")
        persist_buffered_artifacts(
            artifacts,
            entry["id"],
            "owner",
            parent_profile_hash,
            buffer,
        )
        return entry

    def _patch_main_stores(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sessions: SessionsStore,
        artifacts_store: ArtifactsStore,
        chain: TRIZChain,
    ) -> None:
        monkeypatch.setattr("backend.main.get_sessions_store", lambda: sessions)
        monkeypatch.setattr("backend.main.get_artifacts_store", lambda: artifacts_store)
        monkeypatch.setattr("backend.main.get_chain", lambda: chain)
        app.dependency_overrides[get_sessions_store] = lambda: sessions
        app.dependency_overrides[get_artifacts_store] = lambda: artifacts_store
        app.dependency_overrides[get_chain] = lambda: chain
        app.dependency_overrides[get_current_user] = lambda: {"id": "owner", "username": "owner"}

    def test_rerun_applies_overrides_and_creates_child_entry(
        self,
        isolated_stores,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        sessions, artifacts_store = isolated_stores
        parent = self._setup_parent_entry(sessions, artifacts_store)

        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)
        monkeypatch.setattr("backend.llm.chain.validate_solutions", _pass_validation)
        monkeypatch.setattr(
            "backend.llm.chain.check_solution_diversity",
            lambda *_a, **_k: (True, ""),
        )

        self._patch_main_stores(monkeypatch, sessions, artifacts_store, chain)

        try:
            client = TestClient(app)
            token = create_access_token("owner", "owner")
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.post(
                f"/solve/entries/{parent['id']}/rerun",
                headers=headers,
                json={
                    "from_step": "solution_generation",
                    "overrides": {
                        "psa_fp_validation": {
                            "root_cause": FULL_CORE_FIXTURE["root_cause"],
                            "causal_chains": FULL_CORE_FIXTURE["analysis"]["causal_chains"],
                            "technical_contradiction": FULL_CORE_FIXTURE["technical_contradiction"],
                            "physical_contradiction": NEW_FP,
                            "contradiction_type": "физическое",
                        }
                    },
                },
            )
            assert resp.status_code == 200
            job_id = resp.json()["job_id"]

            deadline = time.time() + 5.0
            job_body = None
            while time.time() < deadline:
                status_resp = client.get(f"/solve/jobs/{job_id}", headers=headers)
                job_body = status_resp.json()
                if job_body["status"] in ("done", "error"):
                    break
                time.sleep(0.05)

            assert job_body is not None
            assert job_body["status"] == "done", job_body.get("error")

            children = [
                e
                for e in sessions.list_entries("owner")
                if e.get("parent_entry_id") == parent["id"]
            ]
            assert len(children) == 1
            child = children[0]
            assert child["parent_entry_id"] == parent["id"]
            assert child["result"].get("rerun_from_step") == "solution_generation"
            assert NEW_FP in child["result"]["physical_contradiction"]

            child_psa = artifacts_store.get(
                child["id"], "psa_fp_validation", user_id="owner"
            )
            assert child_psa is not None
            assert child_psa.payload["physical_contradiction"] == NEW_FP
            assert child_psa.payload.get("_user_override") is True
        finally:
            app.dependency_overrides.clear()

    def test_rerun_empty_fp_override_returns_400_before_job(
        self,
        isolated_stores,
    ) -> None:
        sessions, artifacts_store = isolated_stores
        parent = self._setup_parent_entry(sessions, artifacts_store)

        app.dependency_overrides[get_sessions_store] = lambda: sessions
        app.dependency_overrides[get_artifacts_store] = lambda: artifacts_store
        app.dependency_overrides[get_current_user] = lambda: {"id": "owner", "username": "owner"}

        try:
            client = TestClient(app)
            token = create_access_token("owner", "owner")
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.post(
                f"/solve/entries/{parent['id']}/rerun",
                headers=headers,
                json={
                    "from_step": "solution_generation",
                    "overrides": {
                        "psa_fp_validation": {
                            "physical_contradiction": "   ",
                        }
                    },
                },
            )
            assert resp.status_code == 400
            assert "пусто поле" in resp.json()["detail"]
            assert "physical_contradiction" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_rerun_partial_override_root_cause_allowed(
        self,
        isolated_stores,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        sessions, artifacts_store = isolated_stores
        parent = self._setup_parent_entry(sessions, artifacts_store)
        new_root = "Новая корневая причина без правки ТП/ФП"

        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)
        monkeypatch.setattr("backend.llm.chain.validate_solutions", _pass_validation)
        monkeypatch.setattr(
            "backend.llm.chain.check_solution_diversity",
            lambda *_a, **_k: (True, ""),
        )
        self._patch_main_stores(monkeypatch, sessions, artifacts_store, chain)

        try:
            client = TestClient(app)
            token = create_access_token("owner", "owner")
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.post(
                f"/solve/entries/{parent['id']}/rerun",
                headers=headers,
                json={
                    "from_step": "solution_generation",
                    "overrides": {
                        "psa_fp_validation": {"root_cause": new_root},
                    },
                },
            )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_rerun_profile_hash_restored_vs_override(
        self,
        isolated_stores,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        parent_hash = "parent-hash-aaa"
        sessions, artifacts_store = isolated_stores
        parent = self._setup_parent_entry(
            sessions,
            artifacts_store,
            parent_profile_hash=parent_hash,
        )

        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)
        monkeypatch.setattr("backend.llm.chain.validate_solutions", _pass_validation)
        monkeypatch.setattr(
            "backend.llm.chain.check_solution_diversity",
            lambda *_a, **_k: (True, ""),
        )
        self._patch_main_stores(monkeypatch, sessions, artifacts_store, chain)

        try:
            client = TestClient(app)
            token = create_access_token("owner", "owner")
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.post(
                f"/solve/entries/{parent['id']}/rerun",
                headers=headers,
                json={
                    "from_step": "solution_generation",
                    "profile": AnalysisProfile.default_profile().model_copy(
                        update={"target_solutions": 3},
                    ).model_dump(),
                    "overrides": {
                        "psa_fp_validation": {
                            "root_cause": FULL_CORE_FIXTURE["root_cause"],
                            "causal_chains": FULL_CORE_FIXTURE["analysis"]["causal_chains"],
                            "technical_contradiction": FULL_CORE_FIXTURE["technical_contradiction"],
                            "physical_contradiction": NEW_FP,
                            "contradiction_type": "физическое",
                        }
                    },
                },
            )
            job_id = resp.json()["job_id"]

            deadline = time.time() + 5.0
            while time.time() < deadline:
                status_resp = client.get(f"/solve/jobs/{job_id}", headers=headers)
                if status_resp.json()["status"] in ("done", "error"):
                    break
                time.sleep(0.05)

            children = [
                e for e in sessions.list_entries("owner") if e.get("parent_entry_id") == parent["id"]
            ]
            child_id = children[0]["id"]

            restored_core = artifacts_store.get(child_id, "core_analysis", user_id="owner")
            override_psa = artifacts_store.get(child_id, "psa_fp_validation", user_id="owner")
            assert restored_core is not None
            assert override_psa is not None
            assert restored_core.profile_hash == parent_hash
            assert override_psa.profile_hash != parent_hash
            assert override_psa.payload.get("_user_override") is True
        finally:
            app.dependency_overrides.clear()

    def test_job_poller_exposes_rerun_lineage(
        self,
        isolated_stores,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        sessions, artifacts_store = isolated_stores
        parent = self._setup_parent_entry(sessions, artifacts_store)

        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)
        self._patch_main_stores(monkeypatch, sessions, artifacts_store, chain)

        try:
            client = TestClient(app)
            token = create_access_token("owner", "owner")
            headers = {"Authorization": f"Bearer {token}"}

            rerun_resp = client.post(
                f"/solve/entries/{parent['id']}/rerun",
                headers=headers,
                json={"from_step": "assembly", "overrides": {}},
            )
            rerun_job_id = rerun_resp.json()["job_id"]

            deadline = time.time() + 5.0
            rerun_body = None
            while time.time() < deadline:
                status_resp = client.get(f"/solve/jobs/{rerun_job_id}", headers=headers)
                rerun_body = status_resp.json()
                if rerun_body["status"] in ("done", "error"):
                    break
                time.sleep(0.05)

            assert rerun_body["status"] == "done"
            assert rerun_body["job_kind"] == "rerun"
            assert rerun_body["parent_entry_id"] == parent["id"]
            assert rerun_body["rerun_from_step"] == "assembly"
            assert rerun_body["result"]["parent_entry_id"] == parent["id"]
            assert rerun_body["result"]["rerun_from_step"] == "assembly"

            solve_resp = client.post(
                "/solve/jobs",
                headers=headers,
                json={"problem": PROBLEM},
            )
            solve_job_id = solve_resp.json()["job_id"]
            solve_body = client.get(f"/solve/jobs/{solve_job_id}", headers=headers).json()
            assert solve_body["job_kind"] == "solve"
            assert solve_body["parent_entry_id"] is None
            assert solve_body["rerun_from_step"] is None
            if solve_body["result"] is not None:
                assert solve_body["result"].get("parent_entry_id") is None
                assert solve_body["result"].get("rerun_from_step") is None
        finally:
            app.dependency_overrides.clear()

    def test_validate_psa_fp_override_rejects_empty_tp(
        self,
    ) -> None:
        with pytest.raises(TRIZChainError, match="пусто поле"):
            validate_psa_fp_override(
                {"psa_fp_validation": {"technical_contradiction": ""}},
            )

    def test_rerun_foreign_entry_returns_404(
        self,
        isolated_stores,
    ) -> None:
        sessions, artifacts_store = isolated_stores
        parent = self._setup_parent_entry(sessions, artifacts_store)

        app.dependency_overrides[get_sessions_store] = lambda: sessions
        app.dependency_overrides[get_artifacts_store] = lambda: artifacts_store
        app.dependency_overrides[get_current_user] = lambda: {"id": "other", "username": "other"}

        try:
            client = TestClient(app)
            token = create_access_token("other", "other")
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.post(
                f"/solve/entries/{parent['id']}/rerun",
                headers=headers,
                json={"from_step": "assembly", "overrides": {}},
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_rerun_inherits_parent_profile_when_null(
        self,
        isolated_stores,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        custom_profile = AnalysisProfile.default_profile().model_copy(
            update={"effects_rag": False, "target_solutions": 3},
        )
        sessions, artifacts_store = isolated_stores
        parent = self._setup_parent_entry(sessions, artifacts_store, profile=custom_profile)

        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)

        captured_profiles: list[AnalysisProfile | None] = []
        original_run = chain._run_pipeline

        def _capture_run(problem, **kwargs):
            captured_profiles.append(kwargs.get("profile"))
            return original_run(problem, **kwargs)

        chain._run_pipeline = _capture_run  # type: ignore[method-assign]

        self._patch_main_stores(monkeypatch, sessions, artifacts_store, chain)

        try:
            client = TestClient(app)
            token = create_access_token("owner", "owner")
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.post(
                f"/solve/entries/{parent['id']}/rerun",
                headers=headers,
                json={"from_step": "assembly", "overrides": {}, "profile": None},
            )
            job_id = resp.json()["job_id"]

            deadline = time.time() + 5.0
            while time.time() < deadline:
                status_resp = client.get(f"/solve/jobs/{job_id}", headers=headers)
                if status_resp.json()["status"] in ("done", "error"):
                    break
                time.sleep(0.05)

            assert captured_profiles
            applied = AnalysisProfile.resolve(captured_profiles[-1])
            assert applied.target_solutions == 3
            assert applied.effects_rag is False
        finally:
            app.dependency_overrides.clear()

    def test_rerun_assembly_empty_overrides_equivalent_solutions(
        self,
        isolated_stores,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        sessions, artifacts_store = isolated_stores
        parent = self._setup_parent_entry(sessions, artifacts_store)

        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)

        self._patch_main_stores(monkeypatch, sessions, artifacts_store, chain)

        try:
            client = TestClient(app)
            token = create_access_token("owner", "owner")
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.post(
                f"/solve/entries/{parent['id']}/rerun",
                headers=headers,
                json={"from_step": "assembly", "overrides": {}},
            )
            job_id = resp.json()["job_id"]

            deadline = time.time() + 5.0
            job_body = None
            while time.time() < deadline:
                status_resp = client.get(f"/solve/jobs/{job_id}", headers=headers)
                job_body = status_resp.json()
                if job_body["status"] in ("done", "error"):
                    break
                time.sleep(0.05)

            assert job_body["status"] == "done"
            parent_titles = {
                s["title"] for s in parent["result"]["solution_concepts"]
            }
            rerun_titles = {
                s["title"] for s in job_body["result"]["solution_concepts"]
            }
            assert parent_titles == rerun_titles

            trace = job_body["result"]["pipeline_trace"]
            restored_ids = [
                s["step_id"]
                for s in trace
                if _RESTORED_TRACE_NOTE in s["validator_notes"]
            ]
            assert restored_ids == [
                "core_analysis",
                "psa_fp_validation",
                "effects_retrieval",
                "solution_generation",
            ]
            assert trace[-1]["step_id"] == "assembly"
            assert _RESTORED_TRACE_NOTE not in trace[-1]["validator_notes"]
        finally:
            app.dependency_overrides.clear()
