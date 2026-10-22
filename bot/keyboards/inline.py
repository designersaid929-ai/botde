from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_public_profile_keyboard(username: str, default_count: int = 3) -> InlineKeyboardMarkup:
    """
    Inline keyboard displayed when a public Instagram profile is checked.
    Provides one-tap buttons to download posts or active stories.
    """
    buttons = [
        [
            InlineKeyboardButton(
                text=f"📸 Recent Posts ({default_count})",
                callback_data=f"posts:{username}:{default_count}"
            ),
            InlineKeyboardButton(
                text="📸 5 Posts",
                callback_data=f"posts:{username}:5"
            ),
        ],
        [
            InlineKeyboardButton(
                text="⏳ Active Stories (24h)",
                callback_data=f"stories:{username}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔗 View on Instagram",
                url=f"https://www.instagram.com/{username}/"
            ),
            InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data=f"check:{username}"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_private_profile_keyboard(username: str) -> InlineKeyboardMarkup:
    """
    Inline keyboard displayed when a private Instagram profile is detected.
    """
    buttons = [
        [
            InlineKeyboardButton(
                text="🔗 View on Instagram",
                url=f"https://www.instagram.com/{username}/"
            ),
            InlineKeyboardButton(
                text="🔄 Re-check Status",
                callback_data=f"check:{username}"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_post_download_more_keyboard(username: str) -> InlineKeyboardMarkup:
    """
    Action buttons attached to post messages for easy subsequent queries.
    """
    buttons = [
        [
            InlineKeyboardButton(
                text="⏳ Check Stories",
                callback_data=f"stories:{username}"
            ),
            InlineKeyboardButton(
                text="👤 Profile Card",
                callback_data=f"check:{username}"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_welcome_keyboard() -> InlineKeyboardMarkup:
    """Welcome inline keyboard shown on /start."""
    buttons = [
        [
            InlineKeyboardButton(
                text="🤖 AI Chat (Gemini)",
                callback_data="ai:enter"
            ),
        ],
        [
            InlineKeyboardButton(
                text="ℹ️ Bot Qo'llanmasi",
                callback_data="help:show"
            ),
            InlineKeyboardButton(
                text="🔑 Gemini API Kalit",
                callback_data="ai:key_settings"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_ai_menu_keyboard(has_key: bool = True) -> InlineKeyboardMarkup:
    """AI section inline menu."""
    buttons = [
        [
            InlineKeyboardButton(
                text="💬 Suhbatni Boshlash (AI Rejimi)",
                callback_data="ai:enter"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔑 API Kalitni O'zgartirish" if has_key else "🔑 API Kalitni Kiritish",
                callback_data="ai:key_settings"
            ),
            InlineKeyboardButton(
                text="🧹 Tarixni Tozalash",
                callback_data="ai:reset"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_tts_listen_keyboard() -> InlineKeyboardMarkup:
    """Inline button attached to text responses to listen via voice."""
    buttons = [
        [
            InlineKeyboardButton(
                text="🔊 Ovozli tinglash",
                callback_data="ai:tts_listen"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_media_ai_keyboard(instagram_url: str = "") -> InlineKeyboardMarkup:
    """Button attached to sent Instagram media (post/story) for quick AI analysis."""
    buttons = [
        [
            InlineKeyboardButton(
                text="🤖 AI tahlil qilish",
                callback_data="media_ai:options"
            )
        ]
    ]
    if instagram_url:
        buttons.append([
            InlineKeyboardButton(text="🔗 Instagramda ko'rish", url=instagram_url)
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_ai_media_options_keyboard() -> InlineKeyboardMarkup:
    """Options menu for analyzing Instagram post/video/story."""
    buttons = [
        [
            InlineKeyboardButton(text="🎬 Mazmunini tushuntir", callback_data="media_ai:summary"),
            InlineKeyboardButton(text="🎙️ Nutqni matnga aylantir", callback_data="media_ai:transcribe"),
        ],
        [
            InlineKeyboardButton(text="🔍 Matnlarni aniqlash", callback_data="media_ai:ocr"),
            InlineKeyboardButton(text="🛍️ Buyum va joylar", callback_data="media_ai:objects"),
        ],
        [
            InlineKeyboardButton(text="🎯 Asosiy g'oya va maqsad", callback_data="media_ai:purpose"),
            InlineKeyboardButton(text="🏷️ Caption & Hashtaglar", callback_data="media_ai:hashtags"),
        ],
        [
            InlineKeyboardButton(text="❓ O'z savolimni berish", callback_data="media_ai:custom_ask"),
        ],
        [
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="media_ai:cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


