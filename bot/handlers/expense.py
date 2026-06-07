from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from bot.keyboards import main_menu

router = Router()


class ExpenseStates(StatesGroup):
    waiting_text = State()


@router.message(F.text == "Записать трату")
async def expense_handler(message: Message, state: FSMContext):
    await state.set_state(ExpenseStates.waiting_text)
    await message.answer("Что записать? Например: банка колы 3 дирхама")


@router.message(ExpenseStates.waiting_text)
async def process_expense(message: Message, state: FSMContext):
    text = message.text.strip()
    await state.clear()
    # TODO: подключить агент расходов и сохранение в БД
    await message.answer(f"✅ Записал: {text}", reply_markup=main_menu)
