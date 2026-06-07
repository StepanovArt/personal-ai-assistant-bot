import asyncio
import os
import certifi

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from bot.keyboards import (
    main_menu, li_actions, CB,
    email_actions, email_confirm, email_period_kb,
)
from agents.manager import manager_respond
from agents.content_creator import create_post_from_trends
from agents.email_agent import (
    fetch_unread_emails, analyze_email, send_email, extract_email_address,
)

load_dotenv()
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()


# ══════════════════════════════════════════════════════════════
# FSM STATES
# ══════════════════════════════════════════════════════════════

class EmailStates(StatesGroup):
    showing_list = State()
    showing_email = State()
    waiting_custom_reply = State()

class LinkedInStates(StatesGroup):
    waiting_for_topic = State()
    showing_post = State()

class ExpenseStates(StatesGroup):
    waiting_text = State()


# ══════════════════════════════════════════════════════════════
# START
# ══════════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Привет! Я Варюха, твой ассистент. Чем помочь?",
                         reply_markup=main_menu)


# ══════════════════════════════════════════════════════════════
# EMAIL (untouched)
# ══════════════════════════════════════════════════════════════

@dp.message(F.text == "📧 Почта")
async def email_handler(message: Message, state: FSMContext):
    await message.answer(
        "За какой период проверить почту?",
        reply_markup=email_period_kb
    )

@dp.callback_query(F.data.startswith("period:"))
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

@dp.message(EmailStates.showing_list, F.text.regexp(r"^\d+$"))
async def show_summary(message: Message, state: FSMContext):
    n = int(message.text)
    await message.answer(f"Показываю саммари письма #{n}")
    data = await state.get_data()
    emails = data.get("emails", [])
    if n < 1 or n > len(emails):
        await message.answer(f"Письма {n} нет. Их всего {len(emails)}.")
        return
    target = emails[n - 1]
    msg_id = target["Message_id"]
    await message.answer("⏳ Анализирую...")
    result = await asyncio.to_thread(analyze_email, msg_id)
    await state.update_data(
        current_email=target,
        current_draft=result["draft_reply"]
    )
    text = (
        f"📧 От: {target['From']}\n"
        f"📌 Тема: {target['Subject']}\n\n"
        f"📝 САММАРИ:\n{result['summary']}\n\n"
        f"💬 ЧЕРНОВИК ОТВЕТА:\n{result['draft_reply']}"
    )
    await message.answer(text, reply_markup=email_actions)
    await state.set_state(EmailStates.showing_email)

@dp.callback_query(F.data == "email_send")
async def send_draft(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        data = await state.get_data()
        current_email = data["current_email"]
        current_draft = data["current_draft"]
        email_address = extract_email_address(current_email['From'])
        original_subject = data.get("Subject", "No Subject")
        subject = original_subject if original_subject.startswith("Re:") else "Re: " + original_subject
        await asyncio.to_thread(send_email, to=email_address, subject=subject, body=current_draft)
        await callback.message.answer("✅ Отправлено!")
        await state.set_state(EmailStates.showing_list)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка отправки: {e}")

@dp.callback_query(F.data == "email_edit")
async def request_custom_reply(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("✏️ Напиши свой вариант ответа:")
    await state.set_state(EmailStates.waiting_custom_reply)
    await callback.answer()

@dp.message(EmailStates.waiting_custom_reply)
async def custom_reply_text(message: Message, state: FSMContext):
    await state.update_data(current_draft=message.text)
    data = await state.get_data()
    current_email = data["current_email"]
    draft = data["current_draft"]
    preview = (
        f"📧 Кому: {current_email['From']}\n"
        f"📌 Тема: Re: {current_email['Subject']}\n\n"
        f"✉️ Твой ответ:\n{draft}\n\n"
        f"Отправить?"
    )
    await message.answer(preview, reply_markup=email_confirm)
    await state.set_state(EmailStates.showing_email)

@dp.callback_query(F.data == "email_skip")
async def skip_email(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EmailStates.showing_list)
    await callback.message.answer("⏭ Ок, пропустили письмо")
    await callback.answer()

@dp.message(EmailStates.showing_list, F.text.lower() == "выход")
async def exit_email(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚪 Вышли из режима почты")
    await message.answer("🏠 Главное меню", reply_markup=main_menu)


# ══════════════════════════════════════════════════════════════
# LINKEDIN
# ══════════════════════════════════════════════════════════════

async def _generate_and_send_post(telegram_id: int, interest: str, send_func) -> bool:
    result = await asyncio.to_thread(create_post_from_trends, telegram_id=telegram_id, interests=[interest])

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

    await send_func(f"🎯 Источник:\n📰 {chosen.get('title', 'Unknown')}\n🔗 {chosen.get('url', '')}")
    await send_func(post_text, reply_markup=li_actions)
    await send_func(f"📊 {len(post_text)} символов · Скопируй в LinkedIn")
    return True


@dp.message(F.text == "Пост в LinkedIn")
async def linkedin_post_handler(message: Message, state: FSMContext):
    await state.set_state(LinkedInStates.waiting_for_topic)
    await message.answer("На какую тему писать пост?")


@dp.message(LinkedInStates.waiting_for_topic)
async def generate_post_handler(message: Message, state: FSMContext):
    interest = message.text.strip()
    await state.update_data(interest=interest)
    await message.answer(f"⏳ Ищу свежие новости по теме '{interest}'...\n~1-3 минуты")

    ok = await _generate_and_send_post(message.from_user.id, interest, message.answer)
    if ok:
        await state.set_state(LinkedInStates.showing_post)
    else:
        await state.clear()


@dp.callback_query(F.data == CB.LI_LIKE)
async def li_like_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer("Отлично! Вставь пост в LinkedIn.")


@dp.callback_query(F.data == CB.LI_REDO)
async def li_redo_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    interest = data.get("interest", "")
    await callback.message.answer(f"Переделываю по теме '{interest}'...")

    ok = await _generate_and_send_post(callback.from_user.id, interest, callback.message.answer)
    if not ok:
        await state.clear()


# ══════════════════════════════════════════════════════════════
# EXPENSE
# ══════════════════════════════════════════════════════════════

@dp.message(F.text == "Записать трату")
async def expense_handler(message: Message, state: FSMContext):
    await state.set_state(ExpenseStates.waiting_text)
    await message.answer("Что записать? Например: банка колы 3 дирхама")


@dp.message(ExpenseStates.waiting_text)
async def process_expense(message: Message, state: FSMContext):
    text = message.text.strip()
    await state.clear()
    # TODO: подключить агент расходов и сохранение в БД
    await message.answer(f"✅ Записал: {text}", reply_markup=main_menu)


# ══════════════════════════════════════════════════════════════
# GENERAL CHAT
# ══════════════════════════════════════════════════════════════

@dp.message()
async def chat_handler(message: Message):
    answer = manager_respond(message.text)
    await message.answer(answer)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
