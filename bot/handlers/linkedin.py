import asyncio

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from bot.keyboards import li_actions, CB
from agents.content_creator import create_post_from_trends

router = Router()


class LinkedInStates(StatesGroup):
    waiting_for_topic = State()
    showing_post = State()


async def _generate_and_send_post(telegram_id: int, interest: str, send_func) -> bool:
    result = await asyncio.to_thread(
        create_post_from_trends, telegram_id=telegram_id, interests=[interest]
    )

    if "error" in result:
        await send_func(f"❌ {result['error']}")
        return False

    chosen = result.get("chosen_news", {})
    post_text = result.get("variants", {}).get("story", "")

    if not post_text:
        await send_func("❌ Пост не сгенерировался")
        return False

    if len(post_text) > 3900:
        post_text = post_text[:3900] + "..."

    await send_func(
        f"🎯 Источник:\n📰 {chosen.get('title', 'Unknown')}\n🔗 {chosen.get('url', '')}"
    )
    await send_func(post_text, reply_markup=li_actions)
    await send_func(f"📊 {len(post_text)} символов · Скопируй в LinkedIn")
    return True


@router.message(F.text == "Пост в LinkedIn")
async def linkedin_post_handler(message: Message, state: FSMContext):
    await state.set_state(LinkedInStates.waiting_for_topic)
    await message.answer("На какую тему писать пост?")


@router.message(LinkedInStates.waiting_for_topic)
async def generate_post_handler(message: Message, state: FSMContext):
    interest = message.text.strip()
    await state.update_data(interest=interest)
    await message.answer(f"⏳ Ищу свежие новости по теме '{interest}'...\n~1-3 минуты")
    ok = await _generate_and_send_post(message.from_user.id, interest, message.answer)
    if ok:
        await state.set_state(LinkedInStates.showing_post)
    else:
        await state.clear()


@router.callback_query(F.data == CB.LI_LIKE)
async def li_like_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer("Отлично! Вставь пост в LinkedIn.")


@router.callback_query(F.data == CB.LI_REDO)
async def li_redo_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    interest = data.get("interest", "")
    await callback.message.answer(f"Переделываю по теме '{interest}'...")
    ok = await _generate_and_send_post(callback.from_user.id, interest, callback.message.answer)
    if not ok:
        await state.clear()
