# Процесс: основная цепочка

Ниже — **единый канон** потоков: для **реализации и стандартной маршрутизируемой аналитики (Quant)** пользователь входит через **Team Lead**. **Infosec (Ися)** — **двойной вход** (через Тимлида или прямой вызов агента); детали — `ai-office/global/handoff-contracts.mdc` §6.

## Канон (общий)

```text
User → Team Lead → внутренние роли → Team Lead → User
```

- **Team Lead** — основная точка контакта: постановка, merge/release, упаковка итогов Quant и формальных security-выводов.
- **Внутренние роли** — исполнение (код, QA, анализ, security review); **merge/release** — у Тимлида; **Ися** может отвечать пользователю при **прямом вызове** (см. контракты).

## Реализация (delivery): код, конфиг, артефакты в репозитории

**Цепочка:**

```text
User → Team Lead → Programmer → Tester → Team Lead → User
```

**По-русски (имена ролей):**

```
Пользователь → Туся (постановка, EPIC → Story → Task, архитектура)
                    ↓
               Пуся (реализация)
                    ↓
               Труся (QA по чек-листу)
                    ↓
          Всё ОК → Туся (финальное ревью)
                    ↓
               Пользователь (итог)
```

### Один чат Cursor — не упрощение ролей

Пользователь может вести **один чат** с Team Lead (удобно для постановки). Это **не** отдельный «режим» и **не** разрешение тимлиду делать работу программиста или тестировщика. Реализация и QA **всегда** остаются за **Пусей** и **Трусей** (отдельные вызовы ролей, отдельные чаты или явные handoff по шаблонам — как договоритесь). Тимлид только **назначает** и **принимает итог после** QA.

### Правила (delivery)

- **Туся** не принимает «готово» от Пуси напрямую — только после подписи Труси. Тимлид **не** заменяет Пусю или Трусю при реализации и QA.
- **Пуся** передаёт работу **Трусе** с использованием шаблона `ai-office/templates/programmer-handoff-template.md`.
- **Труся** передаёт **Тусе** только после `ai-office/checklists/qa-checklist.md`, отчёт — `ai-office/templates/tester-report-template.md`.

## Роли

| Роль | Имя | Файл роли |
|------|-----|-----------|
| Team Lead | Туся | `ai-office/agents/team-lead/role.mdc` |
| Programmer | Пуся | `ai-office/agents/programmer/role.mdc` |
| Tester | Труся | `ai-office/agents/tester/role.mdc` |
| Quant | Кася | `ai-office/agents/quant/role.mdc` |
| Infosec | Ися | `ai-office/agents/infosec/role.mdc` |

## Вход задач

- Постановка от пользователя — **только Тусе** (`ai-office/global/global-standards.mdc`, `ai-office/global/handoff-contracts.mdc`).
- Шаблон постановки: `ai-office/task-intake.md`.

## Анализ Quant (не user-facing)

**Цепочка:**

```text
User → Team Lead → Quant → Team Lead → User
```

**По-русски:** пользователь передаёт запрос **тимлиду**; тимлид **назначает Касе** анализ и **возвращает пользователю итог** сам (не Quant).

- Если по итогам анализа нужна **реализация в коде** — дальше идёт цепочка **delivery:** `User → Team Lead → Programmer → Tester → Team Lead → User`.

## Security review — Infosec (Ися)

**Формальный путь:**

```text
User → Team Lead → Infosec → Team Lead → User
```

**Прямой вызов** (разрешён контрактами): пользователь явно работает с ролью **Ися** — технические выводы по безопасности в этом контексте; **официальные** merge/release — всё равно у **Туси**, см. `handoff-contracts.mdc` §6.

- Если нужны **изменения в репозитории** — Ися уведомляет **только Team Lead** → цепочка **Programmer → Tester → Team Lead**.

Шаблон выдачи: `ai-office/templates/infosec-findings-template.md`.

## Доработки

- Если QA не прошёл — см. `ai-office/process/process-rework-loop.md`.
