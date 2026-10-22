from datetime import datetime, timezone
from bot.utils.formatters import (
    escape_html,
    format_number,
    format_profile_card,
    format_private_profile_message,
    format_post_caption,
    format_story_caption
)


def test_escape_html():
    raw = 'Hello <world> & "friends"'
    escaped = escape_html(raw)
    assert "<" not in escaped
    assert ">" not in escaped
    assert "&lt;world&gt;" in escaped
    assert "&quot;friends&quot;" in escaped


def test_format_number():
    assert format_number(500) == "500"
    assert format_number(12500) == "12.5K"
    assert format_number(2500000) == "2.5M"
    assert format_number(None) == "N/A"


def test_format_profile_card_public():
    card = format_profile_card(
        username="nasa",
        full_name="NASA",
        biography="Exploring the universe and our home planet.",
        is_private=False,
        is_verified=True,
        posts_count=4500,
        followers_count=98000000,
        following_count=80,
        external_url="https://www.nasa.gov"
    )
    assert "NASA" in card
    assert "@nasa" in card
    assert "☑️ (Verified)" in card
    assert "🌐 Public Profile" in card
    assert "98.0M" in card
    assert "https://www.nasa.gov" in card


def test_format_private_profile_message():
    # Requirement 4
    msg = format_private_profile_message("secret_account")
    assert "secret_account" in msg
    assert "Private" in msg
    assert "sessionid" in msg


def test_format_post_caption_truncation():
    dt = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    long_caption = "A" * 1000
    caption = format_post_caption(
        username="photographer",
        shortcode="XYZ123",
        caption=long_caption,
        likes=1200,
        comments=45,
        date_utc=dt
    )
    assert "@photographer" in caption
    assert "XYZ123" in caption
    assert "❤️ 1,200" in caption
    assert "💬 45" in caption
    assert "2026-10-16" in caption
    # Must be truncated to stay well within Telegram's 1024 char caption limit
    assert len(caption) < 850
    assert "..." in caption


def test_format_story_caption():
    dt = datetime(2026, 10, 16, 10, 30, tzinfo=timezone.utc)
    exp = datetime(2026, 10, 17, 10, 30, tzinfo=timezone.utc)
    caption = format_story_caption(
        username="traveler",
        date_utc=dt,
        expiring_utc=exp,
        caption="Behind the scenes!"
    )
    assert "@traveler" in caption
    assert "Active Story" in caption
    assert "Behind the scenes!" in caption
