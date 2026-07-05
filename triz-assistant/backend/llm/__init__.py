"""Модуль LLM: цепочки LangChain для ответов ассистента."""

__all__ = ["TRIZChain", "TRIZChainError"]


def __getattr__(name: str):
    if name == "TRIZChain":
        from backend.llm.chain import TRIZChain

        return TRIZChain
    if name == "TRIZChainError":
        from backend.llm.chain import TRIZChainError

        return TRIZChainError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
