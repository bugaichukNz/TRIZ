#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

path = Path(__file__).parent / "opto_4o_prompt_fix.txt"
text = path.read_text(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

m = re.search(r"--- core \(кратко\) ---\s*\n(\{.*?\})\s*\n\n--- core", text, re.S)
if m:
    core = json.loads(m.group(1))
    print("=== CORE (attempt 1) ===")
    print("root_cause:", core.get("root_cause"))
    print("FP:", core.get("physical_contradiction"))
    print("IFR:", core.get("ideal_final_result"))

for label, key in [("root_cause", r'"root_cause"'), ("FP", r'"physical_contradiction"')]:
    matches = re.findall(key + r': "([^"]+)"', text)
    if len(matches) > 1:
        print(f"\n=== All {label} ({len(matches)}) ===")
        for i, val in enumerate(matches, 1):
            print(f"{i}. {val[:180]}")

if "PSA/FP alignment attempt 2" in text or "attempt 2" in text:
    print("\n(retry was triggered)")
