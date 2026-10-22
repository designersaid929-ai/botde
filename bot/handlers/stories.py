import logging
import asyncio
import tempfile
from pathlib import Path
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.config import config
from bot.services.instagram import (
    instagram_service,
    PrivateProfileError,
    ProfileNotFoundError,
    RateLimitError,
    SessionRequiredError,
    InstagramServiceException
)
from bot.utils.url_parser import parse_instagram_input
from bot.utils.formatters import format_private_profile_message, escape_html
from bot.utils.media_sender import send_downloaded_story
from bot.utils.rate_limiter import UserRateLimiter

logger = logging.getLogger(__name__)
router = Router(name="stories_router")
rate_limiter = UserRateLimiter(cooldown_seconds=config.USER_COOLDOWN_SECONDS)
download_semaphore = None


def get_download_semaphore():
    global download_semaphore
    if download_semaphore is None:
        import asyncio
        download_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_DOWNLOADS)
    return download_semaphore


@router.message(Command("stories"))
async def handle_stories_command(message: Message):
    """
    Handles /stories <username_or_url> command.
    Requirement 3.
    """
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
            "ℹ️ <b>Usage:</b> <code>/stories &lt;username_or_url&gt;</code>\n"
            "Example: <code>/stories nasa</code> or <code>/stories https://instagram.com/stories/nasa/</code>",
            parse_mode="HTML"
        )
        return

    raw_input = parts[1].strip()
    from bot.services.stats import track_user, log_query
    if message.from_user:
        await track_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
        await log_query(message.from_user.id, raw_input, "stories")

    parsed = parse_instagram_input(raw_input)
    username = parsed.username or raw_input.strip("@ ")

    await fetch_and_send_user_stories(message, username)


@router.callback_query(F.data.startswith("stories:"))
async def handle_stories_callback(callback: CallbackQuery):
    """
    Handles inline button callback: stories:<username>
    """
    username = callback.data.split(":", 1)[1]
    await callback.answer(f"Fetching active stories for @{username}...")
    await fetch_and_send_user_stories(
        message=callback.message,
        username=username,
        reply_to_chat_id=callback.message.chat.id
    )


async def fetch_and_send_user_stories(
    message: Message,
    username: str,
    reply_to_chat_id: Optional[int] = None
):
    """
    Requirement 3: Fetches, downloads, and sends active 24-hour stories.
    Requirement 4 & 5: Handles private profiles, authentication requirement, and rate limits.
    """
    chat_id = reply_to_chat_id or message.chat.id
    user_id = message.from_user.id if message.from_user else chat_id

    # Rate limiting
    allowed, wait_sec = await rate_limiter.check(user_id)
    if not allowed:
        await message.bot.send_message(
            chat_id=chat_id,
            text=f"⏳ Please wait <b>{wait_sec}s</b> before another story request.",
            parse_mode="HTML"
        )
        return

    # Check if session is logged in before attempting story query
    is_logged_in, _ = instagram_service.check_session_status()
    if not is_logged_in:
        await message.bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ <b>Instagram Session Required for Stories</b>\n\n"
                "Instagram strictly requires an authenticated session to view and download stories "
                "(even for public accounts).\n\n"
                "💡 <b>How to Enable Stories:</b>\n"
                "1. Provide your browser's <code>sessionid</code> cookie in <code>.env</code> under <code>INSTAGRAM_SESSION_ID</code>.\n"
                "2. Or run <code>/setsession &lt;sessionid&gt;</code> to configure it directly.\n\n"
                "Type <code>/session</code> for more details."
            ),
            parse_mode="HTML"
        )
        return

    status_msg = await message.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ <i>Checking active 24h stories for @{escape_html(username)}...</i>",
        parse_mode="HTML"
    )

    temp_dir_obj = tempfile.TemporaryDirectory(dir=config.TEMP_DIR)
    temp_dir_path = Path(temp_dir_obj.name)
    semaphore = get_download_semaphore()

    try:
        async with semaphore:
            stories = await asyncio.wait_for(
                instagram_service.get_user_stories(
                    username=username,
                    target_dir=temp_dir_path
                ),
                timeout=60.0
            )

        if not stories:
            await status_msg.edit_text(
                f"ℹ️ No active stories found in the last 24 hours for <b>@{escape_html(username)}</b>.",
                parse_mode="HTML"
            )
            return

        await status_msg.edit_text(
            f"📤 <i>Sending {len(stories)} active story item(s)...</i>",
            parse_mode="HTML"
        )

        sent_count = 0
        for story in stories:
            try:
                success = await send_downloaded_story(
                    bot=message.bot,
                    chat_id=chat_id,
                    story=story
                )
                if success:
                    sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send story item: {e}")

        try:
            await status_msg.delete()
        except Exception:
            pass

        if sent_count == 0:
            await message.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Could not deliver stories to Telegram due to transfer or format limits."
            )

    except asyncio.TimeoutError:
        await status_msg.edit_text(
            "⏱️ <b>Stories yuklab olish vaqti tugadi (Timeout)</b>\n\n"
            "Instagram javob bermadi yoki so'rovlarni vaqtincha chekladi (429).",
            parse_mode="HTML"
        )

    except PrivateProfileError:
        # Requirement 4
        private_msg = format_private_profile_message(username)
        await status_msg.edit_text(private_msg, parse_mode="HTML")

    except ProfileNotFoundError:
        await status_msg.edit_text(
            f"❌ <b>Profile Not Found:</b> The account <b>@{escape_html(username)}</b> does not exist.",
            parse_mode="HTML"
        )

    except SessionRequiredError as sre:
        await status_msg.edit_text(
            f"🔒 <b>Authentication Required:</b>\n{escape_html(str(sre))}\n\n"
            "Use <code>/session</code> to check session details.",
            parse_mode="HTML"
        )

    except RateLimitError as rle:
        await status_msg.edit_text(
            f"⏳ <b>Instagram Rate Limit:</b> {escape_html(str(rle))}",
            parse_mode="HTML"
        )

    except InstagramServiceException as ise:
        await status_msg.edit_text(
            f"⚠️ <b>Instagram Error:</b> {escape_html(str(ise))}",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.exception(f"Unexpected error fetching stories for {username}: {e}")
        await status_msg.edit_text(
            "⚠️ An error occurred while retrieving stories. Please try again later.",
            parse_mode="HTML"
        )

    finally:
        # Guaranteed cleanup of all story files
        try:
            temp_dir_obj.cleanup()
        except Exception as ce:
            logger.warning(f"Error cleaning up story temp directory {temp_dir_path}: {ce}")
