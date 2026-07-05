"""Семантический поиск по корпусу физических эффектов (in-memory, cosine similarity)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import httpx
import numpy as np
from openai import OpenAI

from backend.config import settings
from backend.llm.models import EffectsCorpus, PhysicalEffect

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBED_BATCH_SIZE = 100

CORPUS_DIR = Path(__file__).resolve().parents[2] / "data" / "triz_corpus"
DEFAULT_EFFECTS_PATH = CORPUS_DIR / "effects.json"
DEFAULT_INDEX_PATH = CORPUS_DIR / "effects_index.npz"
DEFAULT_META_PATH = CORPUS_DIR / "effects_index.meta.json"


def build_embedding_text(effect: PhysicalEffect) -> str:
    """Текст для desc-эмбеддинга одного эффекта."""
    functions = ", ".join(effect.functions)
    return (
        f"{effect.name}. {effect.description} "
        f"Вход: {effect.input_action}. Выход: {effect.output_action}. "
        f"Функции: {functions}."
    )


def build_tasks_embedding_text(effect: PhysicalEffect) -> str:
    """Текст для tasks-эмбеддинга: название + инженерные постановки задач."""
    phrases = "; ".join(phrase.strip() for phrase in effect.task_phrases if phrase.strip())
    if not phrases:
        return ""
    return f"{effect.name}. {phrases}"


def create_embeddings_client() -> OpenAI:
    """OpenAI-клиент для embeddings с учётом base URL и прокси."""
    kwargs: dict = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url

    timeout = httpx.Timeout(30.0, read=180.0)
    if settings.openai_proxy_url:
        kwargs["http_client"] = httpx.Client(
            proxy=settings.openai_proxy_url,
            timeout=timeout,
        )

    return OpenAI(**kwargs)


def embed_texts(client: OpenAI, texts: list[str]) -> np.ndarray:
    """Эмбеддинги для списка текстов; возвращает L2-нормированную матрицу float32."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    ordered = sorted(response.data, key=lambda item: item.index)
    matrix = np.array([item.embedding for item in ordered], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix /= np.clip(norms, 1e-12, None)
    return matrix


class EffectsRetriever:
    """In-memory семантический поиск по корпусу физэффектов."""

    def __init__(
        self,
        effects_path: Path = DEFAULT_EFFECTS_PATH,
        index_path: Path = DEFAULT_INDEX_PATH,
        meta_path: Path = DEFAULT_META_PATH,
    ) -> None:
        self._effects_path = effects_path
        self._index_path = index_path
        self._meta_path = meta_path
        self._enabled = False
        self._effects_by_id: dict[str, PhysicalEffect] = {}
        self._matrix: np.ndarray | None = None
        self._ids: list[str] = []
        self._vector_kinds: list[str] = []
        self._load()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _disable(self, reason: str) -> None:
        logger.warning("EffectsRetriever disabled: %s", reason)
        self._enabled = False
        self._effects_by_id = {}
        self._matrix = None
        self._ids = []
        self._vector_kinds = []

    def _load(self) -> None:
        if not self._effects_path.is_file():
            self._disable(f"corpus not found: {self._effects_path}")
            return

        try:
            raw = json.loads(self._effects_path.read_text(encoding="utf-8"))
            corpus = EffectsCorpus.model_validate(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            self._disable(f"invalid corpus JSON: {exc}")
            return

        if not self._index_path.is_file():
            self._disable(f"index not found: {self._index_path}")
            return

        if not self._meta_path.is_file():
            self._disable(f"index meta not found: {self._meta_path}")
            return

        try:
            meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self._disable(f"invalid index meta JSON: {exc}")
            return

        meta_version = meta.get("corpus_version")
        if meta_version != corpus.version:
            self._disable(
                f"corpus version mismatch: index={meta_version!r}, corpus={corpus.version!r}",
            )
            return

        try:
            data = np.load(self._index_path, allow_pickle=True)
            matrix = np.asarray(data["matrix"], dtype=np.float32)
            ids = [str(item) for item in data["ids"]]
        except (OSError, KeyError, ValueError) as exc:
            self._disable(f"failed to load index: {exc}")
            return

        if "vector_kind" not in data:
            self._disable(
                "legacy index format without vector_kind; "
                "rebuild with scripts/build_effects_index.py",
            )
            return

        vector_kinds = [str(item) for item in data["vector_kind"]]
        if len(ids) != len(vector_kinds):
            self._disable(
                f"ids/vector_kind length mismatch: ids={len(ids)}, "
                f"vector_kind={len(vector_kinds)}",
            )
            return

        if matrix.shape[0] != len(ids):
            self._disable(
                f"matrix row count mismatch: matrix={matrix.shape[0]}, ids={len(ids)}",
            )
            return

        self._effects_by_id = {effect.id: effect for effect in corpus.effects}
        corpus_ids = set(self._effects_by_id)
        index_ids = set(ids)
        if index_ids != corpus_ids:
            missing_in_corpus = sorted(index_ids - corpus_ids)[:5]
            missing_in_index = sorted(corpus_ids - index_ids)[:5]
            self._disable(
                f"id set mismatch: missing_in_corpus={missing_in_corpus}, "
                f"missing_in_index={missing_in_index}",
            )
            return

        self._matrix = matrix
        self._ids = ids
        self._vector_kinds = vector_kinds
        self._enabled = True
        logger.info(
            "EffectsRetriever loaded: %d effects, %d vectors, model=%s",
            len(corpus_ids),
            len(ids),
            meta.get("embedding_model", EMBEDDING_MODEL),
        )

    def score_queries(self, queries: list[str]) -> dict[str, float]:
        """Лучший cosine score на эффект (max по desc/tasks векторам и запросам)."""
        if not self._enabled or not queries or self._matrix is None:
            return {}

        cleaned = [query.strip() for query in queries if query.strip()]
        if not cleaned:
            return {}

        client = create_embeddings_client()
        query_matrix = embed_texts(client, cleaned)
        scores = query_matrix @ self._matrix.T

        best_by_id: dict[str, float] = {}
        for row in scores:
            for idx, score in enumerate(row):
                effect_id = self._ids[idx]
                score_f = float(score)
                prev = best_by_id.get(effect_id)
                if prev is None or score_f > prev:
                    best_by_id[effect_id] = score_f
        return best_by_id

    def search(
        self,
        queries: list[str],
        top_k: int = 5,
        *,
        threshold: float | None = None,
    ) -> list[PhysicalEffect]:
        """Семантический поиск; при disabled или пустых запросах — []."""
        if not self._enabled or not queries:
            return []

        cutoff = settings.effects_score_threshold if threshold is None else threshold
        best_by_id = self.score_queries(queries)
        ranked = sorted(best_by_id.items(), key=lambda item: item[1], reverse=True)
        ranked = [(effect_id, score) for effect_id, score in ranked if score >= cutoff]
        ranked = ranked[:top_k]

        return [self._effects_by_id[effect_id] for effect_id, _ in ranked]

    @staticmethod
    def format_for_prompt(effects: list[PhysicalEffect]) -> str:
        """Компактный блок эффектов для подстановки в промпт."""
        if not effects:
            return ""

        lines: list[str] = []
        for effect in effects:
            lines.append(
                f"- {effect.name}: {effect.description} "
                f"Вход: {effect.input_action} → выход: {effect.output_action}. "
                f"Ограничения: {effect.limitations}"
            )
        return "\n".join(lines)


@lru_cache
def get_effects_retriever() -> EffectsRetriever:
    """Singleton retriever (ленивая инициализация)."""
    return EffectsRetriever()


def index_meta_payload(corpus_version: str, *, vector_count: int) -> dict[str, str | int]:
    """Метаданные для effects_index.meta.json."""
    return {
        "embedding_model": EMBEDDING_MODEL,
        "corpus_version": corpus_version,
        "vector_count": vector_count,
        "index_format": "multi_vector",
        "built_at": datetime.now(UTC).isoformat(),
    }
