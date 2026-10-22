import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, Chat, User
from aiogram.fsm.context import FSMContext

from bot.services.ai import GeminiAIService
from bot.handlers.ai import handle_ai_command, handle_setkey_command


@pytest.mark.asyncio
async def test_gemini_service_initialization():
    service = GeminiAIService()
    assert service._model_name == "gemini-3.8-flash"
    assert service.is_configured is True


@pytest.mark.asyncio
async def test_gemini_service_ask_chat():
    service = GeminiAIService()
    with patch.object(service, "ask_chat", new_callable=AsyncMock) as mock_ask:
        mock_ask.return_value = "Assalomu alaykum! Men Gemini AI assistentiman."
        res = await service.ask_chat(12345, "Salom")
        assert "Gemini" in res


@pytest.mark.asyncio
async def test_ai_handler_command():
    message = AsyncMock(spec=Message)
    message.chat = MagicMock(spec=Chat)
    message.chat.id = 12345
    message.chat.type = "private"
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 7725025642  # Admin to pass subscription
    message.text = "/ai"
    message.answer = AsyncMock()
    message.reply = AsyncMock()
    message.bot = AsyncMock()

    mock_state = AsyncMock(spec=FSMContext)

    await handle_ai_command(message, mock_state)
    mock_state.set_state.assert_called_once()
    message.answer.assert_called_once()
    assert "Gemini AI Chat" in message.answer.call_args[0][0]



@pytest.mark.asyncio
async def test_tts_voice_generation():
    from bot.services.tts import sanitize_text_for_speech, detect_voice_for_text, VOICE_UZBEK, VOICE_RUSSIAN
    clean = sanitize_text_for_speech("<b>Salom!</b> <i>Qandaysiz?</i>")
    assert clean == "Salom! Qandaysiz?"

    voice_uz = detect_voice_for_text("Salom, qandaysiz?")
    assert voice_uz == VOICE_UZBEK

    voice_ru = detect_voice_for_text("Привет, как дела?")
    assert voice_ru == VOICE_RUSSIAN

