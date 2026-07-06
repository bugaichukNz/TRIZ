"""LangChain-цепочка TRIZ-ассистента: экспертный анализ и отчёт."""

import logging
import re
import time
from typing import Callable, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from backend.config import settings
from backend.llm.errors import TRIZChainError, wrap_openai_errors
from backend.llm.effects_query_prompt import (
    EFFECT_QUERIES_SYSTEM_PROMPT,
    EFFECT_QUERIES_USER_PROMPT,
)
from backend.llm.effects_rag import build_effects_block
from backend.llm.effects_retriever import get_effects_retriever
from backend.llm.models import (
    AnalysisProfile,
    ContradictionRepair,
    EffectQueries,
    InterviewBrief,
    PipelineStepTrace,
    PSARootRepair,
    SolutionSet,
    TRIZAnalysisCore,
    build_recommendations,
    enrich_legacy_fields,
)
from backend.llm.openai_client import create_chat_llm
from backend.llm.chat_preprocessor import _extract_known_data, _is_tautology_ne_when
from backend.llm.chat_prompt import CHAT_SYSTEM_PROMPT
from backend.llm.fp_retry_prompt import (
    FP_FORMULA,
    FP_RETRY_SYSTEM_PROMPT,
    FP_RETRY_USER_PROMPT,
    PSA_ROOT_RETRY_SYSTEM,
    PSA_ROOT_RETRY_USER,
)
from backend.llm.fp_validator import reconcile_contradiction_type, validate_fp
from backend.llm.psa_validator import (
    validate_psa_and_fp_alignment,
    validate_root_cause_not_crutch,
)
from backend.llm.interview_state import InterviewStateManager
from backend.llm.profile_prompts import get_solution_system_prompt, get_solution_user_prompt
from backend.llm.solution_prompt import SOLUTION_SYSTEM_PROMPT, SOLUTION_USER_PROMPT
from backend.llm.solution_validator import (
    MAX_SOLUTION_GENERATION_ATTEMPTS,
    MIN_SOLUTIONS,
    PARTIAL_GENERATION_WARNING,
    check_solution_diversity,
    merge_valid_solutions,
    select_diverse_solutions,
    validate_solutions,
)
from backend.llm.system_prompt import CORE_SYSTEM_PROMPT, CORE_USER_PROMPT
from backend.llm.tools_registry import TOOL_MANDATORY_MARKER_NAMES

logger = logging.getLogger(__name__)

_TRACE_NOTE_MAX = 200

_PIPELINE_STEP_TITLES: dict[str, str] = {
    "core_analysis": "Core-анализ",
    "psa_fp_validation": "Валидация ПСА/ФП",
    "effects_retrieval": "Подбор физэффектов",
    "solution_generation": "Генерация решений",
    "assembly": "Сборка рекомендаций",
}


def _truncate_trace_note(text: str, limit: int = _TRACE_NOTE_MAX) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _step_status(
    attempts: int,
    *,
    success: bool,
    has_warning_notes: bool = False,
) -> Literal["ok", "ok_with_retries", "warning"]:
    if not success or has_warning_notes:
        return "warning"
    if attempts > 1:
        return "ok_with_retries"
    return "ok"


def _extract_triz_tool_names(core: dict) -> list[str]:
    names: list[str] = []
    for row in core.get("triz_tools") or []:
        if isinstance(row, dict):
            name = (row.get("tool") or "").strip()
        else:
            name = (getattr(row, "tool", "") or "").strip()
        if name:
            names.append(name)
    return names


def _extract_solution_principles(solutions: list[dict]) -> list[str]:
    principles: list[str] = []
    seen: set[str] = set()
    for sol in solutions:
        principle = (sol.get("triz_principle") or "").strip()
        if principle and principle not in seen:
            seen.add(principle)
            principles.append(principle)
    return principles


def _append_pipeline_step(
    pipeline_trace: list[dict],
    *,
    step_id: str,
    status: Literal["ok", "ok_with_retries", "warning"],
    attempts: int,
    tools_used: list[str],
    validator_notes: list[str],
    duration_ms: int,
) -> None:
    try:
        pipeline_trace.append(
            PipelineStepTrace(
                step_id=step_id,
                title=_PIPELINE_STEP_TITLES[step_id],
                status=status,
                attempts=attempts,
                tools_used=tools_used,
                validator_notes=validator_notes,
                duration_ms=duration_ms,
            ).model_dump()
        )
    except Exception as exc:
        logger.warning("Не удалось записать pipeline_trace для %s: %s", step_id, exc)


