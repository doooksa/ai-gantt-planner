# CLAUDE.md — AI Gantt Planner (тестовое задание)

## Что это
Веб-приложение: интерактивная диаграмма Гантта + чат с LLM-агентом, который редактирует план проекта на естественном языке. Импорт/экспорт Excel. Тестовое задание на Full-stack разработчика AI-native продукта.

## Главный принцип (не нарушать)
**LLM не является источником истины и не пишет в базу напрямую.**
LLM только переводит естественный язык в структурированные операции через MCP tools. Бэкенд валидирует каждую операцию, применяет её и детерминированно пересчитывает расписание. Даты задач — всегда derived (вычисляются), никогда не хранятся как source of truth.

## Стек (зафиксирован, не менять)
- **Frontend:** React + Vite + TypeScript, Zustand, `@svar-ui/react-gantt` (MIT)
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLite (через sqlite3 или SQLModel — проще лучше), openpyxl
- **MCP:** официальный `mcp` python-sdk, streamable HTTP transport, сервер монтируется в тот же FastAPI-процесс
- **LLM:** OpenRouter через `openai` SDK (`base_url="https://openrouter.ai/api/v1"`), модель из env `LLM_MODEL` (default: `anthropic/claude-sonnet-4.5`)
- **Деплой:** frontend → Vercel, backend → Render; локально — `docker-compose up`

## Структура репозитория
```
ai-gantt-planner/
  apps/
    frontend/
      src/
        components/   # GanttBoard, ChatPanel, TaskModal, Toolbar (upload/export/reset/undo)
        api/client.ts
        store/plan.ts
        types/plan.ts
    backend/
      app/
        main.py
        api/            # routes_plan.py, routes_chat.py, routes_excel.py
        domain/         # models.py, scheduler.py, validators.py, patches.py
        mcp_server/     # server.py, tools.py
        llm/            # agent.py (агентский цикл), mcp_openai_bridge.py
        storage/        # db.py, seed.py, snapshots.py (для undo)
      tests/
  examples/sample_plan.xlsx
  docs/
    ROADMAP_TO_PRODUCTION.md
    AI_USAGE.md          # вести ПО ХОДУ разработки
    demo.gif
  docker-compose.yml
  README.md
```

## Модель данных
```python
class Task(BaseModel):
    id: str                      # slug или uuid
    name: str
    description: str | None = None
    assignee: str | None = None
    duration_days: int           # >= 1
    predecessor_ids: list[str] = []
    # start/end НЕ хранятся — вычисляются scheduler'ом
```
План хранится с полем `version: int` (инкремент на каждую мутацию) и снапшотами для undo.

## Scheduler (детерминированный, без LLM)
1. Проверить, что все predecessor_ids существуют.
2. Проверить циклы (topological sort; цикл → ValidationError с перечислением задач цикла).
3. Forward pass: задачи без предшественников → `start = project_start` (default: сегодня); иначе `start = max(end всех предшественников) + 1 день`; `end = start + duration_days - 1`.
4. Календарные дни (рабочие дни — сознательно в Roadmap).
5. Пересчёт вызывается автоматически после каждой мутации плана.

## Формат Excel
Колонки (регистронезависимо, с нормализацией пробелов): `задача, описание, исполнитель, длительность, предшественники`.
- Предшественники — имена задач через запятую; резолвить в id, несуществующие → понятная ошибка пользователю.
- Длительность — int; невалидное значение → ошибка с номером строки.
- Экспорт: те же 5 колонок + вычисленные `дата начала, дата конца`.
- Читать только первый лист. openpyxl, `read_only=True` на импорте.

## MCP tools (ровно эти, не плодить)
```
get_plan() -> Plan                       # текущий план с вычисленными датами
validate_patch(patch: Patch) -> Diff     # dry-run: diff + ошибки, БЕЗ применения
apply_patch(patch: Patch) -> Diff        # атомарно применить, пересчитать, вернуть diff
undo_last() -> Plan                      # откат к предыдущему снапшоту
```
`Patch` — массив операций с селекторами:
```python
class Op(BaseModel):
    type: Literal["add_task","update_task","delete_task","shift_task",
                  "reassign","set_dependencies"]
    selector: Selector | None = None     # by_id | by_name | by_assignee
    payload: dict
```
Правила:
- `apply_patch` атомарен: одна операция невалидна → откат всего патча, ошибка агенту.
- Массовые правки («все задачи Ивана → Марии») = один патч с селектором `by_assignee`, НЕ N вызовов.
- После apply бэк бампает `version` и бродкастит в WebSocket `{version, diff}`.

