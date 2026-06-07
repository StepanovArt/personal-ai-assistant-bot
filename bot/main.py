import asyncio
import os
import certifi

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards import main_menu
from bot.handlers import email, linkedin, expense
from agents.manager import manager_respond

load_dotenv()
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Привет! Я Варюха, твой ассистент. Чем помочь?",
                         reply_markup=main_menu)


async def chat_handler(message: Message):
    answer = manager_respond(message.text)
    await message.answer(answer)


async def main():
    dp.include_router(email.router)
    dp.include_router(linkedin.router)
    dp.include_router(expense.router)
    dp.message.register(chat_handler)  # catch-all — регистрируем последним
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
