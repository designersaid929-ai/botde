import os
import logging
from pathlib import Path
from typing import List, Union

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo, Message
from aiogram.exceptions import TelegramBadRequest, TelegramEntityTooLarge

from bot.services.instagram import DownloadedPost, DownloadedStory, MediaItem
from bot.utils.formatters import format_post_caption, format_story_caption
from bot.keyboards.inline import get_media_ai_keyboard

logger = logging.getLogger(__name__)

# Telegram Bot API limits
MAX_TELEGRAM_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_MEDIA_GROUP_SIZE = 10


async def send_downloaded_post(bot: Bot, chat_id: int, post: DownloadedPost) -> bool:
    """
    Sends a downloaded Instagram post to the Telegram chat.
    Handles single images, videos, and multi-item carousels (albums).
    """
    if not post.media_items:
        logger.warning(f"No media items to send for post {post.shortcode}")
        return False

    caption = format_post_caption(
        username=post.username,
        shortcode=post.shortcode,
        caption=post.caption,
        likes=post.likes,
        comments=post.comments,
        date_utc=post.date_utc
    )

    try:
        # Case 1: Single item (photo or video)
        if len(post.media_items) == 1:
            item = post.media_items[0]
            if not _check_file_size(item.path):
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ Media file for post {post.shortcode} exceeds Telegram's 50MB bot upload limit."
                )
                return False

            file_input = FSInputFile(str(item.path))
            post_url = f"https://www.instagram.com/p/{post.shortcode}/" if post.shortcode else ""
            kb = get_media_ai_keyboard(instagram_url=post_url)
            if item.is_video:
                await bot.send_video(
                    chat_id=chat_id,
                    video=file_input,
                    caption=caption,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            else:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=file_input,
                    caption=caption,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            return True

        # Case 2: Multi-item Carousel (Album)
        # Filter valid items that don't exceed Telegram file size limit
        valid_items: List[MediaItem] = [
            m for m in post.media_items if _check_file_size(m.path)
        ]

        if not valid_items:
            await bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ All media files for post {post.shortcode} exceed the 50MB upload limit."
            )
            return False

        # Telegram send_media_group allows max 10 items per group
        chunks = [valid_items[i:i + MAX_MEDIA_GROUP_SIZE] for i in range(0, len(valid_items), MAX_MEDIA_GROUP_SIZE)]

        for chunk_idx, chunk in enumerate(chunks):
            # Only put caption on the first item of the first chunk
            media_group = []
            for item_idx, item in enumerate(chunk):
                item_caption = caption if (chunk_idx == 0 and item_idx == 0) else None
                file_input = FSInputFile(str(item.path))

                if item.is_video:
                    media_group.append(InputMediaVideo(
                        media=file_input,
                        caption=item_caption,
                        parse_mode="HTML" if item_caption else None
                    ))
                else:
                    media_group.append(InputMediaPhoto(
                        media=file_input,
                        caption=item_caption,
                        parse_mode="HTML" if item_caption else None
                    ))

            if len(media_group) == 1:
                # If chunk has only 1 item, send single media
                single = chunk[0]
                single_input = FSInputFile(str(single.path))
                if single.is_video:
                    await bot.send_video(chat_id=chat_id, video=single_input, caption=caption, parse_mode="HTML")
                else:
                    await bot.send_photo(chat_id=chat_id, photo=single_input, caption=caption, parse_mode="HTML")
            else:
                await bot.send_media_group(chat_id=chat_id, media=media_group)

        if len(valid_items) > 1:
            post_url = f"https://www.instagram.com/p/{post.shortcode}/" if post.shortcode else ""
            kb = get_media_ai_keyboard(instagram_url=post_url)
            await bot.send_message(
                chat_id=chat_id,
                text=f"🤖 <b>@{post.username}</b> posti uchun AI yordamchi:",
                reply_markup=kb,
                parse_mode="HTML"
            )

        return True

    except TelegramEntityTooLarge:
        logger.error(f"TelegramEntityTooLarge for post {post.shortcode}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ Media for post {post.shortcode} is too large for Telegram bot API."
        )
        return False
    except TelegramBadRequest as tbe:
        logger.error(f"TelegramBadRequest sending post {post.shortcode}: {tbe}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ Could not send media: {tbe.message}"
        )
        return False
    except Exception as e:
        logger.exception(f"Unexpected error sending post {post.shortcode}: {e}")
        return False


async def send_downloaded_story(bot: Bot, chat_id: int, story: DownloadedStory) -> bool:
    """
    Sends a downloaded Instagram story item (photo or video) to the Telegram chat.
    """
    if not _check_file_size(story.media_item.path):
        await bot.send_message(
            chat_id=chat_id,
            text="⚠️ Story media file exceeds Telegram's 50MB upload limit."
        )
        return False

    caption = format_story_caption(
        username=story.owner_username,
        date_utc=story.date_utc,
        expiring_utc=story.expiring_utc,
        caption=story.caption
    )

    file_input = FSInputFile(str(story.media_item.path))
    story_url = f"https://www.instagram.com/{story.owner_username}/"
    kb = get_media_ai_keyboard(instagram_url=story_url)

    try:
        if story.media_item.is_video:
            await bot.send_video(
                chat_id=chat_id,
                video=file_input,
                caption=caption,
                reply_markup=kb,
                parse_mode="HTML"
            )
        else:
            await bot.send_photo(
                chat_id=chat_id,
                photo=file_input,
                caption=caption,
                reply_markup=kb,
                parse_mode="HTML"
            )
        return True
    except Exception as e:
        logger.error(f"Error sending story from @{story.owner_username}: {e}")
        return False


def _check_file_size(file_path: Path) -> bool:
    """Checks if file is within Telegram's 50MB bot upload limit."""
    try:
        return file_path.stat().st_size <= MAX_TELEGRAM_FILE_SIZE_BYTES
    except Exception:
        return False
