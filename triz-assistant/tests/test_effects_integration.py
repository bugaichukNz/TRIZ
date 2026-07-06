"""Интеграционные тесты RAG физэффектов в пайплайне генерации решений."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from backend.config import settings
from backend.llm.chain import TRIZChain
from backend.llm.effects_rag import EFFECTS_BLOCK_HEADER, build_effects_block
from backend.llm.models import EffectQueries, PhysicalEffect, SolutionSet
from backend.llm.solution_prompt import SOLUTION_USER_PROMPT

# Промпт до добавления {effects_block} — эталон для byte-parity при выключенном флаге.
LEGACY_SOLUTION_USER_PROMPT = """На основе завершённого TRIZ-анализа сгенерируй 3–5 новых концепций решений.

Техническое противоречие (ТП):
{technical_contradiction}

Физическое противоречие (ФП):
{physical_contradiction}

Идеальный конечный результат (ИКР):
{ideal_final_result}

Анализ ресурсов:
{resources_analysis}

Ресурсы из брифа (краткий перечень):
{brief_resources}

Известные попытки решения (тупики — НЕ повторять семантически):
{known_solutions}

Почему не сработало (тупики — НЕ повторять семантически):
{why_failed}

Нереализованные идеи (развить или явно объяснить отказ в applicability):
{unrealized_ideas}

