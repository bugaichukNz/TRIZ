# TRIZ AI-Ассистент

Экспертный TRIZ-анализ через LLM: противоречия, инструменты, ранжированные решения, отчёты HTML/DOCX.

**Стек:** Python, FastAPI, LangChain, OpenAI API, Streamlit.

---

## Требования

- Python 3.11+
- Ключ OpenAI (или совместимый API через `OPENAI_BASE_URL`)

---

## 1. Установка

```bash
cd triz-assistant
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Для DOCX-отчётов: `pip install python-docx matplotlib`

---

## 2. Настройка `.env`

```bash
cp .env.example .env
```

| Переменная | Описание |
|------------|----------|
| `OPENAI_API_KEY` | API-ключ |
| `OPENAI_BASE_URL` | Базовый URL API (по умолчанию OpenAI) |
| `OPENAI_PROXY_URL` | HTTP-прокси, например `http://user:pass@host:port` |
| `LLM_MODEL` | Модель, например `gpt-4o-mini` |
| `BACKEND_URL` | URL backend для Streamlit |

---

## 3. Запуск backend

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

- API: http://localhost:8000  
- Swagger: http://localhost:8000/docs  

---

## 4. Запуск frontend

```bash
streamlit run frontend/app.py
```

---

## Проверка

```bash
python scripts/test_pipeline.py
```

Нужны: запущенный backend и `OPENAI_API_KEY` в `.env`.

---

## API

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/health` | Статус сервера и LLM |
| `POST` | `/solve` | `{"problem": "..."}` — экспертный TRIZ-отчёт |

---

## Устранение неполадок

- **Backend недоступен** — запустите `uvicorn` из папки `triz-assistant`.
- **502 от `/solve`** — проверьте ключ, `OPENAI_BASE_URL`, прокси и лимиты API.
- **degraded в `/health`** — не задан `OPENAI_API_KEY`.
