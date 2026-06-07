# Action Plan: Personal AI Bot — Варюха

## Текущее состояние проекта

```
personal_ai/
├── agents/
│   ├── llm.py             ✅ Ollama (llama3.1) + Google News helpers
│   ├── trendwatcher.py    ⚠️  LangGraph pipeline (баг: detect не импортирован)
│   ├── content_creator.py ✅  LinkedIn пост из трендов
│   ├── email_agent.py     ✅  Gmail IMAP/SMTP (читать, анализировать, отвечать)
│   ├── manager.py         ✅  Общий чат-агент через Ollama
│   └── main.py            🧪  Тестовый запуск trendwatcher
├── bot/
│   ├── main.py            ⚠️  Все хендлеры (4 кнопки без обработчиков)
│   ├── keyboards.py       ✅  Клавиатуры
│   └── handlers.py        ❌  Пустой файл
├── api/main.py            ❌  Ссылается на несуществующее поле summaries
├── database/db.py         ✅  SQLite: users + shown_news
└── requirements.txt       ⚠️  Устарел (нет aiogram, anthropic и др.)
```

---
## Фаза 0 — понимание сюжета бота и кнопки
В боте я добавил кнопки «с запасом» — нужно привести 
их в порядок под РОВНО три сценария (LinkedIn-пост, проверка почты, запись трат).

Задача — сверить и навести порядок, НЕ ломая рабочие потоки:

1. Сначала проведи инвентаризацию: найди все клавиатуры/кнопки в коде 
   (reply и inline), выпиши список «текст кнопки → callback_data → что делает». 
   Покажи мне его перед изменениями.

2. ОСТАВИТЬ ровно этот набор (остальные кнопки — удалить как неиспользуемые):

   Главное меню:
   - Пост в LinkedIn   → menu:linkedin
   - Проверка почты    → menu:email
   - Записать трату     → menu:expense

   LinkedIn: li:like (Нравится), li:redo (Переделать)
   Почта:    mail:period:today|yesterday|7d|30d,
             mail:pick:<n> (динамически по числу писем),
             mail:reply:yes|no, mail:send, mail:edit,
             mail:send_final, mail:cancel
   Траты:    кнопок внутри нет

3. УДАЛИТЬ: кнопку трендвотчера и любые кнопки/хендлеры, не входящие 
   в набор выше. Если кнопка завязана на рабочую логику — спроси меня, 
   прежде чем удалять.

4. ДОБАВИТЬ недостающие кнопки из набора и привязать к существующим агентам.

5. Свободный ввод обернуть в состояния (FSM/ConversationHandler под мою 
   библиотеку): li_waiting_topic, mail_waiting_reply, exp_waiting_text. 
   Сообщение типа «банка колы три дирхама» должно попадать ИМЕННО 
   в exp_waiting_text, а не в общий обработчик.

6. callback_data вынеси в константы/enum, чтобы не было строк-магии.

Отчитайся списком: что оставил, что удалил, что добавил.

## ~~Фаза 1 — Исправить критические баги~~ ✅ DONE

### ✅ 1.1 `trendwatcher.py` — `detect` не определён
- `detect(query)` → `langdetect.detect(query)`

### ✅ 1.2 `bot/main.py` — неверный ключ темы письма
- `data.get("Subject", ...)` → `current_email.get("Subject", "No Subject")`

### ✅ 1.3 `api/main.py` — несуществующее поле `summaries`
- Модель переименована: `SummartItem` → `ArticleItem`, поле `summaries` → `articles`, маппинг на `articles_with_text` из графа

---

## ~~Фаза 2 — Реализовать недостающие кнопки~~ ✅ DONE (в рамках Фазы 0)

Все нерабочие кнопки удалены. Добавлены: `Записать трату` (FSM), `li:like`, `li:redo`.

---

## ~~Фаза 3 — Рефакторинг структуры бота~~ ✅ DONE

