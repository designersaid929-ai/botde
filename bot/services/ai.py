import io
import re
import logging
import asyncio
from pathlib import Path
from typing import Dict, Optional, List, Union
from google import genai
from google.genai import types

from bot.config import config

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "Siz aqlli, xushmuomala va har tomonlama yordam beruvchi AI assistentsiz. "
    "Foydalanuvchi qaysi tilda murojaat qilsa, o'sha tilda (asosan o'zbek, rus yoki ingliz tillarida) "
    "aniq, tushunarli, chiroyli va to'liq javob bering. "
    "Javoblaringizda matnni o'qish oson bo'lishi uchun paragraflar va ro'yxatlardan foydalaning."
)

INSTAGRAM_MEDIA_SYSTEM_INSTRUCTION = (
    "Sen Instagram post, Reels video, Story va rasmlarni tahlil qiluvchi aqlli yordamchisan.\n\n"
    "Asosiy vazifang:\n"
    "Bot foydalanuvchisi Instagram username orqali yuklab olgan Story, post, video yoki rasmlardan birini tanlab, "
    "u haqida savol bersa, media mazmunini tahlil qilib, aniq va tushunarli javob ber.\n\n"
    "Tahlil imkoniyatlari:\n"
    "- Videoda nima sodir bo'layotganini tushuntirish.\n"
    "- Videodagi nutqni matnga aylantirish va tarjima qilish.\n"
    "- Video yoki rasmdagi matnlarni aniqlash.\n"
    "- Video mazmunini qisqacha xulosa qilish.\n"
    "- Videodagi mahsulot, buyum va joylarni tavsiflash.\n"
    "- Postning asosiy g'oyasi va maqsadini tushuntirish.\n"
    "- Kontent uchun caption, sarlavha va hashtaglar taklif qilish.\n"
    "- Foydalanuvchi so'ragan savollarga media asosida javob berish.\n\n"
    "Muhim qoidalar:\n"
    "1. Faqat tanlangan media va mavjud ma'lumotlarga asoslan.\n"
    "2. Media faylni ko'ra olmasang yoki audio mavjud bo'lmasa, buni ochiq ayt.\n"
    "3. Ko'rinmaydigan yoki eshitilmaydigan ma'lumotlarni to'qib chiqarma.\n"
    "4. Javoblarni o'zbek tilida, qisqa va tushunarli ber.\n"
    "5. Foydalanuvchi batafsil izoh so'rasa, kengroq tushuntir.\n"
    "6. Rasm, video va audio tahlil qilish imkoniyatlaridan foydalan.\n"
    "7. Agar savolga javob berish uchun qo'shimcha ma'lumot kerak bo'lsa, foydalanuvchidan so'ra.\n\n"
    "Maqsading — foydalanuvchi tanlagan Instagram mediasini tushunish va u haqidagi savollariga foydali javob berish."
)


