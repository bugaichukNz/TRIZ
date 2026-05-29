"""Генерация HTML-отчёта экспертного TRIZ-анализа."""

from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any


def _esc(value: Any) -> str:
    return html.escape(str(value) if value is not None else "—")


def _total_score(sol: dict[str, Any]) -> float:
    return round(
        sol.get("effectiveness_score", 0)
        + sol.get("scalability_score", 0)
        - (sol.get("complexity_score", 0) + sol.get("cost_score", 0)) / 2,
        1,
    )


def _list_items(items: list[str]) -> str:
    if not items:
        return "<li class='empty'>—</li>"
    return "".join(f"<li>{_esc(i)}</li>" for i in items)


def _table_rows_tools(tools: list[dict[str, Any]]) -> str:
    if not tools:
        return '<tr><td colspan="4" class="empty">—</td></tr>'
    return "".join(
        f"<tr><td>{_esc(t.get('tool'))}</td><td>{_esc(t.get('why_applied'))}</td>"
        f"<td>{_esc(t.get('insight'))}</td><td>{_esc(t.get('practical_value'))}</td></tr>"
        for t in tools
    )


def _table_rows_solutions(concepts: list[dict[str, Any]]) -> str:
    if not concepts:
        return '<tr><td colspan="5" class="empty">—</td></tr>'
    return "".join(
        f"<tr><td>{_esc(s.get('title'))}</td><td>{_esc(s.get('triz_principle'))}</td>"
        f"<td>{_esc(s.get('mechanism'))}</td><td>{_esc(s.get('applicability'))}</td>"
        f"<td>{_esc(s.get('risks'))}</td></tr>"
        for s in concepts
    )


def _table_rows_compare(concepts: list[dict[str, Any]]) -> str:
    if not concepts:
        return '<tr><td colspan="6" class="empty">—</td></tr>'
    return "".join(
        f"<tr><td>{_esc(s.get('title'))}</td>"
        f"<td class='num'>{s.get('effectiveness_score')}</td>"
        f"<td class='num'>{s.get('complexity_score')}</td>"
        f"<td class='num'>{s.get('cost_score')}</td>"
        f"<td class='num'>{s.get('scalability_score')}</td>"
        f"<td class='num total'>{_total_score(s)}</td></tr>"
        for s in concepts
    )


