import logging
import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.config import config
from bot.services.instagram import (
    instagram_service,
    ProfileNotFoundError,
    PrivateProfileError,
    RateLimitError,
    SessionRequiredError,
    InstagramServiceException
)
from bot.utils.url_parser import parse_instagram_input, resolve_and_parse_input
from bot.utils.formatters import (
    format_profile_card,
    format_private_profile_message,
    escape_html
)
from bot.keyboards.inline import get_public_profile_keyboard, get_private_profile_keyboard
from bot.utils.rate_limiter import UserRateLimiter

logger = logging.getLogger(__name__)
router = Router(name="profile_router")
rate_limiter = UserRateLimiter(cooldown_seconds=config.USER_COOLDOWN_SECONDS)


@router.message(Command("check"))
async def handle_check_command(message: Message):
    """Handles /check <username_or_url> command."""
    from bot.services.subscription import check_user_subscription, get_subscription_keyboard
    if message.from_user:
        is_sub, unsub = await check_user_subscription(message.bot, message.from_user.id)
        if not is_sub:
            await message.reply(
                "⚠️ <b>Botdan to'liq foydalanish uchun rasmiy kanalimizga a'zo bo'ling!</b>\n\n"
                "Quyidagi havola orqali kanalga kiring va obuna bo'ling, so'ngra <b>'✅ Obunani tekshirish'</b> tugmasini bosing:",
                reply_markup=get_subscription_keyboard(unsub),
                parse_mode="HTML"
            )
            return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "ℹ️ <b>Usage:</b> <code>/check &lt;username_or_url&gt;</code>\n"
            "Example: <code>/check nasa</code> or <code>/check https://instagram.com/nasa</code>",
            parse_mode="HTML"
        )
        return

    await process_profile_query(message, parts[1].strip())


@router.callback_query(F.data.startswith("check:"))
async def handle_check_callback(callback: CallbackQuery):
    """Handles refresh/re-check button callback."""
    username = callback.data.split(":", 1)[1]
    await callback.answer("Refreshing profile information...")
    await check_and_send_profile(
        target_message=callback.message,
        username=username,
        user_id=callback.from_user.id,
        is_edit=True
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: Message):
    """
    Handles general text messages sent by user (usernames, profile links, post links, etc.).
    In groups, ignores general chats unless explicit Instagram link or directed.
    """
    from aiogram.enums import ChatType
    from bot.services.subscription import check_user_subscription, get_subscription_keyboard

    # In groups/supergroups, ignore general messages that are not Instagram links
    is_group = getattr(message.chat, "type", ChatType.PRIVATE) in [ChatType.GROUP, ChatType.SUPERGROUP]
    raw_text = message.text.strip()
    if not raw_text:
        return

    if is_group:
        # In groups, only process if contains instagram link
        if "instagram.com" not in raw_text.lower():
            return

    # Check required channel subscription in private chats
    if not is_group and message.from_user:
        is_sub, unsub = await check_user_subscription(message.bot, message.from_user.id)
        if not is_sub:
            await message.reply(
                "⚠️ <b>Botdan to'liq foydalanish uchun rasmiy kanalimizga a'zo bo'ling!</b>\n\n"
                "Quyidagi havola orqali kanalga kiring va obuna bo'ling, so'ngra <b>'✅ Obunani tekshirish'</b> tugmasini bosing:",
                reply_markup=get_subscription_keyboard(unsub),
                parse_mode="HTML"
            )
            return

    await process_profile_query(message, raw_text)


