#!/usr/bin/env python3
"""Прогон debug_interview на старой и новой версии interview_state."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
STATE_PATH = PROJECT_ROOT / "backend" / "llm" / "interview_state.py"
DEBUG_SCRIPT = SCRIPTS / "debug_interview.py"


def git_old_state() -> str:
    import subprocess as sp

    result = sp.run(
        ["git", "show", "HEAD:triz-assistant/backend/llm/interview_state.py"],
        cwd=PROJECT_ROOT.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


def run_with_state(source: str, out_path: Path) -> None:
    STATE_PATH.write_text(source, encoding="utf-8")
    env = {**dict(**__import__("os").environ), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(DEBUG_SCRIPT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    out_path.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"debug_interview failed:\n{proc.stderr}")


def main() -> None:
    fixed_path = SCRIPTS / "_interview_state_fixed_snapshot.py"
    fixed_path.write_text(STATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    old = git_old_state()
    run_with_state(old, SCRIPTS / "debug_output_before.txt")
    run_with_state(fixed_path.read_text(encoding="utf-8"), SCRIPTS / "debug_output_after.txt")
    fixed_path.unlink(missing_ok=True)
    print("Wrote debug_output_before.txt and debug_output_after.txt")


if __name__ == "__main__":
    main()