def _psa_fp_snapshot(core: dict) -> dict:
    analysis = core.get("analysis") or {}
    return {
        "root_cause": core.get("root_cause", ""),
        "causal_chains": analysis.get("causal_chains", ""),
        "technical_contradiction": core.get("technical_contradiction", ""),
        "physical_contradiction": core.get("physical_contradiction", ""),
        "contradiction_type": core.get("contradiction_type", ""),
    }


def _emit_stage_complete(
    on_stage_complete: Callable[[str, dict], None] | None,
    step_id: str,
    payload: dict,
) -> None:
    if on_stage_complete is None:
        return
    try:
        on_stage_complete(step_id, payload)
    except Exception as exc:
        logger.warning("Не удалось записать stage artifact для %s: %s", step_id, exc)


_MANDATORY_TOOL_MARKERS: dict[str, tuple[str, ...]] = {
    "Инструмент 2": ("инструмент 2", "постановка задачи"),
    "Инструмент 14 (КСА)": ("инструмент 14", "кса", "компонентно-структурн"),
    "Инструмент 11 (ПСА)": ("инструмент 11", "пса", "причинно-следств"),
}


def _missing_mandatory_tools(result: dict, profile: AnalysisProfile) -> list[str]:
    tools_text = " ".join((t.get("tool") or "").lower() for t in result.get("triz_tools", []))
    missing: list[str] = []
    for tool_key, marker_name in TOOL_MANDATORY_MARKER_NAMES.items():
        if not profile.tools_enabled.get(tool_key, False):
            continue
        markers = _MANDATORY_TOOL_MARKERS[marker_name]
        if not any(m in tools_text for m in markers):
            missing.append(marker_name)
    return missing


