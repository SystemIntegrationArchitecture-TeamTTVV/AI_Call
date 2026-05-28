import os
from dotenv import load_dotenv
load_dotenv()

# ── Groq (LLM miễn phí - thay thế OpenAI GPT) ──────────────
# Đăng ký tại: https://console.groq.com → lấy API key miễn phí
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ── Twilio (audio streaming - thay thế Tel4vn PSR) ──────────
# Đăng ký tại: https://www.twilio.com → $15 credit free
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE       = os.getenv("TWILIO_PHONE", "")  # Số Twilio dạng +1234567890

# ── WebSocket Server ─────────────────────────────────────────
WS_HOST = "0.0.0.0"
WS_PORT = int(os.environ.get("PORT", 8765))

# ── Audio Format (Twilio dùng mulaw 8000Hz) ─────────────────
SAMPLE_RATE = 8000
CHANNELS    = 1
BIT_DEPTH   = 16

# ── Silence Detection ────────────────────────────────────────
SILENCE_SECONDS = 1.5   # Giây không có audio → xử lý STT

# ── Transfer Rules ───────────────────────────────────────────
TRANSFER_KEYWORDS = [
    "gặp nhân viên", "nhân viên", "người thật",
    "khiếu nại", "bực mình", "chuyển máy", "không hiểu"
]
MAX_AI_RETRIES  = 2
AGENT_EXTENSION = "101"

# ── TTS & LLM ────────────────────────────────────────────────
TTS_LANG  = "vi"
GPT_MODEL = "llama-3.1-8b-instant"   # Groq model (miễn phí)
GPT_MAX_TOKENS = 120