def build_report_html(
    problem: str,
    result: dict[str, Any],
    *,
    generated_at: datetime | None = None,
) -> str:
    """Собирает HTML-отчёт по структуре экспертного TRIZ-документа."""
    ts = generated_at or datetime.now()
    ctx = result.get("system_context") or {}
    analysis = result.get("analysis") or {}
    tools = result.get("triz_tools") or []
    concepts = result.get("solution_concepts") or []
    rec = result.get("recommendations") or {}
    conclusion = result.get("final_conclusion") or {}
    chart_labels = [s.get("title", f"#{s.get('id')}")[:40] for s in concepts]
    chart_effectiveness = [s.get("effectiveness_score", 0) for s in concepts]
    chart_complexity = [s.get("complexity_score", 0) for s in concepts]
    chart_data = json.dumps(
        {
            "labels": chart_labels or ["Нет данных"],
            "effectiveness": chart_effectiveness or [0],
            "complexity": chart_complexity or [0],
        },
        ensure_ascii=False,
    )

    sys_rows = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>"
        for k, v in (
            ("Система", ctx.get("system")),
            ("Надсистема", ctx.get("supersystem")),
            ("Подсистемы", "; ".join(ctx.get("subsystems") or [])),
            ("Полезные функции", "; ".join(ctx.get("useful_functions") or [])),
            ("Нежелательные эффекты", "; ".join(ctx.get("harmful_effects") or [])),
            ("Ограничения", "; ".join(ctx.get("constraints") or [])),
            ("Доступные ресурсы", "; ".join(ctx.get("resources") or [])),
        )
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TRIZ Отчёт — {_esc(ts.strftime('%d.%m.%Y %H:%M'))}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root {{
  --text-primary: #1A1A1A;
  --text-secondary: #6B6B6B;
  --text-label: #8A8A8A;
  --accent: #10A37F;
  --border: #E5E5E5;
  --border-muted: #D0D0D0;
  --bg: #F9F9F9;
  --bg-white: #FFFFFF;
  --bg-muted: #F0F0F0;
  --shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: Arial, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--text-primary);
  line-height: 1.55;
  font-size: 14px;
}}
.wrap {{ max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem 3rem; }}
header {{
  background: var(--bg-white);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.75rem 2rem;
  margin-bottom: 1.5rem;
  box-shadow: var(--shadow);
}}
header h1 {{ margin: 0 0 0.5rem; font-size: 1.6rem; font-weight: 600; color: var(--text-primary); }}
header .meta {{ font-size: 0.85rem; color: var(--text-secondary); }}
section {{
  background: var(--bg-white);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.15rem 1.25rem;
  margin-bottom: 1rem;
  box-shadow: var(--shadow);
}}
section h2 {{
  margin: 0 0 0.75rem;
  font-size: 1.05rem;
  font-weight: 500;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.35rem;
}}
section h3 {{ margin: 1rem 0 0.4rem; font-size: 0.95rem; font-weight: 500; color: var(--text-secondary); }}
.ifr {{
  background: var(--bg-muted);
  border-left: 3px solid var(--border-muted);
  padding: 0.85rem 1rem;
  border-radius: 6px;
  font-weight: 500;
  color: var(--text-primary);
}}
table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
th, td {{ border: 1px solid var(--border); padding: 0.5rem 0.6rem; vertical-align: top; }}
th {{
  background: var(--bg-muted);
  color: var(--text-label);
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  text-align: left;
}}
tr:nth-child(even) td {{ background: var(--bg); }}
td.num, th.num {{ text-align: center; }}
td.total {{ font-weight: 600; color: var(--accent); }}
td.empty {{ text-align: center; font-style: italic; color: var(--text-secondary); }}
ul {{ margin: 0.25rem 0 0.5rem 1.2rem; padding: 0; }}
li.empty {{ list-style: none; margin-left: -1.2rem; color: var(--text-secondary); }}
.chart-wrap {{ height: 280px; margin-top: 0.5rem; }}
.summary-grid {{
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 0.35rem 1rem;
  margin-top: 0.5rem;
}}
.summary-grid dt {{
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-label);
}}
.summary-grid dd {{ margin: 0; color: var(--text-primary); }}
.executive {{
  font-size: 0.95rem;
  background: var(--bg-muted);
  border: 1px solid var(--border);
  padding: 0.75rem;
  border-radius: 6px;
}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>TRIZ-аналитический отчёт</h1>
    <p class="meta">{_esc(ts.strftime('%d.%m.%Y %H:%M'))} · Экспертный анализ</p>
    <p style="margin-top:0.75rem;font-size:0.9rem;">{_esc(problem)}</p>
  </header>

  <section>
    <h2>Описание задачи</h2>
    <p>{_esc(result.get('problem_description', problem))}</p>
    {'<h3>Принятые допущения</h3><ul>' + _list_items(result.get('assumptions') or []) + '</ul>' if result.get('assumptions') else ''}
    <div class="executive" style="margin-top:1rem;"><strong>Резюме:</strong> {_esc(result.get('executive_summary', ''))}</div>
  </section>

  <section>
    <h2>Система и надсистема</h2>
    <table><tbody>{sys_rows}</tbody></table>
  </section>

  <section>
    <h2>Противоречия и ИКР</h2>
    <table>
      <tr><th>Техническое противоречие (ТП)</th><td>{_esc(result.get('technical_contradiction'))}</td></tr>
      <tr><th>Физическое противоречие (ФП)</th><td>{_esc(result.get('physical_contradiction'))}</td></tr>
      <tr><th>Тип</th><td>{_esc(result.get('contradiction_type'))}</td></tr>
    </table>
    <p class="ifr" style="margin-top:0.75rem;">ИКР: {_esc(result.get('ideal_final_result'))}</p>
  </section>

  <section>
    <h2>Анализ</h2>
    <h3>Причинно-следственные цепочки</h3><p>{_esc(analysis.get('causal_chains'))}</p>
    <h3>Функциональный анализ</h3><p>{_esc(analysis.get('functional_analysis'))}</p>
    <h3>Выявленные ресурсы</h3><p>{_esc(analysis.get('resources_analysis'))}</p>
    <h3>Ключевые зоны противоречий</h3><p>{_esc(analysis.get('contradiction_zones'))}</p>
  </section>

  <section>
    <h2>Применённые инструменты ТРИЗ</h2>
    <table>
      <thead><tr><th>Инструмент</th><th>Почему применён</th><th>Что выявил</th><th>Практическая ценность</th></tr></thead>
      <tbody>{_table_rows_tools(tools)}</tbody>
    </table>
  </section>

  <section>
    <h2>Решения</h2>
    <table>
      <thead><tr><th>Решение</th><th>Принцип ТРИЗ</th><th>Механизм</th><th>Применимость</th><th>Риски</th></tr></thead>
      <tbody>{_table_rows_solutions(concepts)}</tbody>
    </table>
  </section>

  <section>
    <h2>Сравнение решений</h2>
    <table>
      <thead><tr><th>Решение</th><th class="num">Эффект.</th><th class="num">Сложн.</th>
      <th class="num">Стоим.</th><th class="num">Масшт.</th><th class="num">Итог</th></tr></thead>
      <tbody>{_table_rows_compare(concepts)}</tbody>
    </table>
    <div class="chart-wrap"><canvas id="chartCompare"></canvas></div>
  </section>

  <section>
    <h2>Рекомендации к внедрению</h2>
    <h3>Приоритеты</h3><ul>{_list_items(rec.get('priorities') or [])}</ul>
    <h3>Быстрые проверки</h3><ul>{_list_items(rec.get('quick_checks') or [])}</ul>
    <h3>MVP / пилоты</h3><ul>{_list_items(rec.get('mvp_pilots') or [])}</ul>
    <h3>Критические риски</h3><ul>{_list_items(rec.get('critical_risks') or [])}</ul>
    <h3>Эксперименты</h3><ul>{_list_items(rec.get('experiments') or [])}</ul>
    <h3>Метрики</h3><ul>{_list_items(rec.get('metrics') or [])}</ul>
  </section>

  <section>
    <h2>Итоговый вывод</h2>
    <dl class="summary-grid">
      <dt>Рекомендуемое решение</dt><dd>{_esc(conclusion.get('recommended_solution'))}</dd>
      <dt>Ключевой риск</dt><dd>{_esc(conclusion.get('key_risk'))}</dd>
      <dt>Следующий шаг</dt><dd>{_esc(conclusion.get('next_step'))}</dd>
    </dl>
  </section>

  {'<section><h2>Применённые принципы TRIZ</h2><ul>' + _list_items(result.get('recommended_principles') or []) + '</ul></section>' if result.get('recommended_principles') else ''}

  <footer style="text-align:center;color:#6B6B6B;font-size:0.78rem;margin-top:2rem;">
    TRIZ AI-Ассистент · экспертный отчёт
  </footer>
</div>
<script>
const data = {chart_data};
new Chart(document.getElementById('chartCompare'), {{
  type: 'bar',
  data: {{
    labels: data.labels,
    datasets: [
      {{ label: 'Эффективность', data: data.effectiveness, backgroundColor: '#10A37F' }},
      {{ label: 'Сложность внедрения', data: data.complexity, backgroundColor: '#404040' }},
    ],
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    scales: {{ y: {{ min: 0, max: 10 }} }},
  }},
}});
</script>
</body>
</html>"""
