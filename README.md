# Personal AI Assistant Bot

A multi-agent Telegram bot that automates three daily workflows: LinkedIn post generation, Gmail inbox management, and expense tracking. Built as a portfolio project to demonstrate production-grade agent architecture with LangGraph, Claude API, and per-user data isolation.

## Features

| Feature | How it works |
|---|---|
| **LinkedIn Posts** | Picks trending news via Google News RSS → LLM selects the most viral article → generates a ready-to-publish post |
| **Email Management** | Connects to Gmail via IMAP → summarises unread emails → drafts replies → sends via SMTP |
| **Expense Tracking** | Parses free-text input ("coffee 15 AED") → LLM extracts amount/category/description → stores in SQLite → monthly summary on demand |

## Architecture

```
Telegram
   │
   ▼
┌─────────────────────────────────────────────┐
│  bot/main.py  (aiogram Dispatcher)          │
│                                             │
│  ┌─────────────┐  ┌──────────┐  ┌────────┐ │
│  │ onboarding  │  │ linkedin │  │ email  │ │
│  │   handler   │  │ handler  │  │handler │ │
│  └─────────────┘  └────┬─────┘  └───┬────┘ │
│                        │            │      │
│              ┌─────────┘            │      │
│              ▼                      ▼      │
│  ┌──────────────────┐  ┌────────────────┐  │
│  │ content_creator  │  │  email_agent   │  │
│  │  (LangGraph)     │  │  (IMAP/SMTP)   │  │
│  │                  │  └────────────────┘  │
│  │ TrendWatcher     │                      │
│  │ graph:           │  ┌────────────────┐  │
│  │  load_user       │  │ expense_agent  │  │
│  │  expand_query    │  │  (LLM+regex)   │  │
│  │  search_news     │  └───────┬────────┘  │
│  │  deduplicate     │          │           │
│  │  filter_shown    │          │           │
│  │  read_articles   │          │           │
│  └────────┬─────────┘          │           │
│           │                    │           │
└───────────┼────────────────────┼───────────┘
            │                    │
            ▼                    ▼
┌───────────────────────────────────────────┐
│             agents/llm.py                 │
│   Claude Haiku (primary) → Ollama (fallback) │
└───────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│           SQLite  (personal_ai.db)        │
│  users · shown_news · expenses            │
└───────────────────────────────────────────┘
```

### Key design decisions

**LangGraph for the news pipeline** — the TrendWatcher flow has 6 sequential steps with state passing between them (load user → expand queries → fetch RSS → deduplicate → filter seen → fetch full text). LangGraph makes each step testable in isolation and the graph inspectable without changing application code.

**Claude primary / Ollama fallback** — `call_llm()` in `agents/llm.py` tries Claude Haiku first; if the API is unavailable it falls back to a local Ollama model. This keeps the bot functional during API outages and makes local development free.

**Per-user data isolation** — every DB query is scoped by `user_id`. Email credentials (Gmail address + App Password) are stored encrypted per row, never in `.env`. `shown_news` prevents duplicate articles across sessions per user.

**FSM onboarding gate** — on first `/start` aiogram's FSM walks the user through interests → Gmail → App Password before showing any feature. Subsequent `/start` calls skip directly to the main menu.

**Regex fallback on LLM parsing** — expense extraction tries to parse Claude's JSON response; if the model returns garbage, `_regex_fallback()` extracts the number and matches category keywords. The bot never hard-crashes on a bad LLM response.

## Project structure

```
personal_ai/
├── agents/
│   ├── llm.py              # Claude + Ollama wrapper, Google News URL builder
│   ├── trendwatcher.py     # LangGraph pipeline: RSS → filtered articles with text
│   ├── content_creator.py  # Orchestrates trendwatcher → selector → post writer
│   ├── expense_agent.py    # LLM extraction + regex fallback, monthly summary
│   ├── email_agent.py      # Gmail IMAP/SMTP: fetch, analyse, send
│   └── manager.py          # Free-chat fallback handler
├── bot/
│   ├── main.py             # Entry point: registers routers, starts polling
│   ├── keyboards.py        # All reply/inline keyboards and callback constants
│   └── handlers/
│       ├── onboarding.py   # /start FSM: interests → gmail → app password
│       ├── linkedin.py     # LinkedIn post generation flow
│       ├── email.py        # Email inbox flow
│       └── expense.py      # Expense recording + stats
├── database/
│   └── db.py               # SQLite schema, migrations, all DB functions
├── tests/
│   ├── conftest.py         # test_db fixture (isolated temp SQLite)
│   ├── test_db.py          # users, shown_news, expenses DB layer
│   └── test_expense_agent.py # extraction logic, fallback, DB integration
├── .env.example
└── requirements.txt
```

## Setup

**Requirements:** Python 3.12+, a Telegram bot token, an Anthropic API key. Ollama with `llama3.1` is optional (used as fallback).

```bash
git clone https://github.com/StepanovArt/personal-ai-assistant-bot.git
cd personal-ai-assistant-bot

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in TELEGRAM_BOT_TOKEN and ANTHROPIC_API_KEY

python -m bot.main
```

On first run, the bot creates `personal_ai.db` automatically. Send `/start` to the bot to complete onboarding.

## Environment variables

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) |

Gmail credentials are collected once via the onboarding flow and stored per-user in the database — they are not needed in `.env`.

## Running tests

```bash
pytest tests/ -v
pytest tests/ --cov=agents.expense_agent --cov=database.db --cov-report=term-missing
```

Current coverage: **75%** on `expense_agent` + `database.db` (26 tests).

## Trade-offs and what I'd do differently

**What I'd change with more time:**

- **Async DB layer** — `sqlite3` is synchronous; every DB call inside an async handler blocks the event loop. I'd replace it with `aiosqlite` or move all blocking calls inside `asyncio.to_thread()` (currently only LLM calls are wrapped this way).

- **Secrets management** — Gmail App Passwords are stored in plaintext in SQLite. For a real product I'd encrypt them at rest using a key derived from an environment secret (e.g. `cryptography.fernet`).

- **Structured logging with correlation IDs** — the current setup uses `logging.basicConfig`. In production I'd switch to `structlog` and attach a `request_id` per Telegram update so all log lines for one user interaction can be traced together.

- **LLM response validation** — prompts ask for JSON but the model occasionally wraps it in markdown fences or adds explanation text. The current fix is `re.sub(r"```(?:json)?|```", ...)`. A more robust approach is tool use / structured output via the Anthropic API, which guarantees valid JSON schema.

- **Test coverage for bot handlers** — aiogram handlers are async and depend on Telegram types. I skipped them to stay at 60-70% target coverage; adding them would require mocking `Message`, `CallbackQuery`, and FSM context, which is straightforward with `pytest-asyncio` and `unittest.mock`.

- **Webhook instead of polling** — long polling works fine for development but doesn't scale. In production I'd deploy with a webhook behind nginx and run the bot as a systemd service or Docker container.
