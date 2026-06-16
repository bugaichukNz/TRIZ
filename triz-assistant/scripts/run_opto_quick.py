#!/usr/bin/env python3
"""Быстрый прогон оптоволокна через solve() — печать root_cause и ФП."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings  # noqa: E402
from backend.llm.chain import TRIZChain  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

brief = (PROJECT_ROOT / "scripts" / "brief_optovolokno.txt").read_text(encoding="utf-8")
print(f"Модель: {settings.llm_model}")
result = TRIZChain().solve(brief)
print("\n=== ИТОГ solve() ===")
print("root_cause:", result.get("root_cause"))
print("causal_chains:", (result.get("analysis") or {}).get("causal_chains", "")[:300])
print("IFR:", result.get("ideal_final_result"))
print("ФП:", result.get("physical_contradiction"))

lens_bad = "линз" in (result.get("root_cause") or "").lower()
fp_bad = "линз" in (result.get("physical_contradiction") or "").lower()
geo_ok = any(
    w in (result.get("root_cause") or "").lower()
    for w in ("пространств", "разнес", "геометр", "торц", "сведен")
)
fp_geo = any(
    w in (result.get("physical_contradiction") or "").lower()
    for w in ("торц", "сведен", "диаметр", "ширин", "расстоян")
)
print("\n=== КРИТЕРИИ ===")
print(f"root_cause без линз: {not lens_bad}")
print(f"root_cause про геометрию/разнесение: {geo_ok}")
print(f"ФП без линз: {not fp_bad}")
print(f"ФП про торец/геометрию: {fp_geo}")
