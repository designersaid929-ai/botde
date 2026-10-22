import io
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.enums import ChatAction, ChatType

from bot.config import config
from bot.services.ai import gemini_service
from bot.services.tts import generate_voice_audio
from bot.services.subscription import check_user_subscription, get_subscription_keyboard
from bot.states.ai_states import AIChatStates
from bot.keyboards.reply import get_ai_chat_keyboard, remove_reply_keyboard
from bot.keyboards.inline import (
    get_ai_menu_keyboard,
    get_tts_listen_keyboard,
    get_media_ai_keyboard,
    get_ai_media_options_keyboard
)
from bot.utils.formatters import split_text_safely, escape_html



logger = logging.getLogger(__name__)
router = Router(name="ai_router")


def _extract_media_info(message: Message):
    """
    Extracts file_id, is_video, and caption from a message (direct or reply).
    Supports video, photo, document (video/image), animation.
    """
    if not message:
        return None, False, ""

    caption = message.caption or message.text or ""

    if message.video:
        return message.video.file_id, True, caption
    if message.photo:
        return message.photo[-1].file_id, False, caption
    if message.animation:
        return message.animation.file_id, True, caption
    if message.document:
        mime = message.document.mime_type or ""
        if "video" in mime:
            return message.document.file_id, True, caption
        if "image" in mime:
            return message.document.file_id, False, caption

    # Check if target has a reply
    if message.reply_to_message:
        rep = message.reply_to_message
        rep_caption = rep.caption or rep.text or ""
        if rep.video:
            return rep.video.file_id, True, rep_caption
        if rep.photo:
            return rep.photo[-1].file_id, False, rep_caption
        if rep.animation:
            return rep.animation.file_id, True, rep_caption
        if rep.document:
            mime = rep.document.mime_type or ""
            if "video" in mime:
                return rep.document.file_id, True, rep_caption
            if "image" in mime:
                return rep.document.file_id, False, rep_caption

    return None, False, caption


async def _process_media_analysis(
    bot,
    chat_id: int,
    reply_to_message_id: int,
    file_id: str,
    is_video: bool,
    caption: str,
    prompt: str
):
    """Downloads media from Telegram and analyzes it using Gemini Multimodal."""
    status_msg = await bot.send_message(
        chat_id=chat_id,
        text="⏳ <i>Media tahlil qilinmoqda, iltimos kuting...</i>",
        reply_to_message_id=reply_to_message_id,
        parse_mode="HTML"
    )
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    import tempfile
    from pathlib import Path

    suffix = ".mp4" if is_video else ".jpg"
    tmp_path = None
    try:
        tg_file = await bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)

        await bot.download_file(tg_file.file_path, destination=tmp_path)

        reply = await gemini_service.analyze_media(
            file_path=tmp_path,
            prompt=prompt,
            is_video=is_video,
            caption_context=caption
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

        chunks = split_text_safely(reply)
        for idx, chunk in enumerate(chunks):
            is_last = (idx == len(chunks) - 1)
            kb = get_tts_listen_keyboard() if is_last else None
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_to_message_id=reply_to_message_id if idx == 0 else None,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_to_message_id=reply_to_message_id if idx == 0 else None,
                    reply_markup=kb,
                    parse_mode=None
                )

    except Exception as e:
        logger.error(f"Error analyzing media: {e}", exc_info=True)
        try:
            await status_msg.edit_text(f"❌ <b>Tahlil qilishda xatolik:</b> {escape_html(str(e)[:200])}", parse_mode="HTML")
        except Exception:
            pass
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