async def process_profile_query(message: Message, raw_text: str):
    """
    Parses input and dispatches to profile checking or post/story handlers.
    """
    from bot.services.stats import track_user, log_query
    from bot.config import config

    # Track user and log query
    user = message.from_user
    if user:
        await track_user(user.id, user.username, user.first_name, user.last_name)
        await log_query(user.id, raw_text, "search")

        # Notify admin of new query
        if config.ADMIN_ID and user.id != config.ADMIN_ID:
            try:
                uname = f"@{user.username}" if user.username else "mavjud emas"
                name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Noma'lum"
                admin_alert = (
                    "🔍 <b>Yangi qidiruv so'rovi!</b>\n\n"
                    f"• 👤 <b>Foydalanuvchi:</b> {escape_html(name)} ({uname})\n"
                    f"• 🆔 <b>ID:</b> <code>{user.id}</code>\n"
                    f"• 🔎 <b>So'rov:</b> <code>{escape_html(raw_text)}</code>"
                )
                await message.bot.send_message(chat_id=config.ADMIN_ID, text=admin_alert, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Could not alert admin of query: {e}")

    parsed = await resolve_and_parse_input(raw_text)

    if not parsed.is_valid:
        await message.answer(
            "❓ <b>Noto'g'ri havola yoki nom</b>\n\n"
            "Iltimos, haqiqiy Instagram havolasini (video, Reels, post, story) "
            "yoki foydalanuvchi nomini yuboring (masalan: <code>@username</code>).",
            parse_mode="HTML"
        )
        return

    # If user sent a direct post/reel link, forward to post handler
    if parsed.input_type == "post" and parsed.shortcode:
        from bot.handlers.posts import download_and_send_single_post
        await download_and_send_single_post(message, parsed.shortcode)
        return

    # If user sent a direct story link
    if parsed.input_type == "story" and parsed.username:
        from bot.handlers.stories import fetch_and_send_user_stories
        await fetch_and_send_user_stories(message, parsed.username)
        return

    # Profile lookup
    if parsed.username:
        await check_and_send_profile(
            target_message=message,
            username=parsed.username,
            user_id=message.from_user.id,
            is_edit=False
        )


async def check_and_send_profile(target_message: Message, username: str, user_id: int, is_edit: bool = False):
    """
    Requirement 1: Checks if profile is public.
    Requirement 4: If private, returns clear message explaining privacy restrictions.
    """
    # Rate limit check
    allowed, wait_sec = await rate_limiter.check(user_id)
    if not allowed:
        text = f"⏳ Please wait <b>{wait_sec}s</b> before sending another request."
        if is_edit:
            await target_message.answer(text, parse_mode="HTML")
        else:
            await target_message.answer(text, parse_mode="HTML")
        return

    status_msg = None
    if not is_edit:
        status_msg = await target_message.answer(
            f"🔍 <i>Checking profile @{escape_html(username)}...</i>",
            parse_mode="HTML"
        )

    try:
        profile = await asyncio.wait_for(
            instagram_service.check_profile(username),
            timeout=15.0
        )

        # Requirement 4: Private profile handling
        if profile.is_private and not profile.followed_by_viewer:
            private_text = format_private_profile_message(profile.username)
            keyboard = get_private_profile_keyboard(profile.username)

            if is_edit:
                await target_message.edit_text(private_text, reply_markup=keyboard, parse_mode="HTML")
            elif status_msg:
                await status_msg.edit_text(private_text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await target_message.answer(private_text, reply_markup=keyboard, parse_mode="HTML")
            return

        # Profile handling (Public or followed private account)
        card_text = format_profile_card(
            username=profile.username,
            full_name=profile.full_name,
            biography=profile.biography,
            is_private=profile.is_private,
            is_verified=profile.is_verified,
            posts_count=profile.posts_count,
            followers_count=profile.followers_count,
            following_count=profile.following_count,
            external_url=profile.external_url,
            followed_by_viewer=profile.followed_by_viewer
        )
        keyboard = get_public_profile_keyboard(profile.username, default_count=config.DEFAULT_POSTS_LIMIT)

        if is_edit:
            await target_message.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
        elif status_msg:
            await status_msg.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await target_message.answer(card_text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)

    except asyncio.TimeoutError:
        msg = (
            "⏱️ <b>So'rov vaqti tugadi (Timeout)</b>\n\n"
            "Instagram serveri javob bermadi yoki anonim so'rovlarni vaqtincha chekladi (429).\n"
            "Cheklovni aylanib o'tish uchun <code>/session</code> orqali o'z Instagram <code>sessionid</code> cookie'ingizni ulang."
        )
        if status_msg:
            await status_msg.edit_text(msg, parse_mode="HTML")
        else:
            await target_message.answer(msg, parse_mode="HTML")

    except ProfileNotFoundError:
        msg = f"❌ <b>Profile Not Found:</b> The account <b>@{escape_html(username)}</b> does not exist on Instagram."
        if status_msg:
            await status_msg.edit_text(msg, parse_mode="HTML")
        else:
            await target_message.answer(msg, parse_mode="HTML")

    except RateLimitError as rle:
        msg = f"⏳ <b>Instagram Rate Limit:</b> {escape_html(str(rle))}"
        if status_msg:
            await status_msg.edit_text(msg, parse_mode="HTML")
        else:
            await target_message.answer(msg, parse_mode="HTML")

    except SessionRequiredError as sre:
        msg = (
            f"🔒 <b>Authentication Required:</b>\n"
            f"{escape_html(str(sre))}\n\n"
            "Use <code>/session</code> for instructions on providing a session cookie."
        )
        if status_msg:
            await status_msg.edit_text(msg, parse_mode="HTML")
        else:
            await target_message.answer(msg, parse_mode="HTML")

    except InstagramServiceException as ise:
        msg = f"⚠️ <b>Error:</b> {escape_html(str(ise))}"
        if status_msg:
            await status_msg.edit_text(msg, parse_mode="HTML")
        else:
            await target_message.answer(msg, parse_mode="HTML")

    except Exception as e:
        logger.exception(f"Unexpected error in profile check: {e}")
        msg = "⚠️ An unexpected error occurred while checking this profile. Please try again later."
        if status_msg:
            await status_msg.edit_text(msg, parse_mode="HTML")
        else:
            await target_message.answer(msg, parse_mode="HTML")