- `bot/handlers/email.py` — email FSM + хендлеры
- `bot/handlers/linkedin.py` — LinkedIn FSM + хендлеры
- `bot/handlers/expense.py` — Expense FSM + хендлеры
- `bot/main.py` — только точка входа: регистрирует роутеры, catch-all последним

---

## ~~Фаза 4 — Замена Ollama → Claude API~~ ✅ DONE

Текущий стек: локальная `llama3.1` через `ollama`.
Проблемы: медленно, нужен локально запущенный сервер.

- `call_llm()` — Claude primary (`claude-haiku-4-5`), Ollama fallback
- Все агенты переведены на `call_llm()`, `call_ollama()` сохранён как fallback
- `ANTHROPIC_API_KEY` добавлен в `.env`

---

## ~~Фаза 5 — Новые функции~~ ✅ DONE (отменена как ненужная)

История постов не нужна — `shown_news` уже предотвращает повторы новостей,
а LLM генерирует посты на основе свежих статей.

---

## Фаза 6 — Онбординг и безопасность

### 6.1 БД: расширить таблицу `users`
Добавить колонки (через `ALTER TABLE IF NOT EXISTS` — не ломает существующих записей):
```
gmail_user         TEXT   -- email пользователя
gmail_app_password TEXT   -- Google App Password
is_onboarded       INTEGER DEFAULT 0  -- 0 / 1
```
Новые функции в `db.py`:
- `update_user_email_credentials(telegram_id, gmail_user, gmail_password)`
- `is_user_onboarded(telegram_id) -> bool`

### 6.2 Онбординг (`bot/handlers/onboarding.py`)
FSM при первом `/start`:
```
/start → [новый юзер?]
  да → "Привет! Введи интересы через запятую (напр. AI, стартапы)"
     → сохранить interests в БД
     → "Теперь введи свой Gmail адрес"
     → сохранить gmail_user
     → "Введи Google App Password (16 символов без пробелов)"
     → сохранить gmail_app_password, is_onboarded=1
     → показать main_menu
  нет → сразу main_menu
```

### 6.3 Email агент: кредентиалы из БД, не из .env
- `fetch_unread_emails(period, gmail_user, gmail_password)` — принимать как параметры
- То же для `send_email`, `fetch_email_body`
- `bot/handlers/email.py` — загружать кредентиалы из БД перед вызовом агента
- Если не заполнены → «Сначала пройди настройку /start»

### 6.4 Изоляция данных (проверка)
- `shown_news` — уже фильтруется по `user_id` ✅
- `expenses` (фаза 7) — будет фильтроваться по `user_id`
- LinkedIn интересы — берутся из `users.interests` по `telegram_id` ✅
- Нигде не должно быть запросов без `WHERE user_id = ?`

---

## Фаза 7 — Лёгкий фундамент (из PLAN.md Фаза 1)

### 7.1 Заменить `print` на `logging`
- Во всех агентах и хендлерах: `print(...)` → `logging.getLogger(__name__).info/warning/error(...)`
- Настроить корневой логгер в `bot/main.py`

### 7.2 Добавить `.env.example`
- Создать `.env.example` с ключами без значений: `TELEGRAM_BOT_TOKEN=`, `ANTHROPIC_API_KEY=`, `GMAIL_USER=`, `GMAIL_APP_PASSWORD=`

### 7.3 Тип-хинты и докстринги на публичных функциях
- Пройтись по `agents/` и `database/db.py` — добавить там где нет

### 7.4 Manager → тонкий диспетчер
- `agents/manager.py` — убрать LLM из роутинга (роутинг уже идёт через кнопки)
- Оставить `call_llm` только для режима свободного чата (fallback)
- Статус: **частично сделано** — кнопки уже роутят напрямую, но проверить что менеджер не тянет лишнего

---

## Фаза 7 — Бюджет-агент (из PLAN.md Фаза 2)

Главная новая фича. Пользователь нажимает «Записать трату» → пишет текстом → агент извлекает структуру и сохраняет.

