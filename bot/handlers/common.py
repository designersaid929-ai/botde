import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery

from bot.services.instagram import instagram_service
from bot.utils.formatters import escape_html

logger = logging.getLogger(__name__)
router = Router(name="common_router")


@router.message(CommandStart())
async def handle_start(message: Message):
    """Handles /start command with an engaging welcome message and usage instructions."""
    from bot.services.stats import track_user
    from bot.config import config
    
    user = message.from_user
    if user:
        first_name = getattr(user, "first_name", "") or ""
        last_name = getattr(user, "last_name", "") or ""
        username = getattr(user, "username", "") or ""
        is_new = await track_user(user.id, username, first_name, last_name)
        if is_new and config.ADMIN_ID:
            try:
                uname = f"@{username}" if username else "mavjud emas"
                name = f"{first_name} {last_name}".strip() or "Noma'lum"
                admin_alert = (
                    "🟢 <b>Yangi foydalanuvchi botga kirdi!</b>\n\n"
                    f"• <b>Ism:</b> {escape_html(name)}\n"
                    f"• <b>Username:</b> {uname}\n"
                    f"• <b>ID:</b> <code>{user.id}</code>"
                )
                await message.bot.send_message(chat_id=config.ADMIN_ID, text=admin_alert, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Could not notify admin of new user: {e}")

    from bot.keyboards.inline import get_welcome_keyboard
    from bot.services.subscription import check_user_subscription, get_subscription_keyboard

    # Check required channel subscription
    if user:
        is_sub, unsub = await check_user_subscription(message.bot, user.id)
        if not is_sub:
            await message.answer(
                "👋 <b>Assalomu alaykum!</b>\n\n"
                "Botimizdan to'liq foydalanish uchun rasmiy kanalimizga a'zo bo'lishingiz kerak.\n"
                "Quyidagi havola orqali kanalga kiring va a'zo bo'lgach, <b>'✅ Obunani tekshirish'</b> tugmasini bosing:",
                reply_markup=get_subscription_keyboard(unsub),
                parse_mode="HTML"
            )
            return

    welcome_text = (
        "👋 <b>Instagram Media Downloader & Gemini AI Botga xush kelibsiz!</b>\n\n"
        "Men Instagramdan video/rasm yuklab beruvchi va <b>Google Gemini AI</b> bilan muloqot qiluvchi ko'p tarmoqli aqlli botman.\n\n"
        "⚡ <b>Instagram Yuklovchi:</b>\n"
        "• Profil nomi (masalan: <code>nasa</code> yoki <code>@cristiano</code>)\n"
        "• Profil havolasi (masalan: <code>https://instagram.com/cristiano</code>)\n"
        "• Post / Reel havolasi (masalan: <code>https://instagram.com/p/...</code>)\n\n"
        "🤖 <b>Gemini AI Chat:</b>\n"
        "• <code>/ai</code> - Sun'iy intellekt bilan to'g'ridan-to'g'ri muloqot rejimi\n"
        "• <code>/ai &lt;savol&gt;</code> - Bir martalik tezkor savolga javob\n"
        "• 🎙️ Ovozli xabar yuborsangiz, AI ovoz bilan ham javob beradi!\n"
        "• 👥 Guruhda botga javob (Reply) berib yoki @username orqali chaqirsangiz javob beradi.\n\n"
        "📋 <b>Boshqa buyruqlar:</b>\n"
        "• <code>/check &lt;user&gt;</code> - Profil holatini tekshirish\n"
        "• <code>/posts &lt;user&gt; [soni]</code> - Postlarni yuklash\n"
        "• <code>/stories &lt;user&gt;</code> - Stories yuklash\n"
        "• <code>/help</code> - Batafsil qo'llanma"
    )
    await message.answer(welcome_text, reply_markup=get_welcome_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "sub:check")
async def handle_sub_check_callback(callback: CallbackQuery):
    """Handles verification button when user taps 'Obunani tekshirish'."""
    from bot.services.subscription import check_user_subscription, get_subscription_keyboard
    from bot.keyboards.inline import get_welcome_keyboard

    user_id = callback.from_user.id
    is_sub, unsub = await check_user_subscription(callback.bot, user_id)

    if is_sub:
        await callback.answer("✅ Rahmat! Obunangiz muvaffaqiyatli tasdiqlandi.", show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass

        welcome_text = (
            "🎉 <b>Kanalga a'zo bo'lganingiz tasdiqlandi!</b>\n\n"
            "Endi siz botning barcha imkoniyatlaridan (Instagram yuklovchi, Gemini AI suhbat, ovozli xabarlar) "
            "to'liq va bepul foydalanishingiz mumkin."
        )
        await callback.message.answer(welcome_text, reply_markup=get_welcome_keyboard(), parse_mode="HTML")
    else:
        await callback.answer(
            "❌ Siz hali talab qilingan kanalga obuna bo'lmadingiz! Iltimos, kanalga kiring va obuna bo'ling.",
            show_alert=True
        )


@router.message(Command("setchannel"))
async def handle_setchannel(message: Message):
    """Admin command to set required channel for subscription."""
    from bot.config import config
    from bot.services.subscription import set_required_channels

    # Only admin
    if config.ADMIN_ID and message.from_user and message.from_user.id != config.ADMIN_ID:
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        curr = config.REQUIRED_CHANNELS or "O'rnatilmagan"
        await message.answer(
            f"ℹ️ <b>Joriy talab qilinadigan kanal:</b> <code>{curr}</code>\n\n"
            "Yangi kanal o'rnatish uchun:\n"
            "<code>/setchannel @kanal_nomi</code>\n"
            "yoki bir nechta bo'lsa: <code>/setchannel @kanal1, @kanal2</code>\n\n"
            "<i>Eslatma: Bot kanalga admin qilib qo'yilgan bo'lishi kerak!</i>",
            parse_mode="HTML"
        )
        return

    channel_input = parts[1].strip()
    success = set_required_channels(channel_input)
    if success:
        await message.answer(
            f"✅ <b>Majburiy obuna kanali muvaffaqiyatli saqlandi!</b>\n\n"
            f"• <b>Kanal:</b> <code>{channel_input}</code>\n"
            "Endi barcha yangi foydalanuvchilar ushbu kanalga a'zo bo'lmaguncha botdan foydalana olmaydi.",
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Kanalni saqlashda xatolik yuz berdi.", parse_mode="HTML")



@router.message(Command("setadmin"))
async def handle_setadmin(message: Message):
    """Sets the current user as bot admin and saves to .env."""
    from bot.config import config
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    try:
        import re
        env_path = config.BASE_DIR / ".env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            if "ADMIN_ID=" in content:
                new_content = re.sub(r"ADMIN_ID=.*", f"ADMIN_ID={user_id}", content)
            else:
                new_content = content + f"\nADMIN_ID={user_id}\n"
            env_path.write_text(new_content, encoding="utf-8")
        
        # Update running config
        object.__setattr__(config, "ADMIN_ID", user_id)
        await message.answer(
            f"👑 <b>Siz muvaffaqiyatli Bot Admini etib belgilandingiz!</b>\n\n"
            f"• <b>Admin ID:</b> <code>{user_id}</code>\n"
            "• Endi yangi foydalanuvchilar kirganda va ular qidiruv berganda sizga bildirishnoma kelib turadi.\n"
            "• Statistikani ko'rish uchun: <code>/admin</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error setting admin: {e}")
        await message.answer("❌ Adminni sozlashda xatolik yuz berdi.", parse_mode="HTML")


@router.message(Command("admin"))
async def handle_admin(message: Message):
    """Admin statistics command."""
    from bot.services.stats import get_stats
    from bot.config import config

    # Check if admin
    if config.ADMIN_ID and message.from_user and message.from_user.id != config.ADMIN_ID:
        return

    stats = await get_stats()
    top_text = ""
    if stats["top_queries"]:
        top_text = "\n\n🔥 <b>Eng ko'p qidirilganlar:</b>\n"
        for idx, t in enumerate(stats["top_queries"], 1):
            top_text += f"{idx}. <code>{escape_html(t['query'])}</code> ({t['count']} marta)\n"

    report = (
        "📊 <b>Bot Statistikasi (Admin panel):</b>\n\n"
        f"• 👥 <b>Jami foydalanuvchilar:</b> {stats['total_users']:,} ta\n"
        f"• 🔍 <b>Jami qidiruvlar soni:</b> {stats['total_queries']:,} ta\n"
        f"• 📅 <b>Bugungi qidiruvlar:</b> {stats['today_queries']:,} ta"
        f"{top_text}"
    )
    await message.answer(report, parse_mode="HTML")


def get_help_text() -> str:
    return (
        "📖 <b>Bot Qo'llanmasi & Imkoniyatlari</b>\n\n"
        "🤖 <b>1. Google Gemini AI Chat:</b>\n"
        "• <code>/ai</code> - Sun'iy intellekt chat rejimini ishga tushirish\n"
        "• <code>/ai &lt;savol&gt;</code> - Bir martalik savol berish (masalan: <code>/ai Python nima?</code>)\n"
        "• Rasm yuborib savol bersangiz, Gemini rasmni to'liq tahlil qilib beradi!\n"
        "• <code>/setkey &lt;kalit&gt;</code> - O'z Gemini API kalitingizni o'rnatish\n\n"
        "📥 <b>2. Instagram Profil va Yuklovchi:</b>\n"
        "• Har qanday Instagram username (masalan: <code>nasa</code>) yoki havolani to'g'ridan-to'g'ri yuboring.\n"
        "• <code>/posts &lt;username&gt; [soni]</code> - Postlarni yuklab olish (default: 3 ta)\n"
        "• <code>/stories &lt;username&gt;</code> - 24 soatlik Stories'larni yuklash\n"
        "• <code>/check &lt;username&gt;</code> - Profil holati (ochiq/yopiq)\n\n"
        "⚙️ <b>3. Sozlamalar:</b>\n"
        "• <code>/session</code> - Instagram sessiya holatini tekshirish\n"
        "• <code>/setsession &lt;sessionid&gt;</code> - Instagram sessionid ulash"
    )


@router.message(Command("help"))
async def handle_help(message: Message):
    """Handles /help command."""
    await message.answer(get_help_text(), parse_mode="HTML")


@router.callback_query(F.data == "help:show")
async def handle_help_callback(callback: CallbackQuery):
    """Handles help button callback."""
    await callback.answer()
    await callback.message.answer(get_help_text(), parse_mode="HTML")


@router.message(Command("session"))
async def handle_session(message: Message):
    """Displays current Instagram authentication and session status."""
    is_logged_in, username = instagram_service.check_session_status()

    if is_logged_in:
        status_text = (
            "✅ <b>Instagram Session Status: Active</b>\n\n"
            f"• <b>Authenticated User:</b> @{escape_html(username or 'cookie_session')}\n"
            "• <b>Story Downloads:</b> Enabled\n"
            "• <b>Rate Limit Protection:</b> Enhanced"
        )
    else:
        status_text = (
            "⚠️ <b>Instagram Session Status: Anonymous (Not Logged In)</b>\n\n"
            "• <b>Public Profile Checks:</b> Enabled\n"
            "• <b>Recent Post Downloads:</b> Enabled\n"
            "• <b>Story Downloads:</b> Disabled (Instagram requires authentication for stories)\n\n"
            "💡 <b>To Enable Stories:</b>\n"
            "1. Open instagram.com in your desktop browser and log in.\n"
            "2. Open Developer Tools (F12) -> Application -> Cookies -> instagram.com.\n"
            "3. Copy the value of the <code>sessionid</code> cookie.\n"
            "4. Add <code>INSTAGRAM_SESSION_ID=your_session_id</code> to your <code>.env</code> file, "
            "or run <code>/setsession &lt;sessionid&gt;</code>."
        )

    await message.answer(status_text, parse_mode="HTML")


@router.message(Command("setsession"))
async def handle_set_session(message: Message):
    """Allows setting sessionid cookie dynamically."""
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "ℹ️ <b>Foydalanish:</b> <code>/setsession &lt;sessionid_cookie&gt;</code>\n\n"
            "Brauzerdan <code>sessionid</code> qiymatini nusxalab, ushbu buyruq bilan yuboring.",
            parse_mode="HTML"
        )
        return

    session_id = parts[1].strip()
    success = instagram_service.set_session_cookie(session_id=session_id)

    if success:
        try:
            import re
            env_path = config.BASE_DIR / ".env"
            if env_path.exists():
                content = env_path.read_text(encoding="utf-8")
                if "INSTAGRAM_SESSION_ID=" in content:
                    new_content = re.sub(r"INSTAGRAM_SESSION_ID=.*", f"INSTAGRAM_SESSION_ID={session_id}", content)
                else:
                    new_content = content + f"\nINSTAGRAM_SESSION_ID={session_id}\n"
                env_path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not persist session to .env: {e}")

        await message.answer(
            "✅ <b>Instagram sessiyasi muvaffaqiyatli ulandi!</b>\n\n"
            "Instagram cheklovlari (429 Rate limit) olib tashlandi. Endi bemalol profillarni tekshirishingiz va postlarni yuklab olishingiz mumkin.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Sessiyani sozlashda xatolik yuz berdi. Iltimos, qiymatni tekshirib qayta urinib ko'ring.",
            parse_mode="HTML"
        )

