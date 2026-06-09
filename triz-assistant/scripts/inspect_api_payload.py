"""Показать JSON-подобный payload, который уходит в OpenAI при chat() и solve()."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import re

CHAT_FILE = ROOT / "backend" / "llm" / "chat_prompt.py"
SYSTEM_FILE = ROOT / "backend" / "llm" / "system_prompt.py"


def _extract_triple_quoted(name: str, text: str) -> str:
    m = re.search(rf'{name} = """(.*?)"""', text, re.DOTALL)
    if not m:
        raise ValueError(f"{name} not found")
    return m.group(1)


CHAT_SYSTEM_PROMPT = _extract_triple_quoted("CHAT_SYSTEM_PROMPT", CHAT_FILE.read_text(encoding="utf-8"))
_system_text = SYSTEM_FILE.read_text(encoding="utf-8")
SYSTEM_PROMPT = _extract_triple_quoted("SYSTEM_PROMPT", _system_text)
USER_PROMPT = _extract_triple_quoted("USER_PROMPT", _system_text)


def demo_chat_payload() -> None:
    sample_history = [
        {"role": "assistant", "content": "Как называется задача?"},
        {"role": "user", "content": "Снижение брака на линии покраски"},
        {"role": "assistant", "content": "Опишите нежелательный эффект."},
        {"role": "user", "content": "Пятна на 12% деталей"},
    ]
    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    messages.extend(sample_history)

    payload = {"model": "(from settings.llm_model)", "messages": messages}
    print("=== CHAT (каждое сообщение в диалоге) ===")
    print(f"system prompt chars: {len(CHAT_SYSTEM_PROMPT)}")
    print(f"messages count: {len(payload['messages'])}")
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])
    if len(json.dumps(payload, ensure_ascii=False)) > 4000:
        print("... [truncated display only, full payload is NOT truncated in code]")


def demo_solve_payload() -> None:
    problem = "Краткий бриф из интервью: снизить брак с 12% до 3%..."
    user_text = USER_PROMPT.format(problem=problem)
    payload = {
        "model": "(from settings.llm_model)",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    }
    print("\n=== SOLVE /analyze (один вызов, без истории чата) ===")
    print(f"system prompt chars: {len(SYSTEM_PROMPT)}")
    print(f"user message chars: {len(user_text)}")
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:2500])
    if len(json.dumps(payload, ensure_ascii=False)) > 2500:
        print("... [truncated display only]")


if __name__ == "__main__":
    demo_chat_payload()
    demo_solve_payload()
