"""Тесты персистенции промежуточных артефактов TRIZChain.solve."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.artifacts_store import ArtifactsStore
from backend.auth import create_access_token
from backend.config import settings
from backend.llm.chain import TRIZChain
from backend.auth import create_access_token, get_current_user
from backend.main import app, get_artifacts_store, get_sessions_store
from backend.sessions_store import SessionsStore
from backend.stage_artifact_hooks import make_artifact_buffer, persist_buffered_artifacts
from tests.test_effects_integration import CORE_FIXTURE, PROBLEM
from tests.test_pipeline_trace import FULL_CORE_FIXTURE, _make_chain, _stub_happy_path

EXPECTED_ARTIFACT_STEPS = [
    "core_analysis",
    "psa_fp_validation",
    "effects_retrieval",
    "solution_generation",
]


@pytest.fixture
def isolated_stores(tmp_path):
    db_path = tmp_path / "artifacts.db"
    sessions = SessionsStore(db_path=db_path, max_entries=5)
    artifacts = ArtifactsStore(db_path=db_path)
    return sessions, artifacts


@pytest.fixture
def trim_stores(tmp_path):
    db_path = tmp_path / "trim.db"
    sessions = SessionsStore(db_path=db_path, max_entries=2)
    artifacts = ArtifactsStore(db_path=db_path)
    return sessions, artifacts


def _solve_with_buffer(
    chain: TRIZChain,
    profile=None,
) -> tuple[dict, list[tuple[str, dict[str, Any]]], str]:
    on_stage_complete, buffer, profile_hash = make_artifact_buffer(profile)
    payload = chain.solve(PROBLEM, on_stage_complete=on_stage_complete, profile=profile)
    return payload, buffer, profile_hash


class TestStageArtifactsSolve:
    def test_solve_emits_four_artifacts_in_order(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)

        _payload, buffer, _profile_hash = _solve_with_buffer(chain)

        assert [step_id for step_id, _ in buffer] == EXPECTED_ARTIFACT_STEPS

        core_payload = buffer[0][1]
        assert "root_cause" in core_payload
        assert "physical_contradiction" in core_payload
        assert core_payload["root_cause"] == FULL_CORE_FIXTURE["root_cause"]

        psa_payload = buffer[1][1]
        assert psa_payload["root_cause"] == FULL_CORE_FIXTURE["root_cause"]
        assert psa_payload["physical_contradiction"] == FULL_CORE_FIXTURE["physical_contradiction"]

        effects_payload = buffer[2][1]
        assert "effects_block" in effects_payload
        assert "effects_used" in effects_payload
        assert "queries" in effects_payload

        solutions_payload = buffer[3][1]
        assert "solutions" in solutions_payload
        assert "generation_warning" in solutions_payload
        assert len(solutions_payload["solutions"]) >= 2

    def test_callback_failure_logs_warning_and_solve_completes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        chain = _make_chain(monkeypatch, fake_llm)
        _stub_happy_path(chain, monkeypatch)

        def _failing_callback(_step_id: str, _payload: dict) -> None:
            raise RuntimeError("artifact write failed")

        with caplog.at_level(logging.WARNING, logger="backend.llm.chain"):
            payload = chain.solve(PROBLEM, on_stage_complete=_failing_callback)

        assert payload.get("solution_concepts")
        assert any("stage artifact" in rec.message for rec in caplog.records)


class TestStageArtifactsStore:
    def test_persist_and_list_metadata(
        self,
        isolated_stores,
    ) -> None:
        sessions, artifacts = isolated_stores
        entry = sessions.add_entry(PROBLEM, {"ok": True}, user_id="user-a")
        persist_buffered_artifacts(
            artifacts,
            entry["id"],
            "user-a",
            "hash-1",
            [("core_analysis", {"root_cause": "x"})],
        )

        rows = artifacts.list_metadata(entry["id"], user_id="user-a")
        assert rows is not None
        assert len(rows) == 1
        assert rows[0]["step_id"] == "core_analysis"
        assert rows[0]["profile_hash"] == "hash-1"

        full = artifacts.get(entry["id"], "core_analysis", user_id="user-a")
        assert full is not None
        assert full.payload["root_cause"] == "x"

    def test_cascade_delete_with_entry(
        self,
        isolated_stores,
    ) -> None:
        sessions, artifacts = isolated_stores
        entry = sessions.add_entry(PROBLEM, {"ok": True}, user_id="user-a")
        persist_buffered_artifacts(
            artifacts,
            entry["id"],
            "user-a",
            "hash-1",
            [("core_analysis", {"root_cause": "x"})],
        )

        with sessions._connect() as conn:
            conn.execute("DELETE FROM history_entries WHERE id = ?", (entry["id"],))
            conn.commit()

        with artifacts._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM stage_artifacts WHERE entry_id = ?",
                (entry["id"],),
            ).fetchone()[0]
        assert count == 0
        assert artifacts.list_metadata(entry["id"], user_id="user-a") is None

    def test_history_trim_deletes_artifacts(
        self,
        trim_stores,
    ) -> None:
        sessions, artifacts = trim_stores

        entries = []
        for i in range(3):
            entry = sessions.add_entry(f"problem {i}", {"i": i}, user_id="user-a")
            persist_buffered_artifacts(
                artifacts,
                entry["id"],
                "user-a",
                "hash",
                [("core_analysis", {"n": i})],
            )
            entries.append(entry)

        remaining = sessions.list_entries("user-a")
        assert len(remaining) == 2
        oldest_id = entries[0]["id"]
        assert artifacts.get(oldest_id, "core_analysis", user_id="user-a") is None


class TestStageArtifactsEndpoints:
    def test_foreign_entry_returns_404(
        self,
        isolated_stores,
    ) -> None:
        sessions, artifacts = isolated_stores
        entry = sessions.add_entry(PROBLEM, {"ok": True}, user_id="owner")
        persist_buffered_artifacts(
            artifacts,
            entry["id"],
            "owner",
            "hash-1",
            [("core_analysis", CORE_FIXTURE)],
        )

        app.dependency_overrides[get_sessions_store] = lambda: sessions
        app.dependency_overrides[get_artifacts_store] = lambda: artifacts
        app.dependency_overrides[get_current_user] = lambda: {"id": "other", "username": "other"}

        try:
            client = TestClient(app)
            token = create_access_token("other", "other")
            headers = {"Authorization": f"Bearer {token}"}

            meta_resp = client.get(
                f"/solve/entries/{entry['id']}/artifacts",
                headers=headers,
            )
            assert meta_resp.status_code == 404

            full_resp = client.get(
                f"/solve/entries/{entry['id']}/artifacts/core_analysis",
                headers=headers,
            )
            assert full_resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_owner_gets_metadata_and_full_artifact(
        self,
        isolated_stores,
    ) -> None:
        sessions, artifacts = isolated_stores
        entry = sessions.add_entry(PROBLEM, {"ok": True}, user_id="owner")
        persist_buffered_artifacts(
            artifacts,
            entry["id"],
            "owner",
            "hash-abc",
            [
                ("core_analysis", CORE_FIXTURE),
                ("psa_fp_validation", {"root_cause": CORE_FIXTURE["root_cause"]}),
            ],
        )

        app.dependency_overrides[get_sessions_store] = lambda: sessions
        app.dependency_overrides[get_artifacts_store] = lambda: artifacts
        app.dependency_overrides[get_current_user] = lambda: {"id": "owner", "username": "owner"}

        try:
            client = TestClient(app)
            token = create_access_token("owner", "owner")
            headers = {"Authorization": f"Bearer {token}"}

            meta_resp = client.get(
                f"/solve/entries/{entry['id']}/artifacts",
                headers=headers,
            )
            assert meta_resp.status_code == 200
            body = meta_resp.json()
            assert len(body["items"]) == 2
            assert body["items"][0]["step_id"] == "core_analysis"
            assert "payload" not in body["items"][0]
            assert body["items"][0]["profile_hash"] == "hash-abc"

            full_resp = client.get(
                f"/solve/entries/{entry['id']}/artifacts/core_analysis",
                headers=headers,
            )
            assert full_resp.status_code == 200
            artifact = full_resp.json()
            assert artifact["step_id"] == "core_analysis"
            assert artifact["payload"]["root_cause"] == CORE_FIXTURE["root_cause"]
            assert artifact["profile_hash"] == "hash-abc"
        finally:
            app.dependency_overrides.clear()