class GeminiAIService:
    """Manages Gemini AI interactions using the modern Google GenAI SDK."""

    def __init__(self):
        self._current_key: str = config.GEMINI_API_KEY
        self._model_name: str = config.GEMINI_MODEL or "gemini-3.8-flash"
        self._user_chats: Dict[int, any] = {}
        self._client: Optional[genai.Client] = None
        self._init_client()

    def _init_client(self) -> None:
        """Initializes or reconfigures Google GenAI client."""
        if self._current_key:
            try:
                self._client = genai.Client(api_key=self._current_key)
                logger.info("Gemini AI successfully configured with API key.")
            except Exception as e:
                logger.error(f"Failed to configure Gemini API client: {e}")
                self._client = None
        else:
            self._client = None

    @property
    def is_configured(self) -> bool:
        """Checks if a valid Gemini API client is currently configured."""
        return bool(self._current_key and self._client)

    def set_api_key(self, api_key: str, save_to_env: bool = True) -> bool:
        """
        Updates the active Gemini API key. Optionally saves it to .env.
        """
        clean_key = api_key.strip()
        if not clean_key:
            return False

        self._current_key = clean_key
        object.__setattr__(config, "GEMINI_API_KEY", clean_key)
        self._init_client()
        self._user_chats.clear()

        if save_to_env:
            try:
                env_path = config.BASE_DIR / ".env"
                if env_path.exists():
                    content = env_path.read_text(encoding="utf-8")
                    if "GEMINI_API_KEY=" in content:
                        new_content = re.sub(r"GEMINI_API_KEY=.*", f"GEMINI_API_KEY={clean_key}", content)
                    else:
                        new_content = content + f"\nGEMINI_API_KEY={clean_key}\n"
                    env_path.write_text(new_content, encoding="utf-8")
                else:
                    env_path.write_text(f"GEMINI_API_KEY={clean_key}\n", encoding="utf-8")
                logger.info("New GEMINI_API_KEY saved to .env")
            except Exception as e:
                logger.warning(f"Could not persist GEMINI_API_KEY to .env: {e}")

        return True

    def reset_user_chat(self, user_id: int) -> None:
        """Clears conversational memory for a specific user."""
        if user_id in self._user_chats:
            del self._user_chats[user_id]
            logger.info(f"AI chat session cleared for user {user_id}")

    def _get_or_create_chat(self, user_id: int):
        """Returns existing chat session or creates a new one."""
        if user_id not in self._user_chats:
            cfg = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
            self._user_chats[user_id] = self._client.chats.create(
                model=self._model_name,
                config=cfg
            )
        return self._user_chats[user_id]

    async def ask_chat(self, user_id: int, prompt: str) -> str:
        """
        Sends user message to their ongoing Gemini chat session and returns AI response.
        """
        if not self.is_configured:
            return (
                "⚠️ <b>Gemini API kaliti topilmadi!</b>\n\n"
                "AI Chatdan foydalanish uchun botga Gemini API kalitini kiritish zarur.\n"
                "• O'rnatish uchun: <code>/setkey &lt;Sizning_Gemini_API_Key&gt;</code> buyrug'idan foydalaning.\n"
                "• Bepul kalit olish: <a href='https://aistudio.google.com/'>Google AI Studio</a>"
            )

        chat = self._get_or_create_chat(user_id)
        loop = asyncio.get_running_loop()

        try:
            response = await loop.run_in_executor(
                None,
                lambda: chat.send_message(prompt)
            )
            if response and response.text:
                return response.text
            return "🤖 Kechirasiz, javob olishda bo'sh natija qaytdi. Iltimos, boshqacha so'rab ko'ring."
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Gemini API error for user {user_id}: {err_msg}")

            if "API_KEY_INVALID" in err_msg or "400" in err_msg and "API key" in err_msg:
                return (
                    "❌ <b>Gemini API kaliti noto'g'ri yoki yaroqsiz!</b>\n"
                    "Iltimos, kalitni tekshirib qaytadan kiriting:\n"
                    "<code>/setkey &lt;Sizning_Gemini_API_Key&gt;</code>"
                )
            elif "429" in err_msg or "ResourceExhausted" in err_msg or "quota" in err_msg.lower():
                return (
                    "⏳ <b>Gemini API so'rovlar limiti (quota) to'ldi!</b>\n"
                    "Biroz kuting yoki yangi API kalit o'rnating."
                )

            return f"❌ <b>AI xatosi:</b> {err_msg[:200]}"

    async def ask_vision(self, image_bytes: bytes, mime_type: str = "image/jpeg", prompt: str = "") -> str:
        """
        Analyzes an image with an optional prompt using Gemini multimodal capabilities.
        """
        if not self.is_configured:
            return (
                "⚠️ <b>Gemini API kaliti topilmadi!</b>\n"
                "Iltimos, avval <code>/setkey &lt;API_KEY&gt;</code> orqali kalitni o'rnating."
            )

        if not prompt:
            prompt = "Iltimos, bu rasmni batafsil tushuntirib bering va unda nimalar aks etganini tasvirlang."

        loop = asyncio.get_running_loop()
        try:
            part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            response = await loop.run_in_executor(
                None,
                lambda: self._client.models.generate_content(
                    model=self._model_name,
                    contents=[prompt, part]
                )
            )
            if response and response.text:
                return response.text
            return "🤖 Rasmni tahlil qilishda javob olib bo'lmadi."
        except Exception as e:
            logger.error(f"Gemini Vision error: {e}")
            return f"❌ <b>Rasmni tahlil qilishda xatolik:</b> {str(e)[:200]}"

    async def ask_audio(self, user_id: int, audio_bytes: bytes, mime_type: str = "audio/ogg", prompt: str = "") -> str:
        """
        Processes voice/audio message from user using Gemini multimodal audio capabilities.
        """
        if not self.is_configured:
            return (
                "⚠️ <b>Gemini API kaliti topilmadi!</b>\n"
                "Iltimos, avval <code>/setkey &lt;API_KEY&gt;</code> orqali kalitni o'rnating."
            )

        system_prompt = (
            "Ushbu audio yoki ovozli xabarni diqqat bilan eshiting. "
            "Foydalanuvchi aytgan gap yoki savolini tushunib, unga ravon va aniq javob bering. "
            "Agar savol bo'lsa javob bering, agar biror narsa so'ragan bo'lsa bajaring."
        )
        if prompt:
            system_prompt = f"{prompt}\n\n{system_prompt}"

        loop = asyncio.get_running_loop()
        try:
            part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
            cfg = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
            response = await loop.run_in_executor(
                None,
                lambda: self._client.models.generate_content(
                    model=self._model_name,
                    contents=[system_prompt, part],
                    config=cfg
                )
            )
            if response and response.text:
                return response.text
            return "🤖 Ovozli xabarni eshitdim, ammo javob hosil qilib bo'lmadi. Iltimos qaytadan gapirib ko'ring."
        except Exception as e:
            logger.error(f"Gemini Audio processing error for user {user_id}: {e}")
            return f"❌ <b>Ovozli xabarni tahlil qilishda xatolik:</b> {str(e)[:200]}"

    async def analyze_media(
        self,
        file_path: Union[str, Path],
        prompt: str,
        is_video: bool = False,
        caption_context: str = ""
    ) -> str:
        """
        Analyzes Instagram media (video, reels, story, photo) using Google GenAI SDK.
        Applies the specialized Instagram Media Analyst system instruction.
        """
        if not self.is_configured:
            return (
                "⚠️ <b>Gemini API kaliti topilmadi!</b>\n\n"
                "Media fayllarni tahlil qilish uchun avval Gemini API kalitini kiritishingiz zarur.\n"
                "• O'rnatish: <code>/setkey &lt;API_KEY&gt;</code>"
            )

        loop = asyncio.get_running_loop()
        path = Path(file_path)
        if not path.exists():
            return "❌ Media fayli topilmadi yoki o'chirilgan."

        full_prompt = prompt
        if caption_context:
            full_prompt = f"Post/Story original matni (caption):\n\"{caption_context}\"\n\nFoydalanuvchi so'rovi:\n{prompt}"

        def _do_analysis():
            uploaded_file = None
            try:
                cfg = types.GenerateContentConfig(system_instruction=INSTAGRAM_MEDIA_SYSTEM_INSTRUCTION)
                if is_video:
                    uploaded_file = self._client.files.upload(file=str(path))
                    # Wait for video processing if required
                    import time
                    for _ in range(30):
                        if uploaded_file.state.name == "ACTIVE":
                            break
                        if uploaded_file.state.name == "FAILED":
                            raise RuntimeError("Video faylni qayta ishlashda xatolik yuz berdi.")
                        time.sleep(1)
                        uploaded_file = self._client.files.get(name=uploaded_file.name)

                    response = self._client.models.generate_content(
                        model=self._model_name,
                        contents=[uploaded_file, full_prompt],
                        config=cfg
                    )
                else:
                    import mimetypes
                    mime, _ = mimetypes.guess_type(str(path))
                    mime = mime or "image/jpeg"
                    with open(path, "rb") as f:
                        img_bytes = f.read()
                    image_part = types.Part.from_bytes(data=img_bytes, mime_type=mime)
                    response = self._client.models.generate_content(
                        model=self._model_name,
                        contents=[full_prompt, image_part],
                        config=cfg
                    )

                return response.text if (response and response.text) else "🤖 Tahlil natijasi bo'sh bo'ldi."
            finally:
                if uploaded_file:
                    try:
                        self._client.files.delete(name=uploaded_file.name)
                    except Exception:
                        pass

        try:
            return await loop.run_in_executor(None, _do_analysis)
        except Exception as e:
            logger.error(f"Media analysis error: {e}", exc_info=True)
            return f"❌ <b>Tahlil qilishda xatolik yuz berdi:</b> {str(e)[:250]}"


# Global singleton instance
gemini_service = GeminiAIService()
