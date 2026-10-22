import re
import logging
from typing import List, Dict, Tuple
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.config import config

logger = logging.getLogger(__name__)


def get_required_channels() -> List[str]:
    """Parses and returns list of required channel usernames or IDs."""
    raw = config.REQUIRED_CHANNELS
    if not raw:
        return []
    channels = [ch.strip() for ch in raw.replace(",", " ").split() if ch.strip()]
    return channels


def set_required_channels(channels_str: str) -> bool:
    """Updates REQUIRED_CHANNELS dynamically and persists to .env."""
    clean = channels_str.strip()
    object.__setattr__(config, "REQUIRED_CHANNELS", clean)

    try:
        env_path = config.BASE_DIR / ".env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            if "REQUIRED_CHANNELS=" in content:
                new_content = re.sub(r"REQUIRED_CHANNELS=.*", f"REQUIRED_CHANNELS={clean}", content)
            else:
                new_content = content + f"\nREQUIRED_CHANNELS={clean}\n"
            env_path.write_text(new_content, encoding="utf-8")
        return True
    except Exception as e:
        logger.error(f"Failed to update REQUIRED_CHANNELS in .env: {e}")
        return False


async def check_user_subscription(bot: Bot, user_id: int) -> Tuple[bool, List[Dict[str, str]]]:
    """
    Checks if a user is subscribed to all configured required channels.
    Returns (is_subscribed: bool, list_of_unsubscribed_channels: list).
    """
    channels = get_required_channels()
    if not channels:
        return True, []

    # Admin is exempt from subscription check
    if config.ADMIN_ID and user_id == config.ADMIN_ID:
        return True, []

    unsubscribed = []
    allowed_statuses = {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    }

    for ch in channels:
        try:
            # Handle numeric chat ID (groups, supergroups, channels)
            if ch.startswith("-") or ch.isdigit():
                chat_identifier = int(ch)
            else:
                chat_identifier = ch if ch.startswith("@") else f"@{ch}"

            member = await bot.get_chat_member(chat_id=chat_identifier, user_id=user_id)
            if member.status not in allowed_statuses:
                chat_info = await bot.get_chat(chat_identifier)
                invite_link = chat_info.invite_link
                if not invite_link and chat_info.username:
                    invite_link = f"https://t.me/{chat_info.username}"
                if not invite_link:
                    try:
                        invite_link = await bot.export_chat_invite_link(chat_identifier)
                    except Exception:
                        pass

                unsubscribed.append({
                    "id": str(chat_info.id),
                    "title": chat_info.title or str(chat_identifier),
                    "url": invite_link
                })
        except Exception as e:
            logger.warning(f"Could not verify subscription for user {user_id} in {ch}: {e}")
            clean_name = str(ch).lstrip("@")
            unsubscribed.append({
                "id": str(ch),
                "title": f"Kanal ({clean_name})",
                "url": f"https://t.me/{clean_name}" if not str(ch).startswith("-") else None
            })

    return len(unsubscribed) == 0, unsubscribed


def get_subscription_keyboard(unsubscribed_channels: List[Dict[str, str]]) -> InlineKeyboardMarkup:
    """Builds inline keyboard asking user to join required channels and verify."""
    buttons = []
    for idx, ch in enumerate(unsubscribed_channels, 1):
        url = ch.get("url")
        if url:
            title = ch.get("title", f"Kanal {idx}")
            buttons.append([
                InlineKeyboardButton(
                    text=f"📢 {title} ga a'zo bo'lish",
                    url=url
                )
            ])

    buttons.append([
        InlineKeyboardButton(
            text="✅ Obunani tekshirish",
            callback_data="sub:check"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
