"""LangChain-цепочка TRIZ-ассистента: экспертный анализ и отчёт."""



import logging



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

from backend.llm.models import TRIZAnalysisResult, enrich_legacy_fields

from backend.llm.openai_client import create_chat_llm

from backend.llm.chat_preprocessor import _extract_known_data, _is_tautology_ne_when
from backend.llm.chat_prompt import CHAT_SYSTEM_PROMPT
from backend.llm.interview_state import InterviewStateManager
from backend.llm.system_prompt import SYSTEM_PROMPT, USER_PROMPT



logger = logging.getLogger(__name__)





class TRIZChainError(Exception):

    """Ошибка при работе TRIZ LLM-цепочки."""





class TRIZChain:

    """LangChain-цепочка: задача → экспертный TRIZ-отчёт (только LLM)."""



    def __init__(self) -> None:

        if not settings.openai_api_key:

            raise TRIZChainError(

                "Не задан OPENAI_API_KEY. Укажите ключ в файле .env."

            )



        try:

            self._llm = create_chat_llm(temperature=0.25)
            self._chat_llm = create_chat_llm(temperature=0.35)

            self._structured_llm = self._llm.with_structured_output(TRIZAnalysisResult)

            self._prompt = ChatPromptTemplate.from_messages(

                [

                    ("system", SYSTEM_PROMPT),

                    ("human", USER_PROMPT),

                ]

            )

            self._chain = self._prompt | self._structured_llm

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

        mgr.confirm_pending_answer(last_user, reject_field=_reject_pending)

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

    def solve(self, problem: str) -> dict:

        """

        Анализирует задачу и возвращает полный экспертный отчёт.



        Возвращает dict с полями отчёта + обратной совместимости.

        """

        if not problem or not problem.strip():

            raise TRIZChainError("Описание задачи (problem) не может быть пустым.")



        logger.info("TRIZ solve: длина задачи=%d", len(problem))



        try:

            result = self._chain.invoke({"problem": problem.strip()})

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

        except TRIZChainError:

            raise

        except ValidationError as exc:

            logger.error("Ошибка валидации ответа модели: %s", exc)

            raise TRIZChainError(

                f"Модель вернула некорректную структуру отчёта: {exc}"

            ) from exc

        except Exception as exc:

            logger.exception("Ошибка при вызове TRIZChain.solve")

            raise TRIZChainError(f"Не удалось получить ответ модели: {exc}") from exc



        if isinstance(result, TRIZAnalysisResult):

            payload = result.model_dump()

        elif isinstance(result, dict):

            payload = TRIZAnalysisResult.model_validate(result).model_dump()

        else:

            raise TRIZChainError(

                f"Неожиданный тип ответа модели: {type(result).__name__}"

            )



        payload = enrich_legacy_fields(payload)



        if len(payload.get("solution_concepts", [])) < 2:

            logger.warning(

                "Модель вернула менее 2 решений: %s",

                payload.get("solution_concepts"),

            )



        logger.info(

            "TRIZ solve завершён: тип=%s, инструментов=%d, решений=%d",

            payload.get("contradiction_type"),

            len(payload.get("triz_tools", [])),

            len(payload.get("solution_concepts", [])),

        )

        return payload