@router.message(Command("ai"))
async def handle_ai_command(message: Message, state: FSMContext):
    """
    Handles /ai command.
    If replied to a video/photo/story post, analyzes that media!
    Otherwise standard AI chat interaction.
    """
    user_id = message.from_user.id if message.from_user else 0
    if user_id:
        is_sub, unsub = await check_user_subscription(message.bot, user_id)
        if not is_sub:
            await message.reply(
                "⚠️ <b>Botdan foydalanish uchun rasmiy kanalimizga a'zo bo'ling!</b>\n\n"
                "Quyidagi havola orqali kanalga kiring va obuna bo'ling, so'ngra <b>'✅ Obunani tekshirish'</b> tugmasini bosing:",
                reply_markup=get_subscription_keyboard(unsub),
                parse_mode="HTML"
            )
            return

    parts = message.text.strip().split(maxsplit=1)

    # Check if this /ai command is replied to a media message
    if message.reply_to_message:
        file_id, is_video, caption = _extract_media_info(message.reply_to_message)
        if file_id:
            prompt = parts[1].strip() if len(parts) > 1 else "Ushbu media (video/rasm) da nima sodir bo'layotganini va uning to'liq mazmunini qisqa, aniq va tushunarli bayon qilib ber."
            await _process_media_analysis(
                bot=message.bot,
                chat_id=message.chat.id,
                reply_to_message_id=message.message_id,
                file_id=file_id,
                is_video=is_video,
                caption=caption,
                prompt=prompt
            )
            return

    # One-shot query: /ai <prompt>
    if len(parts) > 1:
        prompt = parts[1].strip()
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        reply = await gemini_service.ask_chat(user_id, prompt)
        chunks = split_text_safely(reply)
        for idx, chunk in enumerate(chunks):
            is_last = (idx == len(chunks) - 1)
            kb = get_tts_listen_keyboard() if is_last else None
            try:
                await message.reply(chunk, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await message.reply(chunk, reply_markup=kb, parse_mode=None)
        return

    # In groups without arguments, inform user how to use
    chat_type = getattr(message.chat, "type", ChatType.PRIVATE)
    if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await message.reply(
            "ℹ️ <b>Guruhda foydalanish:</b> <code>/ai &lt;savolingiz&gt;</code>\n"
            "Yoki botning xabariga javob (Reply) berib, yoxud bot nomini yozib savol bering (masalan: <code>@bot savolingiz</code>).",
            parse_mode="HTML"
        )
        return

    # Enter interactive AI Chat mode (private chats)
    await state.set_state(AIChatStates.chatting)
    key_status = "✅ Faol" if gemini_service.is_configured else "❌ O'rnatilmagan"

    text = (
        "🤖 <b>Gemini AI Chat rejimiga xush kelibsiz!</b>\n\n"
        f"• <b>API Kalit holati:</b> {key_status}\n"
        f"• <b>Model:</b> <code>{config.GEMINI_MODEL}</code>\n\n"
        "💡 <b>Imkoniyatlar:</b>\n"
        "• Menga istalgan savolingizni matn ko'rinishida yozing;\n"
        "• Ovozli xabar yuborsangiz, ovoz bilan ham javob beraman;\n"
        "• Rasm yuborsangiz, rasmni tahlil qilib beraman;\n"
        "• Suhbat xotirasi saqlanadi (oldingi savollarni eslab qolaman);\n"
        "• Chiqish uchun pastdagi <b>'❌ AI Chatdan chiqish'</b> tugmasini bosing yoki /stop yozing."
    )
    await message.answer(text, reply_markup=get_ai_chat_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "ai:enter")
async def handle_ai_enter_callback(callback: CallbackQuery, state: FSMContext):
    """Enters AI chat mode via inline button."""
    await state.set_state(AIChatStates.chatting)
    await callback.answer("🤖 AI Chat rejimi faollashdi!")

    key_status = "✅ Faol" if gemini_service.is_configured else "❌ O'rnatilmagan"
    text = (
        "🤖 <b>Gemini AI Chat rejimi faollashdi!</b>\n\n"
        f"• <b>API Kalit holati:</b> {key_status}\n"
        f"• <b>Model:</b> <code>{config.GEMINI_MODEL}</code>\n\n"
        "Endi menga istalgan savol yoki rasm yuborishingiz mumkin. "
        "AI Chatdan chiqish uchun pastdagi <b>'❌ AI Chatdan chiqish'</b> tugmasini bosing."
    )
    await callback.message.answer(text, reply_markup=get_ai_chat_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "ai:key_settings")
async def handle_ai_key_settings_callback(callback: CallbackQuery, state: FSMContext):
    """Prompts user to send their Gemini API key."""
    await callback.answer()
    await state.set_state(AIChatStates.waiting_for_api_key)

    text = (
        "🔑 <b>Google Gemini API Kalitini sozlash</b>\n\n"
        "Gemini API kalitingizni shu yerga xabar sifatida yuboring.\n\n"
        "🌐 Agar sizda kalit bo'lmasa, uni bepul olishingiz mumkin:\n"
        "1. <a href='https://aistudio.google.com/'>Google AI Studio</a> saytiga kiring\n"
        "2. <b>'Get API key'</b> tugmasini bosing va yangi kalit yarating\n"
        "3. Kalitni nusxalab, shu yerga yuboring.\n\n"
        "<i>Bekor qilish uchun /cancel deb yozing.</i>"
    )
    await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@router.callback_query(F.data == "ai:reset")
async def handle_ai_reset_callback(callback: CallbackQuery):
    """Resets user AI chat history via inline button."""
    gemini_service.reset_user_chat(callback.from_user.id)
    await callback.answer("🧹 AI suhbat xotirasi tozalandi!", show_alert=True)


@router.message(Command("setkey"))
async def handle_setkey_command(message: Message, state: FSMContext):
    """
    Sets Gemini API key via /setkey <key> or prompts for it.
    """
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) > 1:
        new_key = parts[1].strip()
        success = gemini_service.set_api_key(new_key)
        if success:
            await message.reply(
                "✅ <b>Gemini API kaliti muvaffaqiyatli saqlandi!</b>\n\n"
                "Endi AI Chatdan to'liq foydalanishingiz mumkin: /ai",
                parse_mode="HTML"
            )
        else:
            await message.reply("❌ Kalit bo'sh bo'lishi mumkin emas.", parse_mode="HTML")
        return

    # If no key was provided in command, ask for it
    await state.set_state(AIChatStates.waiting_for_api_key)
    await message.reply(
        "🔑 <b>Iltimos, Google Gemini API kalitingizni yuboring:</b>\n\n"
        "<i>Bekor qilish uchun: /cancel</i>",
        parse_mode="HTML"
    )


