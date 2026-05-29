"""LangChain-цепочка TRIZ-ассистента: экспертный анализ и отчёт."""



import logging



from langchain_core.prompts import ChatPromptTemplate

from openai import APIConnectionError, APIStatusError, RateLimitError

from pydantic import ValidationError



from backend.config import settings

from backend.llm.models import TRIZAnalysisResult, enrich_legacy_fields

from backend.llm.openai_client import create_chat_llm

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

        except APIConnectionError as exc:

            logger.error("Нет соединения с OpenAI: %s", exc)

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