## Агентский цикл (llm/agent.py)
1. MCP-клиент подключается к своему MCP-серверу, `list_tools()`.
2. Конвертация MCP tool schemas → OpenAI tools format (mcp_openai_bridge.py).
3. Цикл: user message → `chat.completions` с tools → tool_calls → `session.call_tool()` → результаты обратно → до финального текстового ответа. Лимит: 10 итераций.
4. System prompt агента: «Ты редактор плана проекта. Перед правками всегда читай план через get_plan. Для проверки используй validate_patch, затем apply_patch. Массовые операции — одним патчем. Отвечай кратко на русском, в конце перечисли применённые изменения.»
5. `/api/chat` стримит ответ (SSE). В ответе фронту: текст + структурированный diff (before/after по задачам) для блока «Applied changes».

## API
```
GET  /api/plan
POST /api/upload-excel        # multipart, лимит 2 МБ
GET  /api/export-excel
POST /api/chat                # SSE stream
POST /api/undo
POST /api/reset-demo          # вернуть seed
GET  /api/health
WS   /ws                      # {version, diff} после каждой мутации
```
CORS: разрешить origin фронта из env `FRONTEND_ORIGIN`.

## Seed-данные (и examples/sample_plan.xlsx — тот же план)
| задача | описание | исполнитель | длительность | предшественники |
|---|---|---|---|---|
| Research | Сбор требований | Anna | 2 | |
| Design | Макеты и UX | Anna | 3 | Research |
| Backend API | FastAPI endpoints | Ivan | 4 | Design |
| Frontend | React Gantt UI | Maria | 4 | Design |
| AI Agent | MCP + LLM chat | Ivan | 3 | Backend API |
| Excel Export | Экспорт плана | Maria | 2 | Backend API |
| Testing | E2E сценарий | Oleg | 2 | Frontend, AI Agent, Excel Export |
| Demo | Запись gif | Oleg | 1 | Testing |

## Фазы разработки (работать строго по фазам с гейтами)

### Фаза 1 — домен без UI
models, scheduler, validators, Excel import/export, seed, storage.
**Тесты обязательны:** цепочка зависимостей, ромб (diamond), цикл → ошибка, несуществующий предшественник, кириллические заголовки с лишними пробелами, пустые предшественники, невалидная длительность.
**Гейт: pytest зелёный.**

### Фаза 2 — MCP + агент
mcp_server, bridge, agent, /api/chat, WebSocket, undo/snapshots.
**Гейт:** 10 эталонных команд (см. ниже) проходят 5/5 стабильно, скрипт `tests/test_agent_scenarios.py` (можно с реальным API, дешёвой моделью).
Эталонные команды:
1. Перенеси задачу "Frontend" на 3 дня позже.
2. Все задачи Ivan переназначь на Maria.
3. Добавь задачу "Security review" на 2 дня после Backend API, исполнитель Anna.
4. Сделай Demo зависимой ещё и от Excel Export.
5. Увеличь длительность Design до 5 дней.
6. Удали задачу Testing. (агент должен предупредить о зависимых)
7. Убери зависимость Frontend от Design.
8. Покажи, что изменилось за сессию.
9. Кто самый загруженный исполнитель?
10. Отмени последнее изменение.

### Фаза 3 — фронт + доставка
GanttBoard (SVAR), ChatPanel (стрим + блок Applied changes + Undo), TaskModal (все поля + предшественники + зависимые задачи), Toolbar. Деплой Vercel+Render, docker-compose, gif, README, ROADMAP_TO_PRODUCTION.md.
**Гейт: демо-сценарий проходит на задеплоенном приложении.**

## Конвенции
- Коммиты: conventional commits, по одному логическому изменению.
- Никаких секретов в коде: `.env.example` с `OPENROUTER_API_KEY=`, `LLM_MODEL=`, `FRONTEND_ORIGIN=`.
- Ошибки пользователю — по-русски и понятно («Цикл зависимостей: Design → Frontend → Design»), в логи — технические детали.
- Не добавлять: авторизацию, drag-and-drop редактирование полей, генерацию плана целиком LLM'ом, multi-project.

## docs/AI_USAGE.md — вести по ходу!
После каждой сессии дописывать: что делегировано Claude Code, что модель предложила неверно и как исправлено, что сделано руками. Из этого файла собирается обязательный раздел README «AI assistants usage».

## README (структура)
1. What is this + demo gif
2. Architecture (схема: React → FastAPI → agent loop → MCP client → MCP server → domain/scheduler)
3. How MCP is used (почему tools-слой, а не прямой доступ LLM к данным)
4. How the agent works (цикл, validate → apply, atomic patches)
5. Excel format
6. Local setup (docker-compose + вручную)
7. Deployment
8. AI assistants usage
9. Known limitations
10. Link to Roadmap to production