Жёсткие ограничения (constraints) — нарушать НЕЛЬЗЯ; дорогие, но допустимые варианты допустимы:
{constraints}
{validator_feedback}
Сформируй solution_concepts: 3–5 решений с полями id, title, triz_principle, mechanism, applicability, risks и оценками 1–10.
"""

PROBLEM = "Стаканы на подносе: капли воды после мытья не успевают стекать до переноски."

CORE_FIXTURE: dict[str, Any] = {
    "problem_description": PROBLEM,
    "technical_contradiction": (
        "Чтобы ускорить стекание воды, нужно наклонить поднос, "
        "но тогда стаканы скользят и падают."
    ),
    "physical_contradiction": (
        "Поднос: параметр угол наклона должен быть большим, "
        "чтобы вода стекала с поверхности, и должен быть малым, "
        "чтобы стаканы оставались устойчивыми."
    ),
    "ideal_final_result": (
        "Поднос САМ обеспечивает стекание воды и удержание стаканов "
        "без дополнительных устройств."
    ),
    "root_cause": (
        "Сила тяжести одновременно ускоряет стекание капель "
        "и создаёт смещающую компоненту для стаканов на наклонной плоскости."
    ),
    "known_solutions": "Увеличение наклона подноса",
    "why_failed": "Стаканы соскальзывают при ускоренном стекании",
    "unrealized_ideas": "Микрорельеф на поверхности подноса",
    "system_context": {
        "system": "Поднос со стаканами",
        "supersystem": "Линия розлива",
        "subsystems": ["стаканы", "капли воды"],
        "useful_functions": ["переноска стаканов"],
        "harmful_effects": ["скольжение стаканов"],
        "constraints": ["без остановки линии", "без дополнительных операторов"],
        "resources": ["сжатый воздух", "текстура подноса"],
    },
    "analysis": {
        "causal_chains": "Наклон → стекание ↑, устойчивость ↓",
        "functional_analysis": "Поднос удерживает и транспортирует",
        "resources_analysis": (
            "Вещественные: поднос, стаканы, вода. "
            "Энергетические: гравитация. "
            "Пространственные: зона края подноса."
        ),
        "contradiction_zones": "Контакт стакан–поднос",
    },
}

SAMPLE_EFFECT = PhysicalEffect(
    id="leidenfrost_effect",
    name="Эффект Лейденfrostа",
    category="физический",
    description="При контакте капли с раскалённой поверхностью образуется паровая прослойка.",
    input_action="нагреть поверхность выше температуры Лейdenfrostа",
    output_action="капля levitation на паровой подушке",
    functions=["локальный нагрев", "изменение адгезии"],
    limitations="Требует локального нагрева и контроля температуры",
    examples=["Самоочищающиеся поверхности"],
)

SAMPLE_SOLUTIONS = SolutionSet(
    solution_concepts=[
        {
            "id": 1,
            "title": "Микрорельеф",
            "triz_principle": "№3: местное качество",
            "mechanism": "Текстура подноса удерживает стаканы",
            "applicability": "Поднос САМ удерживает стаканы",
            "risks": "Загрязнение рельефа",
            "effectiveness_score": 7,
            "complexity_score": 4,
            "cost_score": 3,
            "scalability_score": 6,
        },
        {
            "id": 2,
            "title": "Обдув",
            "triz_principle": "№28: замена механики",
            "mechanism": "Сжатый воздух сдувает воду",
            "applicability": "Поднос САМ направляет поток",
            "risks": "Шум",
            "effectiveness_score": 6,
            "complexity_score": 5,
            "cost_score": 4,
            "scalability_score": 5,
        },
        {
            "id": 3,
            "title": "Фазовый наклон",
            "triz_principle": "№9: предварительное анти-действие",
            "mechanism": "Наклон только на фазе сушки",
            "applicability": "Поднос САМ меняет угол",
            "risks": "Механика",
            "effectiveness_score": 8,
            "complexity_score": 6,
            "cost_score": 5,
            "scalability_score": 4,
        },
    ]
)


def _format_solution_user_prompt(chain: TRIZChain, effects_block: str = "") -> str:
    solution_input = chain._build_solution_input(
        CORE_FIXTURE,
        PROBLEM,
        effects_block=effects_block,
    )
    return SOLUTION_USER_PROMPT.format(**solution_input)


@pytest.fixture
def chain_with_fake_llm(monkeypatch: pytest.MonkeyPatch, fake_llm):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    llm = fake_llm(
        {
            EffectQueries: {
                "queries": ["локально нагреть зону края", "изменить трение поверхности"]
            },
            SolutionSet: SAMPLE_SOLUTIONS,
        }
    )
    monkeypatch.setattr("backend.llm.chain.create_chat_llm", lambda **_kw: llm)
    return TRIZChain()


class TestEffectsPromptParity:
    def test_flag_off_solution_prompt_unchanged(
        self,
        monkeypatch: pytest.MonkeyPatch,
        chain_with_fake_llm: TRIZChain,
    ) -> None:
        monkeypatch.setattr(settings, "effects_rag_enabled", False)

        solution_input = chain_with_fake_llm._build_solution_input(
            CORE_FIXTURE, PROBLEM, effects_block=""
        )
        current = SOLUTION_USER_PROMPT.format(**solution_input)
        legacy = LEGACY_SOLUTION_USER_PROMPT.format(
            **{k: v for k, v in solution_input.items() if k != "effects_block"}
        )
        assert current == legacy

    def test_flag_on_includes_effects_block(
        self,
        monkeypatch: pytest.MonkeyPatch,
        chain_with_fake_llm: TRIZChain,
    ) -> None:
        monkeypatch.setattr(settings, "effects_rag_enabled", True)

        class MockRetriever:
            enabled = True

            def search(self, queries: list[str], top_k: int = 6) -> list[PhysicalEffect]:
                assert queries == ["локально нагреть зону края", "изменить трение поверхности"]
                assert top_k == 6
                return [SAMPLE_EFFECT]

        monkeypatch.setattr(
            "backend.llm.chain.get_effects_retriever",
            lambda: MockRetriever(),
        )

        effects_block, names = chain_with_fake_llm._retrieve_effects_for_solutions(CORE_FIXTURE)
        assert names == [SAMPLE_EFFECT.name]
        assert EFFECTS_BLOCK_HEADER in effects_block

        prompt = _format_solution_user_prompt(chain_with_fake_llm, effects_block=effects_block)
        assert EFFECTS_BLOCK_HEADER in prompt
        assert SAMPLE_EFFECT.name in prompt

    def test_empty_effects_block_omits_header(self) -> None:
        block, names = build_effects_block([])
        assert block == ""
        assert names == []


class TestEffectsSolveResilience:
    def test_retriever_exception_does_not_break_solve(
        self,
        monkeypatch: pytest.MonkeyPatch,
        chain_with_fake_llm: TRIZChain,
    ) -> None:
        monkeypatch.setattr(settings, "effects_rag_enabled", True)

        class BrokenRetriever:
            enabled = True

            def search(self, *_args: Any, **_kwargs: Any) -> list[PhysicalEffect]:
                raise RuntimeError("index unavailable")

        monkeypatch.setattr(
            "backend.llm.chain.get_effects_retriever",
            lambda: BrokenRetriever(),
        )

        chain = chain_with_fake_llm
        chain._run_core_analysis = lambda _problem, brief=None: dict(CORE_FIXTURE)
        chain._validate_and_fix_fp = lambda _problem, core, brief=None: (core, 1, [], True)

        def _pass_validation(*_args: Any, **_kwargs: Any) -> tuple[bool, str, list[dict]]:
            batch = [s.model_dump() for s in SAMPLE_SOLUTIONS.solution_concepts]
            return True, "", batch

        monkeypatch.setattr(
            "backend.llm.chain.validate_solutions",
            _pass_validation,
        )
        monkeypatch.setattr(
            "backend.llm.chain.check_solution_diversity",
            lambda *_a, **_k: (True, ""),
        )

        payload = chain.solve(PROBLEM)
        assert payload.get("effects_used") == []
        assert len(payload.get("solution_concepts", [])) == 3

    def test_flag_off_payload_has_empty_effects_used(
        self,
        monkeypatch: pytest.MonkeyPatch,
        chain_with_fake_llm: TRIZChain,
    ) -> None:
        monkeypatch.setattr(settings, "effects_rag_enabled", False)

        chain = chain_with_fake_llm
        chain._run_core_analysis = lambda _problem, brief=None: dict(CORE_FIXTURE)
        chain._validate_and_fix_fp = lambda _problem, core, brief=None: (core, 1, [], True)

        def _pass_validation(*_args: Any, **_kwargs: Any) -> tuple[bool, str, list[dict]]:
            batch = [s.model_dump() for s in SAMPLE_SOLUTIONS.solution_concepts]
            return True, "", batch

        monkeypatch.setattr("backend.llm.chain.validate_solutions", _pass_validation)
        monkeypatch.setattr(
            "backend.llm.chain.check_solution_diversity",
            lambda *_a, **_k: (True, ""),
        )

        payload = chain.solve(PROBLEM)
        assert payload.get("effects_used") == []


class TestEffectsRagStartup:
    def test_triz_chain_logs_disabled(
        self,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        monkeypatch.setattr(settings, "openai_api_key", "test-key")
        monkeypatch.setattr(settings, "effects_rag_enabled", False)
        monkeypatch.setattr(
            "backend.llm.chain.create_chat_llm",
            lambda **_kw: fake_llm(),
        )
        with caplog.at_level(logging.INFO, logger="backend.llm.chain"):
            TRIZChain()
        assert "effects-RAG: выключен" in caplog.text

    def test_triz_chain_logs_retriever_disabled(
        self,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
        fake_llm,
    ) -> None:
        monkeypatch.setattr(settings, "openai_api_key", "test-key")
        monkeypatch.setattr(settings, "effects_rag_enabled", True)

        class DisabledRetriever:
            enabled = False

        monkeypatch.setattr(
            "backend.llm.chain.get_effects_retriever",
            lambda: DisabledRetriever(),
        )
        monkeypatch.setattr(
            "backend.llm.chain.create_chat_llm",
            lambda **_kw: fake_llm(),
        )
        with caplog.at_level(logging.INFO, logger="backend.llm.chain"):
            TRIZChain()
        assert "effects-RAG: включён, retriever отключён" in caplog.text

    def test_solve_works_when_retriever_disabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
        chain_with_fake_llm: TRIZChain,
    ) -> None:
        monkeypatch.setattr(settings, "effects_rag_enabled", True)

        class DisabledRetriever:
            enabled = False

            def search(self, *_args: Any, **_kwargs: Any) -> list[PhysicalEffect]:
                return []

        monkeypatch.setattr(
            "backend.llm.chain.get_effects_retriever",
            lambda: DisabledRetriever(),
        )

        chain = chain_with_fake_llm
        chain._run_core_analysis = lambda _problem, brief=None: dict(CORE_FIXTURE)
        chain._validate_and_fix_fp = lambda _problem, core, brief=None: (core, 1, [], True)

        def _pass_validation(*_args: Any, **_kwargs: Any) -> tuple[bool, str, list[dict]]:
            batch = [s.model_dump() for s in SAMPLE_SOLUTIONS.solution_concepts]
            return True, "", batch

        monkeypatch.setattr("backend.llm.chain.validate_solutions", _pass_validation)
        monkeypatch.setattr(
            "backend.llm.chain.check_solution_diversity",
            lambda *_a, **_k: (True, ""),
        )

        payload = chain.solve(PROBLEM)
        assert payload.get("effects_used") == []
        assert len(payload.get("solution_concepts", [])) == 3
