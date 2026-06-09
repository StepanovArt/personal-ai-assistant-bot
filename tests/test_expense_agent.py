import json
import pytest

from agents.expense_agent import (
    extract_expense,
    _normalize_category,
    _detect_currency,
    _regex_fallback,
    save_expense,
)


# ── unit: category normalizer ──────────────────────────────────────────────────

def test_normalize_known_category():
    assert _normalize_category("food") == "food"


def test_normalize_synonym():
    assert _normalize_category("taxi") == "transport"
    assert _normalize_category("groceries") == "food"
    assert _normalize_category("pharmacy") == "health"


def test_normalize_unknown_falls_back_to_другое():
    assert _normalize_category("космос") == "other"


# ── unit: currency detection ───────────────────────────────────────────────────

def test_detect_dirham():
    assert _detect_currency("cola 3 dirhams") == "AED"


def test_detect_ruble():
    assert _detect_currency("taxi 200 rub") == "RUB"


def test_detect_default_aed():
    assert _detect_currency("что-то непонятное") == "AED"


# ── unit: regex fallback ───────────────────────────────────────────────────────

def test_regex_fallback_extracts_amount():
    result = _regex_fallback("taxi 50 dirhams")
    assert result["amount"] == 50.0
    assert result["currency"] == "AED"
    assert result["category"] == "transport"


def test_regex_fallback_no_amount():
    result = _regex_fallback("купил что-то")
    assert result["amount"] == 0.0


def test_regex_fallback_decimal():
    result = _regex_fallback("coffee 12.5 dirhams")
    assert result["amount"] == 12.5


# ── unit: extract_expense with mocked LLM ─────────────────────────────────────

def test_extract_expense_valid_llm(monkeypatch):
    payload = json.dumps({
        "amount": 50.0, "currency": "AED",
        "category": "transport", "description": "такси до офиса"
    })
    monkeypatch.setattr("agents.expense_agent.call_llm", lambda _: payload)

    result = extract_expense("такси 50")
    assert result["amount"] == 50.0
    assert result["currency"] == "AED"
    assert result["category"] == "transport"
    assert result["description"] == "такси до офиса"


def test_extract_expense_llm_returns_garbage_uses_fallback(monkeypatch):
    monkeypatch.setattr("agents.expense_agent.call_llm", lambda _: "not json at all")

    result = extract_expense("coffee 15 dirhams")
    assert result["amount"] == 15.0
    assert "category" in result
    assert "currency" in result


def test_extract_expense_llm_raises_uses_fallback(monkeypatch):
    def boom(_):
        raise RuntimeError("network error")

    monkeypatch.setattr("agents.expense_agent.call_llm", boom)

    result = extract_expense("groceries 100 rub")
    assert result["amount"] == 100.0
    assert result["currency"] == "RUB"


def test_extract_expense_llm_zero_amount_uses_fallback(monkeypatch):
    payload = json.dumps({
        "amount": 0, "currency": "AED",
        "category": "еда", "description": "что-то"
    })
    monkeypatch.setattr("agents.expense_agent.call_llm", lambda _: payload)

    result = extract_expense("bought food 20 dirhams")
    assert result["amount"] == 20.0


def test_extract_expense_synonym_category_normalized(monkeypatch):
    payload = json.dumps({
        "amount": 25.0, "currency": "AED",
        "category": "restaurant", "description": "lunch"
    })
    monkeypatch.setattr("agents.expense_agent.call_llm", lambda _: payload)

    result = extract_expense("restaurant 25")
    assert result["category"] == "cafe"


def test_extract_expense_empty_llm_response_uses_fallback(monkeypatch):
    monkeypatch.setattr("agents.expense_agent.call_llm", lambda _: "")

    result = extract_expense("coffee 10 aed")
    assert result["amount"] == 10.0


def test_regex_fallback_amount_always_nonnegative():
    result = _regex_fallback("some text without numbers")
    assert result["amount"] >= 0.0


def test_extract_expense_strips_markdown_fences(monkeypatch):
    payload = "```json\n" + json.dumps({
        "amount": 10.0, "currency": "AED",
        "category": "еда", "description": "снек"
    }) + "\n```"
    monkeypatch.setattr("agents.expense_agent.call_llm", lambda _: payload)

    result = extract_expense("снек 10")
    assert result["amount"] == 10.0


# ── integration: save_expense writes to DB ────────────────────────────────────

def test_save_expense_persists(monkeypatch, test_db):
    payload = json.dumps({
        "amount": 30.0, "currency": "AED",
        "category": "food", "description": "обед"
    })
    monkeypatch.setattr("agents.expense_agent.call_llm", lambda _: payload)

    result = save_expense(telegram_id=99999, text="обед 30")
    assert result["id"] is not None
    assert result["amount"] == 30.0

    from database.db import get_expenses, get_or_create_user
    user = get_or_create_user(99999, [])
    expenses = get_expenses(user["id"], days=1)
    assert len(expenses) == 1
    assert expenses[0]["category"] == "food"
