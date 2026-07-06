"""Построение промптов генерации решений с учётом AnalysisProfile."""

from backend.llm.models import AnalysisProfile
from backend.llm.solution_prompt import SOLUTION_SYSTEM_PROMPT, SOLUTION_USER_PROMPT


def get_solution_system_prompt(profile: AnalysisProfile) -> str:
    count = profile.solution_count_label()
    if count == "3–5":
        return SOLUTION_SYSTEM_PROMPT
    return SOLUTION_SYSTEM_PROMPT.replace("3–5", count)


def get_solution_user_prompt(profile: AnalysisProfile) -> str:
    count = profile.solution_count_label()
    if count == "3–5":
        return SOLUTION_USER_PROMPT
    return SOLUTION_USER_PROMPT.replace("3–5", count)
