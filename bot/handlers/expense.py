import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from agents.expense_agent import save_expense, get_monthly_summary
from bot.keyboards import main_menu, expense_saved_kb, CB

logger = logging.getLogger(__name__)
router = Router()


class ExpenseStates(StatesGroup):
    waiting_text = State()


@router.message(F.text == "Log Expense")
async def expense_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(ExpenseStates.waiting_text)
    await message.answer("Что записать? Например: банка колы 3 дирхама")


@router.message(ExpenseStates.waiting_text)
async def process_expense(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    telegram_id = message.from_user.id
    await state.clear()

    try:
        result = save_expense(telegram_id, text)
        reply = (
            f"✅ Записал!\n\n"
            f"💰 {result['amount']:.0f} {result['currency']} — {result['category']}\n"
            f"📝 {result['description']}"
        )
        await message.answer(reply, reply_markup=expense_saved_kb)
    except Exception as e:
        logger.error("Expense save failed for user %s: %s", telegram_id, e)
        await message.answer("Не удалось записать трату, попробуй ещё раз.", reply_markup=main_menu)


@router.callback_query(F.data == CB.EXPENSE_STATS)
async def expense_stats(callback: CallbackQuery) -> None:
    telegram_id = callback.from_user.id
    summary = get_monthly_summary(telegram_id)
    await callback.message.answer(summary, reply_markup=main_menu)
    await callback.answer()
