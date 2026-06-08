import asyncio

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from bot.keyboards import main_menu
from database.db import (
    get_or_create_user,
    is_user_onboarded,
    save_oauth_token,
    complete_onboarding,
)
from agents.gmail_oauth import get_auth_url, exchange_code, get_service, get_gmail_address

router = Router()


class OnboardingStates(StatesGroup):
    waiting_oauth_code = State()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    get_or_create_user(telegram_id, [])

    if is_user_onboarded(telegram_id):
        await message.answer("Welcome back! What can I help with?", reply_markup=main_menu)
        return

    auth_url, code_verifier = get_auth_url()
    await state.update_data(code_verifier=code_verifier)
    await state.set_state(OnboardingStates.waiting_oauth_code)
    await message.answer(
        "Hi! I'm your personal AI assistant.\n\n"
        "Connect your Gmail to get started:\n\n"
        f"{auth_url}\n\n"
        "👆 Open the link, authorize with Google.\n"
        "Your browser will try to open localhost — that's OK, it will fail.\n"
        "Copy the full URL from the browser address bar and paste it here."
    )


@router.message(OnboardingStates.waiting_oauth_code)
async def save_oauth(message: Message, state: FSMContext):
    raw = message.text.strip()
    data = await state.get_data()
    code_verifier = data.get("code_verifier", "")

    await message.answer("⏳ Verifying with Google...")

    def _setup(code_or_url: str, verifier: str) -> tuple[str, str]:
        token_json = exchange_code(code_or_url, verifier)
        service, token_json = get_service(token_json)
        address = get_gmail_address(service)
        return token_json, address

    try:
        token_json, gmail_address = await asyncio.to_thread(_setup, raw, code_verifier)
    except Exception as e:
        await message.answer(
            f"❌ Authorization failed: {e}\n\n"
            "Make sure you copied the full URL from the browser after authorizing. Try again:"
        )
        return

    save_oauth_token(message.from_user.id, token_json, gmail_address)
    complete_onboarding(message.from_user.id)
    await state.clear()

    await message.answer(
        f"✅ All set! Gmail connected: {gmail_address}\n\n"
        "What I can do:\n"
        "• LinkedIn Post — find trending news and write a ready-to-publish post\n"
        "• 📧 Email — read, summarise, and help you reply\n"
        "• Log Expense — track your spending",
        reply_markup=main_menu,
    )
