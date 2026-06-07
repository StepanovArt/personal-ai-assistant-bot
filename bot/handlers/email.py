import asyncio

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from bot.keyboards import email_actions, email_confirm, email_period_kb, main_menu
from agents.email_agent import fetch_unread_emails, analyze_email, send_email, extract_email_address

router = Router()


class EmailStates(StatesGroup):
    showing_list = State()
    showing_email = State()
    waiting_custom_reply = State()


@router.message(F.text == "📧 Почта")
async def email_handler(message: Message):
    await message.answer("За какой период проверить почту?", reply_markup=email_period_kb)


@router.callback_query(F.data.startswith("period:"))
async def process_period(callback: CallbackQuery, state: FSMContext):
    period = callback.data.split(":")[1]
    await callback.message.answer(f"⏳ Получаю письма за {period}...")
    letters = await asyncio.to_thread(fetch_unread_emails, period)
    if not letters:
        await callback.message.answer("📭Новых писем нет")
        return
    await state.update_data(emails=letters)
    text = f"📬 Найдено {len(letters)} писем:\n\n"
    for i, em in enumerate(letters, 1):
        text += f"{i}. От: {em['From']}\n"
        text += f"   Тема: {em['Subject']}\n\n"
    text += "💬 Команды: 'саммари N' или 'выход'"
    await callback.message.answer(text)
    await state.set_state(EmailStates.showing_list)


@router.message(EmailStates.showing_list, F.text.regexp(r"^\d+$"))
async def show_summary(message: Message, state: FSMContext):
    n = int(message.text)
    data = await state.get_data()
    emails = data.get("emails", [])
    if n < 1 or n > len(emails):
        await message.answer(f"Письма {n} нет. Их всего {len(emails)}.")
        return
    target = emails[n - 1]
    await message.answer(f"⏳ Анализирую письмо #{n}...")
    result = await asyncio.to_thread(analyze_email, target["Message_id"])
    await state.update_data(current_email=target, current_draft=result["draft_reply"])
    text = (
        f"📧 От: {target['From']}\n"
        f"📌 Тема: {target['Subject']}\n\n"
        f"📝 САММАРИ:\n{result['summary']}\n\n"
        f"💬 ЧЕРНОВИК ОТВЕТА:\n{result['draft_reply']}"
    )
    await message.answer(text, reply_markup=email_actions)
    await state.set_state(EmailStates.showing_email)


@router.callback_query(F.data == "email_send")
async def send_draft(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        data = await state.get_data()
        current_email = data["current_email"]
        current_draft = data["current_draft"]
        email_address = extract_email_address(current_email["From"])
        original_subject = current_email.get("Subject", "No Subject")
        subject = original_subject if original_subject.startswith("Re:") else "Re: " + original_subject
        await asyncio.to_thread(send_email, to=email_address, subject=subject, body=current_draft)
        await callback.message.answer("✅ Отправлено!")
        await state.set_state(EmailStates.showing_list)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка отправки: {e}")


@router.callback_query(F.data == "email_edit")
async def request_custom_reply(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("✏️ Напиши свой вариант ответа:")
    await state.set_state(EmailStates.waiting_custom_reply)
    await callback.answer()


@router.message(EmailStates.waiting_custom_reply)
async def custom_reply_text(message: Message, state: FSMContext):
    await state.update_data(current_draft=message.text)
    data = await state.get_data()
    current_email = data["current_email"]
    preview = (
        f"📧 Кому: {current_email['From']}\n"
        f"📌 Тема: Re: {current_email['Subject']}\n\n"
        f"✉️ Твой ответ:\n{message.text}\n\n"
        f"Отправить?"
    )
    await message.answer(preview, reply_markup=email_confirm)
    await state.set_state(EmailStates.showing_email)


@router.callback_query(F.data == "email_skip")
async def skip_email(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EmailStates.showing_list)
    await callback.message.answer("⏭ Ок, пропустили письмо")
    await callback.answer()


@router.message(EmailStates.showing_list, F.text.lower() == "выход")
async def exit_email(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚪 Вышли из режима почты")
    await message.answer("🏠 Главное меню", reply_markup=main_menu)
