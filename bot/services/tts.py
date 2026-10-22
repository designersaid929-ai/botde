import re
import html
import logging
import edge_tts

logger = logging.getLogger(__name__)

# Microsoft Edge Neural Voices
VOICE_UZBEK = "uz-UZ-MadinaNeural"
VOICE_RUSSIAN = "ru-RU-SvetlanaNeural"
VOICE_ENGLISH = "en-US-JennyNeural"


def detect_voice_for_text(text: str) -> str:
    """
    Selects the most suitable neural voice based on language heuristics.
    """
    clean = re.sub(r"[^a-zA-Zа-яА-ЯёЁўқғҳЎҚҒҲ]", "", text)
    if not clean:
        return VOICE_UZBEK

    cyrillic_count = len(re.findall(r"[а-яА-ЯёЁ]", clean))
    latin_count = len(re.findall(r"[a-zA-Z]", clean))

    # If mostly cyrillic characters
    if cyrillic_count > latin_count:
        # Check for Uzbek cyrillic specific letters
        if any(ch in clean for ch in "ўқғҳЎҚҒҲ"):
            return VOICE_UZBEK
        return VOICE_RUSSIAN

    # Default to high-quality Uzbek voice for latin characters
    return VOICE_UZBEK


def sanitize_text_for_speech(text: str, max_chars: int = 800) -> str:
    """
    Cleans up markup, code blocks, URLs, and excessive whitespace for natural voice playback.
    """
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", " ", text)
    # Remove markdown formatting (*, _, `, #)
    clean = re.sub(r"[\*_`#~]", "", clean)
    # Remove URLs
    clean = re.sub(r"http\S+|www\.\S+", "", clean)
    # Unescape HTML entities
    clean = html.unescape(clean)
    # Normalize whitespaces
    clean = re.sub(r"\s+", " ", clean).strip()

    if len(clean) > max_chars:
        # Cut at sentence boundary if possible
        cut = clean[:max_chars]
        last_period = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
        if last_period > max_chars // 2:
            clean = cut[:last_period + 1]
        else:
            clean = cut + "..."

    return clean


async def generate_voice_audio(text: str, voice: str = None) -> bytes:
    """
    Converts text to speech audio bytes using Edge TTS neural voices.
    Returns audio bytes (MP3 format).
    """
    clean_text = sanitize_text_for_speech(text)
    if not clean_text:
        return b""

    selected_voice = voice or detect_voice_for_text(clean_text)

    try:
        communicate = edge_tts.Communicate(clean_text, voice=selected_voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]

        return audio_data
    except Exception as e:
        logger.error(f"TTS generation error with voice {selected_voice}: {e}")
        # Retry with English voice as fallback
        if selected_voice != VOICE_ENGLISH:
            try:
                fallback_comm = edge_tts.Communicate(clean_text, voice=VOICE_ENGLISH)
                audio_data = b""
                async for chunk in fallback_comm.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                return audio_data
            except Exception as fe:
                logger.error(f"TTS fallback error: {fe}")

        return b""
