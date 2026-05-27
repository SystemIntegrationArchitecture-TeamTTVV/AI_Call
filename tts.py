# ============================================================
#  TTS - Text to Speech (gTTS - MIỄN PHÍ)
#  + Convert MP3 → mulaw 8000Hz để phát qua Twilio WebSocket
# ============================================================

import asyncio
import audioop
import base64
import io
from gtts import gTTS
import config


async def text_to_mulaw_base64(text: str) -> str | None:
    """
    text → gTTS MP3 → PCM16 8000Hz → mulaw → base64
    Đây là format Twilio yêu cầu để phát audio vào cuộc gọi.
    """
    if not text or not text.strip():
        return None
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _convert, text)
    except Exception as e:
        print(f"[TTS] Lỗi: {e}")
        return None


async def text_to_mp3_base64(text: str) -> str | None:
    """MP3 base64 — dùng cho test client (giữ backward compat)."""
    if not text or not text.strip():
        return None
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _mp3_only, text)
    except Exception as e:
        print(f"[TTS] Lỗi MP3: {e}")
        return None


def _convert(text: str) -> str:
    """Blocking: gTTS → miniaudio → mulaw → base64."""
    import miniaudio

    # 1. gTTS → MP3 bytes
    tts = gTTS(text=text, lang=config.TTS_LANG, slow=False)
    mp3_buf = io.BytesIO()
    tts.write_to_fp(mp3_buf)
    mp3_bytes = mp3_buf.getvalue()

    # 2. MP3 → PCM 16bit / 8000Hz / mono (dùng miniaudio thay vì pydub/ffmpeg)
    decoded = miniaudio.decode(mp3_bytes, nchannels=1, sample_rate=8000)
    pcm16_bytes = decoded.samples.tobytes()

    # 3. PCM16 → mulaw (8bit) — format Twilio yêu cầu
    mulaw_bytes = audioop.lin2ulaw(pcm16_bytes, 2)

    return base64.b64encode(mulaw_bytes).decode("utf-8")


def _mp3_only(text: str) -> str:
    """Blocking: gTTS → MP3 → base64 (dùng cho test_client)."""
    tts = gTTS(text=text, lang=config.TTS_LANG, slow=False)
    mp3_buf = io.BytesIO()
    tts.write_to_fp(mp3_buf)
    return base64.b64encode(mp3_buf.getvalue()).decode("utf-8")
