import re
import aiohttp
from dataclasses import dataclass
from typing import Optional, Literal
from urllib.parse import urlparse

InputType = Literal["profile", "post", "story", "unknown"]

RESERVED_PATHS = {
    "explore", "direct", "accounts", "developer", "about",
    "legal", "help", "api", "graphql", "emails", "settings"
}

# Regex to match Instagram post or reel URLs:
# /p/CODE/, /reel/CODE/, /reels/CODE/, /tv/CODE/, /share/p/CODE/, /share/reel/CODE/
POST_URL_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:instagram\.com|ddinstagram\.com)/(?:share/(?:p|reel|reels)/|(?:p|reel|reels|tv)/)([A-Za-z0-9_-]+)",
    re.IGNORECASE
)

# Regex to match generic Instagram share links (which redirect to actual post)
GENERIC_SHARE_URL_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/share/([A-Za-z0-9._-]+)",
    re.IGNORECASE
)

# Regex to match Instagram stories URLs: /stories/USERNAME/ or /stories/USERNAME/ID/
STORY_URL_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/stories/([A-Za-z0-9._]+)(?:/(\d+))?",
    re.IGNORECASE
)

# Regex to match Instagram profile URLs: /USERNAME/
PROFILE_URL_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9._]{1,30})/?(?:\?[^\s]*)?$",
    re.IGNORECASE
)

# Regex for standalone username input: e.g. "cristiano", "@cristiano"
USERNAME_REGEX = re.compile(
    r"^@?([a-zA-Z0-9._]{1,30})$"
)

# Any URL finder in text
URL_FINDER_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)


@dataclass
class ParsedInstagramInput:
    input_type: InputType
    raw_input: str
    username: Optional[str] = None
    shortcode: Optional[str] = None
    story_id: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.input_type != "unknown"


def parse_instagram_input(text: str) -> ParsedInstagramInput:
    """
    Synchronously parses user input string which may be an Instagram URL or username.
    Extracts posts, reels, stories, or profiles even if embedded in surrounding text.
    """
    if not text:
        return ParsedInstagramInput(input_type="unknown", raw_input=text)

    cleaned = text.strip()

    # 1. Check for Post / Reel / TV URL (first priority for direct media links)
    post_match = POST_URL_REGEX.search(cleaned)
    if post_match:
        shortcode = post_match.group(1)
        return ParsedInstagramInput(
            input_type="post",
            raw_input=cleaned,
            shortcode=shortcode
        )

    # 2. Check for Story URL
    story_match = STORY_URL_REGEX.search(cleaned)
    if story_match:
        username = story_match.group(1).lower().strip(". ")
        story_id = story_match.group(2)
        if username not in RESERVED_PATHS:
            return ParsedInstagramInput(
                input_type="story",
                raw_input=cleaned,
                username=username,
                story_id=story_id
            )

    # 3. Check for Profile URL
    if "instagram.com" in cleaned.lower():
        profile_match = PROFILE_URL_REGEX.search(cleaned)
        if profile_match:
            username = profile_match.group(1).lower().strip(". ")
            if username not in RESERVED_PATHS:
                return ParsedInstagramInput(
                    input_type="profile",
                    raw_input=cleaned,
                    username=username
                )
        # Parse path if profile regex missed query string variations
        try:
            # If text has multiple words, extract url first
            found_urls = URL_FINDER_REGEX.findall(cleaned)
            target_url = found_urls[0] if found_urls else cleaned
            parsed_url = urlparse(target_url if "://" in target_url else f"https://{target_url}")
            path_parts = [p for p in parsed_url.path.strip("/").split("/") if p]
            if path_parts:
                first_part = path_parts[0].lower().strip(". ")
                if first_part not in RESERVED_PATHS and re.match(r"^[a-zA-Z0-9._]{1,30}$", first_part):
                    return ParsedInstagramInput(
                        input_type="profile",
                        raw_input=cleaned,
                        username=first_part
                    )
        except Exception:
            pass

    # 4. Check for direct @username or plain username
    username_match = USERNAME_REGEX.match(cleaned)
    if username_match:
        username = username_match.group(1).lower().strip(". ")
        if username not in RESERVED_PATHS and not cleaned.startswith("/"):
            return ParsedInstagramInput(
                input_type="profile",
                raw_input=cleaned,
                username=username
            )

    return ParsedInstagramInput(input_type="unknown", raw_input=cleaned)


async def resolve_and_parse_input(text: str) -> ParsedInstagramInput:
    """
    Asynchronously parses input, and if it's a generic Instagram share link,
    follows HTTP redirects to resolve the actual post/reel shortcode.
    """
    res = parse_instagram_input(text)
    if res.is_valid:
        return res

    # If not recognized yet, check if there's a generic share link
    share_match = GENERIC_SHARE_URL_REGEX.search(text)
    if share_match:
        share_url = share_match.group(0)
        if not share_url.startswith("http"):
            share_url = "https://" + share_url
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                )
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(share_url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    final_url = str(resp.url)
                    resolved = parse_instagram_input(final_url)
                    if resolved.is_valid:
                        return resolved
        except Exception:
            pass

    return res
