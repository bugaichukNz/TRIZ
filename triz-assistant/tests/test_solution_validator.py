"""Тесты детерминированной логики solution_validator."""

from __future__ import annotations

from backend.llm.solution_validator import (
    _heuristic_constraint_violation,
    _heuristic_diversity_check,
    merge_valid_solutions,
    select_diverse_solutions,
)


def _solution(
    sid: int,
    *,
    title: str,
    mechanism: str,
    principle: str = "№1",
    effectiveness: float = 5,
    complexity: float = 1,
) -> dict:
    return {
        "id": sid,
        "title": title,
        "mechanism": mechanism,
        "triz_principle": principle,
        "effectiveness_score": effectiveness,
        "scalability_score": 3,
        "complexity_score": complexity,
        "cost_score": 1,
        "applicability": "подходит",
    }


class TestMergeValidSolutions:
    def test_does_not_duplicate_same_title_mechanism(self) -> None:
        batch_a = [_solution(1, title="Наклон подноса", mechanism="изменить угол подноса")]
        batch_b = [_solution(2, title="Наклон подноса", mechanism="изменить угол подноса")]
        merged = merge_valid_solutions(batch_a, batch_b)
        assert len(merged) == 1

    def test_keeps_higher_score_on_duplicate(self) -> None:
        low = _solution(1, title="Дренаж", mechanism="канавки на подносе", effectiveness=3)
        high = _solution(2, title="Дренаж", mechanism="канавки на подносе", effectiveness=9)
        merged = merge_valid_solutions([low], [high])
        assert len(merged) == 1
        assert merged[0]["effectiveness_score"] == 9

    def test_merges_distinct_solutions(self) -> None:
        a = _solution(1, title="Обдув", mechanism="воздушный поток над стаканами")
        b = _solution(2, title="Текстура", mechanism="микрорельеф на поверхности подноса")
        merged = merge_valid_solutions([a], [b])
        assert len(merged) == 2
        titles = {s["title"] for s in merged}
        assert titles == {"Обдув", "Текстура"}

    def test_reindexes_ids_after_merge(self) -> None:
        solutions = [
            _solution(5, title="A", mechanism="механизм A"),
            _solution(9, title="B", mechanism="механизм B"),
        ]
        merged = merge_valid_solutions(solutions)
        assert [s["id"] for s in merged] == [1, 2]


class TestSelectDiverseSolutions:
    def test_selects_different_principles(self) -> None:
        solutions = [
            _solution(1, title="A", mechanism="обдув воздухом", principle="№10"),
            _solution(2, title="B", mechanism="наклон подноса", principle="№15"),
            _solution(3, title="C", mechanism="пористое покрытие", principle="№35"),
            _solution(4, title="D", mechanism="ещё один обдув", principle="№10"),
        ]
        selected = select_diverse_solutions(solutions, limit=3)
        principles = [s["triz_principle"] for s in selected]
        assert len(selected) == 3
        assert len(set(principles)) == 3

    def test_avoids_same_mechanism_cluster(self) -> None:
        solutions = [
            _solution(1, title="Силикон 1", mechanism="силиконовая подкладка под стакан", principle="№1"),
            _solution(2, title="Силикон 2", mechanism="силиконовый вкладыш в гнездо", principle="№2"),
            _solution(3, title="Дренаж", mechanism="канавки для стока воды", principle="№3"),
        ]
        selected = select_diverse_solutions(solutions, limit=3)
        silicon_count = sum(1 for s in selected if "силикон" in s["mechanism"].lower())
        assert silicon_count <= 1
        assert len(selected) >= 2

    def test_empty_input_returns_empty(self) -> None:
        assert select_diverse_solutions([]) == []

    def test_reindexes_selected_ids(self) -> None:
        solutions = [
            _solution(10, title="A", mechanism="обдув", principle="№1"),
            _solution(20, title="B", mechanism="наклон", principle="№2"),
        ]
        selected = select_diverse_solutions(solutions, limit=2)
        assert [s["id"] for s in selected] == [1, 2]


class TestHeuristicDiversity:
    def test_fails_when_all_same_principle(self) -> None:
        solutions = [
            _solution(1, title="A", mechanism="обдув 1", principle="№5"),
            _solution(2, title="B", mechanism="обдув 2", principle="№5"),
            _solution(3, title="C", mechanism="обдув 3", principle="№5"),
        ]
        ok, feedback = _heuristic_diversity_check(solutions)
        assert ok is False
        assert "принцип" in feedback.lower()

    def test_passes_for_diverse_set(self) -> None:
        solutions = [
            _solution(1, title="A", mechanism="обдув воздухом", principle="№10"),
            _solution(2, title="B", mechanism="наклон подноса", principle="№15"),
            _solution(3, title="C", mechanism="пористое покрытие", principle="№35"),
        ]
        ok, feedback = _heuristic_diversity_check(solutions)
        assert ok is True
        assert feedback == ""


class TestHeuristicConstraints:
    def test_detects_equipment_vs_consumables_only(self) -> None:
        constraints = "• только расходники, без оборудования"
        solution = _solution(
            1,
            title="Автосушка",
            mechanism="автоматизированная система сушки стаканов",
        )
        violates, _, reason = _heuristic_constraint_violation(solution, constraints)
        assert violates is True
        assert reason

    def test_no_violation_when_constraints_empty(self) -> None:
        solution = _solution(1, title="X", mechanism="что угодно")
        violates, _, _ = _heuristic_constraint_violation(solution, "")
        assert violates is False
