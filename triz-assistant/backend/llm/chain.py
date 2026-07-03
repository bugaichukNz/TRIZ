"""LangChain-цепочка TRIZ-ассистента: экспертный анализ и отчёт."""

import logging
import re
from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)

from pydantic import ValidationError

from backend.config import settings
from backend.llm.models import (
    ContradictionRepair,
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

logger = logging.getLogger(__name__)

_MANDATORY_TOOL_MARKERS: dict[str, tuple[str, ...]] = {
    "Инструмент 2": ("инструмент 2", "постановка задачи"),
    "Инструмент 14 (КСА)": ("инструмент 14", "кса", "компонентно-структурн"),
    "Инструмент 11 (ПСА)": ("инструмент 11", "пса", "причинно-следств"),
}


def _missing_mandatory_tools(result: dict) -> list[str]:
    tools_text = " ".join(
        (t.get("tool") or "").lower() for t in result.get("triz_tools", [])
    )
    return [
        name
        for name, markers in _MANDATORY_TOOL_MARKERS.items()
        if not any(m in tools_text for m in markers)
    ]


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


class TRIZChainError(Exception):
    """Ошибка при работе TRIZ LLM-цепочки."""


class TRIZChain:
    """LangChain-цепочка: задача → экспертный TRIZ-отчёт (пайплайн LLM-этапов)."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise TRIZChainError(
                "Не задан OPENAI_API_KEY. Укажите ключ в файле .env."
            )

        try:
            self._llm = create_chat_llm(temperature=0.25)
            self._chat_llm = create_chat_llm(temperature=0.35)

            self._core_llm = self._llm.with_structured_output(TRIZAnalysisCore)
            self._solution_llm = self._llm.with_structured_output(SolutionSet)
            self._fp_retry_llm = self._llm.with_structured_output(ContradictionRepair)
            self._psa_root_llm = self._llm.with_structured_output(PSARootRepair)

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
        except Exception as exc:
            logger.exception("Ошибка инициализации TRIZChain")
            raise TRIZChainError(
                f"Не удалось инициализировать LangChain: {exc}"
            ) from exc

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

        try:
            response = self._chat_llm.invoke(lc_messages)
        except RateLimitError as exc:
            raise TRIZChainError(f"Rate limit: {exc}") from exc
        except AuthenticationError as exc:
            raise TRIZChainError(
                "Неверный OPENAI_API_KEY. Обновите ключ в .env."
            ) from exc
        except APIConnectionError as exc:
            raise TRIZChainError(
                "Не удалось подключиться к OpenAI API. Проверьте сеть и прокси."
            ) from exc
        except APIStatusError as exc:
            raise TRIZChainError(f"Ошибка OpenAI API: {exc.message}") from exc
        except TRIZChainError:
            raise
        except Exception as exc:
            logger.exception("Ошибка TRIZChain.chat")
            raise TRIZChainError(f"Не удалось получить ответ модели: {exc}") from exc

        text = response.content if hasattr(response, "content") else str(response)
        if not text or not str(text).strip():
            raise TRIZChainError("Модель вернула пустой ответ.")
        return str(text).strip(), updated_messages

    @staticmethod
    def _extract_brief_attempt_history(problem: str) -> dict[str, str]:
        """Извлекает тупики/попытки из сводки интервью (без подстановки всего брифа)."""
        fields: dict[str, str] = {}
        for key, pattern in _BRIEF_FIELD_PATTERNS.items():
            match = pattern.search(problem)
            if match:
                value = match.group(1).strip()
                if value:
                    fields[key] = value
        return fields

    @staticmethod
    def _enrich_core_attempt_history(core: dict, problem: str) -> dict:
        brief_fields = TRIZChain._extract_brief_attempt_history(problem)
        for key in ("known_solutions", "why_failed", "unrealized_ideas"):
            if not str(core.get(key) or "").strip() and brief_fields.get(key):
                core[key] = brief_fields[key]
        return core

    @staticmethod
    def _get_attempt_history(core: dict, problem: str) -> tuple[str, str, str]:
        known = str(core.get("known_solutions") or "").strip()
        why = str(core.get("why_failed") or "").strip()
        unrealized = str(core.get("unrealized_ideas") or "").strip()
        if not known or not why or not unrealized:
            brief = TRIZChain._extract_brief_attempt_history(problem)
            known = known or brief.get("known_solutions", "—")
            why = why or brief.get("why_failed", "—")
            unrealized = unrealized or brief.get("unrealized_ideas", "—")
        return known or "—", why or "—", unrealized or "—"

    def _parse_core_result(self, result: object) -> dict:
        if isinstance(result, TRIZAnalysisCore):
            return result.model_dump()
        if isinstance(result, dict):
            return TRIZAnalysisCore.model_validate(result).model_dump()
        raise TRIZChainError(
            f"Неожиданный тип ответа core-анализа: {type(result).__name__}"
        )

    def _run_core_analysis(self, problem: str) -> dict:
        """Этап a: core-анализ → TRIZAnalysisCore."""
        try:
            result = self._core_chain.invoke({"problem": problem})
        except RateLimitError as exc:
            logger.error("Превышен лимит OpenAI: %s", exc)
            raise TRIZChainError(
                "Превышен лимит запросов OpenAI. Повторите попытку позже."
            ) from exc
        except AuthenticationError as exc:
            logger.error("Неверный OPENAI_API_KEY: %s", exc)
            raise TRIZChainError(
                "Неверный OPENAI_API_KEY. Создайте новый ключ на "
                "https://platform.openai.com/api-keys и обновите .env."
            ) from exc
        except APIConnectionError as exc:
            logger.error("Нет соединения с OpenAI: %s", exc)
            detail = str(exc).lower()
            if "timed out" in detail or "timeout" in detail:
                raise TRIZChainError(
                    "Таймаут при обращении к OpenAI API. Проверьте прокси "
                    "(OPENAI_PROXY_URL) или увеличьте таймаут; без прокси доступ "
                    "может быть заблокирован."
                ) from exc
            raise TRIZChainError(
                "Не удалось подключиться к OpenAI API. Проверьте сеть и прокси."
            ) from exc
        except APIStatusError as exc:
            logger.error("Ошибка OpenAI API (статус %s): %s", exc.status_code, exc)
            raise TRIZChainError(f"Ошибка OpenAI API: {exc.message}") from exc
        except ValidationError as exc:
            logger.error("Ошибка валидации core-ответа модели: %s", exc)
            raise TRIZChainError(
                f"Модель вернула некорректную структуру анализа: {exc}"
            ) from exc
        except TRIZChainError:
            raise
        except Exception as exc:
            logger.exception("Ошибка core-анализа TRIZChain.solve")
            raise TRIZChainError(f"Не удалось получить ответ модели: {exc}") from exc

        return self._enrich_core_attempt_history(
            self._parse_core_result(result), problem
        )

    def _validate_and_fix_fp(self, problem: str, core: dict) -> dict:
        """Этап b: валидация ПСА и ФП; при провале — до двух retry ПСА + ТП/ФП."""
        max_repairs = 2

        for attempt in range(1, max_repairs + 2):
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
                return core

            if not psa_ok and psa_feedback:
                feedback_parts.append(psa_feedback)
            if not fp_passed and fp_feedback:
                feedback_parts.append(fp_feedback)

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
                    repaired = self._regenerate_contradictions(problem, core, combined_feedback)
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
                break

        return core

    @staticmethod
    def _get_constraints(core: dict) -> list[str]:
        ctx = core.get("system_context") or {}
        raw = ctx.get("constraints") or []
        if isinstance(raw, list):
            return [str(c).strip() for c in raw if str(c).strip()]
        if raw:
            return [str(raw).strip()]
        return []

    def _build_solution_input(
        self,
        core: dict,
        problem: str,
        validator_feedback: str = "",
    ) -> dict:
        analysis = core.get("analysis") or {}
        constraints = self._get_constraints(core)
        constraints_text = (
            "\n".join(f"• {c}" for c in constraints) if constraints else "—"
        )
        known, why_failed, unrealized = self._get_attempt_history(core, problem)
        ctx = core.get("system_context") or {}
        resources_list = ctx.get("resources") or []
        if isinstance(resources_list, list):
            brief_resources = (
                "\n".join(f"• {r}" for r in resources_list if str(r).strip()) or "—"
            )
        else:
            brief_resources = str(resources_list).strip() or "—"
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
            "validator_feedback": feedback_block,
        }

    def _generate_solutions(
        self,
        core: dict,
        problem: str,
        *,
        validator_feedback: str = "",
    ) -> list[dict]:
        """Генерация solution_concepts по валидированному ядру."""
        solution_input = self._build_solution_input(
            core, problem, validator_feedback=validator_feedback
        )
        result = self._solution_chain.invoke(solution_input)
        if isinstance(result, SolutionSet):
            return [s.model_dump() for s in result.solution_concepts]
        if isinstance(result, dict):
            return SolutionSet.model_validate(result).model_dump()["solution_concepts"]
        raise TRIZChainError(
            f"Неожиданный тип ответа генерации решений: {type(result).__name__}"
        )

    def _validate_and_generate_solutions(
        self, core: dict, problem: str
    ) -> tuple[list[dict], str, int]:
        """
        Генерация решений + валидация с накоплением валидных попыток.

        Returns:
            (solutions, warning, attempts_used) — warning непустой, если после
            MAX_SOLUTION_GENERATION_ATTEMPTS валидных решений меньше MIN_SOLUTIONS.
        """
        constraints = self._get_constraints(core)
        analysis = core.get("analysis") or {}
        resources = analysis.get("resources_analysis", "")
        known, why_failed, _unrealized = self._get_attempt_history(core, problem)
        ifr = core.get("ideal_final_result", "")

        batches: list[list[dict]] = []
        feedback = ""
        attempts_used = 0

        for attempt in range(1, MAX_SOLUTION_GENERATION_ATTEMPTS + 1):
            attempts_used = attempt
            try:
                if attempt == 1:
                    batch = self._generate_solutions(core, problem)
                else:
                    batch = self._generate_solutions(
                        core, problem, validator_feedback=feedback
                    )
            except Exception as exc:
                logger.warning(
                    "Генерация решений (попытка %d/%d) не удалась: %s",
                    attempt,
                    MAX_SOLUTION_GENERATION_ATTEMPTS,
                    exc,
                )
                break

            passed, feedback, valid_batch = validate_solutions(
                batch, known, why_failed, resources, ifr, self._llm, constraints
            )
            batches.append(valid_batch)
            accumulated = select_diverse_solutions(
                merge_valid_solutions(*batches), limit=5
            )

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
                div_ok, div_feedback = check_solution_diversity(
                    accumulated, resources, self._llm
                )
                if div_ok and passed:
                    return accumulated, "", attempts_used
                if div_ok and attempt == MAX_SOLUTION_GENERATION_ATTEMPTS:
                    return accumulated, "", attempts_used
                if not div_ok:
                    feedback = div_feedback or feedback
                    if attempt < MAX_SOLUTION_GENERATION_ATTEMPTS:
                        logger.info(
                            "Накопленный набор не прошёл проверку разнообразия, retry: %s",
                            div_feedback[:200],
                        )
                        continue
            elif passed:
                return accumulated, "", attempts_used

        accumulated = select_diverse_solutions(
            merge_valid_solutions(*batches), limit=5
        )
        if len(accumulated) >= MIN_SOLUTIONS:
            return accumulated, "", attempts_used

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
        return accumulated, warning, attempts_used

    def _regenerate_psa_root(
        self, problem: str, core: dict, feedback: str
    ) -> dict[str, str]:
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
        raise TRIZChainError(
            f"Неожиданный тип ответа перегенерации ПСА: {type(result).__name__}"
        )

    def _regenerate_contradictions(
        self, problem: str, core: dict, feedback: str
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
        known, why_failed, unrealized = self._get_attempt_history(core, problem)
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

    def _assemble_payload(self, core: dict, solutions: list[dict]) -> dict:
        """Этап d–e: рекомендации + финальный payload."""
        tail = build_recommendations(core, solutions)
        return {**core, "solution_concepts": solutions, **tail}

    def solve(
        self,
        problem: str,
        *,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> dict:
        """
        Пайплайн TRIZ-анализа:

        a) core-анализ (TRIZAnalysisCore)
        b) валидация ФП (+ retry ТП/ФП при провале)
        c) генерация решений (+ валидация и retry)
        d) рекомендации (детерминированно из ранжирования)
        e) сборка payload + enrich_legacy_fields

        Returns:
            dict с полями полного отчёта и обратной совместимости.
        """
        def _progress(pct: int, stage: str) -> None:
            if on_progress is not None:
                on_progress(pct, stage)

        if not problem or not problem.strip():
            raise TRIZChainError("Описание задачи (problem) не может быть пустым.")

        problem = problem.strip()
        logger.info("TRIZ solve pipeline: длина задачи=%d", len(problem))

        _progress(5, "Подготовка к анализу")
        _progress(10, "TRIZ core-анализ")
        core = self._run_core_analysis(problem)
        missing = _missing_mandatory_tools(core)
        if missing:
            logger.info(
                "Обязательные инструменты ШАГ 2.1 отсутствуют после первого прохода: %s — повтор",
                missing,
            )
            retry_note = (
                "\n\nВАЖНО: в предыдущем анализе отсутствовали обязательные инструменты "
                f"ШАГ 2.1: {', '.join(missing)}. Включи их в triz_tools с конкретными "
                "результатами применения к данной задаче."
            )
            core = self._run_core_analysis(problem + retry_note)
            still_missing = _missing_mandatory_tools(core)
            if still_missing:
                logger.warning(
                    "Обязательные инструменты ШАГ 2.1 всё ещё отсутствуют после повтора: %s",
                    still_missing,
                )
        logger.info(
            "TRIZ core-анализ завершён: тип=%s, инструментов=%d",
            core.get("contradiction_type"),
            len(core.get("triz_tools", [])),
        )

        _progress(35, "Валидация физического противоречия")
        core = self._validate_and_fix_fp(problem, core)
        core, type_note = reconcile_contradiction_type(core)
        if type_note:
            logger.info("TRIZ contradiction_type reconciled: %s", type_note)

        _progress(50, "Генерация решений")
        solutions, generation_warning, _attempts = self._validate_and_generate_solutions(
            core, problem
        )

        _progress(85, "Формирование рекомендаций")
        payload = self._assemble_payload(core, solutions)
        if generation_warning:
            payload["solution_generation_note"] = generation_warning
            summary = (payload.get("executive_summary") or "").strip()
            payload["executive_summary"] = (
                f"{summary} {generation_warning}".strip()
                if summary
                else generation_warning
            )
        payload = enrich_legacy_fields(payload)

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
