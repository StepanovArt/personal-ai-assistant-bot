# Personal AI Assistant Bot

A multi-agent Telegram bot that automates three daily workflows: LinkedIn post generation, Gmail inbox management, and expense tracking. Built as a portfolio project to demonstrate production-grade agent architecture with LangGraph, Claude API, OAuth 2.0, and per-user data isolation.

## Features

| Feature | How it works |
|---|---|
| **LinkedIn Posts** | Picks trending news via Google News RSS → LLM selects the most relevant article → generates a ready-to-publish post |
| **Email Management** | Connects to Gmail via OAuth 2.0 → summarises unread emails → drafts replies → sends via Gmail API |
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
│  └──────┬──────┘  └────┬─────┘  └───┬────┘ │
│         │              │            │      │
│         ▼              ▼            ▼      │
│  ┌────────────┐  ┌──────────────┐  ┌─────┐ │
│  │gmail_oauth │  │content_      │  │email│ │
│  │(PKCE flow) │  │creator       │  │agent│ │
│  └────────────┘  │(LangGraph)   │  └──┬──┘ │
│                  │              │     │    │
│                  │ TrendWatcher │     │    │
│                  │ graph:       │  Gmail   │
│                  │  expand_query│  API     │
│                  │  search_news │          │
│                  │  deduplicate │  ┌──────┐│
│                  │  filter_shown│  │expense││
│                  │  read_article│  │agent  ││
│                  └──────┬───────┘  └──┬───┘│
└─────────────────────────┼─────────────┼────┘
                          │             │
                          ▼             ▼
              ┌───────────────────────────────┐
              │         agents/llm.py         │
              │  Claude Haiku → Ollama llama3 │
              └───────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────────────┐
              │      SQLite (personal_ai.db)  │
              │  users · shown_news · expenses│
              └───────────────────────────────┘
```

### Key design decisions

**Gmail OAuth 2.0 with PKCE** — instead of storing Gmail App Passwords, the bot uses a proper OAuth 2.0 authorization flow. The user clicks an auth URL, approves access in Google, and pastes the redirect URL back to the bot. The bot exchanges the code for a token (with PKCE code verifier) and stores it per-user in SQLite. Tokens are refreshed automatically on each Gmail API call.

**LangGraph for the news pipeline** — the TrendWatcher flow has 6 sequential steps with state passing between them (load user → expand queries → fetch RSS → deduplicate → filter seen → fetch full text). LangGraph makes each step testable in isolation and the graph inspectable without changing application code.

**Claude primary / Ollama fallback** — `call_llm()` in `agents/llm.py` tries Claude Haiku first; if the API is unavailable it falls back to a local Ollama model. This keeps the bot functional during API outages and makes local development free.

**Per-user data isolation** — every DB query is scoped by `user_id`. OAuth tokens are stored per row, never shared. `shown_news` prevents duplicate articles across sessions per user.

**FSM onboarding gate** — on first `/start` aiogram's FSM walks the user through Gmail OAuth before showing any feature. Subsequent `/start` calls skip directly to the main menu.

**Regex fallback on LLM parsing** — expense extraction tries to parse the LLM's JSON response; if the model returns garbage, `_regex_fallback()` extracts the number and matches category keywords. The bot never hard-crashes on a bad LLM response.

**Prompt injection defence** — email bodies are sanitised before being inserted into LLM prompts: `SUMMARY:` and `DRAFT_REPLY:` markers are escaped, and the body is wrapped in `<<<`/`>>>` delimiters with an explicit instruction to treat the content as data, not commands.

## Project structure

```
personal_ai/
├── agents/
│   ├── llm.py              # Claude + Ollama wrapper
│   ├── gmail_oauth.py      # OAuth 2.0 + PKCE: auth URL, code exchange, token refresh
│   ├── trendwatcher.py     # LangGraph pipeline: RSS → filtered articles with text
│   ├── content_creator.py  # Orchestrates trendwatcher → selector → post writer
│   ├── expense_agent.py    # LLM extraction + regex fallback, monthly summary
│   ├── email_agent.py      # Gmail API: fetch, analyse, send
│   └── manager.py          # Free-chat fallback handler
├── bot/
│   ├── main.py             # Entry point: registers routers, starts polling
│   ├── keyboards.py        # All reply/inline keyboards and callback constants
│   └── handlers/
│       ├── onboarding.py   # /start FSM: Gmail OAuth flow
│       ├── linkedin.py     # LinkedIn post generation flow
│       ├── email.py        # Email inbox flow (OAuth-based)
│       └── expense.py      # Expense recording + stats
├── database/
│   └── db.py               # SQLite schema, migrations, all DB functions
├── tests/
│   ├── conftest.py         # test_db fixture (isolated temp SQLite)
│   ├── test_db.py          # users, shown_news, expenses DB layer
│   └── test_expense_agent.py # extraction logic, fallback, DB integration
├── Dockerfile
├── .github/workflows/ci.yml
├── .env.example
└── requirements.txt
```

## Setup

**Requirements:** Python 3.12+, a Telegram bot token, an Anthropic API key, Google OAuth credentials. Ollama with `llama3.1` is optional (used as fallback).

```bash
git clone https://github.com/StepanovArt/personal-ai-assistant-bot.git
cd personal-ai-assistant-bot

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY,
# GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

python -m bot.main
```

On first run, the bot creates `personal_ai.db` automatically. Send `/start` to the bot to complete Gmail OAuth onboarding.

### Google OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID → **Desktop app**
3. Download the JSON and save it as `credentials.json` in the project root
4. Enable the **Gmail API** for your project
5. Add your Gmail address as a test user (while the app is in testing mode)

## Environment variables

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) |
| `GOOGLE_CLIENT_ID` | From Google Cloud Console OAuth credentials |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console OAuth credentials |

Gmail tokens are collected once via the in-bot OAuth flow and stored per-user in the database — they are never needed in `.env`.

## Running tests

```bash
pytest tests/ -v
pytest tests/ --cov=agents.expense_agent --cov=database.db --cov-report=term-missing
```

Current coverage: **75%** on `expense_agent` + `database.db` (28 tests).

## Trade-offs and what I'd do differently

- **Async DB layer** — `sqlite3` is synchronous; every DB call inside an async handler blocks the event loop. I'd replace it with `aiosqlite` or move all DB calls into `asyncio.to_thread()`.

- **OAuth token encryption** — tokens (including `refresh_token`) are stored as plaintext in SQLite. For a real product I'd encrypt them at rest with a key derived from an environment secret (`cryptography.fernet`).

- **Structured logging** — the current setup uses `logging.basicConfig`. In production I'd switch to `structlog` with a `request_id` per Telegram update for full traceability.

- **LLM structured output** — prompts ask for JSON but the model occasionally wraps it in markdown or adds text. The current fix strips fences with regex. A cleaner approach is Anthropic tool use / structured output, which guarantees a valid JSON schema.

- **Test coverage for handlers** — aiogram handlers depend on Telegram types and FSM context. Adding them requires mocking `Message`, `CallbackQuery`, and FSM state with `pytest-asyncio` — straightforward but skipped to hit the 60% CI gate quickly.

- **Webhook instead of polling** — long polling works for development but doesn't scale. In production I'd deploy with a webhook behind nginx as a Docker container or systemd service.
