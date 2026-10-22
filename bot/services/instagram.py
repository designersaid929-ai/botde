import os
import time
import shutil
import logging
import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Tuple

import instaloader
from instaloader.exceptions import (
    InstaloaderException,
    AbortDownloadException,
    ProfileNotExistsException,
    PrivateProfileNotFollowedException,
    LoginRequiredException,
    TooManyRequestsException,
    ConnectionException,
    BadResponseException,
    QueryReturnedBadRequestException,
    QueryReturnedNotFoundException,
)

from bot.config import config

logger = logging.getLogger(__name__)

# Monkeypatch Instaloader Windows path mangler so absolute target directories work on Windows
try:
    import instaloader.instaloader as _il
    _il._PostPathFormatter.sanitize_path = staticmethod(lambda ret, force_windows_path=False: ret)
except Exception as _e:
    logger.warning(f"Failed to patch Instaloader path sanitizer: {_e}")

# Monkeypatch Story._fetch_iphone_struct to avoid KeyError on web sessions
def _safe_fetch_iphone_struct(story_self):
    try:
        if story_self._context.iphone_support and story_self._context.is_logged_in and not story_self._iphone_struct_:
            data = story_self._context.get_iphone_json(
                path=f"api/v1/feed/reels_media/?reel_ids={story_self.owner_id}", params={}
            )
            reels = data.get("reels", {}) if isinstance(data, dict) else {}
            story_self._iphone_struct_ = reels.get(str(story_self.owner_id))
    except Exception:
        story_self._iphone_struct_ = None

instaloader.Story._fetch_iphone_struct = _safe_fetch_iphone_struct


# Custom Domain Exceptions
class InstagramServiceException(Exception):
    """Base exception for Instagram service errors."""
    pass


class ProfileNotFoundError(InstagramServiceException):
    """Raised when the specified profile does not exist."""
    pass


class PrivateProfileError(InstagramServiceException):
    """Raised when profile is private and cannot be accessed."""
    pass


class RateLimitError(InstagramServiceException):
    """Raised when Instagram hits rate limiting (HTTP 429)."""
    pass


class SessionRequiredError(InstagramServiceException):
    """Raised when an authenticated session is required (e.g. for stories)."""
    pass


class MediaNotFoundError(InstagramServiceException):
    """Raised when no media was found."""
    pass


@dataclass
class InstagramProfileResult:
    username: str
    full_name: str
    biography: str
    is_private: bool
    is_verified: bool
    posts_count: int
    followers_count: int
    following_count: int
    profile_pic_url: Optional[str] = None
    external_url: Optional[str] = None
    followed_by_viewer: bool = False


@dataclass
class MediaItem:
    path: Path
    is_video: bool


@dataclass
class DownloadedPost:
    shortcode: str
    username: str
    caption: Optional[str]
    date_utc: Optional[datetime]
    likes: Optional[int]
    comments: Optional[int]
    is_video: bool
    is_sidecar: bool
    media_items: List[MediaItem] = field(default_factory=list)
    post_dir: Optional[Path] = None


@dataclass
class DownloadedStory:
    media_item: MediaItem
    date_utc: Optional[datetime]
    expiring_utc: Optional[datetime]
    caption: Optional[str]
    owner_username: str


