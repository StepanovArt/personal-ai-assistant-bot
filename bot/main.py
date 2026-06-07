import asyncio
import os
import certifi

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.types import Message

from bot.handlers import email, linkedin, expense, onboarding
from agents.manager import manager_respond
from database.db import init_db

load_dotenv()
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()


async def chat_handler(message: Message) -> None:
    answer = manager_respond(message.text)
    await message.answer(answer)


async def main() -> None:
    init_db()
    dp.include_router(onboarding.router)  # первым — перехватывает /start
    dp.include_router(email.router)
    dp.include_router(linkedin.router)
    dp.include_router(expense.router)
    dp.message.register(chat_handler)     # catch-all последним
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
