import asyncio
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from bot.keyboards import email_actions, email_confirm, email_period_kb, main_menu
from agents.email_agent import fetch_unread_emails, analyze_email, send_email, extract_email_address
from agents.gmail_oauth import get_service
from database.db import get_oauth_token, save_oauth_token

logger = logging.getLogger(__name__)
router = Router()


class EmailStates(StatesGroup):
    showing_list = State()
    showing_email = State()
    waiting_custom_reply = State()


def _with_service(token_json: str, fn, *args):
    """Build Gmail service, run fn(service, *args), return (result, new_token_json)."""
    service, new_token = get_service(token_json)
    result = fn(service, *args)
    return result, new_token


def _save_token_if_refreshed(telegram_id: int, old: str, new: str) -> None:
    if new != old:
        save_oauth_token(telegram_id, new)


@router.message(F.text == "📧 Email")
async def email_handler(message: Message):
    await message.answer("Which time period to check?", reply_markup=email_period_kb)


@router.callback_query(F.data.startswith("period:"))
async def process_period(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    token_json = get_oauth_token(telegram_id)
    if not token_json:
        await callback.message.answer("📭 Gmail not connected. Run /start to set it up.")
        await callback.answer()
        return

    period = callback.data.split(":")[1]
    await callback.answer()
    await callback.message.answer(f"⏳ Fetching emails for the last {period}...")

    try:
        emails, new_token = await asyncio.to_thread(
            _with_service, token_json, fetch_unread_emails, period
        )
    except Exception as e:
        logger.error("Failed to fetch emails for user %s: %s", telegram_id, e)
        await callback.message.answer("❌ Failed to fetch emails. Please try again.")
        return

    _save_token_if_refreshed(telegram_id, token_json, new_token)

    if not emails:
        await callback.message.answer("📭 No new emails")
        return

    await state.update_data(emails=emails, token_json=new_token)
    text = f"📬 Found {len(emails)} emails:\n\n"
    for i, em in enumerate(emails, 1):
        text += f"{i}. From: {em['From']}\n"
        text += f"   Subject: {em['Subject']}\n\n"
    text += "💬 Send the email number or 'exit'"
    await callback.message.answer(text)
    await state.set_state(EmailStates.showing_list)


@router.message(EmailStates.showing_list, F.text.regexp(r"^\d+$"))
async def show_summary(message: Message, state: FSMContext):
    data = await state.get_data()
    token_json = data.get("token_json") or get_oauth_token(message.from_user.id)
    if not token_json:
        await message.answer("📭 Gmail not connected. Run /start to set it up.")
        return

    n = int(message.text)
    emails = data.get("emails", [])

    if n < 1 or n > len(emails):
        await message.answer(f"No email #{n}. There are {len(emails)} emails.")
        return

    target = emails[n - 1]
    await message.answer(f"⏳ Analyzing email #{n}...")

    try:
        result, new_token = await asyncio.to_thread(
            _with_service, token_json, analyze_email, target["Message_id"]
        )
    except Exception as e:
        logger.error("Failed to analyze email: %s", e)
        await message.answer("❌ Failed to analyze email.")
        return

    _save_token_if_refreshed(message.from_user.id, token_json, new_token)
    await state.update_data(current_email=target, current_draft=result["draft_reply"], token_json=new_token)

    text = (
        f"📧 From: {target['From']}\n"
        f"📌 Subject: {target['Subject']}\n\n"
        f"📝 SUMMARY:\n{result['summary']}\n\n"
        f"💬 DRAFT REPLY:\n{result['draft_reply']}"
    )
    await message.answer(text, reply_markup=email_actions)
    await state.set_state(EmailStates.showing_email)


@router.callback_query(F.data == "email_send")
async def send_draft(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    token_json = data.get("token_json") or get_oauth_token(callback.from_user.id)
    if not token_json:
        await callback.message.answer("📭 Gmail not connected. Run /start to set it up.")
        return

    try:
        current_email = data["current_email"]
        current_draft = data["current_draft"]
        to = extract_email_address(current_email["From"])
        subject = current_email.get("Subject", "No Subject")
        if not subject.startswith("Re:"):
            subject = "Re: " + subject

        _, new_token = await asyncio.to_thread(
            _with_service, token_json, send_email, to, subject, current_draft
        )
        _save_token_if_refreshed(callback.from_user.id, token_json, new_token)

        await callback.message.answer("✅ Sent!")
        await state.set_state(EmailStates.showing_list)
    except Exception as e:
        await callback.message.answer(f"❌ Failed to send: {e}")


@router.callback_query(F.data == "email_edit")
async def request_custom_reply(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("✏️ Write your reply:")
    await state.set_state(EmailStates.waiting_custom_reply)
    await callback.answer()


@router.message(EmailStates.waiting_custom_reply)
async def custom_reply_text(message: Message, state: FSMContext):
    await state.update_data(current_draft=message.text)
    data = await state.get_data()
    current_email = data["current_email"]
    preview = (
        f"📧 To: {current_email['From']}\n"
        f"📌 Subject: Re: {current_email['Subject']}\n\n"
        f"✉️ Your reply:\n{message.text}\n\n"
        "Send it?"
    )
    await message.answer(preview, reply_markup=email_confirm)
    await state.set_state(EmailStates.showing_email)


@router.callback_query(F.data == "email_skip")
async def skip_email(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EmailStates.showing_list)
    await callback.message.answer("⏭ Email skipped")
    await callback.answer()


@router.message(EmailStates.showing_list, F.text.lower() == "exit")
async def exit_email(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚪 Exited email mode", reply_markup=main_menu)
