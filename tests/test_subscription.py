import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.enums import ChatMemberStatus

from bot.services.subscription import (
    get_required_channels,
    set_required_channels,
    check_user_subscription
)


@pytest.mark.asyncio
async def test_subscription_service():
    set_required_channels("@testchannel")
    assert "@testchannel" in get_required_channels()

    mock_bot = AsyncMock()
    mock_member = MagicMock()
    mock_member.status = ChatMemberStatus.MEMBER
    mock_bot.get_chat_member.return_value = mock_member

    is_sub, unsub = await check_user_subscription(mock_bot, 999999)
    assert is_sub is True
    assert len(unsub) == 0

    # Test unsubscribed
    mock_member.status = ChatMemberStatus.LEFT
    mock_chat = MagicMock()
    mock_chat.id = -100123
    mock_chat.title = "Test Channel"
    mock_chat.username = "testchannel"
    mock_chat.invite_link = "https://t.me/testchannel"
    mock_bot.get_chat.return_value = mock_chat

    is_sub, unsub = await check_user_subscription(mock_bot, 888888)
    assert is_sub is False
    assert len(unsub) == 1

    # Cleanup
    set_required_channels("")
