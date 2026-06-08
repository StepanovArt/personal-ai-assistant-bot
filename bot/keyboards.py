from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


class CB:
    LI_LIKE = "li:like"
    LI_REDO = "li:redo"
    EXPENSE_STATS = "expense:stats"


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="LinkedIn Post")],
        [KeyboardButton(text="📧 Email"), KeyboardButton(text="Log Expense")],
    ],
    resize_keyboard=True
)

li_actions = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="Like", callback_data=CB.LI_LIKE),
        InlineKeyboardButton(text="Redo", callback_data=CB.LI_REDO),
    ]
])

expense_saved_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Monthly Summary", callback_data=CB.EXPENSE_STATS)]
])

email_actions = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="✅ Send", callback_data="email_send"),
        InlineKeyboardButton(text="✏️ Edit", callback_data="email_edit"),
    ],
    [
        InlineKeyboardButton(text="❌ Skip", callback_data="email_skip"),
    ]
])

email_confirm = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="✅ Send", callback_data="email_send"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="email_skip"),
    ]
])

email_period_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🕐 1 hour", callback_data="period:1h"),
        InlineKeyboardButton(text="🕒 3 hours", callback_data="period:3h"),
    ],
    [
        InlineKeyboardButton(text="🌅 12 hours", callback_data="period:12h"),
        InlineKeyboardButton(text="📅 1 day", callback_data="period:1d"),
    ]
])