# Legacy fallback: извлечение полей брифа из сырого текста (POST /solve без InterviewBrief).
_BRIEF_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "known_solutions": re.compile(
        r"(?:^|\n)\s*[•\-]\s*(?:Известные попытки решения|Известные решения)"
        r"[:\s]+(.+?)(?=\n\s*[•\-]\s|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
    "why_failed": re.compile(
        r"(?:^|\n)\s*[•\-]\s*Почему не сработало[:\s]+(.+?)(?=\n\s*[•\-]\s|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
    "unrealized_ideas": re.compile(
        r"(?:^|\n)\s*[•\-]\s*Нереализованные идеи[:\s]+(.+?)(?=\n\s*[•\-]\s|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
}


class TRIZChain:
    """LangChain-цепочка: задача → экспертный TRIZ-отчёт (пайплайн LLM-этапов)."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise TRIZChainError("Не задан OPENAI_API_KEY. Укажите ключ в файле .env.")

        try:
            self._llm = create_chat_llm(temperature=0.25)
            self._chat_llm = create_chat_llm(temperature=0.35)

            self._core_llm = self._llm.with_structured_output(TRIZAnalysisCore)
            self._solution_llm = self._llm.with_structured_output(SolutionSet)
            self._fp_retry_llm = self._llm.with_structured_output(ContradictionRepair)
            self._psa_root_llm = self._llm.with_structured_output(PSARootRepair)
            self._effect_queries_llm = self._llm.with_structured_output(EffectQueries)

            self._effect_queries_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", EFFECT_QUERIES_SYSTEM_PROMPT),
                    ("human", EFFECT_QUERIES_USER_PROMPT),
                ]
            )
            self._effect_queries_chain = self._effect_queries_prompt | self._effect_queries_llm

            self._psa_root_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", PSA_ROOT_RETRY_SYSTEM),
                    ("human", PSA_ROOT_RETRY_USER),
                ]
            )
            self._psa_root_chain = self._psa_root_prompt | self._psa_root_llm

            self._core_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", CORE_SYSTEM_PROMPT),
                    ("human", CORE_USER_PROMPT),
                ]
            )
            self._core_chain = self._core_prompt | self._core_llm

            self._solution_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", SOLUTION_SYSTEM_PROMPT),
                    ("human", SOLUTION_USER_PROMPT),
                ]
            )
            self._solution_chain = self._solution_prompt | self._solution_llm

            self._fp_retry_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", FP_RETRY_SYSTEM_PROMPT),
                    ("human", FP_RETRY_USER_PROMPT),
                ]
            )
            self._fp_retry_chain = self._fp_retry_prompt | self._fp_retry_llm

            logger.info(
                "TRIZChain инициализирован: model=%s, base_url=%s, proxy=%s",
                settings.llm_model,
                settings.openai_base_url or "(default)",
                "да" if settings.openai_proxy_url else "нет",
            )
            self._log_effects_rag_status()
        except Exception as exc:
            logger.exception("Ошибка инициализации TRIZChain")
            raise TRIZChainError(f"Не удалось инициализировать LangChain: {exc}") from exc

    @staticmethod
    def _log_effects_rag_status() -> None:
        """Однократный статус effects-RAG при создании TRIZChain."""
        if not settings.effects_rag_enabled:
            logger.info("effects-RAG: выключен")
            return
        retriever = get_effects_retriever()
        if retriever.enabled:
            logger.info("effects-RAG: включён, retriever готов")
        else:
            logger.info("effects-RAG: включён, retriever отключён")

    def chat(self, messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        """Один ход диалогового интервью (текстовый ответ)."""
        if not messages:
            raise TRIZChainError("История сообщений пуста.")

        mgr = InterviewStateManager(messages)

        last_user = InterviewStateManager.last_user_message(messages)

        def _reject_pending(field: str, value: str) -> bool:
            return field == "ne_when" and _is_tautology_ne_when(value, self._chat_llm)

        mgr.confirm_pending_answer(last_user, reject_field=_reject_pending, messages=messages)

        user_text = "\n\n".join(
            m["content"]
            for m in messages
            if m.get("role") == "user" and (m.get("content") or "").strip()
        )
        if user_text:
            known = _extract_known_data(user_text, self._chat_llm)
            mgr.confirm_from_extraction(known)

        mgr.prepare_next_pending()
        context = mgr.build_context_message()
        payload_messages = mgr.build_payload_messages(messages, context)
        updated_messages = mgr.inject_state(messages)

        lc_messages: list[SystemMessage | HumanMessage | AIMessage] = [
            SystemMessage(content=CHAT_SYSTEM_PROMPT),
        ]
        for msg in payload_messages:
            role = msg.get("role", "")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))

        if len(lc_messages) < 2:
            raise TRIZChainError("Нет сообщений для диалога.")

        with wrap_openai_errors("TRIZChain.chat"):
            response = self._chat_llm.invoke(lc_messages)

        text = response.content if hasattr(response, "content") else str(response)
        if not text or not str(text).strip():
            raise TRIZChainError("Модель вернула пустой ответ.")
        return str(text).strip(), updated_messages

    @staticmethod
    def _brief_field_value(brief: InterviewBrief, field: str) -> str:
        val = str(getattr(brief, field, "") or "").strip()
        return val if val and val != "—" else "—"

    @staticmethod
    def _extract_brief_attempt_history(problem: str) -> dict[str, str]:
        """Legacy fallback: извлекает тупики/попытки из сводки интервью (regex по тексту)."""
        fields: dict[str, str] = {}
        for key, pattern in _BRIEF_FIELD_PATTERNS.items():
            match = pattern.search(problem)
            if match:
                value = match.group(1).strip()
                if value:
                    fields[key] = value
        return fields

    @staticmethod
    def _enrich_core_attempt_history(
        core: dict,
        problem: str,
        brief: InterviewBrief | None = None,
    ) -> dict:
        if brief is not None:
            for key in ("known_solutions", "why_failed", "unrealized_ideas"):
                val = TRIZChain._brief_field_value(brief, key)
                if val != "—" and not str(core.get(key) or "").strip():
                    core[key] = val
            return core
        brief_fields = TRIZChain._extract_brief_attempt_history(problem)
        for key in ("known_solutions", "why_failed", "unrealized_ideas"):
            if not str(core.get(key) or "").strip() and brief_fields.get(key):
                core[key] = brief_fields[key]
        return core

    @staticmethod
    def _get_attempt_history(
        core: dict,
        problem: str,
        brief: InterviewBrief | None = None,
    ) -> tuple[str, str, str]:
        if brief is not None:
            return (
                TRIZChain._brief_field_value(brief, "known_solutions"),
                TRIZChain._brief_field_value(brief, "why_failed"),
                TRIZChain._brief_field_value(brief, "unrealized_ideas"),
            )
        known = str(core.get("known_solutions") or "").strip()
        why = str(core.get("why_failed") or "").strip()
        unrealized = str(core.get("unrealized_ideas") or "").strip()
        if not known or not why or not unrealized:
            legacy = TRIZChain._extract_brief_attempt_history(problem)
            known = known or legacy.get("known_solutions", "—")
            why = why or legacy.get("why_failed", "—")
            unrealized = unrealized or legacy.get("unrealized_ideas", "—")
        return known or "—", why or "—", unrealized or "—"

    def _parse_core_result(self, result: object) -> dict:
        if isinstance(result, TRIZAnalysisCore):
            return result.model_dump()
        if isinstance(result, dict):
            return TRIZAnalysisCore.model_validate(result).model_dump()
        raise TRIZChainError(f"Неожиданный тип ответа core-анализа: {type(result).__name__}")

    def _run_core_analysis(
        self,
        problem: str,
        brief: InterviewBrief | None = None,
        *,
        profile: AnalysisProfile | None = None,
    ) -> dict:
        """Этап a: core-анализ → TRIZAnalysisCore."""
        resolved = AnalysisProfile.resolve(profile)
        effective_problem = problem + resolved.core_prompt_suffix()
        with wrap_openai_errors("core-анализа TRIZChain.solve"):
            result = self._core_chain.invoke({"problem": effective_problem})

        return self._enrich_core_attempt_history(
            self._parse_core_result(result), problem, brief
        )

    def _validate_and_fix_fp(
        self, problem: str, core: dict, brief: InterviewBrief | None = None
    ) -> tuple[dict, int, list[str], bool]:
        """Этап b: валидация ПСА и ФП; при провале — до двух retry ПСА + ТП/ФП."""
        max_repairs = 2
        validator_notes: list[str] = []
        attempts_used = 0

        for attempt in range(1, max_repairs + 2):
            attempts_used = attempt
            feedback_parts: list[str] = []

            psa_ok, psa_feedback = validate_psa_and_fp_alignment(core)
            fp_passed, fp_feedback = validate_fp(
                core.get("physical_contradiction", ""),
                core.get("technical_contradiction", ""),
                self._llm,
                root_cause=core.get("root_cause", ""),
                core=core,
                problem=problem,
            )
            logger.info(
                "PSA/FP validation attempt %d: psa=%s, fp=%s",
                attempt,
                psa_ok,
                fp_passed,
            )

            if psa_ok and fp_passed:
                return core, attempts_used, validator_notes, True

            if not psa_ok and psa_feedback:
                feedback_parts.append(psa_feedback)
                validator_notes.append(_truncate_trace_note(psa_feedback))
            if not fp_passed and fp_feedback:
                feedback_parts.append(fp_feedback)
                validator_notes.append(_truncate_trace_note(fp_feedback))

            if attempt > max_repairs:
                break

            combined_feedback = "\n".join(feedback_parts)
            try:
                if not psa_ok:
                    psa_only = self._regenerate_psa_root(problem, core, combined_feedback)
                    core["root_cause"] = psa_only["root_cause"]
                    analysis = dict(core.get("analysis") or {})
                    analysis["causal_chains"] = psa_only["causal_chains"]
                    core["analysis"] = analysis
                    psa_ok, _ = validate_root_cause_not_crutch(core)

                if not fp_passed or not psa_ok:
                    repaired = self._regenerate_contradictions(
                        problem, core, combined_feedback, brief=brief
                    )
                    core["root_cause"] = repaired["root_cause"]
                    analysis = dict(core.get("analysis") or {})
                    analysis["causal_chains"] = repaired["causal_chains"]
                    core["analysis"] = analysis
                    core["technical_contradiction"] = repaired["technical_contradiction"]
                    core["physical_contradiction"] = repaired["physical_contradiction"]
            except Exception as exc:
                logger.warning(
                    "Перегенерация ПСА/ТП/ФП (попытка %d) не удалась: %s",
                    attempt,
                    exc,
                )
                validator_notes.append(_truncate_trace_note(f"Ошибка перегенерации: {exc}"))
                break

        return core, attempts_used, validator_notes, False

    @staticmethod
    def _get_constraints(core: dict) -> list[str]:
        ctx = core.get("system_context") or {}
        raw = ctx.get("constraints") or []
        if isinstance(raw, list):
            return [str(c).strip() for c in raw if str(c).strip()]
        if raw:
            return [str(raw).strip()]
        return []

    def _retrieve_effects_for_solutions(
        self, core: dict, *, profile: AnalysisProfile
    ) -> tuple[str, list[str], list[str]]:
        """Подбор релевантных физэффектов для промпта генерации решений."""
        if not profile.effects_rag:
            return "", [], []

        if not settings.effects_rag_enabled:
            retriever = get_effects_retriever()
            if not retriever.enabled:
                return "", [], []

        try:
            result = self._effect_queries_chain.invoke(
                {
                    "physical_contradiction": core.get("physical_contradiction", ""),
                    "ideal_final_result": core.get("ideal_final_result", ""),
                    "root_cause": core.get("root_cause", ""),
                }
            )
            if isinstance(result, EffectQueries):
                queries = result.queries
            elif isinstance(result, dict):
                queries = EffectQueries.model_validate(result).queries
            else:
                raise TRIZChainError(
                    f"Неожиданный тип ответа EffectQueries: {type(result).__name__}"
                )

            retriever = get_effects_retriever()
            effects = retriever.search(queries, top_k=6)
            block, used = build_effects_block(effects)
            return block, used, list(queries)
        except Exception as exc:
            logger.warning(
                "Этап подбора физэффектов пропущен из-за ошибки: %s",
                exc,
                exc_info=True,
            )
            return "", [], []

    def _build_solution_input(
        self,
        core: dict,
        problem: str,
        validator_feedback: str = "",
        brief: InterviewBrief | None = None,
        *,
        effects_block: str = "",
    ) -> dict:
        analysis = core.get("analysis") or {}
        constraints = self._get_constraints(core)
        constraints_text = "\n".join(f"• {c}" for c in constraints) if constraints else "—"
        if brief is not None:
            brief_constraints = self._brief_field_value(brief, "constraints")
            if brief_constraints != "—":
                constraints_text = brief_constraints
        known, why_failed, unrealized = self._get_attempt_history(core, problem, brief)
        ctx = core.get("system_context") or {}
        resources_list = ctx.get("resources") or []
        if isinstance(resources_list, list):
            brief_resources = "\n".join(f"• {r}" for r in resources_list if str(r).strip()) or "—"
        else:
            brief_resources = str(resources_list).strip() or "—"
        if brief is not None:
            brief_resources_val = self._brief_field_value(brief, "resources")
            if brief_resources_val != "—":
                brief_resources = brief_resources_val
        feedback_block = ""
        if validator_feedback.strip():
            feedback_block = (
                "\n\nЗамечания валидатора решений (ОБЯЗАТЕЛЬНО исправить при перегенерации):\n"
                f"{validator_feedback.strip()}\n"
            )
        return {
            "technical_contradiction": core.get("technical_contradiction", ""),
            "physical_contradiction": core.get("physical_contradiction", ""),
            "ideal_final_result": core.get("ideal_final_result", ""),
            "resources_analysis": analysis.get("resources_analysis", ""),
            "brief_resources": brief_resources,
            "known_solutions": known,
            "why_failed": why_failed,
            "unrealized_ideas": unrealized,
            "constraints": constraints_text,
            "effects_block": effects_block,
            "validator_feedback": feedback_block,
        }

    def _generate_solutions(
        self,
        core: dict,
        problem: str,
        *,
        validator_feedback: str = "",
        brief: InterviewBrief | None = None,
        effects_block: str = "",
        profile: AnalysisProfile | None = None,
    ) -> list[dict]:
        """Генерация solution_concepts по валидированному ядру."""
        resolved = AnalysisProfile.resolve(profile)
        solution_input = self._build_solution_input(
            core,
            problem,
            validator_feedback=validator_feedback,
            brief=brief,
            effects_block=effects_block,
        )
        if resolved.target_solutions == 4:
            result = self._solution_chain.invoke(solution_input)
        else:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", get_solution_system_prompt(resolved)),
                    ("human", get_solution_user_prompt(resolved)),
                ]
            )
            chain = prompt | self._solution_llm
            result = chain.invoke(solution_input)
        if isinstance(result, SolutionSet):
            return [s.model_dump() for s in result.solution_concepts]
        if isinstance(result, dict):
            return SolutionSet.model_validate(result).model_dump()["solution_concepts"]
        raise TRIZChainError(f"Неожиданный тип ответа генерации решений: {type(result).__name__}")

    def _validate_and_generate_solutions(
        self,
        core: dict,
        problem: str,
        brief: InterviewBrief | None = None,
        *,
        effects_block: str = "",
        profile: AnalysisProfile | None = None,
    ) -> tuple[list[dict], str, int, list[str]]:
        """
        Генерация решений + валидация с накоплением валидных попыток.

        Returns:
            (solutions, warning, attempts_used, validator_notes) — warning непустой,
            если после MAX_SOLUTION_GENERATION_ATTEMPTS валидных решений меньше MIN_SOLUTIONS.
        """
        constraints = self._get_constraints(core)
        analysis = core.get("analysis") or {}
        resources = analysis.get("resources_analysis", "")
        known, why_failed, _unrealized = self._get_attempt_history(core, problem, brief)
        ifr = core.get("ideal_final_result", "")

        batches: list[list[dict]] = []
        feedback = ""
        attempts_used = 0
        validator_notes: list[str] = []

        for attempt in range(1, MAX_SOLUTION_GENERATION_ATTEMPTS + 1):
            attempts_used = attempt
            try:
                if attempt == 1:
                    batch = self._generate_solutions(
                        core, problem, brief=brief, effects_block=effects_block, profile=profile
                    )
                else:
                    batch = self._generate_solutions(
                        core,
                        problem,
                        validator_feedback=feedback,
                        brief=brief,
                        effects_block=effects_block,
                        profile=profile,
                    )
            except Exception as exc:
                logger.warning(
                    "Генерация решений (попытка %d/%d) не удалась: %s",
                    attempt,
                    MAX_SOLUTION_GENERATION_ATTEMPTS,
                    exc,
                )
                validator_notes.append(_truncate_trace_note(f"Ошибка генерации: {exc}"))
                break

            passed, feedback, valid_batch = validate_solutions(
                batch, known, why_failed, resources, ifr, self._llm, constraints
            )
            if feedback:
                validator_notes.append(_truncate_trace_note(feedback))
            batches.append(valid_batch)
            accumulated = select_diverse_solutions(merge_valid_solutions(*batches), limit=5)

            logger.info(
                "Solution generation attempt %d/%d: validation_passed=%s, "
                "valid_batch=%d, valid_accumulated=%d, feedback=%s",
                attempt,
                MAX_SOLUTION_GENERATION_ATTEMPTS,
                passed,
                len(valid_batch),
                len(accumulated),
                feedback or "—",
            )

            if len(accumulated) >= MIN_SOLUTIONS:
                div_ok, div_feedback = check_solution_diversity(accumulated, resources, self._llm)
                if div_ok and passed:
                    return accumulated, "", attempts_used, validator_notes
                if div_ok and attempt == MAX_SOLUTION_GENERATION_ATTEMPTS:
                    return accumulated, "", attempts_used, validator_notes
                if not div_ok:
                    feedback = div_feedback or feedback
                    if div_feedback:
                        validator_notes.append(_truncate_trace_note(div_feedback))
                    if attempt < MAX_SOLUTION_GENERATION_ATTEMPTS:
                        logger.info(
                            "Накопленный набор не прошёл проверку разнообразия, retry: %s",
                            div_feedback[:200],
                        )
                        continue
            elif passed:
                return accumulated, "", attempts_used, validator_notes

        accumulated = select_diverse_solutions(merge_valid_solutions(*batches), limit=5)
        if len(accumulated) >= MIN_SOLUTIONS:
            return accumulated, "", attempts_used, validator_notes

        warning = PARTIAL_GENERATION_WARNING
        if not accumulated:
            logger.warning(
                "После %d попыток генерации нет ни одного решения в рамках constraints",
                attempts_used,
            )
        else:
            logger.warning(
                "После %d попыток только %d валидных решений (минимум %d)",
                attempts_used,
                len(accumulated),
                MIN_SOLUTIONS,
            )
        validator_notes.append(_truncate_trace_note(warning))
        return accumulated, warning, attempts_used, validator_notes

    def _regenerate_psa_root(self, problem: str, core: dict, feedback: str) -> dict[str, str]:
        """Перегенерация только root_cause и causal_chains."""
        analysis = core.get("analysis") or {}
        ctx = core.get("system_context") or {}
        constraints_list = ctx.get("constraints") or []
        if isinstance(constraints_list, list):
            constraints = "\n".join(f"• {c}" for c in constraints_list if str(c).strip()) or "—"
        else:
            constraints = str(constraints_list).strip() or "—"
        result = self._psa_root_chain.invoke(
            {
                "problem": problem,
                "ideal_final_result": core.get("ideal_final_result", ""),
                "constraints": constraints,
                "root_cause": core.get("root_cause", ""),
                "causal_chains": analysis.get("causal_chains", ""),
                "feedback": feedback,
            }
        )
        if isinstance(result, PSARootRepair):
            return result.model_dump()
        if isinstance(result, dict):
            return PSARootRepair.model_validate(result).model_dump()
        raise TRIZChainError(f"Неожиданный тип ответа перегенерации ПСА: {type(result).__name__}")

    def _regenerate_contradictions(
        self,
        problem: str,
        core: dict,
        feedback: str,
        brief: InterviewBrief | None = None,
    ) -> dict[str, str]:
        """Повторная генерация ПСА, ТП и ФП с учётом замечаний валидатора."""
        analysis = core.get("analysis") or {}
        ctx = core.get("system_context") or {}
        resources_list = ctx.get("resources") or []
        constraints_list = ctx.get("constraints") or []
        if isinstance(resources_list, list):
            resources = "\n".join(f"• {r}" for r in resources_list if str(r).strip()) or "—"
        else:
            resources = str(resources_list).strip() or "—"
        if isinstance(constraints_list, list):
            constraints = "\n".join(f"• {c}" for c in constraints_list if str(c).strip()) or "—"
        else:
            constraints = str(constraints_list).strip() or "—"
        if brief is not None:
            brief_constraints = self._brief_field_value(brief, "constraints")
            if brief_constraints != "—":
                constraints = brief_constraints
            brief_resources_val = self._brief_field_value(brief, "resources")
            if brief_resources_val != "—":
                resources = brief_resources_val
        known, why_failed, unrealized = self._get_attempt_history(core, problem, brief)
        result = self._fp_retry_chain.invoke(
            {
                "problem": problem,
                "problem_description": core.get("problem_description", ""),
                "root_cause": core.get("root_cause", ""),
                "causal_chains": analysis.get("causal_chains", ""),
                "technical_contradiction": core.get("technical_contradiction", ""),
                "physical_contradiction": core.get("physical_contradiction", ""),
                "feedback": feedback,
                "fp_formula": FP_FORMULA,
                "resources": resources,
                "known_solutions": known,
                "why_failed": why_failed,
                "unrealized_ideas": unrealized,
                "ideal_final_result": core.get("ideal_final_result", ""),
                "constraints": constraints,
            }
        )
        if isinstance(result, ContradictionRepair):
            return result.model_dump()
        if isinstance(result, dict):
            return ContradictionRepair.model_validate(result).model_dump()
        raise TRIZChainError(
            f"Неожиданный тип ответа перегенерации ПСА/ФП: {type(result).__name__}"
        )

    def _assemble_payload(
        self,
        core: dict,
        solutions: list[dict],
        *,
        effects_used: list[str] | None = None,
    ) -> dict:
        """Этап d–e: рекомендации + финальный payload."""
        tail = build_recommendations(core, solutions)
        return {
            **core,
            "solution_concepts": solutions,
            "effects_used": list(effects_used or []),
            **tail,
        }

    def solve(
        self,
        problem: str,
        *,
        brief: InterviewBrief | None = None,
        profile: AnalysisProfile | None = None,
        on_progress: Callable[[int, str], None] | None = None,
        on_stage_complete: Callable[[str, dict], None] | None = None,
    ) -> dict:
        """
        Пайплайн TRIZ-анализа:

        a) core-анализ (TRIZAnalysisCore)
        b) валидация ФП (+ retry ТП/ФП при провале)
        c) подбор физэффектов (опционально, feature-flag)
        d) генерация решений (+ валидация и retry)
        e) рекомендации (детерминированно из ранжирования)
        f) сборка payload + enrich_legacy_fields

        Returns:
            dict с полями полного отчёта и обратной совместимости.
        """

        def _progress(pct: int, stage: str) -> None:
            if on_progress is not None:
                on_progress(pct, stage)

        if not problem or not problem.strip():
            raise TRIZChainError("Описание задачи (problem) не может быть пустым.")

        problem = problem.strip()
        resolved_profile = AnalysisProfile.resolve(profile)
        logger.info("TRIZ solve pipeline: длина задачи=%d", len(problem))

        _progress(5, "Подготовка к анализу")

        pipeline_trace: list[dict] = []

        # --- core_analysis ---
        t0 = time.perf_counter()
        core_attempts = 1
        core_notes: list[str] = []
        core_warning = False
        profile_deviations = resolved_profile.describe_deviations()
        if profile_deviations:
            core_notes.append(
                _truncate_trace_note(
                    "нестандартный профиль: " + "; ".join(profile_deviations)
                )
            )

        _progress(10, "TRIZ core-анализ")
        core = self._run_core_analysis(problem, brief, profile=resolved_profile)
        missing = _missing_mandatory_tools(core, resolved_profile)
        if missing:
            logger.info(
                "Обязательные инструменты ШАГ 2.1 отсутствуют после первого прохода: %s — повтор",
                missing,
            )
            core_notes.append(
                _truncate_trace_note(
                    f"Повтор core-анализа: отсутствовали {', '.join(missing)}"
                )
            )
            retry_note = (
                "\n\nВАЖНО: в предыдущем анализе отсутствовали обязательные инструменты "
                f"ШАГ 2.1: {', '.join(missing)}. Включи их в triz_tools с конкретными "
                "результатами применения к данной задаче."
            )
            core = self._run_core_analysis(problem + retry_note, brief, profile=resolved_profile)
            core_attempts = 2
            still_missing = _missing_mandatory_tools(core, resolved_profile)
            if still_missing:
                core_warning = True
                logger.warning(
                    "Обязательные инструменты ШАГ 2.1 всё ещё отсутствуют после повтора: %s",
                    still_missing,
                )
                core_notes.append(
                    _truncate_trace_note(
                        f"После повтора отсутствуют: {', '.join(still_missing)}"
                    )
                )
        logger.info(
            "TRIZ core-анализ завершён: тип=%s, инструментов=%d",
            core.get("contradiction_type"),
            len(core.get("triz_tools", [])),
        )
        _append_pipeline_step(
            pipeline_trace,
            step_id="core_analysis",
            status=_step_status(
                core_attempts,
                success=not core_warning,
                has_warning_notes=core_warning,
            ),
            attempts=core_attempts,
            tools_used=_extract_triz_tool_names(core),
            validator_notes=core_notes,
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        _emit_stage_complete(on_stage_complete, "core_analysis", dict(core))

        # --- psa_fp_validation ---
        t0 = time.perf_counter()
        _progress(35, "Валидация физического противоречия")
        if not resolved_profile.psa_fp_validation:
            fp_attempts = 0
            fp_notes = ["отключено профилем"]
            fp_ok = False
        else:
            core, fp_attempts, fp_notes, fp_ok = self._validate_and_fix_fp(problem, core, brief)
        core, type_note = reconcile_contradiction_type(core)
        if type_note:
            logger.info("TRIZ contradiction_type reconciled: %s", type_note)
            fp_notes.append(_truncate_trace_note(type_note))
        _append_pipeline_step(
            pipeline_trace,
            step_id="psa_fp_validation",
            status=(
                "warning"
                if not resolved_profile.psa_fp_validation
                else _step_status(fp_attempts, success=fp_ok)
            ),
            attempts=max(fp_attempts, 1),
            tools_used=[],
            validator_notes=fp_notes,
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        _emit_stage_complete(on_stage_complete, "psa_fp_validation", _psa_fp_snapshot(core))

        # --- effects_retrieval ---
        t0 = time.perf_counter()
        _progress(45, "Подбор физических эффектов")
        effects_queries: list[str] = []
        if not resolved_profile.effects_rag:
            effects_block, effects_used = "", []
            if profile is not None and settings.effects_rag_enabled:
                effects_notes = ["отключён профилем"]
            else:
                effects_notes = ["отключён"]
        else:
            effects_block, effects_used, effects_queries = self._retrieve_effects_for_solutions(
                core, profile=resolved_profile
            )
            effects_notes = []
            if not effects_used:
                effects_notes.append(
                    _truncate_trace_note("Физэффекты не найдены или retriever недоступен")
                )
        _append_pipeline_step(
            pipeline_trace,
            step_id="effects_retrieval",
            status="ok",
            attempts=1,
            tools_used=list(effects_used),
            validator_notes=effects_notes,
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        _emit_stage_complete(
            on_stage_complete,
            "effects_retrieval",
            {
                "effects_block": effects_block,
                "effects_used": list(effects_used),
                "queries": list(effects_queries),
            },
        )

        # --- solution_generation ---
        t0 = time.perf_counter()
        _progress(50, "Генерация решений")
        solutions, generation_warning, sol_attempts, sol_notes = (
            self._validate_and_generate_solutions(
                core,
                problem,
                brief,
                effects_block=effects_block,
                profile=resolved_profile,
            )
        )
        sol_ok = not generation_warning
        _append_pipeline_step(
            pipeline_trace,
            step_id="solution_generation",
            status=_step_status(sol_attempts, success=sol_ok),
            attempts=sol_attempts,
            tools_used=_extract_solution_principles(solutions),
            validator_notes=sol_notes,
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        _emit_stage_complete(
            on_stage_complete,
            "solution_generation",
            {
                "solutions": [dict(s) if isinstance(s, dict) else s for s in solutions],
                "generation_warning": generation_warning or "",
            },
        )

        # --- assembly ---
        t0 = time.perf_counter()
        _progress(85, "Формирование рекомендаций")
        payload = self._assemble_payload(core, solutions, effects_used=effects_used)
        if generation_warning:
            payload["solution_generation_note"] = generation_warning
            summary = (payload.get("executive_summary") or "").strip()
            payload["executive_summary"] = (
                f"{summary} {generation_warning}".strip() if summary else generation_warning
            )
        payload = enrich_legacy_fields(payload)
        _append_pipeline_step(
            pipeline_trace,
            step_id="assembly",
            status="ok",
            attempts=1,
            tools_used=[],
            validator_notes=[],
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

        payload["pipeline_trace"] = pipeline_trace
        payload["analysis_profile"] = resolved_profile.model_dump()

        if len(payload.get("solution_concepts", [])) < 2:
            logger.warning(
                "Сформировано менее 2 решений: %s",
                payload.get("solution_concepts"),
            )

        logger.info(
            "TRIZ solve pipeline завершён: тип=%s, инструментов=%d, решений=%d",
            payload.get("contradiction_type"),
            len(payload.get("triz_tools", [])),
            len(payload.get("solution_concepts", [])),
        )
        _progress(100, "Готово")
        return payload