class InstagramService:
    """
    Service wrapper around Instaloader.
    Runs blocking network and I/O calls asynchronously using asyncio.to_thread.
    Handles sessions, cookies, error handling, and rate-limits.
    """

    def __init__(self):
        # Configure Instaloader instance with conservative settings
        self.loader = instaloader.Instaloader(
            sleep=False,  # Crucial: do not sleep for 600+ seconds on rate limits!
            quiet=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            save_metadata=False,
            download_comments=False,
            download_geotags=False,
            download_video_thumbnails=False,
            compress_json=False,
            max_connection_attempts=1,  # Fail fast instead of hanging
            fatal_status_codes=[400, 401, 403, 429],  # Raise error immediately
            request_timeout=15.0,
        )

        # Patch get_raw to reroute blocked/hanging regional CDN nodes (*.fbcdn.net) to global CDN
        orig_get_raw = self.loader.context.get_raw

        def patched_get_raw(url, *args, **kwargs):
            if "fbcdn.net" in url:
                import re
                url = re.sub(r"https://[^/]+\.fbcdn\.net/", "https://scontent.cdninstagram.com/", url)
            return orig_get_raw(url, *args, **kwargs)

        self.loader.context.get_raw = patched_get_raw
        self.loader.context.iphone_support = False

        self.logged_in_username: Optional[str] = None
        self._init_session()

    def _init_session(self) -> None:
        """Initializes session from cookie, session file, or credentials."""
        # 1. Try Session ID cookie from environment
        if config.IG_SESSION_ID:
            logger.info("Initializing Instagram session from INSTAGRAM_SESSION_ID cookie...")
            self.set_session_cookie(
                session_id=config.IG_SESSION_ID,
                csrf_token=config.IG_CSRF_TOKEN,
                ds_user_id=config.IG_DS_USER_ID,
                username=config.IG_USERNAME or None
            )
            return

        # 2. Try pre-saved session file
        if config.IG_SESSION_FILE and os.path.exists(config.IG_SESSION_FILE):
            try:
                username = config.IG_USERNAME or "session_user"
                logger.info(f"Loading Instagram session from file: {config.IG_SESSION_FILE}")
                self.loader.load_session_from_file(username=username, filename=config.IG_SESSION_FILE)
                self.logged_in_username = username
                logger.info("Instagram session loaded successfully from file.")
                return
            except Exception as e:
                logger.warning(f"Failed to load session from file: {e}")

        # 3. Try credentials login if provided
        if config.IG_USERNAME and config.IG_PASSWORD:
            try:
                logger.info(f"Logging into Instagram as {config.IG_USERNAME}...")
                self.loader.login(config.IG_USERNAME, config.IG_PASSWORD)
                self.logged_in_username = config.IG_USERNAME
                # Save session to avoid repeated logins
                session_file = config.BASE_DIR / f"session-{config.IG_USERNAME}"
                self.loader.save_session_to_file(str(session_file))
                logger.info(f"Login successful and session saved to {session_file}")
            except Exception as e:
                logger.warning(f"Instagram credentials login failed: {e}")

    def set_session_cookie(
        self,
        session_id: str,
        csrf_token: Optional[str] = None,
        ds_user_id: Optional[str] = None,
        username: Optional[str] = None
    ) -> bool:
        """
        Sets Instagram session cookies directly into requests session.
        Returns True if successful.
        """
        try:
            self.loader.context._session.cookies.set("sessionid", session_id, domain=".instagram.com")
            if csrf_token:
                self.loader.context._session.cookies.set("csrftoken", csrf_token, domain=".instagram.com")
                self.loader.context._session.headers.update({"X-CSRFToken": csrf_token})
            if ds_user_id:
                self.loader.context._session.cookies.set("ds_user_id", ds_user_id, domain=".instagram.com")

            self.loader.context._session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "X-Requested-With": "XMLHttpRequest",
            })

            # Check if username is known or test login
            if username:
                self.loader.context.username = username
                self.logged_in_username = username
            else:
                try:
                    user = self.loader.test_login()
                    if user:
                        self.logged_in_username = user
                        self.loader.context.username = user
                    else:
                        # Fallback placeholder so instaloader considers context authenticated
                        self.logged_in_username = "cookie_session"
                        self.loader.context.username = "cookie_session"
                except Exception:
                    self.logged_in_username = "cookie_session"
                    self.loader.context.username = "cookie_session"

            logger.info(f"Instagram session cookies set. Active user: {self.logged_in_username}")
            return True
        except Exception as e:
            logger.error(f"Error setting session cookie: {e}")
            return False

    @property
    def is_logged_in(self) -> bool:
        """Checks whether an authenticated session is active."""
        has_session_cookie = any(c.name == "sessionid" and bool(c.value) for c in self.loader.context._session.cookies)
        return has_session_cookie or bool(self.loader.context.username)

    def check_session_status(self) -> Tuple[bool, Optional[str]]:
        """Returns (is_logged_in, username)."""
        return self.is_logged_in, self.logged_in_username

    # =========================================================================
    # Public Async API Methods
    # =========================================================================

    async def check_profile(self, username: str) -> InstagramProfileResult:
        """
        Async check of Instagram profile existence and public/private status.
        Requirement 1 & 4.
        """
        return await asyncio.to_thread(self._sync_check_profile, username)

    async def get_recent_posts(self, username: str, count: int, target_dir: Path) -> List[DownloadedPost]:
        """
        Async fetch and download of recent posts (photos, carousels, videos/reels).
        Requirement 2.
        """
        return await asyncio.to_thread(self._sync_get_recent_posts, username, count, target_dir)

    async def get_post_by_shortcode(self, shortcode: str, target_dir: Path) -> DownloadedPost:
        """
        Async fetch and download of a single post by shortcode.
        """
        return await asyncio.to_thread(self._sync_get_post_by_shortcode, shortcode, target_dir)

    async def get_user_stories(self, username: str, target_dir: Path) -> List[DownloadedStory]:
        """
        Async fetch and download of active 24-hour stories.
        Requirement 3.
        """
        return await asyncio.to_thread(self._sync_get_user_stories, username, target_dir)

    # =========================================================================
    # Internal Synchronous Worker Methods (run via asyncio.to_thread)
    # =========================================================================

    def _sync_check_profile(self, username: str) -> InstagramProfileResult:
        """Synchronously queries Instagram profile metadata."""
        clean_user = username.lower().strip("@ ")
        try:
            profile = instaloader.Profile.from_username(self.loader.context, clean_user)
            return InstagramProfileResult(
                username=profile.username,
                full_name=profile.full_name or profile.username,
                biography=profile.biography or "",
                is_private=profile.is_private,
                is_verified=profile.is_verified,
                posts_count=profile.mediacount,
                followers_count=profile.followers,
                following_count=profile.followees,
                profile_pic_url=profile.profile_pic_url,
                external_url=profile.external_url,
                followed_by_viewer=bool(getattr(profile, "followed_by_viewer", False)),
            )
        except ProfileNotExistsException:
            raise ProfileNotFoundError(f"Instagram profile @{clean_user} does not exist.")
        except (TooManyRequestsException, AbortDownloadException):
            raise RateLimitError("Instagram has temporarily rate-limited requests (HTTP 429). Please wait a few minutes or add an Instagram session (/session).")
        except ConnectionException as ce:
            msg = str(ce).lower()
            if "429" in msg or "too many requests" in msg:
                raise RateLimitError("Instagram rate limit reached (HTTP 429). Please wait a few minutes or add an Instagram session (/session).")
            if "401" in msg or "login required" in msg:
                raise SessionRequiredError("Instagram requires authentication to view this profile.")
            raise InstagramServiceException(f"Network error querying Instagram: {ce}")
        except QueryReturnedNotFoundException:
            raise ProfileNotFoundError(f"Instagram profile @{clean_user} was not found.")
        except QueryReturnedBadRequestException:
            raise InstagramServiceException("Instagram returned bad request. Please check username spelling.")
        except Exception as e:
            logger.exception(f"Unexpected error checking profile {clean_user}: {e}")
            raise InstagramServiceException(f"Failed to check profile @{clean_user}: {e}")

    def _sync_get_recent_posts(self, username: str, count: int, target_dir: Path) -> List[DownloadedPost]:
        """Synchronously downloads recent posts for a public profile (or private if followed)."""
        clean_user = username.lower().strip("@ ")
        try:
            profile = instaloader.Profile.from_username(self.loader.context, clean_user)
        except ProfileNotExistsException:
            raise ProfileNotFoundError(f"Instagram profile @{clean_user} does not exist.")
        except (TooManyRequestsException, AbortDownloadException):
            raise RateLimitError("Instagram rate limit reached (HTTP 429).")
        except Exception as e:
            raise InstagramServiceException(f"Error accessing @{clean_user}: {e}")

        # Check if profile is private and we don't follow them
        if profile.is_private:
            if not getattr(profile, "followed_by_viewer", False):
                raise PrivateProfileError(f"Account @{clean_user} is private and viewer does not follow them.")

        if profile.mediacount == 0:
            return []

        downloaded_posts: List[DownloadedPost] = []
        posts_iterator = profile.get_posts()

        for idx, post in enumerate(posts_iterator):
            if idx >= count:
                break

            post_folder = target_dir / f"post_{post.shortcode}"
            post_folder.mkdir(parents=True, exist_ok=True)

            try:
                # Instaloader download_post downloads media files to post_folder
                self.loader.download_post(post, target=str(post_folder))

                media_items = self._collect_media_files(post_folder)
                if not media_items:
                    logger.warning(f"No media files captured for post {post.shortcode}")
                    continue

                downloaded_posts.append(DownloadedPost(
                    shortcode=post.shortcode,
                    username=post.owner_username,
                    caption=post.caption,
                    date_utc=post.date_utc,
                    likes=post.likes,
                    comments=post.comments,
                    is_video=post.is_video,
                    is_sidecar=(post.typename == "GraphSidecar"),
                    media_items=media_items,
                    post_dir=post_folder
                ))

                # Polite delay between items to mitigate rate limits
                if idx < count - 1:
                    time.sleep(1.0)

            except TooManyRequestsException:
                raise RateLimitError("Instagram rate limit reached while downloading posts.")
            except PrivateProfileNotFollowedException:
                raise PrivateProfileError(f"Account @{clean_user} is private and your session does not follow them.")
            except Exception as e:
                logger.warning(f"Error downloading post {post.shortcode}: {e}")
                continue

        return downloaded_posts

    def _sync_get_post_by_shortcode(self, shortcode: str, target_dir: Path) -> DownloadedPost:
        """Synchronously downloads a single post/reel by shortcode."""
        try:
            post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
        except ProfileNotExistsException:
            raise MediaNotFoundError("The requested post was not found or is private.")
        except LoginRequiredException:
            raise SessionRequiredError("Instagram requires login to access this post.")
        except Exception as e:
            raise InstagramServiceException(f"Error fetching post {shortcode}: {e}")

        # Check if owner is private and we don't follow them
        if post.owner_profile.is_private:
            if not getattr(post.owner_profile, "followed_by_viewer", False):
                raise PrivateProfileError(f"Post belongs to private profile @{post.owner_username}.")

        post_folder = target_dir / f"single_{shortcode}"
        post_folder.mkdir(parents=True, exist_ok=True)

        self.loader.download_post(post, target=str(post_folder))
        media_items = self._collect_media_files(post_folder)

        if not media_items:
            raise MediaNotFoundError(f"Could not extract media for post {shortcode}.")

        return DownloadedPost(
            shortcode=post.shortcode,
            username=post.owner_username,
            caption=post.caption,
            date_utc=post.date_utc,
            likes=post.likes,
            comments=post.comments,
            is_video=post.is_video,
            is_sidecar=(post.typename == "GraphSidecar"),
            media_items=media_items,
            post_dir=post_folder
        )

    def _sync_get_user_stories(self, username: str, target_dir: Path) -> List[DownloadedStory]:
        """Synchronously downloads active 24-hour stories for a user."""
        clean_user = username.lower().strip("@ ")

        # Stories strictly require an authenticated session in Instagram API
        if not self.is_logged_in:
            raise SessionRequiredError(
                "Instagram requires an authenticated session to access stories (even for public profiles). "
                "Please configure INSTAGRAM_SESSION_ID in your .env file."
            )

        try:
            profile = instaloader.Profile.from_username(self.loader.context, clean_user)
        except ProfileNotExistsException:
            raise ProfileNotFoundError(f"Instagram profile @{clean_user} does not exist.")
        except Exception as e:
            raise InstagramServiceException(f"Error accessing @{clean_user}: {e}")

        if profile.is_private:
            if not getattr(profile, "followed_by_viewer", False):
                raise PrivateProfileError(f"Account @{clean_user} is private and viewer does not follow them.")

        try:
            stories_iter = self.loader.get_stories(userids=[profile.userid])
        except LoginRequiredException:
            raise SessionRequiredError("Your Instagram session has expired or is invalid. Please update cookies.")
        except TooManyRequestsException:
            raise RateLimitError("Instagram rate limit reached when requesting stories.")
        except Exception as e:
            raise InstagramServiceException(f"Error fetching stories for @{clean_user}: {e}")

        downloaded_stories: List[DownloadedStory] = []

        try:
            for story in stories_iter:
                try:
                    story_items = list(story.get_items())
                except (KeyError, IndexError):
                    continue

                for item in story_items:
                    story_folder = target_dir / f"story_{item.mediaid}"
                    story_folder.mkdir(parents=True, exist_ok=True)

                    try:
                        self.loader.download_storyitem(item, target=str(story_folder))
                        media_items = self._collect_media_files(story_folder)
                        if not media_items:
                            continue

                        downloaded_stories.append(DownloadedStory(
                            media_item=media_items[0],
                            date_utc=item.date_utc,
                            expiring_utc=item.expiring_utc,
                            caption=item.caption,
                            owner_username=item.owner_username
                        ))

                        time.sleep(0.5)
                    except Exception as e:
                        logger.warning(f"Error downloading story item {item.mediaid}: {e}")
                        continue
        except (KeyError, IndexError):
            pass

        return downloaded_stories

    def _collect_media_files(self, folder: Path) -> List[MediaItem]:
        """Collects image and video files from a download folder in sorted order."""
        items: List[MediaItem] = []
        if not folder.exists():
            return items

        valid_image_exts = {".jpg", ".jpeg", ".png", ".webp"}
        valid_video_exts = {".mp4", ".mov"}

        for p in sorted(folder.iterdir()):
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext in valid_image_exts:
                items.append(MediaItem(path=p, is_video=False))
            elif ext in valid_video_exts:
                items.append(MediaItem(path=p, is_video=True))

        return items


# Global singleton instance
instagram_service = InstagramService()
