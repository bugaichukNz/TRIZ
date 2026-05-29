"""Проверка пайплайна: health → POST /solve."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings  # noqa: E402

TEST_PROBLEM = (
    "Нужно сделать стальную конструкцию одновременно "
    "прочной и лёгкой, но увеличение прочности "
    "увеличивает вес"
)

BACKEND_URL = "http://localhost:8000"
HEALTH_URL = f"{BACKEND_URL}/health"
SOLVE_URL = f"{BACKEND_URL}/solve"


def check_health() -> None:
    print("=" * 60)
    print("1. Проверка GET /health")
    print("=" * 60)
    try:
        response = requests.get(HEALTH_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"   OK: status={data.get('status')}, model={data.get('llm_model')}")
        print(f"   OpenAI: {'да' if data.get('openai_configured') else 'нет'}")
        print(f"   Proxy: {'да' if data.get('proxy_enabled') else 'нет'}")
        if data.get("message"):
            print(f"   Сообщение: {data['message']}")
    except requests.ConnectionError:
        print("   ОШИБКА: backend недоступен.")
        print("   Запустите: uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload")
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"   ОШИБКА: {exc}")
        sys.exit(1)


def test_solve_endpoint() -> dict:
    print()
    print("=" * 60)
    print("2. Тестовый запрос POST /solve")
    print("=" * 60)
    print(f"   Backend: {SOLVE_URL}")
    print(f"   Задача: {TEST_PROBLEM[:80]}...")

    try:
        response = requests.post(
            SOLVE_URL,
            json={"problem": TEST_PROBLEM},
            timeout=180,
        )
    except requests.ConnectionError:
        print("   ОШИБКА: backend недоступен.")
        sys.exit(1)
    except requests.Timeout:
        print("   ОШИБКА: превышено время ожидания (180 с).")
        sys.exit(1)

    if response.status_code != 200:
        detail = response.text
        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass
        print(f"   ОШИБКА: HTTP {response.status_code}: {detail}")
        sys.exit(1)

    print("   OK: ответ получен.")
    return response.json()


def print_result(result: dict) -> None:
    print()
    print("=" * 60)
    print("РЕЗУЛЬТАТ АНАЛИЗА TRIZ")
    print("=" * 60)
    print(f"\nТип противоречия: {result.get('contradiction_type', '—')}")
    print(f"ТП: {result.get('technical_contradiction', result.get('contradiction', '—'))}")
    print(f"ИКР: {result.get('ideal_final_result', '—')}")
    summary = result.get("executive_summary", "—")
    print(f"\nРезюме: {summary[:300]}{'...' if len(summary) > 300 else ''}")

    print("\nКонцепции решений:")
    for sol in result.get("solution_concepts", []):
        print(f"  [{sol.get('id')}] {sol.get('title')} — {sol.get('triz_principle')}")

    fc = result.get("final_conclusion") or {}
    print(f"\nИтог: {fc.get('recommended_solution', '—')}")
    print()
    print("-" * 60)
    print("Полный JSON:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    if not settings.openai_api_key:
        print("Предупреждение: OPENAI_API_KEY не задан в .env — /solve может вернуть ошибку.")

    check_health()
    result = test_solve_endpoint()
    print_result(result)
    print()
    print("Пайплайн проверен успешно.")


if __name__ == "__main__":
    main()
