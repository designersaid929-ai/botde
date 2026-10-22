import html
from datetime import datetime
from typing import Optional


def escape_html(text: Optional[str]) -> str:
    """Escapes HTML special characters safely."""
    if not text:
        return ""
    return html.escape(str(text))


def format_number(n: Optional[int]) -> str:
    """Formats large numbers nicely (e.g. 1.2M, 450K, 12,345)."""
    if n is None:
        return "N/A"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


def format_profile_card(
    username: str,
    full_name: str,
    biography: str,
    is_private: bool,
    is_verified: bool,
    posts_count: int,
    followers_count: int,
    following_count: int,
    external_url: Optional[str] = None,
    followed_by_viewer: bool = False
) -> str:
    """
    Builds a clean, rich HTML summary card for an Instagram profile.
    """
    verified_badge = " ☑️ (Verified)" if is_verified else ""
    if is_private:
        if followed_by_viewer:
            status_badge = "🔒 Private Account (✅ Siz obunasiz / Following)"
        else:
            status_badge = "🔒 Private Account"
    else:
        status_badge = "🌐 Public Profile"

    bio_escaped = escape_html(biography)
    if len(bio_escaped) > 300:
        bio_escaped = bio_escaped[:297] + "..."

    lines = [
        f"<b>{escape_html(full_name or username)}</b> (@{escape_html(username)}){verified_badge}",
        f"<i>{status_badge}</i>",
        ""
    ]

    if bio_escaped:
        lines.append(f"📝 {bio_escaped}")
        lines.append("")

    lines.extend([
        "<b>Profile Statistics:</b>",
        f"• 📸 <b>Posts:</b> {format_number(posts_count)}",
        f"• 👥 <b>Followers:</b> {format_number(followers_count)}",
        f"• 👤 <b>Following:</b> {format_number(following_count)}",
    ])

    if external_url:
        lines.append(f"• 🔗 <b>Link:</b> <a href=\"{escape_html(external_url)}\">{escape_html(external_url)}</a>")

    lines.append("")
    if is_private and not followed_by_viewer:
        lines.append("<i>⚠️ Ushbu profil private (yopiq). Post va stories'larni ko'rish uchun siz ushbu akkauntga Instagramda obuna bo'lgan bo'lishingiz va botga /setsession orqali sessionid ulanishi kerak.</i>")
    else:
        lines.append("<i>👇 Quyidagi tugmalardan birini tanlang:</i>")

    return "\n".join(lines)


def format_private_profile_message(username: str) -> str:
    """
    Clear, user-friendly explanation of Instagram private profile restrictions.
    """
    clean_user = escape_html(username)
    return (
        f"🔒 <b>Yopiq (Private) Akkaunt</b>\n\n"
        f"<b>@{clean_user}</b> profili Instagramda <b>Private</b> (yopiq) qilib sozlangan.\n\n"
        f"Instagram xavfsizlik va maxfiylik siyosatiga ko'ra, yopiq akkauntning postlari, videolari va stories'larini "
        f"begona foydalanuvchilar yoki ochiq dasturlar to'g'ridan-to'g'ri ko'ra olmaydi.\n\n"
        f"💡 <b>Private akkauntlarni yuklab olish yo'li:</b>\n"
        f"Agar siz ushbu akkauntga Instagram profilingiz orqali obuna bo'lgan (follow qilgan) bo'lsangiz:\n"
        f"1. Brauzerdan o'z Instagram akkauntingizning <code>sessionid</code> cookie qiymatini oling.\n"
        f"2. Botga <code>/setsession &lt;sessionid&gt;</code> buyrug'ini yuboring.\n"
        f"Shundan so'ng bot sizning ruxsatingiz bilan ushbu yopiq akkauntning barcha post va stories'larini yuklab beradi!"
    )


def format_post_caption(
    username: str,
    shortcode: str,
    caption: Optional[str] = None,
    likes: Optional[int] = None,
    comments: Optional[int] = None,
    date_utc: Optional[datetime] = None
) -> str:
    """Formats Telegram media caption for an Instagram post."""
    post_url = f"https://www.instagram.com/p/{shortcode}/"
    header = f"👤 <a href=\"https://www.instagram.com/{escape_html(username)}/\">@{escape_html(username)}</a> | <a href=\"{post_url}\">View Post</a>"

    stats = []
    if likes is not None:
        stats.append(f"❤️ {format_number(likes)}")
    if comments is not None:
        stats.append(f"💬 {format_number(comments)}")
    if date_utc:
        stats.append(f"📅 {date_utc.strftime('%Y-%m-%d')}")

    stats_line = " • ".join(stats)

    caption_text = ""
    if caption:
        clean_caption = escape_html(caption.strip())
        # Telegram captions have a 1024 character limit
        max_len = 650
        if len(clean_caption) > max_len:
            clean_caption = clean_caption[:max_len] + "..."
        caption_text = f"\n\n{clean_caption}"

    return f"{header}\n{stats_line}{caption_text}"


def format_story_caption(
    username: str,
    date_utc: Optional[datetime] = None,
    expiring_utc: Optional[datetime] = None,
    caption: Optional[str] = None
) -> str:
    """Formats Telegram media caption for a 24-hour Instagram story."""
    header = f"⏳ <b>Active Story</b> from @{escape_html(username)}"
    details = []
    if date_utc:
        details.append(f"🕒 Posted: {date_utc.strftime('%H:%M:%S UTC')}")
    if expiring_utc:
        details.append(f"⌛ Expires: {expiring_utc.strftime('%H:%M:%S UTC')}")

    details_line = "\n".join(details)
    extra = f"\n\n📝 {escape_html(caption[:300])}" if caption else ""
    return f"{header}\n{details_line}{extra}"


def split_text_safely(text: str, max_chunk_size: int = 3900) -> list[str]:
    """Splits long text messages so they stay strictly within Telegram's 4096 char limit."""
    if not text:
        return []
    if len(text) <= max_chunk_size:
        return [text]

    chunks = []
    lines = text.split("\n")
    current_chunk = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > max_chunk_size:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            # If a single line itself is longer than max_chunk_size
            while len(line) > max_chunk_size:
                chunks.append(line[:max_chunk_size])
                line = line[max_chunk_size:]
            if line:
                current_chunk.append(line)
                current_len = len(line)
        else:
            current_chunk.append(line)
            current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks

