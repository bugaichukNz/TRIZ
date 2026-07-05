"""Подбор и форматирование блока физэффектов для промпта генерации решений."""

from __future__ import annotations

from backend.llm.effects_retriever import EffectsRetriever
from backend.llm.models import PhysicalEffect

EFFECTS_BLOCK_HEADER = (
    "Возможно релевантные физические эффекты (использовать ТОЛЬКО если органично "
    "решают противоречие, не притягивать насильно):"
)


def build_effects_block(effects: list[PhysicalEffect]) -> tuple[str, list[str]]:
    """Формирует блок для {effects_block} и список имён эффектов для payload."""
    if not effects:
        return "", []
    body = EffectsRetriever.format_for_prompt(effects)
    block = f"\n\n{EFFECTS_BLOCK_HEADER}\n{body}\n"
    return block, [effect.name for effect in effects]
