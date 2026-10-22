import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, Chat, User

from bot.handlers.common import handle_start, handle_help, handle_session
from bot.handlers.profile import handle_check_command
from bot.handlers.posts import handle_posts_command
from bot.handlers.stories import handle_stories_command


@pytest.fixture
def mock_message():
    message = AsyncMock(spec=Message)
    message.chat = MagicMock(spec=Chat)
    message.chat.id = 123456789
    message.chat.type = "private"
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 7725025642  # Admin ID to bypass channel subscription in unit tests
    message.from_user.username = "telegram_user"
    message.answer = AsyncMock()
    message.reply = AsyncMock()
    message.bot = AsyncMock()
    return message


@pytest.mark.asyncio
async def test_handle_start(mock_message):
    mock_message.text = "/start"
    await handle_start(mock_message)
    mock_message.answer.assert_called_once()
    assert "Instagram Media Downloader" in mock_message.answer.call_args[0][0]



@pytest.mark.asyncio
async def test_handle_help(mock_message):
    mock_message.text = "/help"
    await handle_help(mock_message)
    mock_message.answer.assert_called_once()
    assert "Bot Qo'llanmasi" in mock_message.answer.call_args[0][0]



@pytest.mark.asyncio
async def test_handle_session_unauthenticated(mock_message):
    mock_message.text = "/session"
    with patch("bot.services.instagram.instagram_service.check_session_status", return_value=(False, None)):
        await handle_session(mock_message)
        mock_message.answer.assert_called_once()
        assert "Anonymous" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_session_authenticated(mock_message):
    mock_message.text = "/session"
    with patch("bot.services.instagram.instagram_service.check_session_status", return_value=(True, "sample_user")):
        await handle_session(mock_message)
        mock_message.answer.assert_called_once()
        assert "Active" in mock_message.answer.call_args[0][0]
        assert "sample_user" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_check_empty_args(mock_message):
    mock_message.text = "/check"
    await handle_check_command(mock_message)
    mock_message.answer.assert_called_once()
    assert "Usage" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_posts_empty_args(mock_message):
    mock_message.text = "/posts"
    await handle_posts_command(mock_message)
    mock_message.answer.assert_called_once()
    assert "Usage" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_stories_empty_args(mock_message):
    mock_message.text = "/stories"
    await handle_stories_command(mock_message)
    mock_message.answer.assert_called_once()
    assert "Usage" in mock_message.answer.call_args[0][0]
