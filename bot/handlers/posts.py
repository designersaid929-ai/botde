import shutil
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
    MediaNotFoundError,
    InstagramServiceException
)
from bot.utils.url_parser import parse_instagram_input
from bot.utils.formatters import format_private_profile_message, escape_html
from bot.utils.media_sender import send_downloaded_post
from bot.utils.rate_limiter import UserRateLimiter

logger = logging.getLogger(__name__)
router = Router(name="posts_router")
rate_limiter = UserRateLimiter(cooldown_seconds=config.USER_COOLDOWN_SECONDS)
download_semaphore = None


def get_download_semaphore():
    global download_semaphore
    if download_semaphore is None:
        import asyncio
        download_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_DOWNLOADS)
    return download_semaphore


@router.message(Command("posts"))
async def handle_posts_command(message: Message):
    """
    Handles /posts <username_or_url> [count] command.
    Requirement 2.
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

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer(
            "ℹ️ <b>Usage:</b> <code>/posts &lt;username_or_url&gt; [count]</code>\n"
            f"Example: <code>/posts nasa 3</code> (Default: {config.DEFAULT_POSTS_LIMIT}, Max: {config.MAX_POSTS_LIMIT})",
            parse_mode="HTML"
        )
        return

    raw_target = parts[1]
    count = config.DEFAULT_POSTS_LIMIT

    from bot.services.stats import track_user, log_query
    if message.from_user:
        await track_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
        await log_query(message.from_user.id, raw_target, "posts")

    if len(parts) >= 3:
        try:
            parsed_count = int(parts[2])
            count = max(1, min(parsed_count, config.MAX_POSTS_LIMIT))
        except ValueError:
            pass

    parsed = parse_instagram_input(raw_target)

    if parsed.input_type == "post" and parsed.shortcode:
        await download_and_send_single_post(message, parsed.shortcode)
        return

    username = parsed.username or raw_target.strip("@ ")
    await fetch_and_send_posts(message, username, count)


@router.callback_query(F.data.startswith("posts:"))
async def handle_posts_callback(callback: CallbackQuery):
    """
    Handles inline button callback: posts:<username>:<count>
    """
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid callback data.")
        return

    username = parts[1]
    try:
        count = int(parts[2])
    except ValueError:
        count = config.DEFAULT_POSTS_LIMIT

    await callback.answer(f"Fetching {count} recent post(s)...")
    await fetch_and_send_posts(callback.message, username, count, reply_to_chat_id=callback.message.chat.id)


async def fetch_and_send_posts(
    message: Message,
    username: str,
    count: int,
    reply_to_chat_id: Optional[int] = None
):
    """
    Requirement 2: Fetches, downloads, and sends recent posts (images, carousels, videos/reels).
    Guarantees cleanup of temporary files in all scenarios.
    """
    chat_id = reply_to_chat_id or message.chat.id
    user_id = message.from_user.id if message.from_user else chat_id

    # Rate limiting
    allowed, wait_sec = await rate_limiter.check(user_id)
    if not allowed:
        await message.bot.send_message(
            chat_id=chat_id,
            text=f"⏳ Please wait <b>{wait_sec}s</b> before starting another download.",
            parse_mode="HTML"
        )
        return

    status_msg = await message.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ <i>Downloading {count} recent post(s) from @{escape_html(username)}...</i>",
        parse_mode="HTML"
    )

    temp_dir_obj = tempfile.TemporaryDirectory(dir=config.TEMP_DIR)
    temp_dir_path = Path(temp_dir_obj.name)

    semaphore = get_download_semaphore()

    try:
        async with semaphore:
            posts = await asyncio.wait_for(
                instagram_service.get_recent_posts(
                    username=username,
                    count=count,
                    target_dir=temp_dir_path
                ),
                timeout=60.0
            )

        if not posts:
            await status_msg.edit_text(
                f"ℹ️ No posts found for <b>@{escape_html(username)}</b>.",
                parse_mode="HTML"
            )
            return

        await status_msg.edit_text(
            f"📤 <i>Sending {len(posts)} post(s) to chat...</i>",
            parse_mode="HTML"
        )

        sent_count = 0
        for post in posts:
            try:
                success = await send_downloaded_post(
                    bot=message.bot,
                    chat_id=chat_id,
                    post=post
                )
                if success:
                    sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send post {post.shortcode}: {e}")

        # Remove the status message after sending media
        try:
            await status_msg.delete()
        except Exception:
            pass

        if sent_count == 0:
            await message.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Unable to deliver posts due to Telegram transfer limits or corrupted media."
            )

    except asyncio.TimeoutError:
        await status_msg.edit_text(
            "⏱️ <b>Yuklab olish vaqti tugadi (Timeout)</b>\n\n"
            "Instagram javob bermadi yoki so'rovlarni vaqtincha chekladi (429). "
            "Iltimos, bir ozdan so'ng qayta urinib ko'ring yoki /session orqali Instagram sessionid ulang.",
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

    except RateLimitError as rle:
        await status_msg.edit_text(
            f"⏳ <b>Instagram Rate Limit:</b> {escape_html(str(rle))}",
            parse_mode="HTML"
        )

    except SessionRequiredError as sre:
        await status_msg.edit_text(
            f"🔒 <b>Authentication Required:</b> {escape_html(str(sre))}\n\n"
            "Use <code>/session</code> to view configuration instructions.",
            parse_mode="HTML"
        )

    except InstagramServiceException as ise:
        await status_msg.edit_text(
            f"⚠️ <b>Instagram Error:</b> {escape_html(str(ise))}",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.exception(f"Unexpected error in fetch_and_send_posts: {e}")
        await status_msg.edit_text(
            "⚠️ An unexpected error occurred while downloading posts. Please try again later.",
            parse_mode="HTML"
        )

    finally:
        # Guaranteed cleanup of all downloaded files
        try:
            temp_dir_obj.cleanup()
        except Exception as ce:
            logger.warning(f"Error cleaning up temp directory {temp_dir_path}: {ce}")


async def download_and_send_single_post(message: Message, shortcode: str):
    """
    Downloads and sends a single post/reel by shortcode.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else chat_id

    allowed, wait_sec = await rate_limiter.check(user_id)
    if not allowed:
        await message.answer(
            f"⏳ Please wait <b>{wait_sec}s</b> before another download.",
            parse_mode="HTML"
        )
        return

    status_msg = await message.answer(
        f"⏳ <i>Instagram media yuklab olinmoqda (<code>{escape_html(shortcode)}</code>)...</i>",
        parse_mode="HTML"
    )

    temp_dir_obj = tempfile.TemporaryDirectory(dir=config.TEMP_DIR)
    temp_dir_path = Path(temp_dir_obj.name)
    semaphore = get_download_semaphore()

    try:
        async with semaphore:
            post = await instagram_service.get_post_by_shortcode(
                shortcode=shortcode,
                target_dir=temp_dir_path
            )

        await status_msg.edit_text("📤 <i>Media Telegramga yuborilmoqda...</i>", parse_mode="HTML")

        success = await send_downloaded_post(
            bot=message.bot,
            chat_id=chat_id,
            post=post
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

        if not success:
            await message.answer("⚠️ Mediani Telegramga yuborishda muammo yuz berdi (hajmi juda katta bo'lishi mumkin).")

    except PrivateProfileError:
        await status_msg.edit_text(
            "🔒 <b>Yopiq (Private) post:</b> Ushbu post yopiq profilga tegishli va uni yuklab bo'lmaydi.",
            parse_mode="HTML"
        )
    except MediaNotFoundError:
        await status_msg.edit_text(
            "❌ <b>Post topilmadi:</b> So'ralgan video yoki post topilmadi yoxud o'chirilgan.",
            parse_mode="HTML"
        )
    except RateLimitError as rle:
        await status_msg.edit_text(
            f"⏳ <b>Instagram cheklovi:</b> {escape_html(str(rle))}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.exception(f"Error in download_and_send_single_post: {e}")
        await status_msg.edit_text(
            f"⚠️ Postni yuklab olishda xatolik yuz berdi: {escape_html(str(e))}",
            parse_mode="HTML"
        )
    finally:
        try:
            temp_dir_obj.cleanup()
        except Exception:
            pass
