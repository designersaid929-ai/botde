# 📸 Instagram Media Downloader Telegram Bot

A high-performance, asynchronous Python-based Telegram bot built with **aiogram 3** and **instaloader** for inspecting Instagram profiles and downloading recent posts (single photos, videos/reels, multi-item carousels) and active 24-hour stories.

---

## ✨ Features

- **Profile Verification (Public vs. Private):**
  - Sends full profile details (name, bio, followers, following, post counts, verification badge).
  - Automatically identifies private accounts and informs users of platform privacy restrictions.
- **Recent Posts Downloader:**
  - Fetches and downloads the latest posts (default: 3, configurable up to 10).
  - Handles **single photos**, **videos / reels**, and **multi-image/video carousels** (sent as Telegram media albums).
  - Automatically splits carousels exceeding 10 items into consecutive batches per Telegram API requirements.
- **Active Stories (24-Hour) Downloader:**
  - Fetches and downloads active 24-hour stories (images and videos).
  - Clearly explains session requirements if unauthenticated.
- **🤖 Google Gemini AI Chat:**
  - Integrated smart AI conversational mode via Google Gemini (`gemini-3.8-flash`).
  - Supports continuous chat sessions with contextual memory (`/ai`).
  - Multimodal Vision: send images to the bot to get instant AI analysis and explanations.
  - Quick single questions via `/ai <question>`.
  - Dynamic API key management directly via `/setkey <api_key>` or `.env`.
- **Direct Post / Reel Link Support:**
  - Paste any direct Instagram URL (e.g., `https://instagram.com/p/CODE/` or `https://instagram.com/reel/CODE/`) to download that specific item directly.
- **Privacy Enforcement:**
  - Clear, user-friendly notices explaining why private profile media cannot be accessed.
- **Production-Ready & Resilient:**
  - **Non-blocking Execution:** All Instaloader network calls run in asynchronous worker threads (`asyncio.to_thread`).
  - **Rate Limiting & Flooding Protection:** Per-user cooldown timer and global download concurrency semaphore.
  - **Session Cookie Authentication:** Direct support for `sessionid` cookies, saved session files, or credentials.
  - **Safe Disk Management:** Every download operation uses a scoped `tempfile.TemporaryDirectory` that is guaranteed to clean up upon completion.

---

## 📁 Project Architecture

```
bot2/
├── .env.example              # Sample environment configuration
├── requirements.txt          # Python dependencies
├── pytest.ini               # Pytest async configuration
├── Dockerfile                # Production Docker container
├── docker-compose.yml        # Docker compose definition
├── main.py                   # Application entrypoint & logging
├── bot/
│   ├── config.py             # Configuration loader & validator
│   ├── services/
│   │   └── instagram.py      # Async Instaloader wrapper & session management
│   ├── handlers/
│   │   ├── common.py         # /start, /help, /session, /setsession
│   │   ├── profile.py        # Profile check & text message routing
│   │   ├── posts.py          # /posts & inline posts download callbacks
│   │   └── stories.py        # /stories & inline stories download callbacks
│   ├── keyboards/
│   │   └── inline.py         # Interactive inline action buttons
│   └── utils/
│       ├── url_parser.py     # Regex parser for usernames & URLs
│       ├── formatters.py     # HTML message & caption formatters
│       ├── media_sender.py   # Telegram media group & file sender
│       └── rate_limiter.py   # Cooldown & concurrency limiter
└── tests/
    ├── test_url_parser.py    # URL & username parser tests
    ├── test_formatters.py    # HTML message formatters tests
    ├── test_rate_limiter.py  # Rate limiter cooldown tests
    ├── test_services.py      # Instagram service mock tests
    └── test_handlers.py      # Aiogram command handlers tests
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+
- Telegram Account
- (Optional, Recommended for Stories) Instagram Account

### 2. Obtain Telegram Bot Token
1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the instructions.
3. Copy the HTTP API token provided by BotFather.

### 3. Clone and Setup Environment
```bash
# Clone or navigate into the project directory
cd bot2

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Configure `.env`
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and fill in your settings:
```ini
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ

# (Optional) Instagram Session Cookie for Stories & Higher Rate Limits
INSTAGRAM_SESSION_ID=
INSTAGRAM_CSRF_TOKEN=
INSTAGRAM_DS_USER_ID=
```

#### How to get your Instagram Session Cookie (`sessionid`):
1. Open [instagram.com](https://www.instagram.com) in your desktop browser (Chrome/Edge/Firefox) and log in.
2. Press `F12` (or Right-Click -> **Inspect**) to open Developer Tools.
3. Switch to the **Application** (or **Storage**) tab.
4. Expand **Cookies** on the left panel and click `https://www.instagram.com`.
5. Locate the row named `sessionid` and copy its **Value**.
6. Paste the value into `INSTAGRAM_SESSION_ID=` in your `.env` file.
*(You can also optionally copy `csrftoken` and `ds_user_id` if present).*

### 5. Run the Bot
```bash
python main.py
```

---

## 🤖 Bot Usage & Commands

| Command | Description | Example |
|---|---|---|
| `/start` | Launch bot and view introduction | `/start` |
| `/help` | Detailed help and feature guide | `/help` |
| `/check <user>` | Verify public/private status and view profile card | `/check nasa` |
| `/posts <user> [n]` | Download `n` recent posts (photos, reels, carousels) | `/posts leomessi 3` |
| `/stories <user>` | Download active 24-hour stories | `/stories natgeo` |
| `/session` | Check whether Instagram session is active | `/session` |
| `/setsession <id>` | Update Instagram session cookie dynamically | `/setsession 12345%3A...` |

### Interactive Usage
- Simply paste an Instagram username: `@cristiano` or `cristiano`
- Or paste any profile link: `https://www.instagram.com/cristiano/`
- The bot will inspect the profile and display interactive inline buttons:
  - `📸 Recent Posts (3)`
  - `📸 5 Posts`
  - `⏳ Active Stories (24h)`
  - `🔗 View on Instagram`
- Or paste a direct post/reel URL: `https://www.instagram.com/reel/C-xyz123/` to download it immediately.

---

## 🔒 Private Account Handling

When a user queries a private Instagram account, the bot automatically checks the privacy flag and responds with a clear explanation:

> 🔒 **Private Account Access Restricted**
>
> The Instagram profile **@secret_user** is set to **Private**.
>
> Due to Instagram's privacy policies and security restrictions, media (posts, carousels, reels, and stories) from private accounts cannot be accessed or downloaded by external services.
>
> 💡 *To view their content, you must follow @secret_user directly on Instagram and receive account approval.*

---

## 🧪 Running Unit Tests

The test suite covers URL parsing, caption formatters, rate limiters, session authentication, and command handlers:

```bash
pytest
```
All 34 unit tests run under 1 second using `pytest-asyncio`.

---

## 🐳 Running with Docker

```bash
# Build and run container
docker-compose up -d --build

# View container logs
docker-compose logs -f
```
