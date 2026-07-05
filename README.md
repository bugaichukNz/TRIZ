# TRIZ AI-ассистент

Репозиторий проекта экспертного TRIZ-анализа с помощью LLM: интервью с задачедателем, построение ПСА и функциональных противоречий, генерация и ранжирование решений, отчёты.

## Структура

| Папка | Назначение |
|-------|------------|
| [`triz-assistant/`](triz-assistant/) | Приложение: backend (FastAPI) и клиенты — основной [`frontend-react/`](triz-assistant/frontend-react/) (Vite + React), legacy [`frontend/`](triz-assistant/frontend/) (Streamlit) |
| [`ai-office/`](ai-office/) | Роли агентов для Cursor (team-lead, programmer, tester и др.) |
| [`docs/`](docs/) | Методическая документация; см. [docs/orchestration.md](docs/orchestration.md) |
| `m/` | Архив материалов; требует разбора и интеграции |

## Запуск

Инструкции по установке, настройке `.env` и запуску backend и frontend — в [triz-assistant/README.md](triz-assistant/README.md).
