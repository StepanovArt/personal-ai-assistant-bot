import pytest
from unittest.mock import AsyncMock, MagicMock

from bot.handlers.expense import expense_handler, process_expense, expense_stats, ExpenseStates


@pytest.fixture
def message():
    msg = MagicMock()
    msg.answer = AsyncMock()
    msg.from_user.id = 12345
    return msg


@pytest.fixture
def state():
    fsm = MagicMock()
    fsm.set_state = AsyncMock()
    fsm.clear = AsyncMock()
    return fsm


@pytest.fixture
def callback():
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.from_user.id = 12345
    return cb


async def test_expense_handler_sets_state_and_prompts(message, state):
    await expense_handler(message, state)

    state.set_state.assert_called_once_with(ExpenseStates.waiting_text)
    message.answer.assert_called_once()


async def test_process_expense_success(message, state, monkeypatch):
    message.text = "такси 50 дирхам"
    saved = {"amount": 50.0, "currency": "AED", "category": "транспорт", "description": "такси", "id": 1}
    monkeypatch.setattr("bot.handlers.expense.save_expense", lambda tid, text: saved)

    await process_expense(message, state)

    state.clear.assert_called_once()
    reply = message.answer.call_args[0][0]
    assert "50" in reply
    assert "AED" in reply
    assert "транспорт" in reply


async def test_process_expense_clears_state_even_on_success(message, state, monkeypatch):
    message.text = "кофе 10"
    monkeypatch.setattr("bot.handlers.expense.save_expense", lambda *_: {
        "amount": 10.0, "currency": "AED", "category": "кафе", "description": "кофе", "id": 2
    })

    await process_expense(message, state)

    state.clear.assert_called_once()


async def test_process_expense_db_error_sends_friendly_message(message, state, monkeypatch):
    message.text = "что-то"

    def raise_error(*_):
        raise RuntimeError("db error")

    monkeypatch.setattr("bot.handlers.expense.save_expense", raise_error)

    await process_expense(message, state)

    reply = message.answer.call_args[0][0]
    assert "Не удалось" in reply


async def test_expense_stats_sends_summary(callback, monkeypatch):
    monkeypatch.setattr("bot.handlers.expense.get_monthly_summary", lambda tid: "📊 Итого: 300 AED")

    await expense_stats(callback)

    reply = callback.message.answer.call_args[0][0]
    assert "300 AED" in reply
    callback.answer.assert_called_once()


async def test_expense_stats_correct_user_id(callback, monkeypatch):
    captured = {}

    def mock_summary(tid):
        captured["tid"] = tid
        return "ok"

    monkeypatch.setattr("bot.handlers.expense.get_monthly_summary", mock_summary)
    callback.from_user.id = 99999

    await expense_stats(callback)

    assert captured["tid"] == 99999
