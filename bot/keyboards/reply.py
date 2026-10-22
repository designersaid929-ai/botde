from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove


def get_ai_chat_keyboard() -> ReplyKeyboardMarkup:
    """
    Bottom reply keyboard displayed during active AI Chat mode.
    Allows quick session reset, API key configuration, or exiting AI chat.
    """
    keyboard = [
        [
            KeyboardButton(text="🧹 Yangi suhbat"),
            KeyboardButton(text="🔑 API Kalit"),
        ],
        [
            KeyboardButton(text="❌ AI Chatdan chiqish"),
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def remove_reply_keyboard() -> ReplyKeyboardRemove:
    """Removes the persistent custom keyboard when exiting AI mode."""
    return ReplyKeyboardRemove()
