"""Сбор и сохранение промежуточных артефактов TRIZChain.solve."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from backend.artifacts_store import ArtifactsStore
from backend.llm.models import AnalysisProfile, compute_profile_hash

logger = logging.getLogger(__name__)

StageCompleteCallback = Callable[[str, dict[str, Any]], None]


def profile_hash_for(profile: AnalysisProfile | None) -> str:
    return compute_profile_hash(AnalysisProfile.resolve(profile))


def make_artifact_buffer(
    profile: AnalysisProfile | None,
) -> tuple[StageCompleteCallback, list[tuple[str, dict[str, Any]]], str]:
    """Буферизует артефакты во время solve (до появления entry_id)."""
    buffer: list[tuple[str, dict[str, Any]]] = []
    profile_hash = profile_hash_for(profile)

    def on_stage_complete(step_id: str, payload: dict[str, Any]) -> None:
        buffer.append((step_id, payload))

    return on_stage_complete, buffer, profile_hash


def persist_buffered_artifacts(
    artifacts_store: ArtifactsStore,
    entry_id: str,
    user_id: str,
    profile_hash: str,
    buffer: list[tuple[str, dict[str, Any]]],
) -> None:
    for step_id, payload in buffer:
        try:
            artifacts_store.save(
                entry_id,
                step_id,
                payload,
                profile_hash=profile_hash,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning(
                "Не удалось сохранить stage artifact %s для entry %s: %s",
                step_id,
                entry_id,
                exc,
            )
