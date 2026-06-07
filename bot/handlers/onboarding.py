from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from bot.keyboards import main_menu
from database.db import (
    get_or_create_user,
    is_user_onboarded,
    update_user_interests,
    update_user_email_credentials,
    complete_onboarding,
)

router = Router()


class OnboardingStates(StatesGroup):
    waiting_interests = State()
    waiting_gmail = State()
    waiting_gmail_password = State()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    get_or_create_user(telegram_id, [])

    if is_user_onboarded(telegram_id):
        await message.answer("С возвращением! Чем помочь?", reply_markup=main_menu)
        return

    await state.set_state(OnboardingStates.waiting_interests)
    await message.answer(
        "Привет! Я Варюха, твой AI-ассистент.\n\n"
        "Давай настроим всё за 3 шага.\n\n"
        "1️⃣ Введи свои интересы через запятую:\n"
        "Например: AI, стартапы, финтех, крипто"
    )


@router.message(OnboardingStates.waiting_interests)
async def save_interests(message: Message, state: FSMContext):
    interests = [i.strip() for i in message.text.split(",") if i.strip()]
    if not interests:
        await message.answer("Введи хотя бы один интерес, например: AI")
        return

    update_user_interests(message.from_user.id, interests)
    await state.update_data(interests=interests)
    await state.set_state(OnboardingStates.waiting_gmail)
    await message.answer(
        f"✅ Сохранил интересы: {', '.join(interests)}\n\n"
        "2️⃣ Введи свой Gmail адрес:"
    )


@router.message(OnboardingStates.waiting_gmail)
async def save_gmail(message: Message, state: FSMContext):
    gmail = message.text.strip().lower()
    if "@" not in gmail or not gmail.endswith("gmail.com"):
        await message.answer("Похоже это не Gmail адрес. Введи адрес вида name@gmail.com")
        return

    await state.update_data(gmail_user=gmail)
    await state.set_state(OnboardingStates.waiting_gmail_password)
    await message.answer(
        f"✅ Gmail: {gmail}\n\n"
        "3️⃣ Введи Google App Password (16 символов без пробелов).\n\n"
        "Где взять: myaccount.google.com → Безопасность → Пароли приложений"
    )


@router.message(OnboardingStates.waiting_gmail_password)
async def save_gmail_password(message: Message, state: FSMContext):
    password = message.text.strip().replace(" ", "")
    if len(password) != 16:
        await message.answer(
            f"App Password должен быть 16 символов, у тебя {len(password)}. Попробуй ещё раз:"
        )
        return

    data = await state.get_data()
    gmail_user = data["gmail_user"]

    update_user_email_credentials(message.from_user.id, gmail_user, password)
    complete_onboarding(message.from_user.id)
    await state.clear()

    await message.answer(
        "✅ Всё готово! Настройка завершена.\n\n"
        "Что умею:\n"
        "• Пост в LinkedIn — нахожу свежие новости и пишу пост\n"
        "• Почта — читаю, анализирую, помогаю ответить\n"
        "• Записать трату — веду учёт расходов",
        reply_markup=main_menu,
    )