@router.message(AIChatStates.waiting_for_api_key, Command("cancel"))
async def handle_cancel_key_input(message: Message, state: FSMContext):
    """Cancels API key input state."""
    await state.clear()
    await message.reply(
        "🚫 API kalit kiritish bekor qilindi.",
        reply_markup=remove_reply_keyboard(),
        parse_mode="HTML"
    )


@router.message(AIChatStates.waiting_for_api_key, F.text)
async def handle_api_key_input(message: Message, state: FSMContext):
    """Receives and saves Gemini API key from user text."""
    key = message.text.strip()
    if key.startswith("/"):
        await state.clear()
        return

    # Delete message containing sensitive API key if bot has rights, for privacy
    try:
        await message.delete()
    except Exception:
        pass

    success = gemini_service.set_api_key(key)
    await state.clear()

    if success:
        await message.answer(
            "✅ <b>Gemini API kaliti muvaffaqiyatli qabul qilindi va saqlandi!</b>\n\n"
            "Maxfiylik maqsadida kalitingiz bo'lgan xabar o'chirildi.\n"
            "Endi bemalol <b>/ai</b> buyrug'i orqali muloqotni boshlashingiz mumkin!",
            reply_markup=get_ai_chat_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(AIChatStates.chatting)
    else:
        await message.answer(
            "❌ Kalitni saqlashda xatolik yuz berdi. Iltimos qaytadan urinib ko'ring: /setkey",
            reply_markup=remove_reply_keyboard(),
            parse_mode="HTML"
        )


@router.message(AIChatStates.chatting, F.text.in_(["❌ AI Chatdan chiqish", "/exit", "/stop"]))
async def handle_ai_exit(message: Message, state: FSMContext):
    """Exits active AI Chat mode and returns to normal Instagram downloader mode."""
    await state.clear()
    await message.answer(
        "👋 <b>AI Chat rejimi yakunlandi.</b>\n\n"
        "Endi siz yana Instagram post/stories linklarini yoki foydalanuvchi nomlarini yuborishingiz mumkin.",
        reply_markup=remove_reply_keyboard(),
        parse_mode="HTML"
    )


@router.message(AIChatStates.chatting, F.text.in_(["🧹 Yangi suhbat", "/newchat"]))
async def handle_ai_new_chat(message: Message):
    """Clears conversational memory for current user."""
    gemini_service.reset_user_chat(message.from_user.id)
    await message.answer(
        "🧹 <b>Suhbat xotirasi tozalandi!</b>\n"
        "Yangi mavzu bo'yicha savollaringizni berishingiz mumkin.",
        parse_mode="HTML"
    )


@router.message(AIChatStates.chatting, F.text.in_(["🔑 API Kalit", "/key"]))
async def handle_ai_key_info(message: Message, state: FSMContext):
    """Shows API key status and button to update."""
    status = "✅ Faol o'rnatilgan" if gemini_service.is_configured else "❌ O'rnatilmagan"
    await message.answer(
        f"🔑 <b>Gemini API Kalit Holati:</b> {status}\n\n"
        "Yangi kalit kiritish uchun: <code>/setkey &lt;kalit&gt;</code> yozing yoki pastdagi tugmani bosing.",
        reply_markup=get_ai_menu_keyboard(has_key=gemini_service.is_configured),
        parse_mode="HTML"
    )


@router.message(AIChatStates.chatting, F.photo)
async def handle_ai_photo_chat(message: Message):
    """
    Handles user photo upload in AI Chat mode and analyzes it with Gemini Vision.
    """
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    prompt = message.caption or "Iltimos, ushbu rasmda nimalar aks etganini batafsil tushuntirib bering."

    try:
        # Download highest resolution photo
        photo = message.photo[-1]
        file_io = io.BytesIO()
        await message.bot.download(photo.file_id, destination=file_io)
        image_bytes = file_io.getvalue()

        reply = await gemini_service.ask_vision(
            image_bytes=image_bytes,
            mime_type="image/jpeg",
            prompt=prompt
        )

        chunks = split_text_safely(reply)
        for chunk in chunks:
            try:
                await message.reply(chunk, parse_mode="HTML")
            except Exception:
                await message.reply(chunk, parse_mode=None)

    except Exception as e:
        logger.error(f"Error processing AI photo: {e}")
        await message.reply(f"❌ Rasmni qayta ishlashda xatolik yuz berdi: {escape_html(str(e)[:150])}", parse_mode="HTML")


@router.message(AIChatStates.chatting, F.text & ~F.text.startswith("/"))
async def handle_ai_text_chat(message: Message):
    """
    Handles text messages during AI Chat mode and communicates with Gemini.
    """
    user_id = message.from_user.id if message.from_user else 0
    prompt = message.text.strip()
    if not prompt:
        return

    # Show typing indicator
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    # Query Gemini
    reply = await gemini_service.ask_chat(user_id=user_id, prompt=prompt)

    # Deliver reply to user (splitting if longer than Telegram limit)
    chunks = split_text_safely(reply)
    for idx, chunk in enumerate(chunks):
        # Attach voice listen button to the final message chunk
        is_last = (idx == len(chunks) - 1)
        kb = get_tts_listen_keyboard() if is_last else None
        try:
            await message.reply(chunk, reply_markup=kb, parse_mode="HTML")
        except Exception:
            # Fallback without parse_mode if AI output had unbalanced HTML tags
            await message.reply(chunk, reply_markup=kb, parse_mode=None)


@router.callback_query(F.data == "ai:tts_listen")
async def handle_tts_listen_callback(callback: CallbackQuery):
    """
    Synthesizes and sends the clicked AI message as a voice message.
    """
    msg = callback.message
    text_content = msg.text or msg.caption or ""
    if not text_content:
        await callback.answer("O'qish uchun matn topilmadi.", show_alert=True)
        return

    await callback.answer("🎙️ Ovoz tayyorlanmoqda...")
    await callback.bot.send_chat_action(chat_id=msg.chat.id, action=ChatAction.RECORD_VOICE)

    audio_bytes = await generate_voice_audio(text_content)
    if not audio_bytes:
        await callback.message.reply("❌ Ovoz hosil qilishda xatolik yuz berdi.")
        return

    voice_file = BufferedInputFile(audio_bytes, filename="voice_response.ogg")
    await callback.message.reply_voice(voice=voice_file, caption="🎙️ <i>Ovozli javob</i>", parse_mode="HTML")


@router.message(AIChatStates.chatting, F.voice | F.audio)
@router.message(F.voice | F.audio)
async def handle_voice_message(message: Message):
    """
    Receives voice/audio messages, queries Gemini Multimodal Audio, 
    and replies both with text and synthesized voice response.
    In groups, strictly only responds if replied to the bot itself.
    """
    is_group = getattr(message.chat, "type", ChatType.PRIVATE) in [ChatType.GROUP, ChatType.SUPERGROUP]
    bot_info = await message.bot.get_me()

    # In groups, only process if the voice message is a reply to the bot
    if is_group:
        if not (message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot_info.id):
            return

    user_id = message.from_user.id if message.from_user else 0
    if user_id:
        is_sub, unsub = await check_user_subscription(message.bot, user_id)
        if not is_sub:
            name = message.from_user.first_name if message.from_user else "foydalanuvchi"
            await message.reply(
                f"⚠️ Hurmatli <b>{escape_html(name)}</b>, botdan foydalanish uchun rasmiy kanalimizga a'zo bo'ling:",
                reply_markup=get_subscription_keyboard(unsub),
                parse_mode="HTML"
            )
            return

    # Notify user that bot is listening
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.RECORD_VOICE)

    voice_obj = message.voice or message.audio
    if not voice_obj:
        return

    try:
        file_io = io.BytesIO()
        await message.bot.download(voice_obj.file_id, destination=file_io)
        audio_bytes = file_io.getvalue()
        mime_type = voice_obj.mime_type or "audio/ogg"

        # Ask Gemini Audio
        reply = await gemini_service.ask_audio(
            user_id=user_id,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            prompt=message.caption or ""
        )

        # Send text response
        chunks = split_text_safely(reply)
        for idx, chunk in enumerate(chunks):
            is_last = (idx == len(chunks) - 1)
            kb = get_tts_listen_keyboard() if is_last else None
            try:
                await message.reply(chunk, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await message.reply(chunk, reply_markup=kb, parse_mode=None)

        # Also synthesize and send voice response back automatically
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.RECORD_VOICE)
        synth_bytes = await generate_voice_audio(reply)
        if synth_bytes:
            voice_file = BufferedInputFile(synth_bytes, filename="voice_answer.ogg")
            await message.reply_voice(
                voice=voice_file,
                caption="🎙️ <b>Ovozli javob</b>",
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Error handling voice message: {e}")
        await message.reply(
            f"❌ Ovozli xabarni qayta ishlashda xatolik yuz berdi: {escape_html(str(e)[:150])}",
            parse_mode="HTML"
        )


@router.message(F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]), F.text & ~F.text.startswith("/"))
async def handle_group_chat_query(message: Message):
    """
    Handles messages in groups/supergroups.
    Strictly only triggers when the bot is invoked:
    1. By replying to the bot's message
    2. By mentioning the bot (@bot_username)
    Never interferes with regular chats between group members!
    """
    bot_info = await message.bot.get_me()
    bot_username = (bot_info.username or "").lower()

    is_reply_to_bot = bool(
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == bot_info.id
    )

    raw_text = message.text.strip()
    is_mention = f"@{bot_username}" in raw_text.lower() if bot_username else False

    # If bot was not invoked, ignore completely to respect group privacy
    if not (is_reply_to_bot or is_mention):
        return

    # Check channel subscription for the invoking user
    user = message.from_user
    if user:
        is_sub, unsub = await check_user_subscription(message.bot, user.id)
        if not is_sub:
            await message.reply(
                f"⚠️ Hurmatli <b>{escape_html(user.first_name)}</b>, botdan guruhda foydalanish uchun ham rasmiy kanalimizga a'zo bo'lishingiz kerak:",
                reply_markup=get_subscription_keyboard(unsub),
                parse_mode="HTML"
            )
            return

    # Clean the bot mention from query text
    clean_prompt = raw_text
    if bot_username:
        import re
        clean_prompt = re.sub(rf"@{re.escape(bot_username)}\b", "", clean_prompt, flags=re.IGNORECASE).strip()

    if not clean_prompt:
        await message.reply(
            "👋 Assalomu alaykum! Savolingizni yozing, sizga mamnuniyat bilan javob beraman.",
            parse_mode="HTML"
        )
        return

    # Show typing action in group
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    # Ask Gemini
    user_id = user.id if user else message.chat.id
    reply = await gemini_service.ask_chat(user_id=user_id, prompt=clean_prompt)

    # Deliver reply to group
    chunks = split_text_safely(reply)
    for idx, chunk in enumerate(chunks):
        is_last = (idx == len(chunks) - 1)
        kb = get_tts_listen_keyboard() if is_last else None
        try:
            await message.reply(chunk, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await message.reply(chunk, reply_markup=kb, parse_mode=None)


@router.callback_query(F.data == "media_ai:options")
async def handle_media_ai_options(callback: CallbackQuery):
    """Shows analysis choices for the Instagram media."""
    await callback.answer()
    text = (
        "🤖 <b>Instagram Mediasini Tahlil Qilish</b>\n\n"
        "Quyidagi imkoniyatlardan birini tanlang yoki o'z savolingizni bering:\n\n"
        "• 🎬 <b>Mazmunini tushuntir:</b> Video yoki rasmda nima sodir bo'layotganini bayon qiladi.\n"
        "• 🎙️ <b>Nutqni matnga aylantir:</b> Videodagi nutqni matnga o'giradi va tarjima qiladi.\n"
        "• 🔍 <b>Matnlarni aniqlash:</b> Media ichidagi yozuvlar va OCR.\n"
        "• 🛍️ <b>Buyum va joylar:</b> Mahsulotlar, kiyimlar va lokatsiyalarni tasvirlaydi.\n"
        "• 🎯 <b>Asosiy g'oya va maqsad:</b> Post maqsadi va asosiy g'oyasi.\n"
        "• 🏷️ <b>Caption & Hashtaglar:</b> Tavsiya etilgan sarlavha va hashtaglar.\n"
        "• ❓ <b>O'z savolimni berish:</b> Istalgan savolingizni berishingiz mumkin."
    )
    await callback.message.reply(text, reply_markup=get_ai_media_options_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("media_ai:"))
async def handle_media_ai_action(callback: CallbackQuery, state: FSMContext):
    """Executes the selected analysis action on the Instagram media."""
    action = callback.data.split(":", 1)[1]
    if action == "options":
        return

    if action == "cancel":
        await callback.answer("Bekor qilindi.")
        try:
            await callback.message.delete()
        except Exception:
            pass
        return

    source_msg = callback.message.reply_to_message or callback.message
    file_id, is_video, caption = _extract_media_info(source_msg)

    if action == "custom_ask":
        await callback.answer()
        if not file_id:
            await callback.message.reply("❌ Media fayli topilmadi.")
            return

        await state.set_state(AIChatStates.waiting_for_media_question)
        await state.update_data(
            media_file_id=file_id,
            is_video=is_video,
            media_caption=caption
        )
        await callback.message.reply(
            "✍️ <b>Ushbu media bo'yicha savolingizni yozing:</b>\n\n"
            "<i>(Matn ko'rinishida yozishingiz yoki ovozli xabar yuborishingiz mumkin. Bekor qilish: /cancel)</i>",
            parse_mode="HTML"
        )
        return

    prompts_map = {
        "summary": "Ushbu media (video/rasm) da nima sodir bo'layotganini va uning to'liq mazmunini qisqa, aniq va tushunarli bayon qilib ber.",
        "transcribe": "Ushbu videodagi nutqni tinglab, uni so'zma-so'z matnga aylantir (transkripsiya) va o'zbek tiliga tushunarli qilib ber.",
        "ocr": "Ushbu video yoki rasmdagi barcha ko'rinib turgan matnlar, yozuvlar, belgilar va titrlarni aniqlab ro'yxat qilib yozib ber.",
        "objects": "Ushbu video/rasmda aks etgan kiyimlar, buyumlar, mahsulotlar, odamlar va joylar/lokatsiyalarni batafsil tasvirlab ber.",
        "purpose": "Ushbu post va videoning asosiy maqsadi, g'oyasi va auditoriyaga yetkazmoqchi bo'lgan asosiy xabari nimadan iborat?",
        "hashtags": "Ushbu media uchun Instagramga mos chiroyli caption (sarlavha) va mashhur, trenddagi hashtaglar to'plamini tuzib ber."
    }

    prompt = prompts_map.get(action)
    if not prompt:
        await callback.answer("Noma'lum amal.")
        return

    if not file_id:
        await callback.answer("Media fayli topilmadi.", show_alert=True)
        return

    await callback.answer("⏳ Media tahlil qilinmoqda...")
    await _process_media_analysis(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        reply_to_message_id=callback.message.message_id,
        file_id=file_id,
        is_video=is_video,
        caption=caption,
        prompt=prompt
    )


@router.message(AIChatStates.waiting_for_media_question, Command("cancel"))
async def handle_cancel_media_question(message: Message, state: FSMContext):
    """Cancels waiting for custom media question."""
    await state.clear()
    await message.reply("🚫 Media bo'yicha savol bekor qilindi.", parse_mode="HTML")


@router.message(AIChatStates.waiting_for_media_question)
async def handle_custom_media_question_input(message: Message, state: FSMContext):
    """Processes custom user question on the selected media."""
    data = await state.get_data()
    file_id = data.get("media_file_id")
    is_video = data.get("is_video", False)
    caption = data.get("media_caption", "")

    if not file_id:
        await state.clear()
        await message.reply("❌ Media fayl ma'lumotlari topilmadi. Qaytadan urinib ko'ring.")
        return

    # Extract prompt: text or voice
    user_prompt = message.text or message.caption or ""
    if message.voice or message.audio:
        voice_obj = message.voice or message.audio
        file_io = io.BytesIO()
        await message.bot.download(voice_obj.file_id, destination=file_io)
        voice_prompt = await gemini_service.ask_audio(
            user_id=message.from_user.id,
            audio_bytes=file_io.getvalue(),
            mime_type=voice_obj.mime_type or "audio/ogg",
            prompt="Foydalanuvchi aytgan gap yoki savolni o'zbek tilida qisqa matn qilib yozib ber:"
        )
        user_prompt = voice_prompt

    if not user_prompt:
        await message.reply("Iltimos, savolingizni yozing yoki ovozli xabar yuboring.")
        return

    await state.clear()
    await _process_media_analysis(
        bot=message.bot,
        chat_id=message.chat.id,
        reply_to_message_id=message.message_id,
        file_id=file_id,
        is_video=is_video,
        caption=caption,
        prompt=user_prompt
    )


@router.message(F.reply_to_message & F.text & ~F.text.startswith("/"))
async def handle_reply_media_question(message: Message):
    """
    Automatically triggers when user replies to any photo or video with a question.
    """
    bot_info = await message.bot.get_me()
    is_private = getattr(message.chat, "type", ChatType.PRIVATE) == ChatType.PRIVATE
    is_reply_to_bot = bool(
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == bot_info.id
    )

    if not (is_private or is_reply_to_bot):
        return

    file_id, is_video, caption = _extract_media_info(message.reply_to_message)
    if not file_id:
        return

    await _process_media_analysis(
        bot=message.bot,
        chat_id=message.chat.id,
        reply_to_message_id=message.message_id,
        file_id=file_id,
        is_video=is_video,
        caption=caption,
        prompt=message.text.strip()
    )


