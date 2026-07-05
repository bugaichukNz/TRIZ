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

**Обязательно** задайте `JWT_SECRET` — без него backend не запустится. Сгенерировать:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

| Переменная | Описание |
|------------|----------|
| `OPENAI_API_KEY` | API-ключ |
| `OPENAI_BASE_URL` | Базовый URL API (по умолчанию OpenAI) |
| `OPENAI_PROXY_URL` | HTTP-прокси, например `http://user:pass@host:port` |
| `LLM_MODEL` | Модель, например `gpt-4o-mini` |
| `BACKEND_URL` | URL backend для Streamlit |
| `DATABASE_URL` | SQLite для истории (`sqlite:///data/sessions/triz.db`) |
| `JWT_SECRET` | **Обязательно.** Секрет для подписи JWT. Сгенерировать: `python -c "import secrets; print(secrets.token_hex(32))"`. Без него backend не запустится. |
| `SEED_DEFAULT_USER` | `true` — создать пользователя `user` при первом запуске (только для dev). По умолчанию `false`. |
| `DEFAULT_USER_PASSWORD` | Пароль для сидируемого `user`. Если пусто при `SEED_DEFAULT_USER=true`, пароль генерируется и пишется в лог один раз. |
| `EFFECTS_RAG_ENABLED` | Указатель физэффектов при генерации решений (`true` по умолчанию). `false` — если индекс не собран. |
| `EFFECTS_SCORE_THRESHOLD` | Порог cosine similarity для отбора эффектов (по умолчанию `0.40`). |

---

## Указатель физэффектов

При генерации решений пайплайн подбирает релевантные физические эффекты из корпуса `data/triz_corpus/effects.json` и передаёт top-6 в промпт (LLM использует их только если они органично разрешают противоречие). Включён по умолчанию (`EFFECTS_RAG_ENABLED=true`); без индекса подсказки пустые, `solve` работает как раньше.

**Сборка корпуса и индекса** (из каталога `triz-assistant`, нужен `OPENAI_API_KEY`):

```bash
python scripts/validate_effects_corpus.py
python scripts/build_effects_index.py
python scripts/calibrate_retriever.py
```

Первая команда проверяет `effects.json`; вторая строит `effects_index.npz`; третья — sanity-check recall@5 и порога (`EFFECTS_SCORE_THRESHOLD` в `.env`).

**A/B-сравнение** качества решений с effects-RAG off vs on:

```bash
python scripts/ab_effects_eval.py --judge
```

Эталонные брифы: `scripts/eval_cases/*.txt`, отчёт: `scripts/eval_out/summary.md`.

---

## 3. Запуск backend

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

- API: http://localhost:8000  
- Swagger: http://localhost:8000/docs  

---

## Фронтенды

### frontend-react (основной клиент)

Vite + React. Новые фичи разрабатываются только здесь.

```bash
cd frontend-react
cp .env.example .env
npm install
npm run dev
```

Переменные `VITE_*` — см. [`frontend-react/.env.example`](frontend-react/.env.example).

### frontend (Streamlit, legacy)

```bash
streamlit run frontend/app.py
```

Поддерживается для совместимости; для нового UI используйте `frontend-react`.

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
| `GET` | `/sessions` | История TRIZ-отчётов (`?limit=20`) |
| `POST` | `/sessions` | Добавить запись в историю |
| `DELETE` | `/sessions` | Очистить историю |
| `GET` | `/chat/sessions` | Список сохранённых диалогов |
| `POST` | `/chat/sessions` | Новый диалог |
| `GET` | `/chat/sessions/{id}` | Состояние диалога (все сообщения) |
| `POST` | `/chat/sessions/{id}/messages` | Сообщение в интервью |
| `POST` | `/chat/sessions/{id}/analyze` | TRIZ-анализ после интервью |

Все данные (диалоги, отчёты, активный диалог) хранятся только в SQLite (`data/sessions/triz.db`) и отображаются в левом меню Streamlit. При первом запуске данные из старого `history.json` импортируются в БД автоматически. Лимиты: `HISTORY_MAX_ENTRIES`, `CHAT_SESSIONS_MAX` в `.env`.

---

## Устранение неполадок

- **Backend недоступен** — запустите `uvicorn` из папки `triz-assistant`.
- **502 от `/solve`** — проверьте ключ, `OPENAI_BASE_URL`, прокси и лимиты API.
- **degraded в `/health`** — не задан `OPENAI_API_KEY`.
