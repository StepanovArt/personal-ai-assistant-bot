from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


class CB:
    LI_LIKE = "li:like"
    LI_REDO = "li:redo"


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Пост в LinkedIn")],
        [KeyboardButton(text="📧 Почта"), KeyboardButton(text="Записать трату")],
    ],
    resize_keyboard=True
)

li_actions = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="Нравится", callback_data=CB.LI_LIKE),
        InlineKeyboardButton(text="Переделать", callback_data=CB.LI_REDO),
    ]
])

# ── email (untouched) ──────────────────────────────────────────────────────────

email_actions = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="✅ Отправить", callback_data="email_send"),
        InlineKeyboardButton(text="✏️ Изменить", callback_data="email_edit"),
    ],
    [
        InlineKeyboardButton(text="❌ Не отвечать", callback_data="email_skip"),
    ]
])

email_confirm = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="✅ Отправить", callback_data="email_send"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="email_skip"),
    ]
])

email_period_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🕐 1 час", callback_data="period:1h"),
        InlineKeyboardButton(text="🕒 3 часа", callback_data="period:3h"),
    ],
    [
        InlineKeyboardButton(text="🌅 12 часов", callback_data="period:12h"),
        InlineKeyboardButton(text="📅 1 день", callback_data="period:1d"),
    ]
])
