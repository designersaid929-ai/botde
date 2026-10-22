import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from bot.services.instagram import (
    InstagramService,
    ProfileNotFoundError,
    PrivateProfileError,
    RateLimitError,
    SessionRequiredError
)
import instaloader.exceptions


@pytest.fixture
def service():
    # Instantiate service without network login
    with patch.object(InstagramService, "_init_session"):
        srv = InstagramService()
        srv.logged_in_username = None
        return srv


@pytest.mark.asyncio
async def test_check_profile_public(service):
    mock_profile = MagicMock()
    mock_profile.username = "test_public"
    mock_profile.full_name = "Public User"
    mock_profile.biography = "Hello world"
    mock_profile.is_private = False
    mock_profile.is_verified = False
    mock_profile.mediacount = 10
    mock_profile.followers = 500
    mock_profile.followees = 200
    mock_profile.profile_pic_url = "https://example.com/pic.jpg"
    mock_profile.external_url = None

    with patch("instaloader.Profile.from_username", return_value=mock_profile):
        result = await service.check_profile("test_public")
        assert result.username == "test_public"
        assert result.is_private is False
        assert result.posts_count == 10


@pytest.mark.asyncio
async def test_check_profile_private(service):
    # Requirement 1 & 4: detect if profile is private
    mock_profile = MagicMock()
    mock_profile.username = "test_private"
    mock_profile.full_name = "Private User"
    mock_profile.biography = "Secret"
    mock_profile.is_private = True
    mock_profile.is_verified = False
    mock_profile.mediacount = 5
    mock_profile.followers = 50
    mock_profile.followees = 50
    mock_profile.profile_pic_url = None
    mock_profile.external_url = None

    with patch("instaloader.Profile.from_username", return_value=mock_profile):
        result = await service.check_profile("test_private")
        assert result.username == "test_private"
        assert result.is_private is True


@pytest.mark.asyncio
async def test_check_profile_not_found(service):
    with patch("instaloader.Profile.from_username", side_effect=instaloader.exceptions.ProfileNotExistsException("not found")):
        with pytest.raises(ProfileNotFoundError):
            await service.check_profile("nonexistent_user_999999")


@pytest.mark.asyncio
async def test_check_profile_rate_limited(service):
    with patch("instaloader.Profile.from_username", side_effect=instaloader.exceptions.TooManyRequestsException("429")):
        with pytest.raises(RateLimitError):
            await service.check_profile("some_user")


@pytest.mark.asyncio
async def test_get_recent_posts_private_profile_raises(service, tmp_path):
    mock_profile = MagicMock()
    mock_profile.username = "secret_user"
    mock_profile.is_private = True
    mock_profile.followed_by_viewer = False

    with patch("instaloader.Profile.from_username", return_value=mock_profile):
        with pytest.raises(PrivateProfileError):
            await service.get_recent_posts("secret_user", count=3, target_dir=tmp_path)


@pytest.mark.asyncio
async def test_get_recent_posts_private_profile_allowed_if_followed(service, tmp_path):
    mock_profile = MagicMock()
    mock_profile.username = "followed_private_user"
    mock_profile.is_private = True
    mock_profile.followed_by_viewer = True
    mock_profile.mediacount = 0

    with patch("instaloader.Profile.from_username", return_value=mock_profile):
        posts = await service.get_recent_posts("followed_private_user", count=3, target_dir=tmp_path)
        assert posts == []


@pytest.mark.asyncio
async def test_get_stories_unauthenticated_raises(service, tmp_path):
    # Requirement 3 & 5: without session, stories raise SessionRequiredError
    with pytest.raises(SessionRequiredError):
        await service.get_user_stories("nasa", target_dir=tmp_path)


def test_set_session_cookie(service):
    # Requirement 5: session cookies handling
    res = service.set_session_cookie(
        session_id="123456%3Aabcd%3A0987",
        csrf_token="csrf12345",
        username="my_test_account"
    )
    assert res is True
    assert service.is_logged_in is True
    assert service.logged_in_username == "my_test_account"
