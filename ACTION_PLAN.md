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

## Фаза 4 — Замена Ollama → Claude API

Текущий стек: локальная `llama3.1` через `ollama`.
Проблемы: медленно, нужен локально запущенный сервер.

**Что менять:**
- `agents/llm.py` — функция `call_ollama()` → `call_claude()`
- Модель: `claude-haiku-4-5` (быстро + дёшево) для новостей, `claude-sonnet-4-6` для постов
- Добавить prompt caching для системных промптов
- Обновить `requirements.txt`: добавить `anthropic`

**Файлы которые используют `call_ollama`:**
- `agents/manager.py`
- `agents/trendwatcher.py`
- `agents/content_creator.py`
- `agents/email_agent.py`

---

## Фаза 5 — Новые функции

### 5.1 Автоматический дайджест
- Использовать `APScheduler` (уже в requirements, но не подключён)
- Ежедневно в заданное время запускать `create_post_from_trends` для каждого юзера
- Результат отправлять через бота

### 5.2 История постов
- Добавить таблицу `generated_posts` в БД
- Кнопка "📜 История" → показать последние 5 постов

---

## Порядок выполнения

```
Фаза 1 (баги)      → прямо сейчас
Фаза 2 (кнопки)    → после фазы 1
Фаза 3 (структура) → после фазы 2
Фаза 4 (Claude)    → параллельно с фазой 3
Фаза 5 (новое)     → после фаз 3-4
```
