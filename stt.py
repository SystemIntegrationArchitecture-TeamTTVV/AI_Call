# ============================================================
#  STT - Speech to Text  (MIỄN PHÍ - Google via SpeechRecognition)
#  Không cần API key, không giới hạn (reasonable use)
#  Input : PCM 16bit/8000Hz (base64) từ Twilio (sau convert mulaw)
#  Output: Text tiếng Việt
# ============================================================

import base64
import io
import wave
import audioop
import speech_recognition as sr
import config

_recognizer = sr.Recognizer()

# Buffer audio theo call_id
_audio_buffers: dict[str, bytes] = {}   # PCM 16bit


def add_mulaw_chunk(call_id: str, base64_payload: str):
    """
    Nhận mulaw base64 (Twilio format) → convert PCM16 → thêm vào buffer.
    """
    try:
        mulaw_bytes = base64.b64decode(base64_payload)
        # Twilio gửi 8bit mulaw → convert sang PCM 16bit
        pcm16_bytes = audioop.ulaw2lin(mulaw_bytes, 2)
        _audio_buffers[call_id] = _audio_buffers.get(call_id, b"") + pcm16_bytes
    except Exception as e:
        print(f"[STT] Lỗi decode mulaw chunk: {e}")


def add_pcm_chunk(call_id: str, base64_payload: str):
    """Nhận PCM16 base64 (test client) → thêm vào buffer."""
    try:
        pcm_bytes = base64.b64decode(base64_payload)
        _audio_buffers[call_id] = _audio_buffers.get(call_id, b"") + pcm_bytes
    except Exception as e:
        print(f"[STT] Lỗi decode pcm chunk: {e}")


def transcribe(call_id: str) -> str:
    """
    Lấy buffer → WAV → Google Speech Recognition (miễn phí) → text.
    Reset buffer sau khi xử lý.
    """
    buf = _audio_buffers.pop(call_id, b"")
    if len(buf) < 3200:   # < 0.2s → bỏ qua (tiếng ồn / quá ngắn)
        return ""

    try:
        wav_bytes = _pcm16_to_wav(buf)
        with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
            audio_data = _recognizer.record(source)

        # Thử tiếng Việt trước, fallback tiếng Anh
        try:
            text = _recognizer.recognize_google(audio_data, language="vi-VN")
        except sr.UnknownValueError:
            return ""   # Không nghe rõ
        except Exception:
            try:
                text = _recognizer.recognize_google(audio_data, language="en-US")
            except Exception:
                return ""

        if text:
            print(f"[STT] Nhận diện: '{text}'")
        return text.strip()

    except Exception as e:
        print(f"[STT] Lỗi: {e}")
        return ""


def clear_buffer(call_id: str):
    _audio_buffers.pop(call_id, None)


def _pcm16_to_wav(pcm_data: bytes) -> bytes:
    """Thêm WAV header vào raw PCM 16bit."""
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wf:
        wf.setnchannels(config.CHANNELS)
        wf.setsampwidth(2)              # 16bit = 2 bytes
        wf.setframerate(config.SAMPLE_RATE)
        wf.writeframes(pcm_data)
    return wav_io.getvalue()