### 7.1 БД: таблица `expenses`
```
id          INTEGER PK
user_id     INTEGER (telegram_id)
amount      REAL
category    TEXT
description TEXT
created_at  TEXT
```
- Добавить в `database/db.py`: `init_db`, репозиторий `ExpenseRepo` (изолированный слой, агент не лезет в SQL напрямую)

### 7.2 Агент-экстрактор (`agents/expense_agent.py`)
- Принимает текст («потратил 500 на такси»)
- Вызывает LLM с промптом: вернуть строго JSON `{amount, category, description}`
- Безопасный парсинг JSON + fallback на regex при ошибке LLM
- Канонические категории + маппинг синонимов (продукты→еда и т.п.)

### 7.3 Намерения агента
- **Добавить расход** → запись в БД → подтверждение пользователю
- **Аналитика** → «сколько за месяц», «топ категорий» → агрегирующий SQL → текстовый ответ

### 7.4 Интеграция в бот
- `bot/handlers/expense.py` — подключить `expense_agent` вместо TODO-заглушки
- Кнопка «Записать трату» уже есть и ведёт в `ExpenseStates.waiting_text`

### 7.5 Тесты (pytest)
- Парсинг текста → структура (включая кривые случаи)
- Запись и чтение из in-memory SQLite
- Агрегации (сумма за период, по категории)

---

## Фаза 8 — Полировка под портфолио (из PLAN.md Фаза 3)

### 8.1 README.md
- Что это, зачем, как запустить
- Переменные окружения (ссылка на `.env.example`)
- ASCII/Mermaid-схема архитектуры: `Telegram → Router(bot) → agents → SQLite`
- Раздел «Trade-offs и что бы сделал дальше» (важно для интервью)

### 8.2 Обработка ошибок
- На уровне роутера и бюджет-агента: ловить исключения, логировать, отвечать пользователю понятно

### 8.3 Опционально: `/report` с графиком
- matplotlib: расходы по категориям за период → картинка в чат

---

## Фаза 9 — Код-ревью (из PLAN.md Фаза 4)

- Создать `.claude/agents/code-reviewer.md` (субагент-ревьюер, описание в PLAN.md Приложение A)
- Запустить ревью бюджет-агента после реализации
- Закрыть находки critical/high

---

---

## Тесты (сквозное требование, цель — 60-70% coverage)

Тесты пишутся на pytest + `pytest-cov` для замера покрытия.

```
tests/
├── test_expense_agent.py   # парсинг текста → JSON, кривые случаи
├── test_expense_db.py      # запись/чтение/агрегации на in-memory SQLite
├── test_db.py              # users, shown_news, filter_unseen_urls
├── test_llm.py             # call_llm fallback: Claude упал → Ollama отработал
└── test_trendwatcher.py    # deduplicate_node, normalize_title, build_google_news_url
```

**Приоритет 1 — бюджет-агент (блокирует фазу 7):**
- Парсинг: «500 на такси» → `{amount: 500, category: "транспорт", description: "такси"}`
- Кривые случаи: нет суммы, незнакомая категория, LLM вернул не JSON
- Запись/чтение БД (in-memory SQLite, не трогает `personal_ai.db`)
- Агрегации: сумма за период, топ категорий

**Приоритет 2 — остальной код (до 60-70% total):**
- `database/db.py`: get_or_create_user, filter_unseen_urls, mark_news_shown
- `agents/llm.py`: call_llm fallback (mock Claude → exception → Ollama вызван)
- `agents/trendwatcher.py`: deduplicate_node, normalize_title, build_google_news_url

Запуск: `pytest --cov=. --cov-report=term-missing`

---

## Порядок выполнения

```
Фаза 6 (онбординг)   → БД, FSM /start, email из БД, изоляция данных
Фаза 7 (фундамент)   → logging, .env.example, тип-хинты
Фаза 8 (расходы)     → главная фича + тесты приоритет 1
Тесты приоритет 2    → параллельно с фазой 8 или сразу после
Фаза 9 (портфолио)   → README + polish
Фаза 10 (ревью)      → после фазы 8
```

